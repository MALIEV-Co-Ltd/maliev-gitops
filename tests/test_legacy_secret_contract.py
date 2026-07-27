from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json"
LEGACY_APPS = REPO_ROOT / "3-apps"
ACTIVE_ENVIRONMENT = REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def tracked_legacy_manifests() -> list[Path]:
    paths: list[Path] = []
    for path in LEGACY_APPS.rglob("*.yaml"):
        if ".worktrees" not in path.parts:
            paths.append(path)
    for path in LEGACY_APPS.rglob("*.yml"):
        if ".worktrees" not in path.parts:
            paths.append(path)
    return paths


def remote_properties() -> dict[Path, set[str]]:
    found: dict[Path, set[str]] = {}
    pattern = re.compile(r"(?m)^\s*property:\s*(legacy-[a-z0-9-]+)\s*$")
    for path in tracked_legacy_manifests():
        matches = set(pattern.findall(path.read_text(encoding="utf-8")))
        if matches:
            found[path] = matches
    return found


class LegacySecretContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_contract()
        cls.present = set(cls.contract["presentProperties"])
        cls.pending = {
            item["name"] for item in cls.contract["pendingProperties"]
        }
        cls.properties = remote_properties()

    def test_contract_is_value_free_and_uses_one_secret_name(self) -> None:
        manager = self.contract["secretManager"]
        self.assertEqual(manager["secret"], "maliev-legacy-secrets")
        self.assertEqual(manager["payloadFormat"], "flat-json")
        self.assertTrue(manager["valuesOmitted"])
        self.assertTrue(self.contract["rules"]["workloadIdentityReplacesServiceAccountKeyFiles"])

    def test_present_properties_are_unique_and_pending_properties_are_explicit(self) -> None:
        self.assertEqual(len(self.present), len(self.contract["presentProperties"]))
        self.assertTrue(self.pending)
        self.assertTrue(self.present.isdisjoint(self.pending))
        self.assertTrue(all(item["name"].startswith("legacy-") for item in self.contract["pendingProperties"]))

    def test_every_gitops_reference_uses_the_single_secret_and_is_catalogued(self) -> None:
        catalogued = self.present | self.pending
        for path, properties in self.properties.items():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("secretKeyRef:", text, str(path))
            self.assertEqual(
                len(properties & catalogued),
                len(properties),
                f"uncatalogued legacy secret property in {path}",
            )
            self.assertNotIn("valueFrom:\n      secretKeyRef:", text)
            for document in yaml.safe_load_all(text):
                if not document or document.get("kind") != "ExternalSecret":
                    continue
                for item in document.get("spec", {}).get("data", []):
                    self.assertEqual(
                        item["remoteRef"]["key"],
                        self.contract["secretManager"]["secret"],
                        f"{path} references a second Secret Manager secret",
                    )

    def test_active_overlay_references_only_properties_already_present(self) -> None:
        active_text = ACTIVE_ENVIRONMENT.read_text(encoding="utf-8")
        self.assertIn("../../3-apps/_legacy-postgres/overlays/legacy", active_text)
        self.assertIn("../../3-apps/_legacy-redis/overlays/legacy", active_text)
        self.assertIn("../../3-apps/_legacy-country-service/overlays/legacy", active_text)

        active_services = set(
            re.findall(r"../../3-apps/(_legacy-[a-z0-9-]+)", active_text)
        )
        self.assertEqual(
            active_services,
            {"_legacy-postgres", "_legacy-redis", "_legacy-country-service"},
        )
        for path, properties in self.properties.items():
            relative_parts = path.relative_to(LEGACY_APPS).parts
            service_name = next(
                (part for part in relative_parts if part.startswith("_legacy-")),
                None,
            )
            if service_name in active_services:
                self.assertTrue(
                    properties <= self.present,
                    f"active service {service_name} references a pending property",
                )

    def test_runtime_session_values_are_not_secret_properties(self) -> None:
        forbidden = set(self.contract["rules"]["dynamicSessionValuesAreForbidden"])
        names = self.present | self.pending
        for value in forbidden:
            self.assertNotIn(value, names)


if __name__ == "__main__":
    unittest.main()
