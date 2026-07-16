#!/usr/bin/env python3
"""Validate ContactService's least-privilege runtime secret projection."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTACT_ROOT = ROOT / "3-apps" / "maliev-contact-service"
ENVIRONMENTS = ("development", "staging", "production")
ENVIRONMENT_PREFIXES = {
    "development": "maliev-dev",
    "staging": "maliev-staging",
    "production": "maliev-prod",
}
EXPECTED_ENVIRONMENT_VALUES = {
    "development": {
        "ASPNETCORE_ENVIRONMENT": "Development",
        "Services__AuthService__BaseUrl": "https://dev.api.maliev.com",
    },
    "staging": {
        "ASPNETCORE_ENVIRONMENT": "Staging",
        "Services__AuthService__BaseUrl": "https://staging.api.maliev.com",
    },
    "production": {
        "ASPNETCORE_ENVIRONMENT": "Production",
        "Services__AuthService__BaseUrl": "https://api.maliev.com",
    },
}

FORBIDDEN_CONTACT_TOKENS = (
    "maliev-shared-secrets",
    "Jwt__PrivateKey",
    "Jwt__SecurityKey",
    "Jwt__SigningKey",
    "Jwt__SecretKey",
)

REQUIRED_CONTACT_TOKENS = (
    "Jwt__PublicKey",
    "Jwt__Issuer",
    "Jwt__Audience",
    "Services__AuthService__BaseUrl",
    "ServiceAuthentication__ClientId",
    "ServiceAuthentication__ClientSecret",
    "ConnectionStrings__ContactDbContext",
    "ConnectionStrings__rabbitmq",
    "ConnectionStrings__redis",
    "CORS__AllowedOrigins",
    "ExternalServices__UploadService",
    "ExternalServices__CountryService",
)

REQUIRED_SECRET_KEYS = {
    "Jwt__PublicKey",
    "Jwt__Issuer",
    "Jwt__Audience",
    "ServiceAuthentication__ClientSecret",
    "ConnectionStrings__ContactDbContext",
    "ConnectionStrings__rabbitmq",
    "ConnectionStrings__redis",
    "CORS__AllowedOrigins",
}

EXPECTED_RENDERED_INVENTORY = Counter(
    {
        ("Service", "maliev-contact-service"): 1,
        ("Deployment", "maliev-contact-service"): 1,
        ("HorizontalPodAutoscaler", "maliev-contact-service-hpa"): 1,
        ("ExternalSecret", "maliev-contact-service-secrets"): 1,
        ("ServiceMonitor", "maliev-contact-service"): 1,
    }
)


def contains_non_empty_template_override(value: object) -> bool:
    """Return true when an ApplicationSet generator tree contains a template override."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "template" and child not in (None, "", {}, []):
                return True
            if contains_non_empty_template_override(child):
                return True
    elif isinstance(value, list):
        return any(contains_non_empty_template_override(child) for child in value)
    return False


def source_can_activate_contact(source: object) -> bool:
    """Fail closed when an Argo source directly or recursively reaches ContactService."""
    if not isinstance(source, dict):
        return False

    source_path = str(source.get("path", "")).strip("/")
    if source_path == ".":
        source_path = ""
    contact_path = "3-apps/maliev-contact-service"
    if "{{" in source_path or "}}" in source_path:
        return True
    if ".." in source_path.split("/"):
        return True
    if source_path == contact_path or source_path.startswith(f"{contact_path}/"):
        return True

    directory = source.get("directory")
    is_contact_ancestor = not source_path or contact_path.startswith(f"{source_path}/")
    if is_contact_ancestor and isinstance(directory, dict):
        has_recursive_discovery = directory.get("recurse") is True
        has_include_pattern = directory.get("include") not in (None, "", [])
        if has_recursive_discovery or has_include_pattern:
            return True
    return False


