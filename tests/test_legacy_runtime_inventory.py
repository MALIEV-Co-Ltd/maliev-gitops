from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-runtime-inventory.json"
DATABASE_CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-service-database-contract.json"
WORKSPACE_ROOT = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))


class LegacyRuntimeInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        cls.database_contract = json.loads(DATABASE_CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_inventory_is_value_free_and_namespace_scoped(self) -> None:
        self.assertEqual(self.inventory["namespace"], "maliev-legacy")
        self.assertEqual(self.inventory["containerPort"], 8080)
        self.assertEqual(
            self.inventory["healthPathSuffixes"],
            {"liveness": "/liveness", "readiness": "/readiness"},
        )
        serialized = json.dumps(self.inventory)
        self.assertNotRegex(serialized, r"(?i)(password|token|secret|api[-_]?key|connectionstring)")

    def test_inventory_covers_every_database_contract_service_once(self) -> None:
        services = self.inventory["services"]
        self.assertEqual(len(services), len({item["service"] for item in services}))
        self.assertEqual(
            {item["service"] for item in services},
            set(self.database_contract["services"]),
        )
        self.assertEqual(
            {item["repository"] for item in services},
            {details["repository"] for details in self.database_contract["services"].values()},
        )

    def test_inventory_lifecycle_matches_gitops_service_resource_contract(self) -> None:
        by_resource = {item["gitOpsResource"]: item for item in self.inventory["services"]}
        expected = {
            resource: "active"
            for resource in self.database_contract["activeGitOpsServiceResources"]
        }
        expected.update(
            {resource: "deferred" for resource in self.database_contract["deferredGitOpsServiceResources"]}
        )
        expected.update(
            {resource: "planned" for resource in self.database_contract["plannedGitOpsServiceResources"]}
        )
        self.assertEqual(set(by_resource), set(expected))
        self.assertEqual(
            {resource: item["lifecycle"] for resource, item in by_resource.items()},
            expected,
        )

    def test_migrated_programs_declare_every_recorded_health_prefix(self) -> None:
        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            if not repository.is_dir():
                self.skipTest(f"Legacy workspace is not mounted: {repository}")

            source = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in repository.rglob("*.cs")
                if "bin" not in path.parts
                and "obj" not in path.parts
                and ".worktrees" not in path.parts
            )
            for prefix in item["healthPrefixes"]:
                self.assertRegex(
                    source,
                    rf'MapDefaultEndpoints\(\s*"{re.escape(prefix)}"\s*\)',
                    f"{item['service']} is missing the recorded {prefix} health surface",
                )


if __name__ == "__main__":
    unittest.main()
