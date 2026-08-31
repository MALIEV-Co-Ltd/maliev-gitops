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
DATA_MIGRATION_ROOT = Path(
    os.environ.get(
        "LEGACY_DATA_MIGRATION_ROOT",
        WORKSPACE_ROOT / "Legacy.Maliev.DataMigration",
    )
)
SOURCE_POLICY = DATA_MIGRATION_ROOT / "deploy/cloudnativepg-shadow-provisioner-policy.yaml"


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

    def test_foundation_is_isolated_and_has_no_workload_or_canonical_database(self) -> None:
        active_names = {
            (resource["kind"], resource["metadata"]["name"])
            for resource in self.active
        }
        self.assertIn(("Database", "legacy-postgres-migration-control"), active_names)
        self.assertIn(("ServiceAccount", "legacy-data-migration-shadow-provisioner"), active_names)
        self.assertEqual(by_kind(self.foundation, "Cluster"), [])
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
        clusters = by_kind(self.active, "Cluster")
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        role_list = cluster["spec"]["managed"]["roles"]
        role_names = [role["name"] for role in role_list]
        self.assertEqual(len(role_names), len(set(role_names)))
        self.assertEqual(role_names.count("legacy_migration_control"), 1)
        self.assertEqual(role_names.count("legacy_migration_shadow"), 1)
        roles = {role["name"]: role for role in role_list}
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

        source_checkpoint = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=DATA_MIGRATION_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        foundation_readme = (
            REPO_ROOT / "3-apps/_legacy-data-migration-shadow-foundation/README.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f"source checkpoint is `{source_checkpoint}`", foundation_readme)

        source_text = SOURCE_POLICY.read_text(encoding="utf-8")
        # The reviewed source contract stores CEL as unquoted plain scalars. Its
        # ternary colons are not valid YAML, so canonicalize only expression
        # scalar quoting before semantic comparison with the deployable copy.
        try:
            source = [document for document in yaml.safe_load_all(source_text) if document]
        except yaml.YAMLError:
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
            [
                {
                    "apiGroups": ["postgresql.cnpg.io"],
                    "resources": ["databases"],
                    "verbs": ["get", "create", "patch", "delete"],
                },
                {
                    "apiGroups": ["postgresql.cnpg.io"],
                    "resources": ["clusters"],
                    "resourceNames": ["legacy-postgres-main"],
                    "verbs": ["get"],
                },
            ],
        )
        policy = by_kind(self.foundation, "ValidatingAdmissionPolicy")[0]
        self.assertEqual(policy["spec"]["failurePolicy"], "Fail")
        self.assertEqual(
            policy["spec"]["matchConstraints"]["resourceRules"][0]["resources"],
            ["databases", "databases/status"],
        )
        self.assertEqual(
            policy["spec"]["matchConditions"],
            [{
                "name": "migration-identity-or-shadow-object",
                "expression": "request.userInfo.username == 'system:serviceaccount:maliev-legacy:legacy-data-migration-shadow-provisioner' || (object != null && (object.metadata.name.startsWith('legacy-shadow-') || object.spec.name.startsWith('legacy_shadow_'))) || (oldObject != null && (oldObject.metadata.name.startsWith('legacy-shadow-') || oldObject.spec.name.startsWith('legacy_shadow_')))",
            }],
        )
        self.assertIn("request.userInfo", policy["spec"]["matchConditions"][0]["expression"])
        shadow_name = re.compile(r"^legacy-shadow-[a-z0-9-]+-[0-9a-f]{32}$")
        shadow_database = re.compile(r"^legacy_shadow_[a-z0-9_]+_[0-9a-f]{32}$")
        self.assertIsNotNone(shadow_name.fullmatch("legacy-shadow-order-0123456789abcdef0123456789abcdef"))
        self.assertIsNone(shadow_name.fullmatch("legacy-postgres-order"))

        def selects_shadow(
            current_metadata: str | None,
            current_database: str | None,
            old_metadata: str | None,
            old_database: str | None,
        ) -> bool:
            return any(
                pattern.fullmatch(value)
                for pattern, value in (
                    (shadow_name, current_metadata),
                    (shadow_database, current_database),
                    (shadow_name, old_metadata),
                    (shadow_database, old_database),
                )
                if value is not None
            )

        shadow_physical = "legacy_shadow_order_0123456789abcdef0123456789abcdef"
        self.assertTrue(selects_shadow("legacy-postgres-order", shadow_physical, None, None))  # CREATE
        self.assertTrue(selects_shadow("legacy-postgres-order", shadow_physical, "legacy-postgres-order", shadow_physical))  # UPDATE
        self.assertTrue(selects_shadow(None, None, "legacy-postgres-order", shadow_physical))  # DELETE
        self.assertFalse(selects_shadow("legacy-postgres-order", "Order", None, None))  # CREATE
        self.assertFalse(selects_shadow("legacy-postgres-order", "Order", "legacy-postgres-order", "Order"))  # UPDATE
        self.assertFalse(selects_shadow(None, None, "legacy-postgres-order", "Order"))  # DELETE
        validations = {
            item["message"]: item["expression"]
            for item in policy["spec"]["validations"]
        }
        migration_identity = "system:serviceaccount:maliev-legacy:legacy-data-migration-shadow-provisioner"
        controller_identity = "system:serviceaccount:maliev-legacy:legacy-postgres-main"
        identity_expression = validations[
            "Only the dedicated migration identity or the exact CloudNativePG instance manager may perform its restricted update on legacy shadow resources."
        ]
        self.assertIn(migration_identity, identity_expression)
        self.assertIn(controller_identity, identity_expression)
        self.assertIn("request.operation == 'UPDATE'", identity_expression)

        controller_expression = validations[
            "The CloudNativePG instance manager may update only status and its exact cnpg.io/deleteDatabase finalizer on an otherwise unchanged fenced shadow resource."
        ]
        for immutable_field in (
            "object.spec == oldObject.spec",
            "object.metadata.labels == oldObject.metadata.labels",
            "object.metadata.annotations == oldObject.metadata.annotations",
            "object.metadata.ownerReferences == oldObject.metadata.ownerReferences",
            "finalizer != 'cnpg.io/deleteDatabase'",
        ):
            self.assertIn(immutable_field, controller_expression)

        def identity_gate(
            username: str,
            operation: str,
            *,
            spec_equal: bool = True,
            labels_equal: bool = True,
            annotations_equal: bool = True,
            owner_references_equal: bool = True,
            old_finalizers: tuple[str, ...] = (),
            new_finalizers: tuple[str, ...] = (),
        ) -> bool:
            if username == migration_identity:
                return True
            return (
                username == controller_identity
                and operation == "UPDATE"
                and spec_equal
                and labels_equal
                and annotations_equal
                and owner_references_equal
                and tuple(item for item in old_finalizers if item != "cnpg.io/deleteDatabase")
                == tuple(item for item in new_finalizers if item != "cnpg.io/deleteDatabase")
            )

        self.assertFalse(identity_gate(controller_identity, "CREATE"))
        self.assertFalse(identity_gate(controller_identity, "DELETE"))
        self.assertFalse(identity_gate(controller_identity, "UPDATE", spec_equal=False))
        self.assertFalse(identity_gate(controller_identity, "UPDATE", labels_equal=False))
        self.assertFalse(identity_gate(controller_identity, "UPDATE", annotations_equal=False))
        self.assertFalse(identity_gate(controller_identity, "UPDATE", owner_references_equal=False))
        self.assertFalse(
            identity_gate(
                controller_identity,
                "UPDATE",
                old_finalizers=("third-party.example/fence",),
                new_finalizers=(),
            )
        )
        self.assertTrue(identity_gate(controller_identity, "UPDATE"))  # status only
        self.assertTrue(
            identity_gate(
                controller_identity,
                "UPDATE",
                new_finalizers=("cnpg.io/deleteDatabase",),
            )
        )
        self.assertTrue(
            identity_gate(
                controller_identity,
                "UPDATE",
                old_finalizers=("cnpg.io/deleteDatabase",),
            )
        )
        self.assertTrue(identity_gate(migration_identity, "CREATE"))
        self.assertTrue(identity_gate(migration_identity, "DELETE"))
        self.assertFalse(identity_gate("system:serviceaccount:maliev-legacy:other", "UPDATE"))
        self.assertEqual(
            validations["Shadow creation requires delete reclaim policy."],
            "request.operation != 'CREATE' || object.spec.databaseReclaimPolicy == 'delete'",
        )
        self.assertEqual(
            validations["Shadow PostgreSQL names are immutable during updates."],
            "request.operation != 'UPDATE' || (object.spec.databaseReclaimPolicy == 'delete' && oldObject.spec.databaseReclaimPolicy == 'delete' && oldObject.spec.name == object.spec.name)",
        )
        self.assertEqual(
            validations["Shadow deletion requires the fenced disabled absent state and delete reclaim policy."],
            "request.operation != 'DELETE' || (oldObject.spec.databaseReclaimPolicy == 'delete' && oldObject.spec.allowConnections == false && oldObject.spec.ensure == 'absent')",
        )
        connection_expression = validations[
            "Connections may only be enabled from a fenced disabled resource."
        ]
        self.assertIn(controller_identity, connection_expression)
        self.assertIn("object.spec == oldObject.spec", connection_expression)

        def connections_gate(
            username: str,
            old_allow_connections: bool,
            new_allow_connections: bool,
            ensure: str,
            spec_equal: bool,
        ) -> bool:
            return (
                not new_allow_connections
                or (
                    username == controller_identity
                    and spec_equal
                )
                or (
                    not old_allow_connections
                    and ensure == "present"
                )
            )

        self.assertTrue(connections_gate(controller_identity, False, False, "present", True))
        self.assertTrue(connections_gate(controller_identity, True, True, "present", True))
        # The generic connection transition accepts false -> true, but the
        # independent controller immutability validation above rejects its
        # accompanying spec drift for the controller identity.
        self.assertTrue(connections_gate(controller_identity, False, True, "present", False))
        self.assertTrue(connections_gate(migration_identity, False, True, "present", False))
        self.assertTrue(connections_gate(migration_identity, True, False, "present", False))
        self.assertFalse(connections_gate(migration_identity, True, True, "present", True))
        binding = by_kind(self.foundation, "ValidatingAdmissionPolicyBinding")[0]
        self.assertEqual(binding["spec"]["validationActions"], ["Deny"])

    def test_contract_is_value_free_and_records_manual_acl_and_activation_gates(self) -> None:
        contract = json.loads(SECRET_CONTRACT.read_text(encoding="utf-8"))
        migration = contract["rules"]["exact25ShadowMigration"]
        self.assertTrue(migration["active"])
        self.assertEqual(migration["controlDatabase"], "legacy_migration_control")
        self.assertEqual(migration["controlRole"], "legacy_migration_control")
        self.assertEqual(migration["shadowRole"], "legacy_migration_shadow")
        self.assertTrue(migration["requiresManualAclBootstrap"])
        self.assertTrue(migration["requiresOwnerApprovedActivation"])
        self.assertNotIn("value", json.dumps(migration).lower())
        self.assertNotIn("connectionstring", json.dumps(migration).lower())

        present = set(contract["presentProperties"])
        self.assertTrue(set(migration["credentialProperties"]) <= present)
        self.assertEqual(
            {item["name"] for item in contract["pendingProperties"] if item["name"] in migration["credentialProperties"]},
            set(),
        )

        database_contract = json.loads(DATABASE_CONTRACT.read_text(encoding="utf-8"))
        foundation = database_contract["exact25ShadowMigration"]
        self.assertEqual(foundation["lifecycle"], "owner-approved-shadow-validation")
        self.assertEqual(foundation["controlDatabase"], "legacy_migration_control")
        self.assertFalse(foundation["mutatesCanonicalDataOrSchema"])
        self.assertEqual(foundation["aclBootstrap"], "manual-owner-approved")
        self.assertNotIn("value", json.dumps(foundation).lower())

        runbook = (
            REPO_ROOT / "3-apps/_legacy-data-migration-shadow-foundation/README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;", runbook)
        self.assertIn("GRANT CONNECT ON DATABASE postgres TO streaming_replica;", runbook)
        self.assertIn("GRANT CONNECT ON DATABASE postgres TO legacy_migration_shadow;", runbook)
        self.assertIn("REVOKE CREATE ON DATABASE postgres FROM legacy_migration_shadow;", runbook)
        self.assertIn("GitOps does not execute these SQL statements", runbook)

    def test_ci_mounts_canonical_data_migration_policy_for_alignment_test(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        self.assertIn("Legacy.Maliev.DataMigration.git", workflow)
        self.assertIn('"$workspace/Legacy.Maliev.DataMigration"', workflow)

    def test_argocd_activation_is_exact_and_cluster_scope_is_narrow(self) -> None:
        project = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
        self.assertEqual(
            project["spec"]["clusterResourceWhitelist"],
            [
                {"group": "", "kind": "Namespace"},
                {"group": "admissionregistration.k8s.io", "kind": "ValidatingAdmissionPolicy"},
                {"group": "admissionregistration.k8s.io", "kind": "ValidatingAdmissionPolicyBinding"},
            ],
        )
        active_kustomization = (
            REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"
        ).read_text(encoding="utf-8")
        self.assertEqual(active_kustomization.count("_legacy-postgres/overlays/legacy"), 1)
        self.assertEqual(active_kustomization.count("_legacy-data-migration-shadow-foundation/overlays/legacy"), 1)

        foundation_kustomization = (
            REPO_ROOT
            / "3-apps/_legacy-data-migration-shadow-foundation/overlays/legacy/kustomization.yaml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-postgres", foundation_kustomization)

        active_identities = [
            (resource["kind"], resource["metadata"]["name"])
            for resource in self.active
        ]
        self.assertEqual(active_identities.count(("Cluster", "legacy-postgres-main")), 1)
        self.assertEqual(
            active_identities.count(("Database", "legacy-postgres-migration-control")),
            1,
        )


if __name__ == "__main__":
    unittest.main()
