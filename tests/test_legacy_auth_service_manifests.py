from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "3-apps/_legacy-auth-service/overlays/legacy"
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


class LegacyAuthServiceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(OVERLAY)

    def test_projection_is_dormant(self) -> None:
        active = (REPO_ROOT / ACTIVE_ENVIRONMENT).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-auth-service", active)
        self.assertTrue(self.documents)
        self.assertTrue(
            all(document["metadata"].get("namespace") == "maliev-legacy" for document in self.documents)
        )

    def test_projection_uses_only_consolidated_secret_and_keeps_refresh_sessions_fail_closed(self) -> None:
        external = self.documents[0]
        self.assertEqual(external["kind"], "ExternalSecret")
        self.assertEqual(external["spec"]["target"]["name"], "legacy-maliev-auth-runtime")
        self.assertEqual(
            {item["remoteRef"]["key"] for item in external["spec"]["data"]},
            {"maliev-legacy-secrets"},
        )
        properties = {item["remoteRef"]["property"] for item in external["spec"]["data"]}
        self.assertIn("legacy-jwt-private-key", properties)
        self.assertIn("legacy-jwt-key-id", properties)
        self.assertIn("legacy-auth-refresh-sessions-username", properties)
        self.assertIn("legacy-auth-refresh-sessions-password", properties)
        self.assertNotIn("legacy-jwt-public-key", properties)
        template = external["spec"]["target"]["template"]["data"]
        self.assertIn("Jwt__PrivateKeyPem", template)
        self.assertIn("Jwt__KeyId", template)
        self.assertNotIn("IdentityStorage__Provider", template)
        self.assertFalse(any("SqlServer" in value for value in template.values()))
        self.assertIn("ConnectionStrings__RefreshSessions", template)
        self.assertIn("Database=Auth", template["ConnectionStrings__RefreshSessions"])
        for key in (
            "ConnectionStrings__CustomerIdentity",
            "ConnectionStrings__EmployeeIdentity",
            "ConnectionStrings__RefreshSessions",
        ):
            self.assertIn("SSL Mode=Disable", template[key])
            self.assertNotIn("SSL Mode=Require", template[key])

    def test_refresh_sessions_is_a_deferred_gke_binding_not_a_local_only_connection(self) -> None:
        contract = json.loads(
            (
                REPO_ROOT
                / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
            ).read_text(encoding="utf-8")
        )
        auth = contract["services"]["Legacy.Maliev.AuthService"]
        self.assertIn("RefreshSessions", auth["connectionKeys"])
        self.assertNotIn("RefreshSessions", auth.get("localOnlyConnectionKeys", []))


if __name__ == "__main__":
    unittest.main()
