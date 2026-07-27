#!/usr/bin/env python3
"""Fail-closed validator for a live SQL Server/PostgreSQL parity receipt.

The collector that produces the receipt owns credentials and network access. This
module only validates redacted aggregate evidence and never connects to either
database. A receipt is not a cutover authorization; it is one required input to
the existing migration gate verifier.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEY = re.compile(
    r"(?:password|secret|token|credential|connectionstring|cookie|access[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)


class ParityError(ValueError):
    """Raised when a parity receipt cannot prove the migration contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParityError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ParityError(f"cannot read valid JSON from {path.name}") from error
    _require(isinstance(value, dict), f"{path.name} must contain one JSON object")
    return value


def _reject_secret_material(value: Any, path: str = "receipt") -> None:
    """Reject credential-shaped fields without echoing their values."""

    if isinstance(value, dict):
        for key, child in value.items():
            _require(not FORBIDDEN_KEY.search(str(key)), f"{path} contains a forbidden credential field")
            _reject_secret_material(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_material(child, f"{path}[{index}]")


def _sha(value: Any, field: str) -> str:
    _require(
        isinstance(value, str) and SHA256.fullmatch(value) is not None,
        f"{field} must be a lowercase SHA-256 digest",
    )
    return value


def _table_map(database_items: Any, side: str) -> dict[str, dict[str, Any]]:
    _require(isinstance(database_items, list) and database_items, f"{side} databases are required")
    result: dict[str, dict[str, Any]] = {}
    for database in database_items:
        _require(isinstance(database, dict), f"{side} database entry is malformed")
        name = database.get("database")
        _require(isinstance(name, str) and name, f"{side} database name is missing")
        tables = database.get("tables")
        _require(isinstance(tables, list) and tables, f"{side} database {name} has no tables")
        for table in tables:
            _require(isinstance(table, dict), f"{side} table entry in {name} is malformed")
            table_name = table.get("table")
            _require(isinstance(table_name, str) and table_name, f"{side} table name in {name} is missing")
            key = f"{name}|{table_name}"
            _require(key not in result, f"{side} contains duplicate table {key}")
            result[key] = table
    return result


def _validate_table(table: dict[str, Any], side: str, key: str) -> None:
    row_count = table.get("rowCount")
    _require(isinstance(row_count, int) and row_count >= 0, f"{side} {key} rowCount is invalid")
    null_counts = table.get("nullCounts")
    _require(isinstance(null_counts, dict), f"{side} {key} nullCounts are required")
    for column, count in null_counts.items():
        _require(isinstance(column, str) and column, f"{side} {key} has an invalid null-count column")
        _require(isinstance(count, int) and count >= 0, f"{side} {key} null count is invalid")
    _sha(table.get("fingerprintSha256"), f"{side} {key} fingerprintSha256")
    _sha(table.get("schemaFingerprintSha256"), f"{side} {key} schemaFingerprintSha256")
    orphans = table.get("foreignKeyOrphans")
    _require(isinstance(orphans, dict), f"{side} {key} foreignKeyOrphans are required")
    for constraint, count in orphans.items():
        _require(isinstance(constraint, str) and constraint, f"{side} {key} has an invalid foreign-key name")
        _require(isinstance(count, int) and count >= 0, f"{side} {key} foreign-key orphan count is invalid")
    sequences = table.get("identitySequences")
    _require(isinstance(sequences, dict), f"{side} {key} identitySequences are required")
    for column, sequence in sequences.items():
        _require(isinstance(column, str) and column, f"{side} {key} has an invalid identity column")
        _require(isinstance(sequence, dict), f"{side} {key} identity sequence is malformed")
        maximum = sequence.get("migratedMaximum")
        next_value = sequence.get("nextValue")
        _require(
            maximum is None or isinstance(maximum, int) and maximum >= 0,
            f"{side} {key} identity maximum is invalid",
        )
        _require(isinstance(next_value, int) and next_value >= 1, f"{side} {key} identity nextValue is invalid")
        if maximum is not None:
            _require(next_value > maximum, f"{side} {key} identity sequence is not ahead of migratedMaximum")


def validate_receipt(receipt: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Validate a complete source/target parity receipt and return safe aggregates."""

    _reject_secret_material(receipt)
    _require(receipt.get("schemaVersion") == 1, "parity receipt schemaVersion must be 1")
    _require(receipt.get("status") == "verified", "parity receipt status must be verified")

    source = receipt.get("source")
    _require(isinstance(source, dict), "source evidence is required")
    _require(source.get("engine") == "sqlserver", "source engine must be sqlserver")
    _require(source.get("readOnly") is True, "source evidence must come from a read-only principal")
    _require(source.get("transactionIsolation") == "snapshot", "source evidence must use a snapshot transaction")

    target = receipt.get("target")
    _require(isinstance(target, dict), "target evidence is required")
    _require(target.get("engine") == "postgresql", "target engine must be postgresql")
    _require(target.get("namespace") == "maliev-legacy", "target namespace must be maliev-legacy")
    _require(target.get("cluster") == "legacy-postgres-main", "target cluster must be legacy-postgres-main")

    expected_databases = contract.get("activeDatabases")
    _require(isinstance(expected_databases, list) and expected_databases, "contract activeDatabases are required")
    expected = set(expected_databases)
    source_databases = {item.get("database") for item in source.get("databases", []) if isinstance(item, dict)}
    target_databases = {item.get("database") for item in target.get("databases", []) if isinstance(item, dict)}
    _require(source_databases == expected, "source database inventory does not match the active contract")
    _require(target_databases == expected, "target database inventory does not match the active contract")

    source_tables = _table_map(source.get("databases"), "source")
    target_tables = _table_map(target.get("databases"), "target")
    _require(set(source_tables) == set(target_tables), "source and target table inventories differ")

    for key in sorted(source_tables):
        source_table = source_tables[key]
        target_table = target_tables[key]
        _validate_table(source_table, "source", key)
        _validate_table(target_table, "target", key)
        _require(source_table["rowCount"] == target_table["rowCount"], f"{key} row count mismatch")
        _require(source_table["nullCounts"] == target_table["nullCounts"], f"{key} null counts mismatch")
        _require(source_table["fingerprintSha256"] == target_table["fingerprintSha256"], f"{key} content fingerprint mismatch")
        _require(source_table["schemaFingerprintSha256"] == target_table["schemaFingerprintSha256"], f"{key} schema fingerprint mismatch")
        _require(source_table["foreignKeyOrphans"] == target_table["foreignKeyOrphans"], f"{key} foreign-key orphan counts mismatch")
        _require(all(value == 0 for value in target_table["foreignKeyOrphans"].values()), f"{key} contains foreign-key orphans")
        _require(source_table["identitySequences"] == target_table["identitySequences"], f"{key} identity sequence mismatch")

    return {
        "schemaVersion": 1,
        "parityVerified": True,
        "status": "verified",
        "databaseCount": len(expected),
        "tableCount": len(source_tables),
        "sourceReadOnly": True,
        "target": "maliev-legacy/legacy-postgres-main",
        "valuesPrinted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("3-apps/_legacy-postgres/readiness/migration-readiness-contract.json"),
    )
    args = parser.parse_args(argv)
    try:
        report = validate_receipt(_load(args.receipt), _load(args.contract))
    except ParityError as error:
        print(json.dumps({"parityVerified": False, "valuesPrinted": False, "error": str(error)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
