from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ENVIRONMENT = "2-environments/4-legacy"
PLUGIN_INFRA = "1-cluster-infra/07-barman-cloud-plugin"
PLUGIN_IMAGE = (
    "ghcr.io/cloudnative-pg/plugin-barman-cloud:v0.13.0@"
    "sha256:71589dbac582333442812b07b31f7ea4d00324a8358aac7ca507dabf9f4b6c96"
)
REPOSITORY = "https://github.com/MALIEV-Co-Ltd/maliev-gitops.git"

ACTIVE_DATABASES = {
    "Country": "legacy_country_owner",
    "Currency": "legacy_currency_owner",
    "Customer": "legacy_customer_owner",
    "CustomerIdentity": "legacy_customer_identity_owner",
    "DataProtectionKeys": "legacy_data_protection_keys_owner",
    "DataProtectionKeysEmployee": "legacy_data_protection_keys_employee_owner",
    "Employee": "legacy_employee_owner",
    "EmployeeIdentity": "legacy_employee_identity_owner",
    "Invoice": "legacy_invoice_owner",
    "JobOffers": "legacy_job_offers_owner",
    "Material": "legacy_material_owner",
    "Message": "legacy_message_owner",
    "Order": "legacy_order_owner",
    "OrderStatus": "legacy_order_status_owner",
    "Payment": "legacy_payment_owner",
    "PurchaseOrder": "legacy_purchase_order_owner",
    "Quotation": "legacy_quotation_owner",
    "QuotationRequest": "legacy_quotation_request_owner",
    "Receipt": "legacy_receipt_owner",
    "Supplier": "legacy_supplier_owner",
    "Upload": "legacy_upload_owner",
}


