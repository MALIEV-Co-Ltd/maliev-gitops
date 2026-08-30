from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = REPO_ROOT / "3-apps/_legacy-quotation-migrations/overlays/legacy"
ACTIVE_ENVIRONMENT = REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"
CONTRACT_PATH = OVERLAY.parents[1] / "readiness/quotation-migration-contract.json"
PLACEHOLDER_IMAGE = (
    "example.invalid/maliev/legacy-maliev-quotation-migration@sha256:"
    + "0" * 64
)


def render() -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(OVERLAY)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class LegacyQuotationMigrationManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render()
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def resources(self, kind: str) -> list[dict]:
        return [document for document in self.documents if document["kind"] == kind]

    def test_overlay_is_dormant_and_does_not_fabricate_missing_evidence(self) -> None:
        active = ACTIVE_ENVIRONMENT.read_text(encoding="utf-8")
        self.assertNotIn("_legacy-quotation-migrations", active)
        names = {(item["kind"], item["metadata"]["name"]) for item in self.documents}
        self.assertNotIn(("Secret", "legacy-quotation-schema-baseline-evidence"), names)
        self.assertNotIn(("ExternalSecret", "legacy-quotation-schema-baseline-evidence"), names)
        self.assertNotIn(("Secret", "legacy-quotation-postgres-snapshot-evidence"), names)
        self.assertNotIn(("ExternalSecret", "legacy-quotation-postgres-snapshot-evidence"), names)

        self.assertFalse(self.contract["active"])
        self.assertEqual(self.contract["schemaBaselineProducer"]["status"], "blocked")
        self.assertEqual(self.contract["postgresSnapshotGate"]["status"], "blocked")
        self.assertFalse(self.contract["cutoverAuthorized"])

    def test_only_consolidated_secret_projects_migrator_credentials_and_public_key(self) -> None:
        externals = {
            item["metadata"]["name"]: item for item in self.resources("ExternalSecret")
            if item["metadata"].get("labels", {}).get("app.kubernetes.io/name")
            == "legacy-quotation-migration"
        }
        self.assertEqual(
            set(externals),
            {
                "legacy-quotation-migration-runtime",
                "legacy-quotation-migration-role",
                "legacy-quotation-request-migration-role",
            },
        )
        for external in externals.values():
            self.assertEqual(
                {item["remoteRef"]["key"] for item in external["spec"]["data"]},
                {"maliev-legacy-secrets"},
            )

        runtime = externals["legacy-quotation-migration-runtime"]
        self.assertEqual(runtime["spec"]["target"]["name"], "legacy-quotation-migration-runtime")
        template = runtime["spec"]["target"]["template"]["data"]
        self.assertEqual(
            set(template),
            {
                "ConnectionStrings__QuotationDbContext",
                "ConnectionStrings__QuotationRequestDbContext",
                "trusted-public-key.pem",
                "trusted-key-id",
            },
        )
        for connection in (key for key in template if key.startswith("ConnectionStrings__")):
            self.assertIn("Host=legacy-postgres-pooler-rw", template[connection])
            self.assertIn("SSL Mode=Require", template[connection])
            self.assertNotIn("SqlServer", template[connection])

    def test_dormant_roles_are_nonsuperuser_single_connection_owner_members(self) -> None:
        clusters = self.resources("Cluster")
        self.assertEqual(len(clusters), 1)
        roles = {role["name"]: role for role in clusters[0]["spec"]["managed"]["roles"]}
        expected = {
            "legacy_quotation_migrator": (
                "legacy-postgres-quotation-migrator",
                "legacy_quotation_owner",
            ),
            "legacy_quotation_request_migrator": (
                "legacy-postgres-quotation-request-migrator",
                "legacy_quotation_request_owner",
            ),
        }
        for role_name, (password_secret, owner_role) in expected.items():
            role = roles[role_name]
            self.assertTrue(role["login"])
            self.assertEqual(role["connectionLimit"], 1)
            self.assertFalse(role["superuser"])
            self.assertFalse(role["createdb"])
            self.assertFalse(role["createrole"])
            self.assertFalse(role["replication"])
            self.assertFalse(role["bypassrls"])
            self.assertEqual(role["inRoles"], [owner_role])
            self.assertEqual(role["passwordSecret"]["name"], password_secret)

    def test_jobs_are_suspended_ordered_tokenless_and_fail_closed_on_missing_receipts(self) -> None:
        jobs = {job["metadata"]["name"]: job for job in self.resources("Job")}
        self.assertEqual(
            set(jobs),
            {
                "legacy-quotation-request-schema-migration",
                "legacy-quotation-schema-migration",
            },
        )
        expected = {
            "legacy-quotation-request-schema-migration": ("quotation-request", "20"),
            "legacy-quotation-schema-migration": ("quotation", "30"),
        }
        for name, (workload, wave) in expected.items():
            job = jobs[name]
            self.assertTrue(job["spec"]["suspend"])
            self.assertEqual(job["metadata"]["annotations"]["argocd.argoproj.io/hook"], "PreSync")
            self.assertEqual(job["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"], wave)
            template = job["spec"]["template"]["spec"]
            self.assertFalse(template["automountServiceAccountToken"])
            self.assertEqual(template["restartPolicy"], "Never")
            container = template["containers"][0]
            self.assertEqual(container["image"], PLACEHOLDER_IMAGE)
            self.assertEqual(container["args"], [workload])
            env = {item["name"]: item for item in container["env"]}
            self.assertNotIn("Migration__Workload", env)
            for key in (
                "Migration__SourceSnapshotId",
                "Migration__CopyPlanId",
                "Migration__SchemaHash",
            ):
                self.assertEqual(
                    env[key]["valueFrom"]["secretKeyRef"]["name"],
                    "legacy-quotation-schema-baseline-evidence",
                )
            self.assertEqual(env["Migration__ReceiptPath"]["value"], f"/evidence/{workload}.receipt.json")
            self.assertEqual(env["Migration__TrustedPublicKeyPath"]["value"], "/trust/trusted-public-key.pem")
            self.assertEqual(
                env["Migration__TrustedKeyId"]["valueFrom"]["secretKeyRef"]["name"],
                "legacy-quotation-migration-runtime",
            )
            volumes = {item["name"]: item for item in template["volumes"]}
            self.assertEqual(
                volumes["schema-baseline-evidence"]["secret"]["secretName"],
                "legacy-quotation-schema-baseline-evidence",
            )
            self.assertFalse(volumes["schema-baseline-evidence"]["secret"].get("optional", False))
            security = container["securityContext"]
            self.assertTrue(security["runAsNonRoot"])
            self.assertTrue(security["readOnlyRootFilesystem"])
            self.assertFalse(security["allowPrivilegeEscalation"])
            self.assertEqual(security["capabilities"]["drop"], ["ALL"])

    def test_contract_matches_exact_service_consumer_and_records_unimplemented_gates(self) -> None:
        self.assertEqual(self.contract["runnerContract"]["schemaVersion"], "1.0")
        self.assertEqual(
            self.contract["runnerContract"]["domainSeparator"],
            "Legacy.Maliev.QuotationService.SchemaBaselineReceipt.v1",
        )
        self.assertEqual(
            self.contract["runnerContract"]["workloads"],
            ["quotation-request", "quotation"],
        )
        self.assertEqual(
            self.contract["requiredOrder"],
            [
                "signed-schema-baseline-evidence",
                "recoverable-postgres-snapshot",
                "quotation-request-schema-migration",
                "quotation-schema-migration",
                "aspire-consumer-proof",
                "owner-release-approval",
            ],
        )
        self.assertTrue(self.contract["requiresSeparateActivationReview"])

    def test_secret_catalog_tracks_every_unprovisioned_property_as_pending(self) -> None:
        secret_contract = json.loads(
            (REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json").read_text(
                encoding="utf-8"
            )
        )
        pending = {item["name"] for item in secret_contract["pendingProperties"]}
        self.assertTrue(set(self.contract["consolidatedSecretPendingProperties"]) <= pending)
        self.assertTrue(set(self.contract["consolidatedSecretPendingProperties"]).isdisjoint(
            secret_contract["presentProperties"]
        ))


if __name__ == "__main__":
    unittest.main()
