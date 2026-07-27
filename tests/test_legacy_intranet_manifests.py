from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "3-apps/_legacy-intranet/overlays/legacy"
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


class LegacyIntranetManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(OVERLAY)

    def test_projection_is_dormant_and_namespaced(self) -> None:
        active = (REPO_ROOT / ACTIVE_ENVIRONMENT).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-intranet", active)
        self.assertTrue(
            all(document["metadata"].get("namespace") == "maliev-legacy" for document in self.documents)
        )

    def test_projection_maps_single_secret_to_bff_and_compatibility_runtime(self) -> None:
        external = self.documents[0]
        self.assertEqual(external["kind"], "ExternalSecret")
        self.assertEqual(external["spec"]["target"]["name"], "legacy-maliev-intranet-runtime")
        self.assertEqual(
            {item["remoteRef"]["key"] for item in external["spec"]["data"]},
            {"maliev-legacy-secrets"},
        )
        properties = {item["remoteRef"]["property"] for item in external["spec"]["data"]}
        self.assertIn("legacy-intranet-google-maps-browser-api-key", properties)
        self.assertIn("legacy-google-identity-client-id", properties)
        template = external["spec"]["target"]["template"]["data"]
        self.assertIn("ConnectionStrings__redis", template)
        self.assertIn("GoogleMaps__BrowserApiKey", template)
        self.assertNotIn("Jwt__PrivateKeyPem", template)


if __name__ == "__main__":
    unittest.main()
