from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "3-apps/_legacy-document-service/overlays/legacy"
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


class LegacyDocumentServiceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(OVERLAY)

    def test_projection_is_dormant_and_namespace_scoped(self) -> None:
        active = (REPO_ROOT / ACTIVE_ENVIRONMENT).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-document-service", active)
        self.assertEqual(len(self.documents), 1)
        self.assertEqual(self.documents[0]["metadata"]["namespace"], "maliev-legacy")

    def test_projection_uses_only_the_consolidated_secret(self) -> None:
        external = self.documents[0]
        self.assertEqual(external["kind"], "ExternalSecret")
        self.assertEqual(external["spec"]["target"]["name"], "legacy-maliev-document-runtime")
        self.assertEqual(
            {item["remoteRef"]["key"] for item in external["spec"]["data"]},
            {"maliev-legacy-secrets"},
        )
        properties = {item["remoteRef"]["property"] for item in external["spec"]["data"]}
        self.assertEqual(
            properties,
            {"legacy-jwt-public-key", "legacy-jwt-issuer", "legacy-jwt-audience"},
        )
        template = external["spec"]["target"]["template"]["data"]
        self.assertEqual(set(template), {"Jwt__PublicKey", "Jwt__Issuer", "Jwt__Audience"})
        self.assertEqual(template["Jwt__PublicKey"], "{{ .jwtPublicKey | b64enc }}")
        self.assertFalse(any("SqlServer" in value for value in template.values()))

    def test_contracts_classify_document_projection_as_dormant(self) -> None:
        secret_contract = json.loads(
            (REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json").read_text(
                encoding="utf-8"
            )
        )
        dormant = {projection["service"] for projection in secret_contract["dormantProjections"]}
        planned = {projection["service"] for projection in secret_contract["plannedProjections"]}
        self.assertIn("document", dormant)
        self.assertNotIn("document", planned)

        database_contract = json.loads(
            (
                REPO_ROOT
                / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("_legacy-document-service", database_contract["deferredGitOpsServiceResources"])
        self.assertNotIn("_legacy-document-service", database_contract["plannedGitOpsServiceResources"])


if __name__ == "__main__":
    unittest.main()
