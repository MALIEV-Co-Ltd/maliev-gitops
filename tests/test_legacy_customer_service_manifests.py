from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "3-apps/_legacy-customer-service/overlays/legacy"
ACTIVE_ENVIRONMENT = "2-environments/4-legacy/kustomization.yaml"


def render(path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class LegacyCustomerServiceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(OVERLAY)
        cls.external = cls.documents[0]

    def test_projection_is_dormant_and_namespace_scoped(self) -> None:
        active = (REPO_ROOT / ACTIVE_ENVIRONMENT).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-customer-service", active)
        self.assertEqual([document["kind"] for document in self.documents], ["ExternalSecret"])
        self.assertEqual(self.external["metadata"]["namespace"], "maliev-legacy")

    def test_projection_uses_exact_consolidated_secret_contract(self) -> None:
        self.assertEqual(self.external["spec"]["target"]["name"], "legacy-maliev-customer-runtime")
        data = self.external["spec"]["data"]
        self.assertEqual({item["remoteRef"]["key"] for item in data}, {"maliev-legacy-secrets"})
        self.assertEqual(
            {item["remoteRef"]["property"] for item in data},
            {
                "legacy-postgres-customer-username",
                "legacy-postgres-customer-password",
                "legacy-redis-password",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
            },
        )

        template = self.external["spec"]["target"]["template"]["data"]
        self.assertEqual(
            set(template),
            {
                "ConnectionStrings__CustomerDbContext",
                "ConnectionStrings__redis",
                "Jwt__PublicKey",
                "Jwt__Issuer",
                "Jwt__Audience",
            },
        )
        connection = template["ConnectionStrings__CustomerDbContext"]
        for expected in (
            "Host=legacy-postgres-pooler-rw",
            "Port=5432",
            "Database=Customer",
            "Username={{ .customerUsername }}",
            "Password={{ .customerPassword }}",
            "SSL Mode=Require",
            "Trust Server Certificate=true",
            "Pooling=true",
            "Minimum Pool Size=0",
            "Maximum Pool Size=20",
        ):
            self.assertIn(expected, connection)
        for forbidden in (
            "SqlServer",
            "Data Source=",
            "Initial Catalog=",
            "CustomerIdentity",
            "Database=Material",
            "Database=Country",
        ):
            self.assertNotIn(forbidden, connection)

        self.assertEqual(
            template["ConnectionStrings__redis"],
            "legacy-redis:6379,password={{ .redisPassword }},ssl=false,abortConnect=false",
        )
        self.assertEqual(template["Jwt__PublicKey"], "{{ .jwtPublicKey | b64enc }}")
        for forbidden_key in (
            "Jwt__PrivateKeyPem",
            "Jwt__KeyId",
            "Jwt__SecurityKey",
            "Services__ClientSecret",
        ):
            self.assertNotIn(forbidden_key, template)

    def test_contracts_classify_customer_projection_as_dormant(self) -> None:
        secret_contract = json.loads(
            (REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json").read_text(
                encoding="utf-8"
            )
        )
        dormant = {projection["service"] for projection in secret_contract["dormantProjections"]}
        planned = {projection["service"] for projection in secret_contract["plannedProjections"]}
        self.assertIn("customer", dormant)
        self.assertNotIn("customer", planned)

        database_contract = json.loads(
            (
                REPO_ROOT
                / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("_legacy-customer-service", database_contract["deferredGitOpsServiceResources"])
        self.assertNotIn("_legacy-customer-service", database_contract["plannedGitOpsServiceResources"])

        runtime_inventory = json.loads(
            (REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-runtime-inventory.json").read_text(
                encoding="utf-8"
            )
        )
        customer = next(
            item
            for item in runtime_inventory["services"]
            if item["service"] == "Legacy.Maliev.CustomerService"
        )
        self.assertEqual(customer["lifecycle"], "deferred")
        self.assertEqual(customer["healthPrefixes"], ["customer"])


if __name__ == "__main__":
    unittest.main()
