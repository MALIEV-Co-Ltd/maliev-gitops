from __future__ import annotations

import os
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-runtime-inventory.json"
WORKSPACE_ROOT = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", REPO_ROOT.parent))
PINNED_WORKFLOW = (
    "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/.github/workflows/publish-image.yml@"
    "6017816fa67f369d785ed30794f002cfd6299af7"
)


class LegacyCiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import json

        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_every_runtime_service_has_a_gated_publication_workflow(self) -> None:
        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            if not repository.is_dir():
                self.skipTest(f"Legacy workspace is not mounted: {repository}")

            workflow_path = repository / ".github/workflows/publish-image.yml"
            self.assertTrue(workflow_path.is_file(), item["service"])
            source = workflow_path.read_text(encoding="utf-8")
            documents = list(yaml.safe_load_all(source))
            self.assertEqual(len(documents), 1, item["service"])
            workflow = documents[0]
            jobs = workflow["jobs"]
            gate = jobs["deployment-gate"]

            self.assertIn("LEGACY_DEPLOY_ENABLED != 'true'", gate["if"], item["service"])
            self.assertEqual(workflow["permissions"]["id-token"], "write", item["service"])

            expected_slug = item["service"].removeprefix("Legacy.Maliev.")
            if expected_slug.endswith("Service"):
                expected_slug = expected_slug.removesuffix("Service") + "Service"
            expected_image_suffix = (
                "legacy-maliev-"
                + expected_slug.replace("Service", "-service").replace(".", "-").lower()
            )
            publish_jobs = {
                name: job for name, job in jobs.items() if name.startswith("publish")
            }
            self.assertTrue(publish_jobs, item["service"])
            for name, publish in publish_jobs.items():
                with self.subTest(service=item["service"], job=name):
                    self.assertIn("LEGACY_DEPLOY_ENABLED == 'true'", publish["if"])
                    self.assertEqual(publish["uses"], PINNED_WORKFLOW)
                    self.assertEqual(publish["with"]["context"], ".")
                    dockerfile = repository / publish["with"]["dockerfile"]
                    self.assertTrue(dockerfile.is_file(), f"missing Dockerfile for {item['service']}")
                    self.assertIn(expected_image_suffix, publish["with"]["image"])

    def test_publication_workflows_do_not_contain_secret_values(self) -> None:
        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            if not repository.is_dir():
                self.skipTest(f"Legacy workspace is not mounted: {repository}")
            source = (repository / ".github/workflows/publish-image.yml").read_text(encoding="utf-8")
            self.assertNotRegex(source, r"(?i)(password|private[-_]?key|client[-_]?secret)\s*:")
            self.assertNotIn("maliev-legacy-secrets", source)


if __name__ == "__main__":
    unittest.main()
