from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "3-apps/_legacy-notification-service/overlays/legacy"
LEGACY_ENVIRONMENT = "2-environments/4-legacy"
IMAGE = (
    "asia-southeast1-docker.pkg.dev/maliev-website/"
    "maliev-website-artifact-prod/legacy-maliev-notification-service:not-published"
)


def render(path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def one(documents: list[dict], kind: str, name: str) -> dict:
    matches = [
        item for item in documents
        if item.get("kind") == kind and item["metadata"]["name"] == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}, found {len(matches)}")
    return matches[0]


class LegacyNotificationServiceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(OVERLAY)

    def test_overlay_is_dormant_and_namespace_isolated(self) -> None:
        self.assertNotIn(
            "legacy-maliev-notification-service",
            {item["metadata"]["name"] for item in render(LEGACY_ENVIRONMENT)},
        )
        for item in self.documents:
            self.assertEqual(item["metadata"].get("namespace"), "maliev-legacy")

    def test_deployment_is_internal_non_root_and_resource_bounded(self) -> None:
        deployment = one(self.documents, "Deployment", "legacy-maliev-notification-service")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]

        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(container["image"], IMAGE)
        self.assertEqual(deployment["metadata"]["namespace"], "maliev-legacy")
        self.assertEqual(deployment["metadata"]["labels"]["owner"], "maliev")
        self.assertEqual(deployment["metadata"]["annotations"]["email"], "info@maliev.com")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["restartPolicy"], "Always")
        self.assertEqual(pod["dnsConfig"]["options"], [{"name": "ndots", "value": "2"}])
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0],
            {"key": "kubernetes.io/os", "operator": "In", "values": ["linux"]},
        )
        self.assertTrue(container["securityContext"]["runAsNonRoot"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertEqual(container["resources"]["requests"], {"cpu": "20m", "memory": "96Mi"})
        self.assertEqual(container["resources"]["limits"], {"cpu": "150m", "memory": "192Mi"})
        self.assertEqual(container["livenessProbe"]["httpGet"]["path"], "/emails/liveness")
        self.assertEqual(container["readinessProbe"]["httpGet"]["path"], "/emails/readiness")
        self.assertEqual(
            one(self.documents, "Service", "legacy-maliev-notification-service")["spec"]["type"],
            "ClusterIP",
        )
        self.assertNotIn("Ingress", {item.get("kind") for item in self.documents})

    def test_external_secret_projects_only_brevo_and_jwt_contract(self) -> None:
        external = one(self.documents, "ExternalSecret", "legacy-maliev-notification-service")
        self.assertEqual(
            {item["remoteRef"]["key"] for item in external["spec"]["data"]},
            {"maliev-legacy-secrets"},
        )
        self.assertEqual(
            {item["remoteRef"]["property"] for item in external["spec"]["data"]},
            {
                "legacy-notification-brevo-api-key",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
            },
        )
        self.assertEqual(
            set(external["spec"]["target"]["template"]["data"]),
            {"Brevo__ApiKey", "Jwt__PublicKey", "Jwt__Issuer", "Jwt__Audience"},
        )

    def test_network_policy_allows_only_namespace_ingress_dns_and_provider_https(self) -> None:
        policy = one(self.documents, "NetworkPolicy", "legacy-maliev-notification-service")
        self.assertEqual(set(policy["spec"]["policyTypes"]), {"Ingress", "Egress"})
        ports = {
            port["port"]
            for rule in policy["spec"]["egress"]
            for port in rule.get("ports", [])
        }
        self.assertEqual(ports, {53, 443})
        self.assertNotIn(5432, ports)
        self.assertNotIn(6379, ports)


if __name__ == "__main__":
    unittest.main()
