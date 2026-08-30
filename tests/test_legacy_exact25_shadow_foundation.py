from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = "3-apps/_legacy-data-migration-shadow-foundation/overlays/legacy"
ACTIVE_ENVIRONMENT = "2-environments/4-legacy"
SECRET_CONTRACT = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json"
DATABASE_CONTRACT = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
PROJECT = REPO_ROOT / "argocd/projects/maliev-legacy-project.yaml"
WORKSPACE_ROOT = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))
SOURCE_POLICY = (
    WORKSPACE_ROOT
    / "Legacy.Maliev.DataMigration/deploy/cloudnativepg-shadow-provisioner-policy.yaml"
)


def render(relative_path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / relative_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def by_kind(documents: list[dict], kind: str) -> list[dict]:
    return [document for document in documents if document.get("kind") == kind]


class LegacyExact25ShadowFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.foundation = render(FOUNDATION)
        cls.active = render(ACTIVE_ENVIRONMENT)

    def test_foundation_is_dormant_and_has_no_workload_or_canonical_database(self) -> None:
        active_names = {
            (resource["kind"], resource["metadata"]["name"])
            for resource in self.active
        }
        self.assertNotIn(("Database", "legacy-postgres-migration-control"), active_names)
        self.assertNotIn(("ServiceAccount", "legacy-data-migration-shadow-provisioner"), active_names)
        self.assertEqual(by_kind(self.foundation, "Deployment"), [])
        self.assertEqual(by_kind(self.foundation, "Job"), [])

        migration_databases = [
            resource
            for resource in by_kind(self.foundation, "Database")
            if resource["metadata"]["name"].startswith("legacy-postgres-migration-")
            or resource["metadata"]["name"].startswith("legacy-shadow-")
        ]
        self.assertEqual(len(migration_databases), 1)
        control = migration_databases[0]
        self.assertEqual(control["metadata"]["name"], "legacy-postgres-migration-control")
        self.assertEqual(control["spec"]["name"], "legacy_migration_control")
        self.assertEqual(control["spec"]["owner"], "legacy_migration_control")
        self.assertEqual(control["spec"]["cluster"]["name"], "legacy-postgres-main")
        self.assertEqual(control["spec"]["databaseReclaimPolicy"], "retain")
        self.assertNotIn("legacy_shadow_", control["spec"]["name"])

    def test_control_and_shadow_roles_are_distinct_unprivileged_and_secret_backed(self) -> None:
        cluster = by_kind(self.foundation, "Cluster")[0]
        roles = {role["name"]: role for role in cluster["spec"]["managed"]["roles"]}
        expected = {
            "legacy_migration_control": "legacy-postgres-migration-control",
            "legacy_migration_shadow": "legacy-postgres-migration-shadow",
        }
        for name, secret in expected.items():
            role = roles[name]
            self.assertTrue(role["login"])
            self.assertEqual(role["connectionLimit"], 2)
            self.assertFalse(role["superuser"])
            self.assertFalse(role["createdb"])
            self.assertFalse(role["createrole"])
            self.assertFalse(role["inherit"])
            self.assertFalse(role["replication"])
            self.assertFalse(role["bypassrls"])
            self.assertEqual(role["passwordSecret"]["name"], secret)
        self.assertNotEqual(*expected)

        external = {
            item["metadata"]["name"]: item
            for item in by_kind(self.foundation, "ExternalSecret")
            if item["metadata"]["name"] in expected.values()
        }
        self.assertEqual(set(external), set(expected.values()))
        properties: set[str] = set()
        for resource in external.values():
            self.assertEqual(resource["spec"]["target"]["template"]["type"], "kubernetes.io/basic-auth")
            for item in resource["spec"]["data"]:
                self.assertEqual(item["remoteRef"]["key"], "maliev-legacy-secrets")
                properties.add(item["remoteRef"]["property"])
        self.assertEqual(
            properties,
            {
                "legacy-postgres-migration-control-username",
                "legacy-postgres-migration-control-password",
                "legacy-postgres-migration-shadow-username",
                "legacy-postgres-migration-shadow-password",
            },
        )

    def test_provisioner_identity_rbac_and_admission_policy_match_reviewed_source(self) -> None:
        if not SOURCE_POLICY.is_file():
            message = f"Legacy DataMigration source is not mounted: {SOURCE_POLICY}"
            if "MALIEV_WORKSPACE_ROOT" in os.environ:
                self.fail(message)
            self.skipTest(message)

        source_text = SOURCE_POLICY.read_text(encoding="utf-8")
        # The reviewed source contract stores CEL as unquoted plain scalars. Its
        # ternary colons are not valid YAML, so canonicalize only expression
        # scalar quoting before semantic comparison with the deployable copy.
        source_text = re.sub(
            r"(?m)^(\s+(?:- )?expression:) (.+)$",
            lambda match: f"{match.group(1)} {json.dumps(match.group(2))}",
            source_text,
        )
        source = [document for document in yaml.safe_load_all(source_text) if document]
        source_by_identity = {
            (resource["kind"], resource["metadata"]["name"]): resource
            for resource in source
        }
        rendered_by_identity = {
            (resource["kind"], resource["metadata"]["name"]): resource
            for resource in self.foundation
        }
        for identity, expected in source_by_identity.items():
            self.assertIn(identity, rendered_by_identity)
            self.assertEqual(rendered_by_identity[identity], expected)

        service_account = by_kind(self.foundation, "ServiceAccount")[0]
        self.assertFalse(service_account["automountServiceAccountToken"])
        role = by_kind(self.foundation, "Role")[0]
        self.assertEqual(
            role["rules"],
            [{
                "apiGroups": ["postgresql.cnpg.io"],
                "resources": ["databases"],
                "verbs": ["get", "create", "patch", "delete"],
            }],
        )
        policy = by_kind(self.foundation, "ValidatingAdmissionPolicy")[0]
        self.assertEqual(policy["spec"]["failurePolicy"], "Fail")
        binding = by_kind(self.foundation, "ValidatingAdmissionPolicyBinding")[0]
        self.assertEqual(binding["spec"]["validationActions"], ["Deny"])

    def test_contract_is_value_free_and_records_manual_acl_and_activation_gates(self) -> None:
        contract = json.loads(SECRET_CONTRACT.read_text(encoding="utf-8"))
        migration = contract["rules"]["exact25ShadowMigration"]
        self.assertFalse(migration["active"])
        self.assertEqual(migration["controlDatabase"], "legacy_migration_control")
        self.assertEqual(migration["controlRole"], "legacy_migration_control")
        self.assertEqual(migration["shadowRole"], "legacy_migration_shadow")
        self.assertTrue(migration["requiresManualAclBootstrap"])
        self.assertTrue(migration["requiresOwnerApprovedActivation"])
        self.assertNotIn("value", json.dumps(migration).lower())
        self.assertNotIn("connectionstring", json.dumps(migration).lower())

        catalogued = set(contract["presentProperties"]) | {
            item["name"] for item in contract["pendingProperties"]
        }
        self.assertTrue(set(migration["credentialProperties"]) <= catalogued)
        self.assertEqual(
            {item["name"] for item in contract["pendingProperties"] if item["name"] in migration["credentialProperties"]},
            set(migration["credentialProperties"]),
        )

        database_contract = json.loads(DATABASE_CONTRACT.read_text(encoding="utf-8"))
        foundation = database_contract["exact25ShadowMigration"]
        self.assertEqual(foundation["lifecycle"], "dormant")
        self.assertEqual(foundation["controlDatabase"], "legacy_migration_control")
        self.assertFalse(foundation["mutatesCanonicalDataOrSchema"])
        self.assertEqual(foundation["aclBootstrap"], "manual-owner-approved")
        self.assertNotIn("value", json.dumps(foundation).lower())

    def test_ci_mounts_canonical_data_migration_policy_for_alignment_test(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        self.assertIn("Legacy.Maliev.DataMigration.git", workflow)
        self.assertIn('"$workspace/Legacy.Maliev.DataMigration"', workflow)

    def test_argocd_does_not_activate_or_expand_cluster_scope_for_dormant_foundation(self) -> None:
        project = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
        self.assertEqual(
            project["spec"]["clusterResourceWhitelist"],
            [{"group": "", "kind": "Namespace"}],
        )
        active_kustomization = (
            REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-data-migration-shadow-foundation", active_kustomization)


if __name__ == "__main__":
    unittest.main()