def render(overlay: Path) -> str:
    completed = subprocess.run(
        ["kustomize", "build", str(overlay)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"kustomize build failed for {overlay.relative_to(ROOT)}:\n"
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def validate_contact_overlay(environment: str) -> list[str]:
    rendered = render(CONTACT_ROOT / "overlays" / environment)
    errors: list[str] = []

    documents = [document for document in yaml.safe_load_all(rendered) if document]
    rendered_inventory = Counter(
        (document.get("kind"), document.get("metadata", {}).get("name"))
        for document in documents
    )
    if rendered_inventory != EXPECTED_RENDERED_INVENTORY:
        errors.append(
            f"{environment}: rendered ContactService inventory is "
            f"{dict(rendered_inventory)!r}; expected exact inventory "
            f"{dict(EXPECTED_RENDERED_INVENTORY)!r}"
        )

    deployments = [
        document
        for document in documents
        if document.get("kind") == "Deployment"
        and document.get("metadata", {}).get("name") == "maliev-contact-service"
    ]
    external_secrets = [
        document
        for document in documents
        if document.get("kind") == "ExternalSecret"
        and document.get("metadata", {}).get("name")
        == "maliev-contact-service-secrets"
    ]
    deployment = deployments[0] if len(deployments) == 1 else None
    external_secret = external_secrets[0] if len(external_secrets) == 1 else None

    if deployment is None:
        errors.append(
            f"{environment}: exactly one ContactService Deployment must render"
        )
    if external_secret is None:
        errors.append(
            f"{environment}: exactly one ContactService ExternalSecret must render"
        )
    if deployment is None or external_secret is None:
        return errors

    pod_specification = deployment["spec"]["template"]["spec"]
    containers = pod_specification.get("containers", [])
    container = next(
        (
            item
            for item in containers
            if item.get("name") == "maliev-contact-service"
        ),
        None,
    )
    if container is None:
        return [f"{environment}: ContactService container did not render"]

    if [item.get("name") for item in containers] != ["maliev-contact-service"]:
        errors.append(
            f"{environment}: ContactService pod containers do not match the exact "
            "single-container contract"
        )
    if pod_specification.get("initContainers"):
        errors.append(f"{environment}: ContactService initContainers are not allowlisted")
    if pod_specification.get("ephemeralContainers"):
        errors.append(
            f"{environment}: ContactService ephemeralContainers are not allowlisted"
        )

    secret_volume_names: set[str] = set()
    if pod_specification.get("volumes"):
        errors.append(f"{environment}: ContactService pod volumes are not allowlisted")
    for volume in pod_specification.get("volumes", []):
        secret_name = volume.get("secret", {}).get("secretName")
        projected_secret_names = [
            source.get("secret", {}).get("name")
            for source in volume.get("projected", {}).get("sources", [])
            if isinstance(source, dict) and source.get("secret")
        ]
        if secret_name or any(projected_secret_names):
            secret_volume_names.add(volume.get("name", ""))
            errors.append(
                f"{environment}: ContactService secret-bearing volume "
                f"{volume.get('name', '<unnamed>')!r} is not allowlisted"
            )

    all_pod_containers = [
        *containers,
        *pod_specification.get("initContainers", []),
        *pod_specification.get("ephemeralContainers", []),
    ]
    for pod_container in all_pod_containers:
        if pod_container.get("volumeMounts"):
            errors.append(
                f"{environment}: container {pod_container.get('name', '<unnamed>')!r} "
                "volumeMounts are not allowlisted"
            )
        mounted_secret_volumes = {
            mount.get("name")
            for mount in pod_container.get("volumeMounts", [])
            if mount.get("name") in secret_volume_names
        }
        if mounted_secret_volumes:
            errors.append(
                f"{environment}: container {pod_container.get('name', '<unnamed>')!r} "
                f"mounts non-allowlisted secret volumes {sorted(mounted_secret_volumes)!r}"
            )

    contact_projection = yaml.safe_dump(
        {
            "containers": [
                {
                    "name": item.get("name"),
                    "env": item.get("env", []),
                    "envFrom": item.get("envFrom", []),
                    "volumeMounts": item.get("volumeMounts", []),
                }
                for item in all_pod_containers
            ],
            "volumes": pod_specification.get("volumes", []),
        },
        sort_keys=True,
    )
    secret_projection = yaml.safe_dump(external_secret.get("spec", {}), sort_keys=True)
    environment_variables = {
        item.get("name"): item for item in container.get("env", []) if item.get("name")
    }

    if container.get("envFrom"):
        errors.append(f"{environment}: ContactService must not use envFrom")

    signing_name_markers = ("private", "security", "signing", "secret")
    for projected_name in (
        set(environment_variables)
        | {
            item.get("secretKey", "")
            for item in external_secret.get("spec", {}).get("data", [])
        }
    ):
        normalized_name = projected_name.casefold()
        if "jwt" in normalized_name and any(
            marker in normalized_name for marker in signing_name_markers
        ):
            errors.append(
                f"{environment}: ContactService projects JWT signing-like key "
                f"{projected_name!r}"
            )

    for token in FORBIDDEN_CONTACT_TOKENS:
        if token in contact_projection or token in secret_projection:
            errors.append(f"{environment}: forbidden ContactService projection {token!r}")

    for token in REQUIRED_CONTACT_TOKENS:
        if token not in contact_projection:
            errors.append(f"{environment}: missing ContactService projection {token!r}")

    expected_secret_references = {
        key: {
            "name": "maliev-contact-service-secrets",
            "key": key,
        }
        for key in REQUIRED_SECRET_KEYS
    }
    actual_secret_references = {
        key: environment_variables.get(key, {}).get("valueFrom", {}).get("secretKeyRef")
        for key in REQUIRED_SECRET_KEYS
    }
    if actual_secret_references != expected_secret_references:
        errors.append(
            f"{environment}: ContactService secretKeyRef projection does not match "
            "the explicit runtime allowlist"
        )

    expected_non_secret_values = {
        "ServiceAuthentication__ClientId": "service-contact-service",
        "ExternalServices__UploadService": "http://maliev-upload-service:8080",
        "ExternalServices__CountryService": "http://maliev-country-service",
        **EXPECTED_ENVIRONMENT_VALUES[environment],
    }
    expected_environment_names = REQUIRED_SECRET_KEYS | set(expected_non_secret_values)
    if set(environment_variables) != expected_environment_names:
        errors.append(
            f"{environment}: ContactService environment keys are "
            f"{sorted(environment_variables)!r}; expected exact allowlist "
            f"{sorted(expected_environment_names)!r}"
        )

    actual_non_secret_values = {
        key: environment_variables.get(key, {}).get("value")
        for key in expected_non_secret_values
    }
    if actual_non_secret_values != expected_non_secret_values:
        errors.append(
            f"{environment}: ContactService non-secret runtime configuration does not "
            "match the reviewed environment contract"
        )

    expected_remote_mappings = {
        "Jwt__PublicKey": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "property": "Jwt__PublicKey",
        },
        "Jwt__Issuer": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "property": "Jwt__Issuer",
        },
        "Jwt__Audience": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "property": "Jwt__Audience",
        },
        "ServiceAuthentication__ClientSecret": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-contact-service-config",
            "property": "ServiceAuthentication__ClientSecret",
        },
        "ConnectionStrings__ContactDbContext": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-contact-service-config",
            "property": "ConnectionStrings__ContactDbContext",
        },
        "ConnectionStrings__rabbitmq": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "property": "ConnectionStrings__rabbitmq",
        },
        "ConnectionStrings__redis": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "property": "ConnectionStrings__redis",
        },
        "CORS__AllowedOrigins": {
            "key": f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "property": "CORS__AllowedOrigins",
        },
    }
    expected_external_secret_spec = {
        "secretStoreRef": {
            "kind": "ClusterSecretStore",
            "name": "gcp-secret-manager",
        },
        "target": {
            "name": "maliev-contact-service-secrets",
            "creationPolicy": "Owner",
        },
        "data": [
            {"secretKey": secret_key, "remoteRef": remote_reference}
            for secret_key, remote_reference in sorted(expected_remote_mappings.items())
        ],
    }
    actual_external_secret_spec = external_secret.get("spec", {})
    actual_data = actual_external_secret_spec.get("data")
    normalized_actual_spec = dict(actual_external_secret_spec)
    if isinstance(actual_data, list):
        normalized_actual_spec["data"] = sorted(
            actual_data,
            key=lambda item: str(item.get("secretKey"))
            if isinstance(item, dict)
            else repr(item),
        )
    if normalized_actual_spec != expected_external_secret_spec:
        errors.append(
            f"{environment}: ContactService ExternalSecret spec does not match the "
            "exact environment property contract"
        )

    return errors


