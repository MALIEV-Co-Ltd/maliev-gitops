from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.legacy_data_readiness import (
    ReadinessError,
    authorize_cutover,
    verify_evidence,
    verify_receipt_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DATABASES = {
    "Country",
    "Currency",
    "Customer",
    "CustomerIdentity",
    "DataProtectionKeys",
    "DataProtectionKeysEmployee",
    "Employee",
    "EmployeeIdentity",
    "Invoice",
    "JobOffers",
    "Material",
    "Message",
    "Order",
    "OrderStatus",
    "Payment",
    "PurchaseOrder",
    "Quotation",
    "QuotationRequest",
    "Receipt",
    "Supplier",
    "Upload",
}
IDENTITY_DATABASES = {"CustomerIdentity": 3048, "EmployeeIdentity": 4}
NONIDENTITY_DATABASES = ACTIVE_DATABASES - set(IDENTITY_DATABASES)


def restore_receipt() -> dict:
    databases = [
        {"database": name, "checkdb": "clean", "backupFilename": f"Full_{name}_2026-07-14_125231.bak"}
        for name in sorted(ACTIVE_DATABASES | {"Log", "MachineLearningData"})
    ]
    return {
        "source": {
            "gcsPrefix": "gs://maliev.com/database/full/2026-07-14/",
            "localBackupCount": 23,
            "localBackupBytes": 510709760,
        },
        "summary": {"databaseCount": 23, "backupBytes": 510709760, "checkdbCleanCount": 23},
        "databases": databases,
    }


def identity_receipt() -> dict:
    return {
        "cutoverAuthorized": False,
        "result": "pass",
        "databases": [
            {
                "sourceDatabase": name,
                "sourceRows": rows,
                "destinationRows": rows,
                "semanticFingerprintSha256": "a" * 64,
                "copyValidation": "pass",
                "postCopyValidation": "pass",
            }
            for name, rows in IDENTITY_DATABASES.items()
        ],
    }


def nonidentity_receipt() -> dict:
    return {
        "cutover_authorized": False,
        "databases": [
            {
                "database": name,
                "state": "disposable_copy_validated",
                "cutover_authorized": False,
                "tables": [
                    {
                        "table": f"dbo.{name}",
                        "source_count": 1,
                        "destination_count": 1,
                        "semantic_fingerprint_sha256": "b" * 64,
                        "foreign_key_orphan_counts": {},
                        "identity_sequences": {
                            "ID": {"migrated_maximum": 1, "next_value": 2, "sequence_last_value": 1}
                        },
                    }
                ],
            }
            for name in sorted(NONIDENTITY_DATABASES)
        ],
    }


def complete_nonidentity_receipt() -> dict:
    receipt = nonidentity_receipt()
    for item in receipt["databases"]:
        item["table_inventory_complete"] = True
        item["table_count"] = len(item["tables"])
    return receipt


class LegacyDataReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (REPO_ROOT / "3-apps/_legacy-postgres/readiness/migration-readiness-contract.json").read_text(
                encoding="utf-8"
            )
        )

    def test_verified_rehearsal_receipts_are_accepted_but_cutover_stays_blocked(self) -> None:
        self.assertEqual(
            self.contract["latestSourceAudit"]["commit"],
            "edf451e367ce774d63a74778731bb3c20daf1063",
        )
        self.assertFalse(self.contract["latestSourceAudit"]["secretValuesCopied"])
        report = verify_evidence(
            restore_receipt(), identity_receipt(), nonidentity_receipt(), self.contract
        )

        self.assertTrue(report["evidenceValid"])
        self.assertFalse(report["cutoverAuthorized"])
        self.assertFalse(report["tableInventoryComplete"])
        self.assertIn("table-inventory-completeness", report["blockingGates"])
        self.assertEqual(set(report["activeDatabases"]), ACTIVE_DATABASES)
        self.assertEqual(report["verifiedBaselineGates"], ["source-backup-integrity", "initial-copy-parity"])
        self.assertIn("cnpg-recovery-drill", report["blockingGates"])
        self.assertIn("rollback-rehearsal", report["blockingGates"])
        self.assertIn("owner-aspire-review", report["blockingGates"])

    def test_machine_learning_database_cannot_enter_active_copy_receipts(self) -> None:
        receipt = nonidentity_receipt()
        receipt["databases"].append(
            {
                "database": "MachineLearningData",
                "state": "disposable_copy_validated",
                "cutover_authorized": False,
                "tables": [],
            }
        )

        with self.assertRaisesRegex(ReadinessError, "MachineLearningData"):
            verify_evidence(restore_receipt(), identity_receipt(), receipt, self.contract)

    def test_row_count_mismatch_fails_closed(self) -> None:
        receipt = nonidentity_receipt()
        receipt["databases"][0]["tables"][0]["destination_count"] = 0

        with self.assertRaisesRegex(ReadinessError, "row count"):
            verify_evidence(restore_receipt(), identity_receipt(), receipt, self.contract)

    def test_incomplete_table_inventory_fails_closed(self) -> None:
        receipt = complete_nonidentity_receipt()
        receipt["databases"][0].pop("table_inventory_complete")

        with self.assertRaisesRegex(ReadinessError, "complete table inventory"):
            verify_evidence(
                restore_receipt(),
                identity_receipt(),
                receipt,
                self.contract,
                require_complete_table_inventory=True,
            )

    def test_duplicate_table_names_fail_closed(self) -> None:
        receipt = nonidentity_receipt()
        table = dict(receipt["databases"][0]["tables"][0])
        receipt["databases"][0]["tables"].append(table)
        receipt["databases"][0]["table_count"] = 2

        with self.assertRaisesRegex(ReadinessError, "duplicate table names"):
            verify_evidence(restore_receipt(), identity_receipt(), receipt, self.contract)

    def test_receipt_file_must_match_the_pinned_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            receipt.write_text('{"result":"pass"}', encoding="utf-8")

            with self.assertRaisesRegex(ReadinessError, "SHA-256"):
                verify_receipt_file(receipt, "0" * 64)

    def test_identity_receipts_require_the_recorded_customer_and_employee_counts(self) -> None:
        receipt = identity_receipt()
        receipt["databases"][0]["destinationRows"] = 3047

        with self.assertRaisesRegex(ReadinessError, "CustomerIdentity"):
            verify_evidence(restore_receipt(), receipt, nonidentity_receipt(), self.contract)

    def test_cutover_requires_every_live_gate_and_explicit_owner_approval(self) -> None:
        live_receipt = {
            "ownerApproved": True,
            "sourceWriteFreezeConfirmed": True,
            "gates": [
                {"id": gate, "status": "pass"}
                for gate in self.contract["requiredCutoverGates"]
            ],
        }

        report = verify_evidence(
            restore_receipt(), identity_receipt(), complete_nonidentity_receipt(), self.contract,
            require_complete_table_inventory=True,
        )
        authorized = authorize_cutover(report, live_receipt, self.contract)
        self.assertTrue(authorized["cutoverAuthorized"])

        live_receipt["ownerApproved"] = False
        with self.assertRaisesRegex(ReadinessError, "owner approval"):
            authorize_cutover(report, live_receipt, self.contract)


