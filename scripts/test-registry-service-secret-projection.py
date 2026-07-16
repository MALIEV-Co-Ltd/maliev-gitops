#!/usr/bin/env python3
"""Adversarial tests for the RegistryService GitOps projection policy."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY_ROOT / "scripts" / "check-registry-service-secret-projection.py"
SPEC = importlib.util.spec_from_file_location("registry_projection_policy", POLICY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load policy module from {POLICY_PATH}")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class RegistryProjectionPolicyTests(unittest.TestCase):
    """Exercise negative paths against isolated manifest fixtures."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.original_root = POLICY.ROOT
        self.original_registry_root = POLICY.REGISTRY_ROOT
        POLICY.ROOT = self.root
        POLICY.REGISTRY_ROOT = self.root / "3-apps" / "maliev-registry-service"

    def tearDown(self) -> None:
        POLICY.ROOT = self.original_root
        POLICY.REGISTRY_ROOT = self.original_registry_root
        self.temporary_directory.cleanup()

    def copy_registry_manifests(self) -> None:
        """Copy the current Registry manifests and shared empty transformer."""
        shutil.copytree(
            REPOSITORY_ROOT / "3-apps" / "maliev-registry-service",
            self.root / "3-apps" / "maliev-registry-service",
        )
        common = self.root / "3-apps" / "_common"
        common.mkdir(parents=True)
        shutil.copy2(
            REPOSITORY_ROOT / "3-apps" / "_common" / "kustomization.yaml",
            common / "kustomization.yaml",
        )

    def copy_disabled_applications(self) -> None:
        """Copy only the exact disabled Registry Application contracts."""
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
                / "maliev-registry-service.yaml",
                destination / "maliev-registry-service.yaml",
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
        self.copy_registry_manifests()
        deployment_path = POLICY.REGISTRY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["envFrom"] = [
            {"secretRef": {"name": "maliev-shared-secrets"}},
            {"secretRef": {"name": "maliev-registry-service-secrets"}},
        ]
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        secret_path = POLICY.REGISTRY_ROOT / "base" / "service-secrets.yaml"
        external_secret = yaml.safe_load(secret_path.read_text(encoding="utf-8"))
        external_secret["spec"].pop("data")
        external_secret["spec"]["dataFrom"] = [
            {"extract": {"key": "maliev-prod-registry-service-config"}}
        ]
        secret_path.write_text(
            yaml.safe_dump(external_secret, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_registry_overlay("production")

        self.assertTrue(any("must not use envFrom" in error for error in errors))
        self.assertTrue(any("forbidden RegistryService projection" in error for error in errors))
        self.assertTrue(any("exact object contract" in error for error in errors))

    def test_helper_container_and_secret_volume_are_rejected(self) -> None:
        """Alternate pod secret channels must not bypass the main container allowlist."""
        self.copy_registry_manifests()
        deployment_path = POLICY.REGISTRY_ROOT / "base" / "deployment.yaml"
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

        errors = POLICY.validate_registry_overlay("production")

        self.assertTrue(any("pod containers do not match" in error for error in errors))
        self.assertTrue(any("pod volumes are not allowlisted" in error for error in errors))
        self.assertTrue(any("forbidden RegistryService projection" in error for error in errors))

    def test_external_secret_metadata_and_mapping_drift_are_rejected(self) -> None:
        """The complete ExternalSecret object is an allowlist, not a partial check."""
        self.copy_registry_manifests()
        secret_path = POLICY.REGISTRY_ROOT / "base" / "service-secrets.yaml"
        external_secret = yaml.safe_load(secret_path.read_text(encoding="utf-8"))
        external_secret["metadata"]["annotations"] = {"unreviewed": "true"}
        external_secret["spec"]["data"][0]["remoteRef"]["property"] = "Jwt__PrivateKey"
        secret_path.write_text(
            yaml.safe_dump(external_secret, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_registry_overlay("production")

        self.assertTrue(any("exact object contract" in error for error in errors))

    def test_service_account_token_projection_is_rejected(self) -> None:
        """RegistryService does not use the Kubernetes API and must not receive its token."""
        self.copy_registry_manifests()
        deployment_path = POLICY.REGISTRY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_registry_overlay("production")

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
            "maliev-registry-service-child",
            "3-apps/maliev-registry-service/overlays/development",
        )

        errors = POLICY.validate_registry_applications_remain_disabled()

        self.assertTrue(
            any("Application', 'maliev-registry-service-child" in error for error in errors)
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
  name: maliev-registry-service
spec:
  selector:
    matchLabels:
      app: registry
  template:
    metadata:
      labels:
        app: registry
    spec:
      containers:
        - name: registry
          image: example.invalid/registry
""",
            encoding="utf-8",
        )

        errors = POLICY.validate_registry_applications_remain_disabled()

        self.assertTrue(
            any("Deployment', 'maliev-registry-service" in error for error in errors)
        )

    def test_renamed_workload_using_registry_image_is_rejected(self) -> None:
        """Runtime image identity must survive arbitrary workload and container renames."""
        self.copy_disabled_applications()
        self.write_application(
            self.root / "argocd" / "environments" / "dev" / "root.yaml",
            "generic-root",
            "generic-workload",
        )
        workload = self.root / "generic-workload"
        workload.mkdir()
        (workload / "kustomization.yaml").write_text(
            "resources:\n  - deployment.yaml\n", encoding="utf-8"
        )
        (workload / "deployment.yaml").write_text(
            """apiVersion: apps/v1
kind: Deployment
metadata:
  name: generic-worker
spec:
  selector:
    matchLabels:
      app: generic-worker
  template:
    metadata:
      labels:
        app: generic-worker
    spec:
      containers:
        - name: worker
          image: asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact-dev/maliev-registry-service:dev-review
""",
            encoding="utf-8",
        )

        errors = POLICY.validate_registry_applications_remain_disabled()

        self.assertTrue(
            any("Deployment', 'generic-worker" in error for error in errors)
        )

    def test_iam_origins_use_environment_external_https_api_routes(self) -> None:
        """IAM requests need the real TLS ingress because IAM pods expose HTTP only."""
        self.copy_registry_manifests()
        expected_origins = {
            "development": "https://dev.api.maliev.com",
            "staging": "https://staging.api.maliev.com",
            "production": "https://api.maliev.com",
        }
        for environment, expected_origin in expected_origins.items():
            rendered = POLICY.render(POLICY.REGISTRY_ROOT / "overlays" / environment)
            deployment = next(
                document
                for document in yaml.safe_load_all(rendered)
                if document
                and document.get("kind") == "Deployment"
                and document.get("metadata", {}).get("name")
                == "maliev-registry-service"
            )
            environment_variables = {
                item["name"]: item
                for item in deployment["spec"]["template"]["spec"]["containers"][0][
                    "env"
                ]
            }
            self.assertEqual(
                expected_origin,
                environment_variables["Services__IAMService__BaseUrl"].get("value"),
                environment,
            )

    def test_external_company_provider_configuration_is_narrowly_isolated(self) -> None:
        """Only BDEX OAuth credentials may cross the Registry secret boundary."""
        self.copy_registry_manifests()
        rendered = POLICY.render(POLICY.REGISTRY_ROOT / "overlays" / "production")
        documents = [
            document
            for document in yaml.safe_load_all(rendered)
            if isinstance(document, dict)
        ]
        deployment = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name")
            == "maliev-registry-service"
        )
        external_secret = next(
            document
            for document in documents
            if document.get("kind") == "ExternalSecret"
            and document.get("metadata", {}).get("name")
            == "maliev-registry-service-secrets"
        )
        environment_names = {
            item["name"]
            for item in deployment["spec"]["template"]["spec"]["containers"][0][
                "env"
            ]
        }
        provider_environment = {
            name
            for name in environment_names
            if name.startswith("BDEX__") or name.startswith("Creden__")
        }
        provider_secret_keys = {
            item["secretKey"]
            for item in external_secret["spec"]["data"]
            if item["secretKey"].startswith("BDEX__")
            or item["secretKey"].startswith("Creden__")
        }

        expected = {"BDEX__ConsumerKey", "BDEX__ConsumerSecret"}
        self.assertEqual(expected, provider_environment)
        self.assertEqual(expected, provider_secret_keys)

    def test_runtime_image_detection_covers_every_container_set(self) -> None:
        """Main, init, and ephemeral Registry images all identify the runtime."""
        registry_image = "registry.example/maliev-registry-service@sha256:review"
        for container_set in ("containers", "initContainers", "ephemeralContainers"):
            pod_spec = {
                "containers": [{"name": "main", "image": "example.invalid/generic"}],
                container_set: [{"name": "renamed", "image": registry_image}],
            }
            workload = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "generic-worker"},
                "spec": {"template": {"spec": pod_spec}},
            }

            with self.subTest(container_set=container_set):
                self.assertTrue(POLICY.workload_uses_registry_runtime(workload))


if __name__ == "__main__":
    unittest.main(verbosity=2)
