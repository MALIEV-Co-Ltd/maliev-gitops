from __future__ import annotations

import json
import fnmatch
import os
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT
    / "3-apps/_legacy-postgres/readiness/legacy-service-configuration-contract.json"
)
SECRET_CONTRACT_PATH = (
    REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json"
)
DATABASE_CONTRACT_PATH = (
    REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
)
RUNTIME_INVENTORY_PATH = (
    REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-runtime-inventory.json"
)
WORKSPACE_ROOT = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))

SENSITIVE_ROOTS = {
    "Authentication",
    "Brevo",
    "ConnectionStrings",
    "DataProtection",
    "GoogleIdentity",
    "GoogleMaps",
    "Jwt",
    "Recaptcha",
    "ServiceAuthentication",
    "ServiceClients",
}
CONFIGURATION_PATTERNS = (
    re.compile(r"(?:builder\.)?Configuration\s*\[\s*[\"']([^\"']+)[\"']"),
    re.compile(r"GetSection\(\s*[\"']([^\"']+)[\"']"),
    re.compile(r"GetConnectionString\(\s*[\"']([^\"']+)[\"']"),
    re.compile(r"UseSetting\(\s*[\"']([^\"']+)[\"']"),
    re.compile(r"WithEnvironment\(\s*[\"']([^\"']+)[\"']"),
    re.compile(r"connectionName\s*:\s*[\"']([^\"']+)[\"']"),
)
SKIPPED_SOURCE_PARTS = {
    ".git",
    ".worktrees",
    "bin",
    "obj",
    "node_modules",
    "Migrations",
    ".dependencies",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class LegacyServiceConfigurationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load(CONTRACT_PATH)
        cls.secret_contract = load(SECRET_CONTRACT_PATH)
        cls.database_contract = load(DATABASE_CONTRACT_PATH)
        cls.runtime_inventory = load(RUNTIME_INVENTORY_PATH)
        cls.catalogued = set(cls.secret_contract["presentProperties"])
        cls.catalogued.update(
            item["name"] for item in cls.secret_contract["pendingProperties"]
        )
        cls.classes = cls.contract["classes"]
        cls.services = {
            item["service"]: item for item in cls.contract["services"]
        }

    def test_contract_is_value_free_and_covers_every_runtime_service(self) -> None:
        self.assertTrue(self.contract["valuesOmitted"])
        expected = {
            item["service"]
            for item in self.runtime_inventory["services"]
        }
        self.assertEqual(expected, set(self.services))
        self.assertEqual(
            len(self.services),
            len(self.contract["services"]),
        )

    def test_configuration_classes_have_catalogued_properties_and_no_values(self) -> None:
        for name, definition in self.classes.items():
            self.assertNotIn("value", definition, name)
            self.assertNotIn("example", definition, name)
            self.assertNotIn("defaultValue", definition, name)
            self.assertEqual(
                len(definition["secretProperties"]),
                len(set(definition["secretProperties"])),
                name,
            )
            self.assertTrue(
                set(definition["secretProperties"]) <= self.catalogued,
                name,
            )
            self.assertEqual(
                len(definition["configurationPaths"]),
                len(set(definition["configurationPaths"])),
                name,
            )

    def test_service_projection_properties_equal_source_configuration_bindings(self) -> None:
        projections = {}
        for lifecycle in ("activeProjections", "dormantProjections", "plannedProjections"):
            for projection in self.secret_contract[lifecycle]:
                if projection["service"] in {"postgres", "redis"}:
                    continue
                self.assertNotIn(projection["service"], projections)
                projections[projection["service"]] = set(projection["properties"])

        service_projection_names = {
            service: service.rsplit(".", 1)[-1].removesuffix("Service").lower()
            for service in self.services
        }
        self.assertEqual(set(service_projection_names.values()), set(projections))
        for service, binding in self.services.items():
            declared = set()
            for class_name in binding["classes"]:
                self.assertIn(class_name, self.classes, service)
                declared.update(self.classes[class_name]["secretProperties"])
            for connection in binding["connections"]:
                database = connection["database"]
                credential = next(
                    item
                    for item in self.secret_contract["rules"]["databaseCredentialProperties"]
                    if item["database"] == database
                )
                declared.update(
                    (credential["usernameProperty"], credential["passwordProperty"])
                )
            projection_name = service_projection_names[service]
            self.assertEqual(projections[projection_name], declared, service)

    def test_database_connection_bindings_match_database_contract(self) -> None:
        for service, binding in self.services.items():
            expected = set(
                self.database_contract["services"][service].get("connectionKeys", [])
            )
            expected.update(
                self.database_contract["services"][service].get(
                    "localOnlyConnectionKeys", []
                )
            )
            actual = {item["name"] for item in binding["connections"]}
            self.assertEqual(expected, actual, service)
            for connection in binding["connections"]:
                if connection["database"] == "Auth":
                    self.assertEqual(connection.get("lifecycle"), "deferred")
                else:
                    self.assertIn(connection["database"], self.database_contract["databases"])
                self.assertTrue(connection["name"])

    def test_non_secret_paths_are_not_secret_shaped(self) -> None:
        forbidden_fragments = (
            "password",
            "secret",
            "apikey",
            "api-key",
            "privatekey",
            "private-key",
            "certificatepfx",
            "certificate-password",
        )
        for service, binding in self.services.items():
            for path in binding["nonSecretConfigurationPaths"]:
                lowered = path.lower().replace(":", "")
                self.assertFalse(
                    any(fragment in lowered for fragment in forbidden_fragments),
                    f"secret-shaped non-secret path in {service}: {path}",
                )

    def test_source_forbidden_patterns_are_explicit_and_value_free(self) -> None:
        self.assertEqual(
            self.contract["forbiddenSourcePatterns"],
            [
                "legacy SQL Server connection strings",
                "service-account key files",
                "access tokens",
                "refresh tokens",
                "cookies",
                "user-session identifiers",
            ],
        )
        self.assertIn(
            "Host, port, database and pool settings are non-secret runtime configuration; only the username/password components are projected from maliev-legacy-secrets.",
            self.contract["databaseConnectionClass"]["note"],
        )

    def test_mounted_legacy_source_sensitive_paths_are_classified(self) -> None:
        """Audit real mounted Legacy source without printing configuration values."""

        if "MALIEV_WORKSPACE_ROOT" not in os.environ:
            self.skipTest(f"Legacy workspace is not mounted: {WORKSPACE_ROOT}")
        if not WORKSPACE_ROOT.is_dir():
            self.fail(f"Legacy workspace is not mounted: {WORKSPACE_ROOT}")

        for service, binding in self.services.items():
            repository = WORKSPACE_ROOT / service
            if not repository.is_dir():
                self.fail(f"Missing mounted Legacy repository: {repository}")

            known_paths = set()
            for class_name in binding["classes"]:
                known_paths.update(self.classes[class_name]["configurationPaths"])
            known_paths.update(
                f"ConnectionStrings:{connection['name']}"
                for connection in binding["connections"]
            )
            if "redis" in binding["classes"]:
                known_paths.add("ConnectionStrings:redis")

            non_secret_paths = set(binding["nonSecretConfigurationPaths"])
            observed = set()
            for path in repository.rglob("*"):
                if not path.is_file() or SKIPPED_SOURCE_PARTS.intersection(path.parts):
                    continue
                if any(part.endswith(".Tests") for part in path.parts):
                    continue
                if path.suffix == ".json" and path.name != "appsettings.json":
                    continue
                if path.suffix not in {".cs", ".json"}:
                    continue

                text = path.read_text(encoding="utf-8", errors="ignore")
                for pattern in CONFIGURATION_PATTERNS:
                    for match in pattern.finditer(text):
                        candidate = match.group(1).replace("__", ":")
                        if ":" not in candidate:
                            continue
                        if candidate.startswith("ConnectionStrings:"):
                            observed.add(candidate)
                            continue
                        if candidate.split(":", 1)[0] in SENSITIVE_ROOTS:
                            observed.add(candidate)

                if path.name == "appsettings.json":
                    try:
                        document = json.loads(text)
                    except json.JSONDecodeError:
                        continue

                    def walk(value: object, prefix: str = "") -> None:
                        if isinstance(value, dict):
                            for key, child in value.items():
                                current = f"{prefix}:{key}" if prefix else key
                                if ":" in current and current.split(":", 1)[0] in SENSITIVE_ROOTS:
                                    observed.add(current)
                                walk(child, current)
                        elif isinstance(value, list):
                            for child in value:
                                walk(child, prefix)

                    walk(document)

            unknown = sorted(
                path
                for path in observed
                if path not in known_paths
                and not any(fnmatch.fnmatch(path, pattern) for pattern in non_secret_paths)
            )
            self.assertEqual([], unknown, service)


if __name__ == "__main__":
    unittest.main()
