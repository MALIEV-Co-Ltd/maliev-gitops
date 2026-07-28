from __future__ import annotations

import copy
import unittest

from scripts.legacy_live_parity import ParityError, validate_receipt


def _table(name: str = "dbo.Country") -> dict:
    return {
        "table": name,
        "rowCount": 2,
        "nullCounts": {"Name": 0},
        "fingerprintSha256": "a" * 64,
        "schemaFingerprintSha256": "b" * 64,
        "foreignKeyOrphans": {},
        "identitySequences": {"ID": {"migratedMaximum": 2, "nextValue": 3}},
    }


def _receipt() -> tuple[dict, dict]:
    contract = {"activeDatabases": ["Country"]}
    receipt = {
        "schemaVersion": 1,
        "status": "verified",
        "source": {
            "engine": "sqlserver",
            "readOnly": True,
            "transactionIsolation": "snapshot",
            "databases": [{"database": "Country", "tables": [_table()]}],
        },
        "target": {
            "engine": "postgresql",
            "namespace": "maliev-legacy",
            "cluster": "legacy-postgres-main",
            "databases": [{"database": "Country", "tables": [_table()]}],
        },
    }
    return receipt, contract


class LegacyLiveParityTests(unittest.TestCase):
    def test_verified_receipt_returns_safe_aggregates(self) -> None:
        report = validate_receipt(*_receipt())
        self.assertTrue(report["parityVerified"])
        self.assertEqual(report["databaseCount"], 1)
        self.assertEqual(report["tableCount"], 1)
        self.assertFalse(report["valuesPrinted"])

    def test_row_count_mismatch_fails_closed(self) -> None:
        receipt, contract = _receipt()
        receipt["target"]["databases"][0]["tables"][0]["rowCount"] = 3
        with self.assertRaisesRegex(ParityError, "row count mismatch"):
            validate_receipt(receipt, contract)

    def test_source_must_be_read_only_snapshot(self) -> None:
        receipt, contract = _receipt()
        receipt["source"]["readOnly"] = False
        with self.assertRaisesRegex(ParityError, "read-only"):
            validate_receipt(receipt, contract)

        receipt, contract = _receipt()
        receipt["source"]["transactionIsolation"] = "read-committed"
        with self.assertRaisesRegex(ParityError, "snapshot"):
            validate_receipt(receipt, contract)

    def test_inventory_mismatch_fails_closed(self) -> None:
        receipt, contract = _receipt()
        receipt["target"]["databases"][0]["tables"].append(_table("dbo.Other"))
        with self.assertRaisesRegex(ParityError, "table inventories"):
            validate_receipt(receipt, contract)

    def test_schema_and_identity_mismatches_fail_closed(self) -> None:
        receipt, contract = _receipt()
        receipt["target"]["databases"][0]["tables"][0]["schemaFingerprintSha256"] = "c" * 64
        with self.assertRaisesRegex(ParityError, "schema fingerprint"):
            validate_receipt(receipt, contract)

        receipt, contract = _receipt()
        receipt["target"]["databases"][0]["tables"][0]["identitySequences"]["ID"]["nextValue"] = 2
        with self.assertRaisesRegex(ParityError, "not ahead"):
            validate_receipt(receipt, contract)

    def test_credential_shaped_fields_are_rejected_without_echoing_values(self) -> None:
        receipt, contract = _receipt()
        receipt["source"]["connectionString"] = "Server=secret-value"
        with self.assertRaisesRegex(ParityError, "credential field") as error:
            validate_receipt(receipt, contract)
        self.assertNotIn("secret-value", str(error.exception))

    def test_input_fixture_is_not_mutated(self) -> None:
        receipt, contract = _receipt()
        before = copy.deepcopy(receipt)
        validate_receipt(receipt, contract)
        self.assertEqual(receipt, before)


if __name__ == "__main__":
    unittest.main()