class LegacyRecoveryManifestTests(unittest.TestCase):
    def test_current_parity_audit_is_explicitly_fail_closed(self) -> None:
        audit = json.loads(
            (
                REPO_ROOT
                / "3-apps/_legacy-postgres/readiness/current-parity-audit-2026-08-07.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(audit["source"]["expectedAsOfDate"], "2026-08-07")
        self.assertFalse(audit["source"]["currentAsOfBackupPresent"])
        self.assertEqual(audit["source"]["latestVisibleSqlServerBackupDate"], "2026-07-20")
        self.assertEqual(audit["historicalComparison"]["exactCurrentSourceParity"], "unproven")
        fresh = audit["freshReadOnlyComparison"]
        self.assertEqual(fresh["nonidentityTablesCompared"], 60)
        self.assertEqual(fresh["nonidentityTablesWithChangedCounts"], 21)
        self.assertEqual(fresh["identityTablesWithChangedCounts"], 1)
        self.assertEqual(fresh["changedTableCount"], 22)
        self.assertFalse(fresh["sourceExportAvailable"])
        self.assertEqual(fresh["exactCurrentSourceParity"], "unproven")
        self.assertFalse(audit["target"]["authDatabaseApplied"])
        self.assertEqual(audit["target"]["authDatabaseDesiredOwner"], "legacy_auth_refresh")
        self.assertEqual(audit["target"]["authDatabaseObservedOwner"], "legacy_auth_owner")
        self.assertFalse(audit["target"]["authDatabaseManifestMatchesLive"])
        self.assertFalse(audit["target"]["applicationWorkloadsDeployed"])
        self.assertEqual(audit["target"]["activeDatabaseCount"], 21)
        self.assertEqual(audit["target"]["latestTargetBackupUtc"], "2026-08-06T19:00:01Z")
        self.assertEqual(audit["target"]["migrationHistory"]["domainDatabasesWithoutEfHistory"], 17)
        self.assertFalse(audit["target"]["migrationHistory"]["baselineReceiptFilesPresent"])
        self.assertFalse(audit["target"]["timestampSchemaContract"]["migrationAppliedToLiveTarget"])
        self.assertIn("migration-history-baseline", audit["blockingGates"])
        self.assertIn("current-sql-server-export", audit["blockingGates"])
        self.assertIn("auth-database-apply", audit["blockingGates"])
        self.assertFalse(audit["cutoverAuthorized"])
        self.assertFalse(audit["productionMutationPerformed"])

    def test_recovery_rehearsal_is_single_instance_bounded_and_dormant(self) -> None:
        rehearsal = REPO_ROOT / "3-apps/_legacy-postgres/readiness/recovery-rehearsal"
        kustomization = (rehearsal / "kustomization.yaml").read_text(encoding="utf-8")
        cluster = (rehearsal / "cluster.yaml").read_text(encoding="utf-8")

        self.assertIn("namespace: maliev-legacy", kustomization)
        self.assertIn("name: legacy-postgres-recovery-rehearsal", cluster)
        self.assertIn("instances: 1", cluster)
        self.assertIn("source: legacy-postgres-main-backup", cluster)
        self.assertIn("barmanObjectName: legacy-postgres-backup-main", cluster)
        self.assertIn("serverName: legacy-postgres-main", cluster)
        self.assertNotIn("\n  plugins:", cluster, "A rehearsal restore must not write WAL to the source archive")
        self.assertIn("requests:", cluster)
        self.assertIn("limits:", cluster)

        active = (REPO_ROOT / "2-environments/4-legacy/kustomization.yaml").read_text(encoding="utf-8")
        self.assertNotIn("readiness/recovery-rehearsal", active)
        self.assertNotIn("legacy-postgres-recovery-rehearsal", active)


if __name__ == "__main__":
    unittest.main()
