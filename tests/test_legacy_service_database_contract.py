from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
DATABASE_MANIFEST = REPO_ROOT / "3-apps/_legacy-postgres/base/databases.yaml"
ACTIVE_KUSTOMIZATION = REPO_ROOT / "2-environments/4-legacy/kustomization.yaml"
COUNTRY_SECRET = REPO_ROOT / "3-apps/_legacy-country-service/base/external-secret.yaml"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def parse_database_documents(text: str) -> dict[str, dict[str, str]]:
    """Parse the small, regular CNPG Database manifest without requiring PyYAML."""

    databases: dict[str, dict[str, str]] = {}
    for document in text.split("\n---"):
        if "kind: Database" not in document:
            continue
        name = re.search(r"(?m)^\s*name:\s*([^\s#]+)\s*$", document)
        spec_name = re.search(r"(?m)^\s*name:\s*([^\s#]+)\s*$", document[document.find("spec:") :])
        owner = re.search(r"(?m)^\s*owner:\s*([^\s#]+)\s*$", document)
        cluster = re.search(r"(?m)^\s*name:\s*([^\s#]+)\s*$", document[document.find("cluster:") :])
        reclaim = re.search(r"(?m)^\s*databaseReclaimPolicy:\s*([^\s#]+)\s*$", document)
        if not all((name, spec_name, owner, cluster, reclaim)):
            raise AssertionError(f"incomplete CNPG Database document: {document[:120]!r}")
        databases[spec_name.group(1)] = {
            "resource": name.group(1),
            "owner": owner.group(1),
            "cluster": cluster.group(1),
            "reclaim": reclaim.group(1),
        }
    return databases


def tracked_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [repo / value for value in result.stdout.splitlines()]


def source_text(repo: Path) -> str:
    allowed = {".cs", ".csproj", ".json", ".props", ".targets"}
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in tracked_files(repo)
        if path.suffix.lower() in allowed
    )


class LegacyServiceDatabaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_contract()
        cls.databases = parse_database_documents(DATABASE_MANIFEST.read_text(encoding="utf-8"))

    def test_cnpg_database_resources_preserve_every_active_name_and_owner(self) -> None:
        expected = self.contract["databases"]
        self.assertEqual(set(self.databases), set(expected))
        for database, details in expected.items():
            actual = self.databases[database]
            self.assertEqual(details["owner"], actual["owner"], database)
            self.assertEqual("legacy-postgres-main", actual["cluster"], database)
            self.assertEqual("retain", actual["reclaim"], database)

    def test_runtime_bindings_and_retained_source_databases_account_for_all_names(self) -> None:
        expected = set(self.contract["databases"])
        runtime = {
            database
            for service in self.contract["services"].values()
            for database in service["databases"]
        }
        source_only = set(self.contract["sourceOnlyDatabases"])
        self.assertEqual(expected, runtime | source_only)
        self.assertTrue(runtime.isdisjoint(source_only))
        for database in source_only:
            self.assertIsNone(self.contract["databases"][database]["binding"])

    def test_active_overlay_exposes_only_explicitly_active_service_resources(self) -> None:
        active = ACTIVE_KUSTOMIZATION.read_text(encoding="utf-8")
        self.assertIn("../../3-apps/_legacy-postgres/overlays/legacy", active)
        for resource in self.contract["activeGitOpsServiceResources"]:
            self.assertIn(resource, active)
        for resource in self.contract["deferredGitOpsServiceResources"]:
            self.assertNotIn(resource, active)
        self.assertNotIn("../../3-apps/_legacy-redis/overlays/legacy", active)
        self.assertNotIn("../../3-apps/_legacy-country-service/overlays/legacy", active)

    def test_gitops_resource_states_match_directories_and_are_disjoint(self) -> None:
        states = {
            state: set(self.contract.get(state, []))
            for state in (
                "activeGitOpsServiceResources",
                "deferredGitOpsServiceResources",
                "plannedGitOpsServiceResources",
            )
        }
        all_resources = set().union(*states.values())
        self.assertEqual(
            sum(len(resources) for resources in states.values()),
            len(all_resources),
            "a GitOps service resource must have exactly one lifecycle state",
        )
        for state in ("activeGitOpsServiceResources", "deferredGitOpsServiceResources"):
            for resource in states[state]:
                self.assertTrue(
                    (REPO_ROOT / "3-apps" / resource).is_dir(),
                    f"{state} claims a missing GitOps directory: {resource}",
                )
        for resource in states["plannedGitOpsServiceResources"]:
            self.assertFalse(
                (REPO_ROOT / "3-apps" / resource).exists(),
                f"planned resource now exists but was not moved to deferred/active: {resource}",
            )

    def test_active_country_secret_uses_the_legacy_pooler_and_exact_database(self) -> None:
        secret = COUNTRY_SECRET.read_text(encoding="utf-8")
        self.assertIn("Host=legacy-postgres-pooler-rw;Port=5432;Database=Country;", secret)
        self.assertIn("legacy-postgres-country-username", secret)
        self.assertIn("legacy-postgres-country-password", secret)
        self.assertNotIn("legacy-postgres-main-1", secret)

    def test_database_services_use_legacy_defaults_and_postgres_contracts_when_workspace_is_available(self) -> None:
        workspace = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))
        missing = [
            details["repository"]
            for details in self.contract["services"].values()
            if not (workspace / details["repository"]).exists()
        ]
        if missing:
            self.skipTest(f"local Legacy workspace is not mounted; missing {', '.join(missing)}")

        for service_name, details in self.contract["services"].items():
            repository = workspace / details["repository"]
            text = source_text(repository)
            if details["databases"]:
                self.assertIn("UseNpgsql", text, service_name)
                self.assertIn(details["testPackage"], text, service_name)
                for key in details["connectionKeys"]:
                    self.assertIn(key, text, f"{service_name} is missing connection key {key}")
            self.assertNotIn(
                r"Maliev.Aspire\Maliev.Aspire.ServiceDefaults",
                text,
                f"{service_name} still references current-generation ServiceDefaults",
            )

    def test_service_repository_references_are_canonical_legacy_repositories(self) -> None:
        workspace = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))
        for service_name, details in self.contract["services"].items():
            repository = details["repository"]
            self.assertFalse(
                re.search(r"(?:main-merge|validation|parity|owner|2026\d{4})", repository, re.IGNORECASE),
                f"{service_name} points at a snapshot/worktree instead of a canonical repository",
            )
            if workspace.exists():
                self.assertTrue(
                    (workspace / repository).is_dir(),
                    f"{service_name} points at a missing canonical repository: {repository}",
                )

    def test_non_database_repositories_do_not_claim_database_bindings(self) -> None:
        services = self.contract["services"]
        for repository in self.contract["nonDatabaseRepositories"]:
            self.assertNotIn(repository, services)


if __name__ == "__main__":
    unittest.main()