def validate_contact_applications_remain_disabled() -> list[str]:
    errors: list[str] = []
    disabled = ROOT / "argocd" / "environments" / "_disabled_apps"
    disabled_contracts = {
        "dev": {
            "name": "maliev-contact-service-dev",
            "path": "3-apps/maliev-contact-service/overlays/development",
            "environment": "development",
            "namespace": "maliev-dev",
            "targetRevision": "main",
        },
        "staging": {
            "name": "maliev-contact-service-staging",
            "path": "3-apps/maliev-contact-service/overlays/staging",
            "environment": "staging",
            "namespace": "maliev-staging",
            "targetRevision": "main",
        },
        "prod": {
            "name": "maliev-contact-service-prod",
            "path": "3-apps/maliev-contact-service/overlays/production",
            "environment": "production",
            "namespace": "maliev-prod",
            "targetRevision": "v1.0.0",
        },
    }
    for environment, contract in disabled_contracts.items():
        expected = disabled / environment / "maliev-contact-service.yaml"
        if not expected.is_file():
            errors.append(f"missing disabled ContactService Application: {expected}")
            continue

        documents = [
            document
            for document in yaml.safe_load_all(expected.read_text(encoding="utf-8"))
            if document
        ]
        if len(documents) != 1:
            errors.append(
                f"disabled ContactService manifest must contain exactly one Application: "
                f"{expected.relative_to(ROOT)}"
            )
            continue

        application = documents[0]
        actual_contract = {
            "apiVersion": application.get("apiVersion"),
            "kind": application.get("kind"),
            "name": application.get("metadata", {}).get("name"),
            "metadataNamespace": application.get("metadata", {}).get("namespace"),
            "appLabel": application.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/name"),
            "environment": application.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/environment"),
            "path": application.get("spec", {}).get("source", {}).get("path"),
            "repoURL": application.get("spec", {}).get("source", {}).get("repoURL"),
            "targetRevision": application.get("spec", {})
            .get("source", {})
            .get("targetRevision"),
            "destinationServer": application.get("spec", {})
            .get("destination", {})
            .get("server"),
            "destinationNamespace": application.get("spec", {})
            .get("destination", {})
            .get("namespace"),
        }
        expected_contract = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "name": contract["name"],
            "metadataNamespace": "argocd",
            "appLabel": "maliev-contact-service",
            "environment": contract["environment"],
            "path": contract["path"],
            "repoURL": "https://github.com/MALIEV-Co-Ltd/maliev-gitops.git",
            "targetRevision": contract["targetRevision"],
            "destinationServer": "https://kubernetes.default.svc",
            "destinationNamespace": contract["namespace"],
        }
        if actual_contract != expected_contract:
            errors.append(
                "disabled ContactService Application does not match its exact environment "
                f"contract: {expected.relative_to(ROOT)}"
            )

    argocd_root = ROOT / "argocd"
    manifests = [*argocd_root.rglob("*.yaml"), *argocd_root.rglob("*.yml")]
    for manifest in manifests:
        if "_disabled_apps" in manifest.parts:
            continue

        documents = [
            document
            for document in yaml.safe_load_all(manifest.read_text(encoding="utf-8"))
            if document
        ]
        for document in documents:
            kind = document.get("kind")
            if kind not in ("Application", "ApplicationSet"):
                continue

            application_names = [document.get("metadata", {}).get("name", "")]
            specification = document.get("spec", {})
            if kind == "ApplicationSet":
                template_patch = specification.get("templatePatch")
                if template_patch not in (None, "", {}):
                    errors.append(
                        "ContactService Application must remain disabled; active "
                        "ApplicationSet with non-empty templatePatch found in "
                        f"{manifest.relative_to(ROOT)}"
                    )
                if contains_non_empty_template_override(
                    specification.get("generators", [])
                ):
                    errors.append(
                        "ContactService Application must remain disabled; active "
                        "ApplicationSet generator template override found in "
                        f"{manifest.relative_to(ROOT)}"
                    )
                template = specification.get("template", {})
                application_names.append(template.get("metadata", {}).get("name", ""))
                specification = template.get("spec", {})
            sources = []
            if isinstance(specification.get("source"), dict):
                sources.append(specification["source"])
            sources.extend(
                source
                for source in specification.get("sources", [])
                if isinstance(source, dict)
            )
            source_paths = [str(source.get("path", "")) for source in sources]
            has_contact_reference = any(
                "maliev-contact-service" in name for name in application_names
            ) or any(source_can_activate_contact(source) for source in sources)
            has_unresolved_dynamic_source = kind == "ApplicationSet" and any(
                "{{" in path or "}}" in path for path in source_paths
            )
            has_unresolved_dynamic_name = kind == "ApplicationSet" and any(
                "{{" in name or "}}" in name for name in application_names
            )
            if (
                has_contact_reference
                or has_unresolved_dynamic_source
                or has_unresolved_dynamic_name
            ):
                errors.append(
                    "ContactService Application must remain disabled; active "
                    f"{kind} with a Contact or unresolved dynamic source found in "
                    f"{manifest.relative_to(ROOT)}"
                )
    return errors


def main() -> int:
    errors: list[str] = []
    for environment in ENVIRONMENTS:
        try:
            errors.extend(validate_contact_overlay(environment))
        except RuntimeError as error:
            errors.append(str(error))

    errors.extend(validate_contact_applications_remain_disabled())

    if errors:
        print("ContactService secret projection policy failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("ContactService secret projection policy passed for all environments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
