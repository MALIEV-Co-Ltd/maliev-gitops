#!/usr/bin/env python3
"""Adversarial tests for the SearchService GitOps projection policy."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY_ROOT / "scripts" / "check-search-service-secret-projection.py"
SPEC = importlib.util.spec_from_file_location("search_projection_policy", POLICY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load policy module from {POLICY_PATH}")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class SearchProjectionPolicyTests(unittest.TestCase):
    """Exercise negative paths against isolated manifest fixtures."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.original_root = POLICY.ROOT
        self.original_search_root = POLICY.SEARCH_ROOT
        POLICY.ROOT = self.root
        POLICY.SEARCH_ROOT = self.root / "3-apps" / "maliev-search-service"

    def tearDown(self) -> None:
        POLICY.ROOT = self.original_root
        POLICY.SEARCH_ROOT = self.original_search_root
        self.temporary_directory.cleanup()

    def copy_search_manifests(self) -> None:
        """Copy the current Search manifests and shared empty transformer."""
        shutil.copytree(
            REPOSITORY_ROOT / "3-apps" / "maliev-search-service",
            self.root / "3-apps" / "maliev-search-service",
        )
        common = self.root / "3-apps" / "_common"
        common.mkdir(parents=True)
        shutil.copy2(
            REPOSITORY_ROOT / "3-apps" / "_common" / "kustomization.yaml",
            common / "kustomization.yaml",
        )

    def copy_disabled_applications(self) -> None:
        """Copy only the exact disabled Search Application contracts."""
        for folder in ("dev", "staging", "prod"):
            destination = (
                self.root / "argocd" / "environments" / "_disabled_apps" / folder
            )
            destination.mkdir(parents=True)
            shutil.copy2(
                REPOSITORY_ROOT
                / "argocd"
                / "environments"
                / "_disabled_apps"
                / folder
                / "maliev-search-service.yaml",
                destination / "maliev-search-service.yaml",
            )

    def write_application(
        self,
        path: Path,
        name: str,
        source_path: str,
        repository_url: str = POLICY.GITOPS_REPOSITORY_URL,
    ) -> None:
        """Write a minimal static Argo Application fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "Application",
                    "metadata": {"name": name},
                    "spec": {
                        "source": {
                            "repoURL": repository_url,
                            "path": source_path,
                        }
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_broad_env_from_and_data_from_are_rejected(self) -> None:
        """Broad shared and service secret bundles must remain impossible."""
        self.copy_search_manifests()
        deployment_path = POLICY.SEARCH_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["envFrom"] = [
            {"secretRef": {"name": "maliev-shared-secrets"}},
            {"secretRef": {"name": "maliev-search-service-secrets"}},
        ]
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        secret_path = POLICY.SEARCH_ROOT / "base" / "service-secrets.yaml"
        external_secret = yaml.safe_load(secret_path.read_text(encoding="utf-8"))
        external_secret["spec"].pop("data")
        external_secret["spec"]["dataFrom"] = [
            {"extract": {"key": "maliev-prod-search-service-config"}}
        ]
        secret_path.write_text(
            yaml.safe_dump(external_secret, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_search_overlay("production")

        self.assertTrue(any("must not use envFrom" in error for error in errors))
        self.assertTrue(any("forbidden SearchService projection" in error for error in errors))
        self.assertTrue(any("exact object contract" in error for error in errors))

    def test_helper_container_and_secret_volume_are_rejected(self) -> None:
        """Alternate pod secret channels must not bypass the main container allowlist."""
        self.copy_search_manifests()
        deployment_path = POLICY.SEARCH_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        pod_spec = deployment["spec"]["template"]["spec"]
        pod_spec["containers"].append(
            {
                "name": "helper",
                "image": "example.invalid/helper",
                "envFrom": [{"secretRef": {"name": "maliev-shared-secrets"}}],
            }
        )
        pod_spec["volumes"] = [
            {"name": "shared", "secret": {"secretName": "maliev-shared-secrets"}}
        ]
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_search_overlay("production")

        self.assertTrue(any("pod containers do not match" in error for error in errors))
        self.assertTrue(any("pod volumes are not allowlisted" in error for error in errors))
        self.assertTrue(any("forbidden SearchService projection" in error for error in errors))

    def test_external_secret_metadata_and_mapping_drift_are_rejected(self) -> None:
        """The complete ExternalSecret object is an allowlist, not a partial check."""
        self.copy_search_manifests()
        secret_path = POLICY.SEARCH_ROOT / "base" / "service-secrets.yaml"
        external_secret = yaml.safe_load(secret_path.read_text(encoding="utf-8"))
        external_secret["metadata"]["annotations"] = {"unreviewed": "true"}
        external_secret["spec"]["data"][0]["remoteRef"]["property"] = "Jwt__PrivateKey"
        secret_path.write_text(
            yaml.safe_dump(external_secret, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_search_overlay("production")

        self.assertTrue(any("exact object contract" in error for error in errors))

    def test_service_account_token_projection_is_rejected(self) -> None:
        """SearchService does not use the Kubernetes API and must not receive its token."""
        self.copy_search_manifests()
        deployment_path = POLICY.SEARCH_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_search_overlay("production")

        self.assertTrue(any("service account token" in error for error in errors))

    def test_equivalent_repository_url_raw_child_is_rejected(self) -> None:
        """The no-.git repository spelling must still receive local render inspection."""
        self.copy_disabled_applications()
        self.write_application(
            self.root / "argocd" / "environments" / "dev" / "root.yaml",
            "root",
            "raw-root",
            "https://github.com/MALIEV-Co-Ltd/maliev-gitops",
        )
        self.write_application(
            self.root / "raw-root" / "child.yaml",
            "maliev-search-service-child",
            "3-apps/maliev-search-service/overlays/development",
        )

        errors = POLICY.validate_search_applications_remain_disabled()

        self.assertTrue(
            any("Application', 'maliev-search-service-child" in error for error in errors)
        )

    def test_rendered_child_application_source_is_traversed_recursively(self) -> None:
        """Every same-repository child source must be rendered until the graph closes."""
        self.copy_disabled_applications()
        self.write_application(
            self.root / "argocd" / "environments" / "dev" / "root.yaml",
            "root",
            "raw-root",
        )
        self.write_application(
            self.root / "raw-root" / "child.yaml",
            "generic-child",
            "environment-root",
            "https://github.com/MALIEV-Co-Ltd/maliev-gitops",
        )
        environment = self.root / "environment-root"
        nested = environment / "nested"
        nested.mkdir(parents=True)
        (environment / "kustomization.yaml").write_text(
            "resources:\n  - nested\n", encoding="utf-8"
        )
        (nested / "kustomization.yaml").write_text(
            "resources:\n  - deployment.yaml\n", encoding="utf-8"
        )
        (nested / "deployment.yaml").write_text(
            """apiVersion: apps/v1
kind: Deployment
metadata:
  name: maliev-search-service
spec:
  selector:
    matchLabels:
      app: search
  template:
    metadata:
      labels:
        app: search
    spec:
      containers:
        - name: search
          image: example.invalid/search
""",
            encoding="utf-8",
        )

        errors = POLICY.validate_search_applications_remain_disabled()

        self.assertTrue(
            any("Deployment', 'maliev-search-service" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
