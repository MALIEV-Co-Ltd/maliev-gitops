#!/usr/bin/env python3
"""Fail-closed verifier for the legacy SQL Server to PostgreSQL migration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReadinessError(ValueError):
    """Raised when migration evidence cannot prove the required safety contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReadinessError(message)


def _database_map(items: list[dict[str, Any]], key: str, receipt: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        name = item.get(key)
        _require(isinstance(name, str) and name, f"{receipt} contains a database without {key}")
        _require(name not in result, f"{receipt} contains duplicate database {name}")
        result[name] = item
    return result


def verify_evidence(
    restore: dict[str, Any],
    identity: dict[str, Any],
    nonidentity: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Validate immutable rehearsal receipts without authorizing a cutover."""

    expected_active = set(contract["activeDatabases"])
    expected_identity = contract["identityRowCounts"]
    expected_nonidentity = expected_active - set(expected_identity)
    _require(len(expected_active) == 21, "contract must define exactly 21 active databases")
    _require(contract["dispositions"] == {"Log": "archive_only", "MachineLearningData": "exclude"},
             "contract dispositions must keep Log archive-only and MachineLearningData excluded")

    source = restore.get("source", {})
    summary = restore.get("summary", {})
    _require(source.get("gcsPrefix") == contract["sourceBackup"]["gcsPrefix"], "source GCS prefix mismatch")
    _require(source.get("localBackupCount") == 23, "source backup inventory must contain 23 files")
    _require(source.get("localBackupBytes") == 510709760, "source backup byte total mismatch")
    _require(summary.get("databaseCount") == 23, "restore receipt must cover 23 databases")
    _require(summary.get("backupBytes") == 510709760, "restore receipt byte total mismatch")
    _require(summary.get("checkdbCleanCount") == 23, "all 23 restored databases must pass DBCC CHECKDB")
    restored = _database_map(restore.get("databases", []), "database", "restore receipt")
    expected_restored = expected_active | {"Log", "MachineLearningData"}
    _require(set(restored) == expected_restored, "restore receipt database inventory mismatch")
    _require(all(item.get("checkdb") == "clean" for item in restored.values()), "restore receipt contains a failed DBCC CHECKDB result")

    _require(identity.get("result") == "pass", "identity copy receipt did not pass")
    _require(identity.get("cutoverAuthorized") is False, "identity receipt must not authorize cutover")
    identities = _database_map(identity.get("databases", []), "sourceDatabase", "identity receipt")
    _require(set(identities) == set(expected_identity), "identity receipt database inventory mismatch")
    for name, expected_rows in expected_identity.items():
        item = identities[name]
        _require(
            item.get("sourceRows") == expected_rows and item.get("destinationRows") == expected_rows,
            f"{name} must preserve the recorded {expected_rows} rows",
        )
        _require(item.get("copyValidation") == "pass", f"{name} copy validation failed")
        _require(item.get("postCopyValidation") == "pass", f"{name} post-copy validation failed")
        _require(bool(SHA256.fullmatch(str(item.get("semanticFingerprintSha256", "")))), f"{name} semantic fingerprint is invalid")

    _require(nonidentity.get("cutover_authorized") is False, "nonidentity receipt must not authorize cutover")
    copied = _database_map(nonidentity.get("databases", []), "database", "nonidentity receipt")
    _require("MachineLearningData" not in copied, "MachineLearningData must remain excluded")
    _require("Log" not in copied, "Log must remain archive-only")
    _require(set(copied) == expected_nonidentity, "nonidentity receipt must cover exactly the 19 active nonidentity databases")
    for database, item in copied.items():
        _require(item.get("state") == "disposable_copy_validated", f"{database} was not validated as a disposable copy")
        _require(item.get("cutover_authorized") is False, f"{database} receipt must not authorize cutover")
        tables = item.get("tables", [])
        _require(bool(tables), f"{database} receipt contains no table reconciliation")
        for table in tables:
            table_name = table.get("table", "<unknown>")
            _require(
                table.get("source_count") == table.get("destination_count"),
                f"{database}.{table_name} row count mismatch",
            )
            _require(
                bool(SHA256.fullmatch(str(table.get("semantic_fingerprint_sha256", "")))),
                f"{database}.{table_name} semantic fingerprint is invalid",
            )
            orphan_counts = table.get("foreign_key_orphan_counts", {})
            _require(all(value == 0 for value in orphan_counts.values()), f"{database}.{table_name} has foreign-key orphans")
            for column, sequence in table.get("identity_sequences", {}).items():
                migrated_maximum = sequence.get("migrated_maximum")
                next_value = sequence.get("next_value")
                _require(isinstance(next_value, int), f"{database}.{table_name}.{column} has no sequence next value")
                if migrated_maximum is not None:
                    _require(next_value > migrated_maximum, f"{database}.{table_name}.{column} sequence was not reseeded")

    verified_baseline = contract["verifiedBaselineGates"]
    required = contract["requiredCutoverGates"]
    _require(set(verified_baseline).issubset(required), "baseline gates must be part of required cutover gates")
    blocking = [gate for gate in required if gate not in verified_baseline]
    return {
        "schemaVersion": 1,
        "evidenceValid": True,
        "sourceCommit": contract["sourceEvidenceCommit"],
        "activeDatabases": sorted(expected_active),
        "verifiedBaselineGates": verified_baseline,
        "blockingGates": blocking,
        "cutoverAuthorized": False,
    }


def authorize_cutover(
    baseline_report: dict[str, Any], live_receipt: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    """Authorize only when a separate live receipt satisfies every remaining gate."""

    _require(baseline_report.get("evidenceValid") is True, "baseline evidence is not valid")
    _require(live_receipt.get("ownerApproved") is True, "explicit owner approval is required")
    _require(live_receipt.get("sourceWriteFreezeConfirmed") is True, "source write freeze is not confirmed")
    gates = _database_map(live_receipt.get("gates", []), "id", "live cutover receipt")
    required = set(contract["requiredCutoverGates"])
    _require(set(gates) == required, "live cutover receipt must contain every required gate exactly once")
    failed = sorted(gate for gate, item in gates.items() if item.get("status") != "pass")
    _require(not failed, f"live cutover gates are not passing: {', '.join(failed)}")
    result = dict(baseline_report)
    result["blockingGates"] = []
    result["cutoverAuthorized"] = True
    return result


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    _require(isinstance(value, dict), f"{path} must contain one JSON object")
    return value


def verify_receipt_file(path: Path, expected_sha256: str) -> dict[str, Any]:
    """Load a receipt only when its raw bytes match the pinned evidence digest."""

    _require(bool(SHA256.fullmatch(expected_sha256)), f"configured SHA-256 for {path} is invalid")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ReadinessError(f"cannot read receipt {path}: {error}") from error
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    _require(
        actual_sha256 == expected_sha256,
        f"receipt {path.name} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}",
    )
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ReadinessError(f"receipt {path} is not valid JSON: {error}") from error
    _require(isinstance(value, dict), f"{path} must contain one JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-evidence", type=Path, required=True)
    parser.add_argument("--identity-evidence", type=Path, required=True)
    parser.add_argument("--nonidentity-evidence", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("3-apps/_legacy-postgres/readiness/migration-readiness-contract.json"),
    )
    parser.add_argument("--live-cutover-receipt", type=Path)
    parser.add_argument("--require-cutover", action="store_true")
    args = parser.parse_args(argv)

    try:
        contract = _load(args.contract)
        receipt_hashes = contract["receiptSha256"]
        report = verify_evidence(
            verify_receipt_file(args.restore_evidence, receipt_hashes["restore"]),
            verify_receipt_file(args.identity_evidence, receipt_hashes["identity"]),
            verify_receipt_file(args.nonidentity_evidence, receipt_hashes["nonidentity"]),
            contract,
        )
        if args.live_cutover_receipt:
            report = authorize_cutover(report, _load(args.live_cutover_receipt), contract)
        if args.require_cutover and not report["cutoverAuthorized"]:
            raise ReadinessError("cutover remains blocked because live gates and owner approval are missing")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ReadinessError) as error:
        print(json.dumps({"evidenceValid": False, "cutoverAuthorized": False, "error": str(error)}))
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