def render(relative_path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / relative_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def resources_by_kind(documents: list[dict], kind: str) -> list[dict]:
    return [document for document in documents if document.get("kind") == kind]


def camel_to_kebab(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", value).lower()


class LegacyPostgresManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.legacy = render(LEGACY_ENVIRONMENT)

    def test_barman_plugin_is_vendored_and_digest_pinned_in_cnpg_system(self) -> None:
        plugin_kustomization = REPO_ROOT / PLUGIN_INFRA / "kustomization.yaml"
        self.assertTrue((REPO_ROOT / PLUGIN_INFRA / "release.yaml").is_file())
        self.assertNotIn("github.com", plugin_kustomization.read_text(encoding="utf-8"))

        first_render = render(PLUGIN_INFRA)
        second_render = render(PLUGIN_INFRA)
        self.assertEqual(first_render, second_render)
        self.assertEqual(resources_by_kind(first_render, "Secret"), [])
        sidecar_config = resources_by_kind(first_render, "ConfigMap")
        self.assertIn(
            "plugin-barman-cloud-m5m67kfh8f",
            {resource["metadata"]["name"] for resource in sidecar_config},
        )

        crds = resources_by_kind(first_render, "CustomResourceDefinition")
        self.assertIn(
            "objectstores.barmancloud.cnpg.io",
            {resource["metadata"]["name"] for resource in crds},
        )
        deployments = resources_by_kind(first_render, "Deployment")
        self.assertEqual(len(deployments), 1)
        deployment = deployments[0]
        self.assertEqual(deployment["metadata"]["name"], "barman-cloud")
        self.assertEqual(deployment["metadata"]["namespace"], "cnpg-system")
        self.assertEqual(
            deployment["spec"]["template"]["spec"]["containers"][0]["image"],
            PLUGIN_IMAGE,
        )
        sidecar_source = deployment["spec"]["template"]["spec"]["containers"][0]["env"][0][
            "valueFrom"
        ]
        self.assertIn("configMapKeyRef", sidecar_source)
        self.assertNotIn("secretKeyRef", sidecar_source)
        self.assertFalse(
            any(resource["metadata"]["name"] == "cnpg-controller-manager" for resource in deployments)
        )

    def test_legacy_environment_renders_deterministically_and_is_namespace_isolated(self) -> None:
        self.assertEqual(self.legacy, render(LEGACY_ENVIRONMENT))
        namespace = resources_by_kind(self.legacy, "Namespace")
        self.assertEqual([item["metadata"]["name"] for item in namespace], ["maliev-legacy"])

        cluster_scoped_kinds = {"Namespace", "CustomResourceDefinition", "ClusterRole", "ClusterRoleBinding"}
        for resource in self.legacy:
            if resource["kind"] not in cluster_scoped_kinds:
                self.assertEqual(
                    resource["metadata"].get("namespace"),
                    "maliev-legacy",
                    f"{resource['kind']}/{resource['metadata']['name']} escaped maliev-legacy",
                )

    def test_cluster_uses_cnpg_i_gcs_backup_and_resource_limits(self) -> None:
        cluster = resources_by_kind(self.legacy, "Cluster")[0]
        self.assertEqual(cluster["metadata"]["name"], "legacy-postgres-main")
        self.assertEqual(cluster["spec"]["instances"], 2)
        self.assertEqual(cluster["spec"]["affinity"]["podAntiAffinityType"], "required")
        self.assertTrue(cluster["spec"]["enablePDB"])
        self.assertEqual(cluster["spec"]["storage"]["storageClass"], "standard-rwo")
        self.assertIn("requests", cluster["spec"]["resources"])
        self.assertIn("limits", cluster["spec"]["resources"])
        self.assertNotIn("backup", cluster["spec"])
        self.assertEqual(
            cluster["spec"]["plugins"],
            [
                {
                    "name": "barman-cloud.cloudnative-pg.io",
                    "isWALArchiver": True,
                    "parameters": {"barmanObjectName": "legacy-postgres-backup-main"},
                }
            ],
        )
        self.assertEqual(
            cluster["spec"]["serviceAccountTemplate"]["metadata"]["annotations"][
                "iam.gke.io/gcp-service-account"
            ],
            "legacy-postgres-main@maliev-website.iam.gserviceaccount.com",
        )
        self.assertEqual(
            cluster["spec"]["serviceAccountTemplate"]["metadata"]["name"],
            "legacy-postgres-main",
        )

        bootstrap = cluster["spec"]["bootstrap"]["initdb"]
        self.assertEqual(bootstrap["database"], "Country")
        self.assertEqual(bootstrap["owner"], ACTIVE_DATABASES["Country"])
        self.assertEqual(bootstrap["secret"]["name"], "legacy-postgres-country")

        object_store = resources_by_kind(self.legacy, "ObjectStore")[0]
        self.assertEqual(object_store["metadata"]["name"], "legacy-postgres-backup-main")
        self.assertEqual(
            object_store["spec"]["configuration"]["destinationPath"],
            "gs://maliev.com/database/legacy-postgres/main/",
        )
        self.assertTrue(
            object_store["spec"]["configuration"]["googleCredentials"]["gkeEnvironment"]
        )
        self.assertEqual(object_store["spec"]["retentionPolicy"], "14d")

        scheduled_backup = resources_by_kind(self.legacy, "ScheduledBackup")[0]
        self.assertEqual(scheduled_backup["spec"]["cluster"]["name"], "legacy-postgres-main")
        self.assertEqual(scheduled_backup["spec"]["method"], "plugin")
        self.assertEqual(
            scheduled_backup["spec"]["pluginConfiguration"]["name"],
            "barman-cloud.cloudnative-pg.io",
        )

    def test_cnpg_owns_the_pdb_and_monitor_selects_the_legacy_cluster(self) -> None:
        self.assertEqual(resources_by_kind(self.legacy, "PodDisruptionBudget"), [])
        pod_monitor = resources_by_kind(self.legacy, "PodMonitor")[0]
        self.assertEqual(
            pod_monitor["spec"]["selector"]["matchLabels"]["cnpg.io/cluster"],
            "legacy-postgres-main",
        )

    def test_all_active_databases_have_distinct_owner_roles(self) -> None:
        databases = resources_by_kind(self.legacy, "Database")
        actual = {item["spec"]["name"]: item["spec"]["owner"] for item in databases}
        self.assertEqual(actual, ACTIVE_DATABASES)
        self.assertNotIn("Log", actual)
        self.assertNotIn("MachineLearningData", actual)
        self.assertEqual(
            {item["spec"]["cluster"]["name"] for item in databases},
            {"legacy-postgres-main"},
        )

        cluster = resources_by_kind(self.legacy, "Cluster")[0]
        roles = cluster["spec"]["managed"]["roles"]
        self.assertEqual({role["name"] for role in roles}, set(ACTIVE_DATABASES.values()))
        self.assertTrue(all(role["login"] for role in roles))

    def test_external_secrets_use_only_the_single_legacy_gsm_secret(self) -> None:
        external_secrets = [
            resource
            for resource in resources_by_kind(self.legacy, "ExternalSecret")
            if resource["metadata"]["name"].startswith("legacy-postgres-")
        ]
        self.assertEqual(len(external_secrets), len(ACTIVE_DATABASES) + 1)
        properties: set[str] = set()
        for external_secret in external_secrets:
            self.assertEqual(
                external_secret["spec"]["secretStoreRef"],
                {"kind": "ClusterSecretStore", "name": "gcp-secret-manager"},
            )
            self.assertEqual(
                external_secret["spec"]["target"]["template"]["type"],
                "kubernetes.io/basic-auth",
            )
            for item in external_secret["spec"]["data"]:
                self.assertEqual(item["remoteRef"]["key"], "maliev-legacy-secrets")
                properties.add(item["remoteRef"]["property"])

        expected = {
            "legacy-postgres-superuser-username",
            "legacy-postgres-superuser-password",
        }
        for database_name in ACTIVE_DATABASES:
            prefix = f"legacy-postgres-{camel_to_kebab(database_name)}"
            expected.update({f"{prefix}-username", f"{prefix}-password"})
        self.assertEqual(properties, expected)

    def test_argo_project_and_app_are_exactly_scoped_to_legacy(self) -> None:
        argo = render("argocd")
        project = next(
            resource
            for resource in resources_by_kind(argo, "AppProject")
            if resource["metadata"]["name"] == "maliev-legacy"
        )
        self.assertEqual(project["spec"]["sourceRepos"], [REPOSITORY])
        self.assertEqual(
            project["spec"]["destinations"],
            [{"namespace": "maliev-legacy", "server": "https://kubernetes.default.svc"}],
        )

        applications = resources_by_kind(argo, "Application")
        legacy_app = next(
            resource for resource in applications if resource["metadata"]["name"] == "maliev-legacy"
        )
        self.assertEqual(legacy_app["spec"]["project"], "maliev-legacy")
        self.assertEqual(legacy_app["spec"]["source"]["repoURL"], REPOSITORY)
        self.assertEqual(legacy_app["spec"]["source"]["path"], LEGACY_ENVIRONMENT)
        self.assertEqual(legacy_app["spec"]["destination"]["namespace"], "maliev-legacy")
        self.assertNotIn("automated", legacy_app["spec"]["syncPolicy"])

        plugin_app = next(
            resource
            for resource in applications
            if resource["metadata"]["name"] == "barman-cloud-plugin"
        )
        self.assertEqual(plugin_app["spec"]["source"]["path"], PLUGIN_INFRA)
        self.assertEqual(plugin_app["spec"]["destination"]["namespace"], "cnpg-system")

    def test_existing_platform_environments_do_not_include_legacy_resources(self) -> None:
        for path in (
            "2-environments/1-development",
            "2-environments/2-staging",
            "2-environments/3-production",
        ):
            with self.subTest(path=path):
                documents = render(path)
                names = {resource["metadata"]["name"] for resource in documents}
                self.assertFalse(any(name.startswith("legacy-postgres-") for name in names))


if __name__ == "__main__":
    unittest.main()
