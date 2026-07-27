from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "3-apps/_legacy-employee-service/overlays/legacy"
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


def one(documents: list[dict], kind: str, name: str) -> dict:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind and document["metadata"]["name"] == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}, found {len(matches)}")
    return matches[0]


class LegacyEmployeeServiceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(OVERLAY)

    def test_projection_is_dormant_and_namespace_isolated(self) -> None:
        active = (REPO_ROOT / ACTIVE_ENVIRONMENT).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-employee-service", active)
        for document in self.documents:
            self.assertEqual(document["metadata"].get("namespace"), "maliev-legacy")

    def test_projection_uses_only_the_consolidated_secret(self) -> None:
        external = one(self.documents, "ExternalSecret", "legacy-maliev-employee-runtime")
        self.assertEqual(external["spec"]["target"]["name"], "legacy-maliev-employee-runtime")
        self.assertEqual(
            {
                item["remoteRef"]["property"] for item in external["spec"]["data"]
            },
            {
                "legacy-postgres-employee-username",
                "legacy-postgres-employee-password",
                "legacy-redis-password",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
            },
        )
        self.assertEqual(
            {item["remoteRef"]["key"] for item in external["spec"]["data"]},
            {"maliev-legacy-secrets"},
        )
        self.assertEqual(
            set(external["spec"]["target"]["template"]["data"]),
            {
                "ConnectionStrings__EmployeeDbContext",
                "ConnectionStrings__redis",
                "Jwt__PublicKey",
                "Jwt__Issuer",
                "Jwt__Audience",
            },
        )
        self.assertIn("Database=Employee", external["spec"]["target"]["template"]["data"]["ConnectionStrings__EmployeeDbContext"])
        self.assertIn("legacy-postgres-pooler-rw", external["spec"]["target"]["template"]["data"]["ConnectionStrings__EmployeeDbContext"])


if __name__ == "__main__":
    unittest.main()
