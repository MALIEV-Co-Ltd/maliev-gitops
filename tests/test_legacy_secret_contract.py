from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json"
DATABASE_CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
RUNTIME_INVENTORY_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-runtime-inventory.json"
LEGACY_APPS = REPO_ROOT / "3-apps"
ACTIVE_ENVIRONMENT = REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"
MIGRATED_ROOT = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))
APPHOST_SOURCE = (
    MIGRATED_ROOT
    / "Legacy.Maliev.AppHost/Legacy.Maliev.AppHost/AppHost.cs"
)


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def load_database_contract() -> dict:
    return json.loads(DATABASE_CONTRACT_PATH.read_text(encoding="utf-8"))


def load_runtime_inventory() -> dict:
    return json.loads(RUNTIME_INVENTORY_PATH.read_text(encoding="utf-8"))


def migrated_configuration_files() -> list[Path]:
    inventory = load_runtime_inventory()
    paths: list[Path] = []
    for service in inventory["services"]:
        repository = MIGRATED_ROOT / service["repository"]
        if not repository.is_dir():
            continue
        for pattern in ("appsettings*.json", "*.yaml", "*.yml", "Dockerfile*"):
            paths.extend(
                path
                for path in repository.rglob(pattern)
                if ".worktrees" not in path.parts
                and "bin" not in path.parts
                and "obj" not in path.parts
                and "node_modules" not in path.parts
            )
    return sorted(set(paths))


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

    def test_non_secret_storage_auth_and_source_credential_exclusions_are_explicit(self) -> None:
        rules = self.contract["rules"]
        self.assertIn(
            "gke-workload-identity-for-google-cloud-storage",
            rules["nonSecretRuntimeConfiguration"],
        )
        self.assertIn(
            "google-cloud-storage-bucket-and-object-names",
            rules["nonSecretRuntimeConfiguration"],
        )
        self.assertEqual(
            rules["sourceOnlyCredentialsMustNotBeCopied"],
            [
                "legacy-sql-server-connection-strings",
                "legacy-source-service-account-key-files",
            ],
        )

    def test_service_credentials_pair_raw_values_with_auth_hash_projections(self) -> None:
        catalogued = self.present | self.pending
        pairs = self.contract["rules"]["pairedServiceCredentialProperties"]
        self.assertEqual(
            {pair["clientId"] for pair in pairs},
            {"legacy-web", "legacy-intranet", "legacy-quotation", "legacy-accounting"},
        )
        self.assertEqual(
            len(pairs),
            len({pair["clientId"] for pair in pairs}),
        )
        for pair in pairs:
            self.assertIn(pair["rawProperty"], catalogued, pair["clientId"])
            self.assertIn(pair["hashProperty"], catalogued, pair["clientId"])
            self.assertTrue(pair["rawProperty"].endswith("-service-client-secret"))
            self.assertTrue(pair["hashProperty"].endswith("-secret-sha256"))

        auth = next(item for item in self.contract["dormantProjections"] if item["service"] == "auth")
        auth_properties = set(auth["properties"])
        for pair in pairs:
            self.assertIn(pair["hashProperty"], auth_properties, pair["clientId"])

    def test_database_secret_bindings_cover_active_and_deferred_databases(self) -> None:
        database_contract = load_database_contract()
        bindings = self.contract["rules"]["databaseCredentialProperties"]
        self.assertEqual(
            len(bindings),
            len({binding["database"] for binding in bindings}),
        )

        active = {
            database["database"]
            for database in bindings
            if database["lifecycle"] == "active"
        }
        self.assertEqual(active, set(database_contract["databases"]))
        self.assertEqual(
            {database["database"] for database in bindings if database["lifecycle"] == "deferred"},
            set(),
        )

        catalogued = self.present | self.pending
        for binding in bindings:
            self.assertIn(binding["usernameProperty"], catalogued, binding["database"])
            self.assertIn(binding["passwordProperty"], catalogued, binding["database"])
            self.assertTrue(binding["usernameProperty"].endswith("-username"))
            self.assertTrue(binding["passwordProperty"].endswith("-password"))

    def test_database_secret_bindings_are_value_free(self) -> None:
        for binding in self.contract["rules"]["databaseCredentialProperties"]:
            self.assertNotIn("value", binding)
            self.assertNotIn("connection", binding)
            self.assertNotIn("password", binding)
            self.assertNotIn("username", binding)

    def test_apphost_gke_secret_references_are_catalogued(self) -> None:
        if not APPHOST_SOURCE.is_file():
            self.skipTest(f"Legacy AppHost is not mounted: {APPHOST_SOURCE}")

        source = APPHOST_SOURCE.read_text(encoding="utf-8")
        properties = set(
            re.findall(
                r"(?:RequireGkeSecret|SetGkeAspireParameter)\s*\(\s*gkeSecrets!\s*,\s*\"(legacy-[a-z0-9-]+)\"",
                source,
            )
        )
        self.assertTrue(properties)
        self.assertTrue(
            properties <= (self.present | self.pending),
            f"AppHost references uncatalogued secret properties: {sorted(properties - (self.present | self.pending))}",
        )

    def test_every_pending_property_has_a_lifecycle_destination(self) -> None:
        projected: set[str] = set()
        for lifecycle in ("activeProjections", "dormantProjections", "plannedProjections"):
            for projection in self.contract[lifecycle]:
                if isinstance(projection["properties"], list):
                    projected.update(projection["properties"])
        for pair in self.contract["rules"]["pairedServiceCredentialProperties"]:
            projected.update((pair["rawProperty"], pair["hashProperty"]))

        self.assertEqual(self.pending, self.pending & projected)

    def test_present_properties_are_unique_and_pending_properties_are_explicit(self) -> None:
        self.assertEqual(len(self.present), len(self.contract["presentProperties"]))
        self.assertTrue(self.pending)
        self.assertTrue(self.present.isdisjoint(self.pending))
        self.assertTrue(all(item["name"].startswith("legacy-") for item in self.contract["pendingProperties"]))

    def test_every_legacy_application_has_one_lifecycle_projection(self) -> None:
        database_contract = load_database_contract()
        expected = set()
        for service_name in database_contract["services"]:
            short_name = service_name.rsplit(".", 1)[-1]
            expected.add(short_name.removesuffix("Service").lower())

        projections = (
            self.contract["activeProjections"]
            + self.contract["dormantProjections"]
            + self.contract["plannedProjections"]
        )
        by_service = {}
        for projection in projections:
            self.assertNotIn(
                projection["service"],
                by_service,
                f"duplicate lifecycle projection for {projection['service']}",
            )
            by_service[projection["service"]] = projection

        self.assertEqual(expected, set(by_service) - {"postgres", "redis"})

    def test_planned_and_dormant_projection_properties_are_catalogued(self) -> None:
        catalogued = self.present | self.pending
        for lifecycle in ("dormantProjections", "plannedProjections"):
            for projection in self.contract[lifecycle]:
                properties = set(projection["properties"])
                self.assertTrue(properties <= catalogued, projection["service"])
                self.assertTrue(
                    projection["targetSecret"].startswith("legacy-maliev-"),
                    projection["service"],
                )

    def test_planned_projection_lifecycle_matches_planned_gitops_resources(self) -> None:
        database_contract = load_database_contract()
        planned_resources = {
            resource.removeprefix("_legacy-").removesuffix("-service")
            for resource in database_contract["plannedGitOpsServiceResources"]
        }
        planned_projections = {
            projection["service"] for projection in self.contract["plannedProjections"]
        }
        self.assertEqual(planned_resources, planned_projections)

    def test_active_projection_properties_are_already_present(self) -> None:
        for projection in self.contract["activeProjections"]:
            if isinstance(projection["properties"], list):
                self.assertTrue(
                    set(projection["properties"]) <= self.present,
                    projection["service"],
                )

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

    def test_migrated_configuration_does_not_embed_source_only_credentials(self) -> None:
        source_only_patterns = (
            re.compile(
                r"(?is)\b(?:server|data\s+source)\s*=.*?;\s*"
                r"(?:initial\s+catalog|database)\s*=.*?;"
            ),
            re.compile(r"(?is)\b(?:user\s+id|uid)\s*=.*?;\s*password\s*="),
            re.compile(r"(?im)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
            re.compile(r'(?im)[\"\']private_key[\"\']\s*:'),
        )
        findings: list[str] = []
        for path in migrated_configuration_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in source_only_patterns):
                findings.append(str(path))

        self.assertEqual(
            findings,
            [],
            "migrated runtime configuration embeds source-only SQL Server/key material: "
            + ", ".join(findings),
        )


if __name__ == "__main__":
    unittest.main()
