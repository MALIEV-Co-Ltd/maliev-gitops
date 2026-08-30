from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ENVIRONMENT = REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"
READINESS = REPO_ROOT / "3-apps/_legacy-postgres/readiness"

EXPECTED = {
    "order": {
        "target": "legacy-maliev-order-runtime",
        "connections": {
            "ConnectionStrings__OrderDbContext": (
                "Order",
                "orderUsername",
                "orderPassword",
            ),
            "ConnectionStrings__OrderStatusDbContext": (
                "OrderStatus",
                "orderStatusUsername",
                "orderStatusPassword",
            ),
        },
        "properties": {
            "legacy-postgres-order-username",
            "legacy-postgres-order-password",
            "legacy-postgres-order-status-username",
            "legacy-postgres-order-status-password",
            "legacy-redis-password",
            "legacy-jwt-public-key",
            "legacy-jwt-issuer",
            "legacy-jwt-audience",
        },
        "extra_template": {},
    },
    "procurement": {
        "target": "legacy-maliev-procurement-runtime",
        "connections": {
            "ConnectionStrings__SupplierDbContext": (
                "Supplier",
                "supplierUsername",
                "supplierPassword",
            ),
            "ConnectionStrings__PurchaseOrderDbContext": (
                "PurchaseOrder",
                "purchaseOrderUsername",
                "purchaseOrderPassword",
            ),
        },
        "properties": {
            "legacy-postgres-supplier-username",
            "legacy-postgres-supplier-password",
            "legacy-postgres-purchase-order-username",
            "legacy-postgres-purchase-order-password",
            "legacy-redis-password",
            "legacy-jwt-public-key",
            "legacy-jwt-issuer",
            "legacy-jwt-audience",
        },
        "extra_template": {},
    },
    "quotation": {
        "target": "legacy-maliev-quotation-runtime",
        "connections": {
            "ConnectionStrings__QuotationDbContext": (
                "Quotation",
                "quotationUsername",
                "quotationPassword",
            ),
            "ConnectionStrings__QuotationRequestDbContext": (
                "QuotationRequest",
                "quotationRequestUsername",
                "quotationRequestPassword",
            ),
        },
        "properties": {
            "legacy-postgres-quotation-username",
            "legacy-postgres-quotation-password",
            "legacy-postgres-quotation-request-username",
            "legacy-postgres-quotation-request-password",
            "legacy-redis-password",
            "legacy-jwt-public-key",
            "legacy-jwt-issuer",
            "legacy-jwt-audience",
            "legacy-quotation-service-client-secret",
        },
        "extra_template": {
            "ServiceAuthentication__ClientSecret": "{{ .serviceClientSecret }}",
        },
    },
}


def render(service: str) -> list[dict]:
    overlay = REPO_ROOT / f"3-apps/_legacy-{service}-service/overlays/legacy"
    result = subprocess.run(
        ["kubectl", "kustomize", str(overlay)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class LegacyOrderProcurementQuotationServiceManifestTests(unittest.TestCase):
    def test_each_projection_is_dormant_namespace_scoped_and_secret_only(self) -> None:
        active = ACTIVE_ENVIRONMENT.read_text(encoding="utf-8")
        for service in EXPECTED:
            with self.subTest(service=service):
                resource = f"_legacy-{service}-service"
                self.assertNotIn(resource, active)
                documents = render(service)
                self.assertEqual([document["kind"] for document in documents], ["ExternalSecret"])
                self.assertEqual(documents[0]["metadata"]["namespace"], "maliev-legacy")

    def test_each_projection_uses_exact_consolidated_secret_contract(self) -> None:
        for service, expected in EXPECTED.items():
            with self.subTest(service=service):
                external = render(service)[0]
                self.assertEqual(external["spec"]["target"]["name"], expected["target"])
                data = external["spec"]["data"]
                self.assertEqual(
                    {item["remoteRef"]["key"] for item in data},
                    {"maliev-legacy-secrets"},
                )
                self.assertEqual(
                    {item["remoteRef"]["property"] for item in data},
                    expected["properties"],
                )

    def test_each_projection_matches_real_postgres_redis_and_jwt_consumers(self) -> None:
        common = {
            "ConnectionStrings__redis": (
                "legacy-redis:6379,password={{ .redisPassword }},ssl=false,abortConnect=false"
            ),
            "Jwt__PublicKey": "{{ .jwtPublicKey | b64enc }}",
            "Jwt__Issuer": "{{ .jwtIssuer }}",
            "Jwt__Audience": "{{ .jwtAudience }}",
        }
        for service, expected in EXPECTED.items():
            with self.subTest(service=service):
                template = render(service)[0]["spec"]["target"]["template"]["data"]
                expected_keys = set(expected["connections"]) | set(common) | set(expected["extra_template"])
                self.assertEqual(set(template), expected_keys)
                for key, value in common.items():
                    self.assertEqual(template[key], value)
                for key, value in expected["extra_template"].items():
                    self.assertEqual(template[key], value)
                for key, (database, username, password) in expected["connections"].items():
                    connection = template[key]
                    for fragment in (
                        "Host=legacy-postgres-pooler-rw",
                        "Port=5432",
                        f"Database={database}",
                        f"Username={{{{ .{username} }}}}",
                        f"Password={{{{ .{password} }}}}",
                        "SSL Mode=Require",
                        "Trust Server Certificate=true",
                        "Pooling=true",
                        "Minimum Pool Size=0",
                        "Maximum Pool Size=20",
                    ):
                        self.assertIn(fragment, connection)
                    for forbidden in ("SqlServer", "Data Source=", "Initial Catalog="):
                        self.assertNotIn(forbidden, connection)

    def test_readiness_contracts_classify_all_three_projections_as_dormant(self) -> None:
        secret = json.loads((READINESS / "legacy-secret-contract.json").read_text(encoding="utf-8"))
        database = json.loads(
            (READINESS / "legacy-service-database-contract.json").read_text(encoding="utf-8")
        )
        inventory = json.loads(
            (READINESS / "legacy-runtime-inventory.json").read_text(encoding="utf-8")
        )

        expected_services = set(EXPECTED)
        dormant = {projection["service"] for projection in secret["dormantProjections"]}
        planned = {projection["service"] for projection in secret["plannedProjections"]}
        self.assertTrue(expected_services <= dormant)
        self.assertTrue(expected_services.isdisjoint(planned))

        expected_resources = {f"_legacy-{service}-service" for service in expected_services}
        self.assertTrue(expected_resources <= set(database["deferredGitOpsServiceResources"]))
        self.assertTrue(expected_resources.isdisjoint(database["plannedGitOpsServiceResources"]))

        lifecycle = {
            item["gitOpsResource"]: item["lifecycle"]
            for item in inventory["services"]
        }
        for resource in expected_resources:
            self.assertEqual(lifecycle[resource], "deferred")


if __name__ == "__main__":
    unittest.main()
