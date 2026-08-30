from __future__ import annotations

import os
import re
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

    @staticmethod
    def _publication_workflows(repository: Path) -> list[Path]:
        workflow_directory = repository / ".github/workflows"
        return sorted(
            [*workflow_directory.glob("publish*.yml"), *workflow_directory.glob("publish*.yaml")]
        )

    @staticmethod
    def _workflow_files(repository: Path) -> list[Path]:
        workflow_directory = repository / ".github/workflows"
        return sorted(
            [*workflow_directory.glob("*.yml"), *workflow_directory.glob("*.yaml")]
        )

    def _require_repository(self, repository: Path) -> None:
        if repository.is_dir():
            return
        message = f"Legacy workspace is not mounted: {repository}"
        if "MALIEV_WORKSPACE_ROOT" in os.environ:
            self.fail(message)
        self.skipTest(message)

    def test_every_runtime_service_has_a_gated_publication_workflow(self) -> None:
        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            self._require_repository(repository)

            workflow_path = repository / ".github/workflows/publish-image.yml"
            self.assertTrue(workflow_path.is_file(), item["service"])
            source = workflow_path.read_text(encoding="utf-8")
            documents = list(yaml.safe_load_all(source))
            self.assertEqual(len(documents), 1, item["service"])
            workflow = documents[0]
            jobs = workflow["jobs"]
            gate = jobs.get("deployment-gate")
            if gate is not None:
                self.assertIn("LEGACY_DEPLOY_ENABLED != 'true'", gate["if"], item["service"])

            publication_permissions = [
                job.get("permissions", {})
                for name, job in jobs.items()
                if name.startswith("publish")
            ]
            self.assertTrue(
                workflow.get("permissions", {}).get("id-token") == "write"
                or any(permissions.get("id-token") == "write" for permissions in publication_permissions),
                item["service"],
            )

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

    def test_gitops_validation_discovers_every_legacy_contract_module(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests -p 'test_legacy*.py' -v", workflow)
        self.assertIn("python -m unittest tests.test_secret_contract_validator -v", workflow)
        self.assertIn("MALIEV-Co-Ltd/Legacy.Maliev.AppHost.git", workflow)
        self.assertIn('"$workspace/Legacy.Maliev.AppHost"', workflow)

    def test_publication_workflows_do_not_contain_secret_values(self) -> None:
        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            self._require_repository(repository)
            for workflow_path in self._publication_workflows(repository):
                source = workflow_path.read_text(encoding="utf-8")
                self.assertNotRegex(
                    source,
                    r"(?i)(password|private[-_]?key|client[-_]?secret)\s*:",
                    str(workflow_path),
                )
                self.assertNotIn("maliev-legacy-secrets", source, str(workflow_path))

    def test_every_publication_entrypoint_is_fail_closed_and_pinned(self) -> None:
        """Cover secondary image workflows such as Auth identity migration and Intranet BFF."""

        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            self._require_repository(repository)

            workflow_paths = self._publication_workflows(repository)
            self.assertTrue(workflow_paths, item["service"])
            for workflow_path in workflow_paths:
                with self.subTest(service=item["service"], workflow=workflow_path.name):
                    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
                    jobs = workflow["jobs"]
                    gate = jobs.get("deployment-gate")
                    if gate is not None:
                        self.assertIn("LEGACY_DEPLOY_ENABLED != 'true'", gate["if"])

                    publication_jobs = {
                        name: job
                        for name, job in jobs.items()
                        if name.startswith("publish")
                    }
                    self.assertTrue(publication_jobs)
                    for name, job in publication_jobs.items():
                        with self.subTest(job=name):
                            condition = job.get("if", "")
                            self.assertIn("LEGACY_DEPLOY_ENABLED == 'true'", condition)
                            if "inputs.confirm-publication" in condition:
                                self.assertIn("inputs.confirm-publication == true", condition)
                            else:
                                self.assertEqual(condition, "vars.LEGACY_DEPLOY_ENABLED == 'true'")
                            permissions = job.get("permissions", workflow.get("permissions", {}))
                            self.assertEqual(permissions.get("id-token"), "write")
                            self.assertEqual(job.get("uses"), PINNED_WORKFLOW)
                            inputs = job.get("with", {})
                            self.assertEqual(inputs.get("context"), ".")
                            self.assertRegex(
                                inputs.get("image", ""),
                                r"^\$\{\{ vars\.LEGACY_ARTIFACT_REGISTRY \}\}/legacy-maliev-[a-z0-9-]+$",
                            )
                            dockerfile = repository / inputs.get("dockerfile", "")
                            self.assertTrue(dockerfile.is_file(), str(dockerfile))

    def test_every_legacy_workflow_has_no_direct_publication_or_runtime_secret_access(self) -> None:
        """Publication must go through the pinned reusable workflow, never caller shell code."""

        forbidden_fragments = (
            "docker push",
            "gcloud auth configure-docker",
            "kustomize edit set image",
            "gh pr create",
            "git clone https://x-access-token:",
            "gcloud secrets versions access",
            "maliev-legacy-secrets",
            "maliev-prod-",
            "${{ secrets.",
        )

        for item in self.inventory["services"]:
            repository = WORKSPACE_ROOT / item["repository"]
            self._require_repository(repository)

            workflow_paths = self._workflow_files(repository)
            self.assertTrue(workflow_paths, item["service"])
            for workflow_path in workflow_paths:
                source = workflow_path.read_text(encoding="utf-8")
                with self.subTest(service=item["service"], workflow=workflow_path.name):
                    for fragment in forbidden_fragments:
                        self.assertNotIn(fragment, source, fragment)

                    if re.search(r"(?m)^\s+id-token:\s*write\s*$", source):
                        self.assertTrue(
                            workflow_path.name.startswith("publish"),
                            f"OIDC publication permission escaped publish workflow: {workflow_path}",
                        )


if __name__ == "__main__":
    unittest.main()
