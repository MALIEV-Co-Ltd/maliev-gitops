#!/usr/bin/env python3
"""Adversarial tests for the CurrencyService GitOps projection policy."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY_ROOT / "scripts" / "check-currency-service-secret-projection.py"
SPEC = importlib.util.spec_from_file_location("currency_projection_policy", POLICY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load policy module from {POLICY_PATH}")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class CurrencyProjectionPolicyTests(unittest.TestCase):
    """Exercise negative paths against isolated manifest fixtures."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.original_root = POLICY.ROOT
        self.original_currency_root = POLICY.CURRENCY_ROOT
        POLICY.ROOT = self.root
        POLICY.CURRENCY_ROOT = self.root / "3-apps" / "maliev-currency-service"

    def tearDown(self) -> None:
        POLICY.ROOT = self.original_root
        POLICY.CURRENCY_ROOT = self.original_currency_root
        self.temporary_directory.cleanup()

    def copy_currency_manifests(self) -> None:
        """Copy the current Currency manifests and shared empty transformer."""
        shutil.copytree(
            REPOSITORY_ROOT / "3-apps" / "maliev-currency-service",
            self.root / "3-apps" / "maliev-currency-service",
        )
        common = self.root / "3-apps" / "_common"
        common.mkdir(parents=True)
        shutil.copy2(
            REPOSITORY_ROOT / "3-apps" / "_common" / "kustomization.yaml",
            common / "kustomization.yaml",
        )

    def copy_disabled_applications(self) -> None:
        """Copy only the exact disabled Currency Application contracts."""
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
                / "maliev-currency-service.yaml",
                destination / "maliev-currency-service.yaml",
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

    def add_duplicate_env_patch(self, environment: str, relative_path: str) -> None:
        """Reference a real Deployment patch whose duplicate env key is normalized away."""
        overlay = POLICY.CURRENCY_ROOT / "overlays" / environment
        patch_path = overlay / relative_path
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "maliev-currency-service"},
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "maliev-currency-service",
                                        "env": [
                                            {
                                                "name": "ServiceAuthentication__ClientSecret",
                                                "valueFrom": {
                                                    "secretKeyRef": {
                                                        "name": "unreviewed-secret",
                                                        "key": "client-secret",
                                                    }
                                                },
                                            },
                                            {
                                                "name": "ServiceAuthentication__ClientSecret",
                                                "valueFrom": {
                                                    "secretKeyRef": {
                                                        "name": "maliev-currency-service-secrets",
                                                        "key": "ServiceAuthentication__ClientSecret",
                                                    }
                                                },
                                            },
                                        ],
                                    }
                                ]
                            }
                        }
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        kustomization_path = overlay / "kustomization.yaml"
        kustomization = yaml.safe_load(kustomization_path.read_text(encoding="utf-8"))
        kustomization.setdefault("patches", []).append({"path": relative_path})
        kustomization_path.write_text(
            yaml.safe_dump(kustomization, sort_keys=False), encoding="utf-8"
        )

    def test_broad_env_from_and_data_from_are_rejected(self) -> None:
        """Broad shared and service secret bundles must remain impossible."""
        self.copy_currency_manifests()
        deployment_path = POLICY.CURRENCY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["envFrom"] = [
            {"secretRef": {"name": "maliev-shared-secrets"}},
            {"secretRef": {"name": "maliev-currency-service-secrets"}},
        ]
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        secret_path = POLICY.CURRENCY_ROOT / "base" / "service-secrets.yaml"
        external_secret = yaml.safe_load(secret_path.read_text(encoding="utf-8"))
        external_secret["spec"].pop("data")
        external_secret["spec"]["dataFrom"] = [
            {"extract": {"key": "maliev-prod-currency-service-config"}}
        ]
        secret_path.write_text(
            yaml.safe_dump(external_secret, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(any("must not use envFrom" in error for error in errors))
        self.assertTrue(any("forbidden CurrencyService projection" in error for error in errors))
        self.assertTrue(any("exact object contract" in error for error in errors))

    def test_duplicate_environment_names_cannot_hide_unreviewed_projection(self) -> None:
        """Raw source duplicates must fail before Kustomize can normalize them away."""
        self.copy_currency_manifests()
        deployment_path = POLICY.CURRENCY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["env"].insert(
            0,
            {
                "name": "ServiceAuthentication__ClientSecret",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "unreviewed-secret",
                        "key": "ServiceAuthentication__ClientSecret",
                    }
                },
            },
        )
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(
            any("source env list has duplicate names" in error for error in errors)
        )

    def test_referenced_yml_patch_duplicate_is_rejected_end_to_end(self) -> None:
        """Referenced .yml patches must be source-checked before Kustomize normalization."""
        self.copy_currency_manifests()
        self.add_duplicate_env_patch("production", "unreviewed.yml")

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(
            any("unreviewed.yml source env list has duplicate names" in error for error in errors)
        )

    def test_referenced_nested_patch_duplicate_is_rejected_end_to_end(self) -> None:
        """Nested referenced patches must be discovered from the Kustomization graph."""
        self.copy_currency_manifests()
        self.add_duplicate_env_patch("production", "nested/unreviewed.yaml")

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(
            any(
                "nested/unreviewed.yaml source env list has duplicate names" in error
                for error in errors
            )
        )

    def test_helper_container_and_secret_volume_are_rejected(self) -> None:
        """Alternate pod secret channels must not bypass the main container allowlist."""
        self.copy_currency_manifests()
        deployment_path = POLICY.CURRENCY_ROOT / "base" / "deployment.yaml"
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

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(any("pod containers do not match" in error for error in errors))
        self.assertTrue(any("pod volumes are not allowlisted" in error for error in errors))
        self.assertTrue(any("forbidden CurrencyService projection" in error for error in errors))

    def test_external_secret_metadata_and_mapping_drift_are_rejected(self) -> None:
        """The complete ExternalSecret object is an allowlist, not a partial check."""
        self.copy_currency_manifests()
        secret_path = POLICY.CURRENCY_ROOT / "base" / "service-secrets.yaml"
        external_secret = yaml.safe_load(secret_path.read_text(encoding="utf-8"))
        external_secret["metadata"]["annotations"] = {"unreviewed": "true"}
        external_secret["spec"]["data"][0]["remoteRef"]["property"] = "Jwt__PrivateKey"
        secret_path.write_text(
            yaml.safe_dump(external_secret, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(any("exact object contract" in error for error in errors))

    def test_service_account_token_projection_is_rejected(self) -> None:
        """CurrencyService does not use the Kubernetes API and must not receive its token."""
        self.copy_currency_manifests()
        deployment_path = POLICY.CURRENCY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

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
            "maliev-currency-service-child",
            "3-apps/maliev-currency-service/overlays/development",
        )

        errors = POLICY.validate_currency_applications_remain_disabled()

        self.assertTrue(
            any("Application', 'maliev-currency-service-child" in error for error in errors)
        )

    def test_percent_encoded_same_repository_url_is_unsafe_and_traversed(self) -> None:
        """Encoded same-repo spellings must be rejected without hiding rendered activation."""
        self.copy_disabled_applications()
        self.write_application(
            self.root / "argocd" / "environments" / "dev" / "root.yaml",
            "generic-root",
            "encoded-root",
            "https://github.com/MALIEV-Co-Ltd/%6Daliev-gitops.git",
        )
        workload = self.root / "encoded-root"
        workload.mkdir()
        (workload / "kustomization.yaml").write_text(
            "resources:\n  - deployment.yaml\n", encoding="utf-8"
        )
        (workload / "deployment.yaml").write_text(
            """apiVersion: apps/v1
kind: Deployment
metadata:
  name: encoded-currency-runtime
spec:
  selector:
    matchLabels:
      app: encoded-currency-runtime
  template:
    metadata:
      labels:
        app: encoded-currency-runtime
    spec:
      containers:
        - name: runtime
          image: registry.example/maliev-currency-service:review
""",
            encoding="utf-8",
        )

        errors = POLICY.validate_currency_applications_remain_disabled()

        self.assertTrue(any("noncanonical MALIEV GitOps URL" in error for error in errors))
        self.assertTrue(any("encoded-currency-runtime" in error for error in errors))

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
  name: maliev-currency-service
spec:
  selector:
    matchLabels:
      app: currency
  template:
    metadata:
      labels:
        app: currency
    spec:
      containers:
        - name: currency
          image: example.invalid/currency
""",
            encoding="utf-8",
        )

        errors = POLICY.validate_currency_applications_remain_disabled()

        self.assertTrue(
            any("Deployment', 'maliev-currency-service" in error for error in errors)
        )

    def test_renamed_workload_using_currency_image_is_rejected(self) -> None:
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
          image: asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact-dev/maliev-currency-service:dev-review
""",
            encoding="utf-8",
        )

        errors = POLICY.validate_currency_applications_remain_disabled()

        self.assertTrue(
            any("Deployment', 'generic-worker" in error for error in errors)
        )

    def test_iam_origins_use_environment_external_https_api_routes(self) -> None:
        """IAM requests need the real TLS ingress because IAM pods expose HTTP only."""
        self.copy_currency_manifests()
        expected_origins = {
            "development": "https://dev.api.maliev.com",
            "staging": "https://staging.api.maliev.com",
            "production": "https://api.maliev.com",
        }
        for environment, expected_origin in expected_origins.items():
            rendered = POLICY.render(POLICY.CURRENCY_ROOT / "overlays" / environment)
            deployment = next(
                document
                for document in yaml.safe_load_all(rendered)
                if document
                and document.get("kind") == "Deployment"
                and document.get("metadata", {}).get("name")
                == "maliev-currency-service"
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

    def test_health_probes_use_actual_unversioned_service_routes(self) -> None:
        """Kubernetes probes must target the endpoints mapped by ServiceDefaults."""
        self.copy_currency_manifests()
        for environment in POLICY.ENVIRONMENTS:
            rendered = POLICY.render(POLICY.CURRENCY_ROOT / "overlays" / environment)
            deployment = next(
                document
                for document in yaml.safe_load_all(rendered)
                if document
                and document.get("kind") == "Deployment"
                and document.get("metadata", {}).get("name")
                == "maliev-currency-service"
            )
            container = deployment["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(
                "/currency/liveness",
                container["livenessProbe"]["httpGet"]["path"],
                environment,
            )
            self.assertEqual(
                "/currency/readiness",
                container["readinessProbe"]["httpGet"]["path"],
                environment,
            )

    def test_probe_port_and_extra_fields_are_rejected(self) -> None:
        """Probe validation must cover complete reviewed objects, not paths alone."""
        self.copy_currency_manifests()
        deployment_path = POLICY.CURRENCY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["livenessProbe"]["httpGet"]["port"] = 9090
        container["readinessProbe"]["unexpected"] = True
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(any("health probe contract is not exact" in error for error in errors))

    def test_service_contract_is_internal_and_monitorable(self) -> None:
        """The disabled service must be internal and expose the named monitor port."""
        self.copy_currency_manifests()
        for environment in POLICY.ENVIRONMENTS:
            rendered = POLICY.render(POLICY.CURRENCY_ROOT / "overlays" / environment)
            service = next(
                document
                for document in yaml.safe_load_all(rendered)
                if document
                and document.get("kind") == "Service"
                and document.get("metadata", {}).get("name")
                == "maliev-currency-service"
            )
            self.assertEqual("ClusterIP", service["spec"]["type"], environment)
            self.assertEqual(
                [{"name": "http", "port": 80, "targetPort": 8080}],
                service["spec"]["ports"],
                environment,
            )

    def test_deployment_replicas_and_hpa_drift_are_rejected(self) -> None:
        """Argo must not fight the HPA and reviewed scaling bounds must remain exact."""
        self.copy_currency_manifests()
        deployment_path = POLICY.CURRENCY_ROOT / "base" / "deployment.yaml"
        deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
        deployment["spec"]["replicas"] = 2
        deployment_path.write_text(
            yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8"
        )
        hpa_path = POLICY.CURRENCY_ROOT / "base" / "hpa.yaml"
        hpa = yaml.safe_load(hpa_path.read_text(encoding="utf-8"))
        hpa["spec"]["maxReplicas"] = 4
        hpa_path.write_text(
            yaml.safe_dump(hpa, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(any("deployment replicas" in error for error in errors))
        self.assertTrue(any("HPA contract" in error for error in errors))

    def test_hpa_unknown_fields_are_rejected(self) -> None:
        """An allowlisted HPA must reject behavior and every other unreviewed field."""
        self.copy_currency_manifests()
        hpa_path = POLICY.CURRENCY_ROOT / "base" / "hpa.yaml"
        hpa = yaml.safe_load(hpa_path.read_text(encoding="utf-8"))
        hpa["spec"]["behavior"] = {"scaleDown": {"stabilizationWindowSeconds": 300}}
        hpa_path.write_text(
            yaml.safe_dump(hpa, sort_keys=False), encoding="utf-8"
        )

        errors = POLICY.validate_currency_overlay("production")

        self.assertTrue(any("HPA contract" in error for error in errors))

    def test_dynamic_applicationset_activation_paths_are_rejected(self) -> None:
        """Dynamic templates and generator overrides must fail closed."""
        self.copy_disabled_applications()
        manifest = (
            self.root
            / "argocd"
            / "environments"
            / "dev"
            / "dynamic-currency-appset.yaml"
        )
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "ApplicationSet",
                    "metadata": {"name": "dynamic-currency-root"},
                    "spec": {
                        "generators": [
                            {
                                "list": {
                                    "elements": [{"service": "currency"}],
                                    "template": {
                                        "spec": {
                                            "source": {
                                                "path": "3-apps/maliev-currency-service"
                                            }
                                        }
                                    },
                                }
                            }
                        ],
                        "templatePatch": "spec:\n  source:\n    path: '{{service}}'\n",
                        "template": {
                            "metadata": {"name": "{{service}}"},
                            "spec": {
                                "source": {
                                    "repoURL": POLICY.GITOPS_REPOSITORY_URL,
                                    "path": "3-apps/{{service}}/overlays/development",
                                }
                            },
                        },
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        errors = POLICY.validate_currency_applications_remain_disabled()

        self.assertTrue(any("templatePatch" in error for error in errors))
        self.assertTrue(any("generator overrides" in error for error in errors))
        self.assertTrue(
            any("ApplicationSet can activate CurrencyService" in error for error in errors)
        )

    def test_runtime_image_detection_covers_every_container_set(self) -> None:
        """Main, init, and ephemeral Currency images all identify the runtime."""
        currency_image = "registry.example/maliev-currency-service@sha256:review"
        for container_set in ("containers", "initContainers", "ephemeralContainers"):
            pod_spec = {
                "containers": [{"name": "main", "image": "example.invalid/generic"}],
                container_set: [{"name": "renamed", "image": currency_image}],
            }
            workload = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "generic-worker"},
                "spec": {"template": {"spec": pod_spec}},
            }

            with self.subTest(container_set=container_set):
                self.assertTrue(POLICY.workload_uses_currency_runtime(workload))


if __name__ == "__main__":
    unittest.main(verbosity=2)
