from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ENVIRONMENT = "3-apps/_legacy-redis/overlays/legacy"
ROOT_ENVIRONMENT = "2-environments/4-legacy"


def render() -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / LEGACY_ENVIRONMENT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def render_path(relative_path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / relative_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class LegacyRedisManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render()

    def test_password_is_projected_without_embedding_it_in_probe_arguments(self) -> None:
        deployment = next(
            resource
            for resource in self.documents
            if resource.get("kind") == "Deployment"
            and resource["metadata"]["name"] == "legacy-redis"
        )
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        environment = {item["name"]: item for item in container["env"]}

        password_source = {
            "valueFrom": {
                "secretKeyRef": {"name": "legacy-redis", "key": "REDIS_PASSWORD"}
            }
        }
        self.assertEqual(environment["REDIS_PASSWORD"], {"name": "REDIS_PASSWORD", **password_source})
        self.assertEqual(environment["REDISCLI_AUTH"], {"name": "REDISCLI_AUTH", **password_source})

        readiness_command = container["readinessProbe"]["exec"]["command"]
        self.assertEqual(readiness_command, ["redis-cli", "--no-auth-warning", "ping"])
        self.assertNotIn("$(REDIS_PASSWORD)", readiness_command)

    def test_redis_is_bounded_private_and_uses_the_single_legacy_secret(self) -> None:
        config = next(
            resource
            for resource in self.documents
            if resource.get("kind") == "ConfigMap"
            and resource["metadata"]["name"] == "legacy-redis-config"
        )
        self.assertIn("protected-mode yes", config["data"]["redis.conf"])
        self.assertIn("maxmemory 64mb", config["data"]["redis.conf"])

        external_secret = next(
            resource
            for resource in self.documents
            if resource.get("kind") == "ExternalSecret"
            and resource["metadata"]["name"] == "legacy-redis"
        )
        self.assertEqual(external_secret["metadata"]["namespace"], "maliev-legacy")
        self.assertEqual(
            external_secret["spec"]["data"][0]["remoteRef"],
            {"key": "maliev-legacy-secrets", "property": "legacy-redis-password"},
        )

    def test_network_policy_allows_only_declared_legacy_redis_consumers(self) -> None:
        policy = next(
            resource
            for resource in self.documents
            if resource.get("kind") == "NetworkPolicy"
            and resource["metadata"]["name"] == "legacy-redis"
        )
        expression = policy["spec"]["ingress"][0]["from"][0]["podSelector"]["matchExpressions"][0]
        self.assertEqual(expression["key"], "app.kubernetes.io/name")
        self.assertEqual(expression["operator"], "In")
        self.assertEqual(
            set(expression["values"]),
            {
                "legacy-maliev-accounting-service",
                "legacy-maliev-career-service",
                "legacy-maliev-catalog-service",
                "legacy-maliev-contact-service",
                "legacy-maliev-country-service",
                "legacy-maliev-customer-service",
                "legacy-maliev-employee-service",
                "legacy-maliev-file-service",
                "legacy-maliev-intranet",
                "legacy-maliev-intranet-bff",
                "legacy-maliev-order-service",
                "legacy-maliev-procurement-service",
                "legacy-maliev-quotation-service",
                "legacy-maliev-web",
            },
        )
        self.assertEqual(
            policy["spec"]["ingress"][0]["ports"],
            [{"protocol": "TCP", "port": 6379}],
        )

    def test_legacy_environment_reconciles_redis_alongside_postgres_foundation(self) -> None:
        root = render_path(ROOT_ENVIRONMENT)
        names = {(resource.get("kind"), resource["metadata"]["name"]) for resource in root}
        self.assertIn(("Deployment", "legacy-redis"), names)
        self.assertIn(("NetworkPolicy", "legacy-redis"), names)


if __name__ == "__main__":
    unittest.main()
