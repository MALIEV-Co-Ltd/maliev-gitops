from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ENVIRONMENT = "3-apps/_legacy-country-service/overlays/legacy"
REDIS_ENVIRONMENT = "3-apps/_legacy-redis/overlays/legacy"
REGISTRY = "asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact-prod"


def render(relative_path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / relative_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def one(documents: list[dict], kind: str, name: str) -> dict:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind and document["metadata"]["name"] == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}, found {len(matches)}")
    return matches[0]


class LegacyCountryServiceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(LEGACY_ENVIRONMENT)
        cls.redis_documents = render(REDIS_ENVIRONMENT)

    def test_country_service_is_internal_hardened_and_resource_bounded(self) -> None:
        deployment = one(self.documents, "Deployment", "legacy-maliev-country-service")
        self.assertEqual(deployment["metadata"]["namespace"], "maliev-legacy")
        self.assertEqual(deployment["spec"]["replicas"], 1)

        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(
            container["image"], f"{REGISTRY}/legacy-maliev-country-service:latest"
        )
        self.assertTrue(container["securityContext"]["runAsNonRoot"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertEqual(container["resources"]["requests"], {"cpu": "25m", "memory": "96Mi"})
        self.assertEqual(container["resources"]["limits"], {"cpu": "200m", "memory": "192Mi"})
        self.assertEqual(container["livenessProbe"]["httpGet"]["path"], "/countries/liveness")
        self.assertEqual(container["readinessProbe"]["httpGet"]["path"], "/countries/readiness")
        self.assertEqual(pod["automountServiceAccountToken"], False)

        service = one(self.documents, "Service", "legacy-maliev-country-service")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertNotIn("Ingress", {document.get("kind") for document in self.documents})

    def test_country_service_uses_only_the_consolidated_legacy_secret(self) -> None:
        external = one(self.documents, "ExternalSecret", "legacy-maliev-country-service")
        self.assertEqual(external["spec"]["target"]["name"], "legacy-maliev-country-service")
        properties = {
            item["remoteRef"]["property"] for item in external["spec"]["data"]
        }
        self.assertEqual(
            properties,
            {
                "legacy-postgres-country-username",
                "legacy-postgres-country-password",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
                "legacy-redis-password",
            },
        )
        self.assertEqual(
            {item["remoteRef"]["key"] for item in external["spec"]["data"]},
            {"maliev-legacy-secrets"},
        )
        template = external["spec"]["target"]["template"]["data"]
        self.assertIn("legacy-postgres-pooler-rw", template["ConnectionStrings__CountryDbContext"])
        self.assertNotIn("legacy-postgres-main-rw", template["ConnectionStrings__CountryDbContext"])
        self.assertIn("Database=Country", template["ConnectionStrings__CountryDbContext"])
        self.assertIn("legacy-redis:6379", template["ConnectionStrings__redis"])
        self.assertIn("password={{ .redisPassword }}", template["ConnectionStrings__redis"])

    def test_legacy_redis_is_ephemeral_private_and_capacity_bounded(self) -> None:
        deployment = one(self.redis_documents, "Deployment", "legacy-redis")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertTrue(container["image"].startswith("redis:8."))
        self.assertEqual(container["resources"]["requests"], {"cpu": "10m", "memory": "48Mi"})
        self.assertEqual(container["resources"]["limits"], {"cpu": "100m", "memory": "96Mi"})
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["volumeMounts"][0]["name"], "data")
        self.assertEqual(
            deployment["spec"]["template"]["spec"]["volumes"][0]["emptyDir"],
            {"sizeLimit": "64Mi"},
        )
        service = one(self.redis_documents, "Service", "legacy-redis")
        self.assertEqual(service["spec"]["clusterIP"], "None")
        external = one(self.redis_documents, "ExternalSecret", "legacy-redis")
        self.assertEqual(
            external["spec"]["data"][0]["remoteRef"],
            {"key": "maliev-legacy-secrets", "property": "legacy-redis-password"},
        )

    def test_network_policies_limit_country_dependencies(self) -> None:
        policy = one(self.documents, "NetworkPolicy", "legacy-maliev-country-service")
        self.assertEqual(set(policy["spec"]["policyTypes"]), {"Ingress", "Egress"})
        ports = {
            port["port"]
            for rule in policy["spec"]["egress"]
            for port in rule.get("ports", [])
        }
        self.assertTrue({53, 5432, 6379}.issubset(ports))


if __name__ == "__main__":
    unittest.main()
