#!/usr/bin/env python3
"""Validate CountryService's least-privilege runtime secret projection."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
COUNTRY_ROOT = ROOT / "3-apps" / "maliev-country-service"
ENVIRONMENTS = ("development", "staging", "production")
ENVIRONMENT_PREFIXES = {
    "development": "maliev-dev",
    "staging": "maliev-staging",
    "production": "maliev-prod",
}
ENVIRONMENT_NAMESPACES = {
    "development": "maliev-dev",
    "staging": "maliev-staging",
    "production": "maliev-prod",
}
EXPECTED_ENVIRONMENT_VALUES = {
    "development": {
        "ASPNETCORE_ENVIRONMENT": "Development",
        "Services__AuthService__BaseUrl": "https://dev.api.maliev.com",
        "Services__IAMService__BaseUrl": "https://dev.api.maliev.com",
    },
    "staging": {
        "ASPNETCORE_ENVIRONMENT": "Staging",
        "Services__AuthService__BaseUrl": "https://staging.api.maliev.com",
        "Services__IAMService__BaseUrl": "https://staging.api.maliev.com",
    },
    "production": {
        "ASPNETCORE_ENVIRONMENT": "Production",
        "Services__AuthService__BaseUrl": "https://api.maliev.com",
        "Services__IAMService__BaseUrl": "https://api.maliev.com",
    },
}
REQUIRED_SECRET_KEYS = {
    "Jwt__PublicKey",
    "Jwt__Issuer",
    "Jwt__Audience",
    "ServiceAuthentication__ClientSecret",
    "ConnectionStrings__CountryDbContext",
    "ConnectionStrings__rabbitmq",
    "ConnectionStrings__redis",
    "CORS__AllowedOrigins",
}
FORBIDDEN_TOKENS = (
    "maliev-shared-secrets",
    "Jwt__PrivateKey",
    "Jwt__SecurityKey",
    "Jwt__SigningKey",
    "Jwt__SecretKey",
)
EXPECTED_RENDERED_INVENTORY = Counter(
    {
        ("Service", "maliev-country-service"): 1,
        ("Deployment", "maliev-country-service"): 1,
        ("HorizontalPodAutoscaler", "country-service-hpa"): 1,
        ("ExternalSecret", "maliev-country-service-secrets"): 1,
        ("ServiceMonitor", "maliev-country-service"): 1,
    }
)
COUNTRY_RENDERED_IDENTITIES = set(EXPECTED_RENDERED_INVENTORY)
POD_PRODUCING_KINDS = {
    "Pod",
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "ReplicationController",
    "Job",
    "CronJob",
    "Rollout",
}
GITOPS_REPOSITORY_OWNER = "maliev-co-ltd"
GITOPS_REPOSITORY_NAME = "maliev-gitops"
GITOPS_REPOSITORY_URL = "https://github.com/MALIEV-Co-Ltd/maliev-gitops.git"
KUSTOMIZATION_FILENAMES = (
    "kustomization.yaml",
    "kustomization.yml",
    "Kustomization",
)


def classify_gitops_repository_url(value: object) -> str:
    """Classify an Argo repository URL as this repo, another repo, or unsafe."""
    repository_url = str(value or "").strip()
    if not repository_url:
        return "other"

    if repository_url.casefold().startswith("git@github.com:"):
        repository_path = repository_url.split(":", 1)[1]
        approved_transport = True
    else:
        try:
            parsed = urlsplit(repository_url)
            repository_path = parsed.path
            approved_transport = (
                parsed.scheme.casefold() == "https"
                and parsed.hostname is not None
                and parsed.hostname.casefold() == "github.com"
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
                and not parsed.query
                and not parsed.fragment
            ) or (
                parsed.scheme.casefold() == "ssh"
                and parsed.hostname is not None
                and parsed.hostname.casefold() == "github.com"
                and parsed.username == "git"
                and parsed.password is None
                and parsed.port in (None, 22)
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            return "unsafe" if "maliev-gitops" in repository_url.casefold() else "other"

    normalized_path = repository_path.strip("/")
    if normalized_path.casefold().endswith(".git"):
        normalized_path = normalized_path[:-4]
    parts = normalized_path.split("/")
    is_this_repository = len(parts) == 2 and (
        parts[0].casefold() == GITOPS_REPOSITORY_OWNER
        and parts[1].casefold() == GITOPS_REPOSITORY_NAME
    )
    if not is_this_repository:
        return "other"
    return "same" if approved_transport else "unsafe"


def contains_non_empty_template_override(value: object) -> bool:
    """Return true when an ApplicationSet generator can override its template."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "template" and child not in (None, "", {}, []):
                return True
            if contains_non_empty_template_override(child):
                return True
    elif isinstance(value, list):
        return any(contains_non_empty_template_override(child) for child in value)
    return False


def source_can_activate_country(source: object) -> bool:
    """Fail closed when an Argo source directly or recursively reaches CountryService."""
    if not isinstance(source, dict):
        return False
    source_path = str(source.get("path", "")).strip("/")
    if source_path == ".":
        source_path = ""
    country_path = "3-apps/maliev-country-service"
    if "{{" in source_path or "}}" in source_path:
        return True
    if ".." in source_path.split("/"):
        return True
    if source_path == country_path or source_path.startswith(f"{country_path}/"):
        return True

    directory = source.get("directory")
    is_country_ancestor = not source_path or country_path.startswith(f"{source_path}/")
    if is_country_ancestor and isinstance(directory, dict):
        return directory.get("recurse") is True or directory.get("include") not in (
            None,
            "",
            [],
        )
    return False


def render(path: Path) -> str:
    """Render a local Kustomize root and preserve actionable failure output."""
    completed = subprocess.run(
        ["kustomize", "build", str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"kustomize build failed for {path.relative_to(ROOT)}:\n"
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def render_active_in_repo_source(source: dict[str, object]) -> list[dict[str, object]]:
    """Render a static source from this repository or fail closed."""
    source_path = str(source.get("path", "")).strip()
    if not source_path:
        raise RuntimeError("active in-repo Argo source has no path")
    if "{{" in source_path or "}}" in source_path:
        raise RuntimeError(f"active in-repo Argo source is dynamic: {source_path!r}")

    candidate = (ROOT / source_path).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as error:
        raise RuntimeError(
            f"active in-repo Argo source escapes the repository: {source_path!r}"
        ) from error
    if not candidate.is_dir():
        raise RuntimeError(f"active in-repo Argo source is missing: {source_path!r}")

    unsupported = sorted(
        key
        for key in ("chart", "helm", "plugin")
        if source.get(key) not in (None, "", {}, [])
    )
    if unsupported:
        raise RuntimeError(
            f"active in-repo source {source_path!r} uses unsupported {unsupported!r}"
        )

    if any((candidate / name).is_file() for name in KUSTOMIZATION_FILENAMES):
        return [
            document
            for document in yaml.safe_load_all(render(candidate))
            if isinstance(document, dict)
        ]

    if source.get("directory") not in (None, {}):
        raise RuntimeError(
            f"active raw directory {source_path!r} uses unsupported discovery options"
        )
    documents: list[dict[str, object]] = []
    for manifest in [*candidate.glob("*.yaml"), *candidate.glob("*.yml")]:
        documents.extend(
            document
            for document in yaml.safe_load_all(manifest.read_text(encoding="utf-8"))
            if isinstance(document, dict)
        )
    return documents


def argo_sources(document: dict[str, object]) -> tuple[list[str], list[dict[str, object]]]:
    """Extract names and sources from an Application or ApplicationSet."""
    names = [str(document.get("metadata", {}).get("name", ""))]
    specification = document.get("spec", {})
    if document.get("kind") == "ApplicationSet":
        template = specification.get("template", {})
        names.append(str(template.get("metadata", {}).get("name", "")))
        specification = template.get("spec", {})
    sources: list[dict[str, object]] = []
    if isinstance(specification.get("source"), dict):
        sources.append(specification["source"])
    sources.extend(
        source
        for source in specification.get("sources", [])
        if isinstance(source, dict)
    )
    return names, sources


def pod_specification(document: dict[str, object]) -> dict[str, object] | None:
    """Extract the pod specification from supported pod-producing resources."""
    kind = document.get("kind")
    specification = document.get("spec", {})
    if kind == "Pod":
        return specification if isinstance(specification, dict) else None
    if kind == "CronJob":
        specification = specification.get("jobTemplate", {}).get("spec", {})
    if kind in POD_PRODUCING_KINDS:
        pod_spec = specification.get("template", {}).get("spec")
        return pod_spec if isinstance(pod_spec, dict) else None
    return None


def image_is_country_runtime(value: object) -> bool:
    """Match the canonical CountryService image regardless of registry, tag, or digest."""
    image = str(value or "").strip()
    if not image:
        return False
    image_name = image.rsplit("/", 1)[-1].split("@", 1)[0].split(":", 1)[0]
    return image_name.casefold() == "maliev-country-service"


def workload_uses_country_runtime(document: dict[str, object]) -> bool:
    """Detect Country runtime identity even when workload resources are renamed."""
    if document.get("kind") not in POD_PRODUCING_KINDS:
        return False
    pod_spec = pod_specification(document)
    if pod_spec is None:
        return False

    containers = [
        container
        for key in ("containers", "initContainers", "ephemeralContainers")
        for container in pod_spec.get(key, [])
        if isinstance(container, dict)
    ]
    if any(image_is_country_runtime(container.get("image")) for container in containers):
        return True

    metadata = document.get("metadata", {})
    template_metadata = (
        document.get("spec", {})
        .get("jobTemplate", {})
        .get("spec", {})
        .get("template", {})
        .get("metadata", {})
        if document.get("kind") == "CronJob"
        else document.get("spec", {}).get("template", {}).get("metadata", {})
    )
    label_values = {
        str(value).casefold()
        for labels in (
            metadata.get("labels", {}),
            template_metadata.get("labels", {}),
        )
        if isinstance(labels, dict)
        for value in labels.values()
    }
    if "maliev-country-service" in label_values:
        return True

    return "maliev-country-service-secrets" in yaml.safe_dump(
        pod_spec, sort_keys=True
    )


def rendered_document_activates_country(document: dict[str, object]) -> bool:
    """Return true when a rendered resource activates CountryService."""
    identity = (
        document.get("kind"),
        document.get("metadata", {}).get("name"),
    )
    if identity in COUNTRY_RENDERED_IDENTITIES:
        return True
    if workload_uses_country_runtime(document):
        return True
    if document.get("kind") not in ("Application", "ApplicationSet"):
        return False
    names, sources = argo_sources(document)
    return any("maliev-country-service" in name for name in names) or any(
        source_can_activate_country(source) for source in sources
    )


def expected_external_secret(environment: str) -> dict[str, object]:
    """Return the complete reviewed ExternalSecret contract for one environment."""
    shared_key = f"{ENVIRONMENT_PREFIXES[environment]}-shared-config"
    country_key = f"{ENVIRONMENT_PREFIXES[environment]}-country-service-config"
    remote_keys = {
        "Jwt__PublicKey": shared_key,
        "Jwt__Issuer": shared_key,
        "Jwt__Audience": shared_key,
        "ConnectionStrings__rabbitmq": shared_key,
        "ConnectionStrings__redis": shared_key,
        "CORS__AllowedOrigins": shared_key,
        "ConnectionStrings__CountryDbContext": country_key,
        "ServiceAuthentication__ClientSecret": country_key,
    }
    return {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {
            "name": "maliev-country-service-secrets",
            "namespace": ENVIRONMENT_NAMESPACES[environment],
        },
        "spec": {
            "secretStoreRef": {
                "kind": "ClusterSecretStore",
                "name": "gcp-secret-manager",
            },
            "target": {
                "name": "maliev-country-service-secrets",
                "creationPolicy": "Owner",
            },
            "data": [
                {
                    "secretKey": secret_key,
                    "remoteRef": {
                        "key": remote_key,
                        "property": secret_key,
                    },
                }
                for secret_key, remote_key in sorted(remote_keys.items())
            ],
        },
    }


def validate_country_overlay(environment: str) -> list[str]:
    """Validate exact rendered inventory, pod projection, and ExternalSecret."""
    errors: list[str] = []
    rendered = render(COUNTRY_ROOT / "overlays" / environment)
    documents = [
        document for document in yaml.safe_load_all(rendered) if isinstance(document, dict)
    ]
    inventory = Counter(
        (document.get("kind"), document.get("metadata", {}).get("name"))
        for document in documents
    )
    if inventory != EXPECTED_RENDERED_INVENTORY:
        errors.append(
            f"{environment}: rendered inventory {dict(inventory)!r} does not match "
            f"{dict(EXPECTED_RENDERED_INVENTORY)!r}"
        )

    native_secrets = [document for document in documents if document.get("kind") == "Secret"]
    if native_secrets:
        errors.append(f"{environment}: native Secret objects are forbidden")

    deployments = [
        document
        for document in documents
        if document.get("kind") == "Deployment"
        and document.get("metadata", {}).get("name") == "maliev-country-service"
    ]
    external_secrets = [
        document
        for document in documents
        if document.get("kind") == "ExternalSecret"
        and document.get("metadata", {}).get("name")
        == "maliev-country-service-secrets"
    ]
    if len(deployments) != 1 or len(external_secrets) != 1:
        errors.append(
            f"{environment}: exactly one Country Deployment and ExternalSecret must render"
        )
        return errors

    deployment = deployments[0]
    external_secret = external_secrets[0]
    pod_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", [])
    if [container.get("name") for container in containers] != ["maliev-country-service"]:
        errors.append(f"{environment}: pod containers do not match the exact allowlist")
    if not containers:
        return errors
    if pod_spec.get("initContainers") or pod_spec.get("ephemeralContainers"):
        errors.append(f"{environment}: init or ephemeral containers are forbidden")
    if pod_spec.get("volumes"):
        errors.append(f"{environment}: pod volumes are not allowlisted")
    if pod_spec.get("automountServiceAccountToken") is not False:
        errors.append(f"{environment}: service account token projection is forbidden")

    container = containers[0]
    if container.get("envFrom"):
        errors.append(f"{environment}: CountryService must not use envFrom")
    if container.get("volumeMounts"):
        errors.append(f"{environment}: CountryService volumeMounts are not allowlisted")

    expected_probe_paths = {
        "livenessProbe": "/country/liveness",
        "readinessProbe": "/country/readiness",
    }
    actual_probe_paths = {
        probe_name: container.get(probe_name, {}).get("httpGet", {}).get("path")
        for probe_name in expected_probe_paths
    }
    if actual_probe_paths != expected_probe_paths:
        errors.append(
            f"{environment}: health probe paths {actual_probe_paths!r} do not match "
            f"{expected_probe_paths!r}"
        )

    environment_variables = {
        item.get("name"): item for item in container.get("env", []) if item.get("name")
    }
    expected_non_secret_values = {
        "ServiceAuthentication__ClientId": "service-country-service",
        **EXPECTED_ENVIRONMENT_VALUES[environment],
    }
    expected_names = REQUIRED_SECRET_KEYS | set(expected_non_secret_values)
    if set(environment_variables) != expected_names:
        errors.append(
            f"{environment}: environment keys {sorted(environment_variables)!r} do not "
            f"match {sorted(expected_names)!r}"
        )

    actual_secret_references = {
        key: environment_variables.get(key, {}).get("valueFrom", {}).get("secretKeyRef")
        for key in REQUIRED_SECRET_KEYS
    }
    expected_secret_references = {
        key: {"name": "maliev-country-service-secrets", "key": key}
        for key in REQUIRED_SECRET_KEYS
    }
    if actual_secret_references != expected_secret_references:
        errors.append(f"{environment}: secretKeyRef projection is not exact")

    actual_non_secret_values = {
        key: environment_variables.get(key, {}).get("value")
        for key in expected_non_secret_values
    }
    if actual_non_secret_values != expected_non_secret_values:
        errors.append(f"{environment}: non-secret runtime configuration is not exact")

    projection = yaml.safe_dump(
        {
            "containers": containers,
            "initContainers": pod_spec.get("initContainers", []),
            "ephemeralContainers": pod_spec.get("ephemeralContainers", []),
            "volumes": pod_spec.get("volumes", []),
            "externalSecret": external_secret,
        },
        sort_keys=True,
    )
    for token in FORBIDDEN_TOKENS:
        if token in projection:
            errors.append(f"{environment}: forbidden CountryService projection {token!r}")

    actual_spec = dict(external_secret.get("spec", {}))
    if isinstance(actual_spec.get("data"), list):
        actual_spec["data"] = sorted(
            actual_spec["data"],
            key=lambda item: str(item.get("secretKey"))
            if isinstance(item, dict)
            else repr(item),
        )
    normalized_external_secret = dict(external_secret)
    normalized_external_secret["spec"] = actual_spec
    if normalized_external_secret != expected_external_secret(environment):
        errors.append(
            f"{environment}: ExternalSecret does not match the exact object contract"
        )
    return errors


def validate_country_applications_remain_disabled() -> list[str]:
    """Validate disabled app contracts and reject direct or transitive activation."""
    errors: list[str] = []
    disabled = ROOT / "argocd" / "environments" / "_disabled_apps"
    disabled_contracts = {
        "dev": {
            "name": "maliev-country-service-dev",
            "environment": "development",
            "namespace": "maliev-dev",
            "revision": "main",
        },
        "staging": {
            "name": "maliev-country-service-staging",
            "environment": "staging",
            "namespace": "maliev-staging",
            "revision": "main",
        },
        "prod": {
            "name": "maliev-country-service-prod",
            "environment": "production",
            "namespace": "maliev-prod",
            "revision": "v1.0.0",
        },
    }
    for folder, contract in disabled_contracts.items():
        path = disabled / folder / "maliev-country-service.yaml"
        if not path.is_file():
            errors.append(f"missing disabled CountryService Application: {path}")
            continue
        documents = [
            document
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if isinstance(document, dict)
        ]
        if len(documents) != 1:
            errors.append(f"disabled Country manifest must contain one Application: {path}")
            continue
        application = documents[0]
        actual = {
            "apiVersion": application.get("apiVersion"),
            "kind": application.get("kind"),
            "name": application.get("metadata", {}).get("name"),
            "namespace": application.get("metadata", {}).get("namespace"),
            "app": application.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/name"),
            "environment": application.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/environment"),
            "repoURL": application.get("spec", {}).get("source", {}).get("repoURL"),
            "revision": application.get("spec", {})
            .get("source", {})
            .get("targetRevision"),
            "path": application.get("spec", {}).get("source", {}).get("path"),
            "server": application.get("spec", {}).get("destination", {}).get("server"),
            "destination": application.get("spec", {})
            .get("destination", {})
            .get("namespace"),
        }
        expected = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "name": contract["name"],
            "namespace": "argocd",
            "app": "maliev-country-service",
            "environment": contract["environment"],
            "repoURL": GITOPS_REPOSITORY_URL,
            "revision": contract["revision"],
            "path": f"3-apps/maliev-country-service/overlays/{contract['environment']}",
            "server": "https://kubernetes.default.svc",
            "destination": contract["namespace"],
        }
        if actual != expected:
            errors.append(f"disabled Country Application contract is not exact: {path}")

    active_sources: dict[tuple[str, str], dict[str, object]] = {}
    argocd = ROOT / "argocd"
    for manifest in [*argocd.rglob("*.yaml"), *argocd.rglob("*.yml")]:
        if "_disabled_apps" in manifest.parts:
            continue
        for document in yaml.safe_load_all(manifest.read_text(encoding="utf-8")):
            if not isinstance(document, dict) or document.get("kind") not in (
                "Application",
                "ApplicationSet",
            ):
                continue
            kind = document["kind"]
            specification = document.get("spec", {})
            if kind == "ApplicationSet":
                if specification.get("templatePatch") not in (None, "", {}):
                    errors.append(
                        f"active ApplicationSet has templatePatch: {manifest.relative_to(ROOT)}"
                    )
                if contains_non_empty_template_override(specification.get("generators", [])):
                    errors.append(
                        "active ApplicationSet generator overrides its template: "
                        f"{manifest.relative_to(ROOT)}"
                    )
            names, sources = argo_sources(document)
            source_paths = [str(source.get("path", "")) for source in sources]
            direct_reference = any("maliev-country-service" in name for name in names) or any(
                source_can_activate_country(source) for source in sources
            )
            unresolved = kind == "ApplicationSet" and (
                any("{{" in name or "}}" in name for name in names)
                or any("{{" in path or "}}" in path for path in source_paths)
            )
            if direct_reference or unresolved:
                errors.append(
                    f"active {kind} can activate CountryService: {manifest.relative_to(ROOT)}"
                )

            for source in sources:
                repository_class = classify_gitops_repository_url(source.get("repoURL"))
                if repository_class == "unsafe":
                    errors.append(
                        "noncanonical MALIEV GitOps URL in active source: "
                        f"{manifest.relative_to(ROOT)}"
                    )
                if repository_class == "same":
                    source_path = str(source.get("path", ""))
                    if "{{" not in source_path and "}}" not in source_path:
                        contract = yaml.safe_dump(source, sort_keys=True)
                        active_sources.setdefault((source_path, contract), source)

    pending_sources = list(sorted(active_sources.items()))
    processed_sources: set[tuple[str, str]] = set()
    while pending_sources:
        (source_path, source_contract), source = pending_sources.pop(0)
        source_key = (source_path, source_contract)
        if source_key in processed_sources:
            continue
        processed_sources.add(source_key)
        try:
            documents = render_active_in_repo_source(source)
        except (OSError, RuntimeError, yaml.YAMLError) as error:
            errors.append(f"cannot render active source {source_path!r}: {error}")
            continue

        for document in documents:
            if document.get("kind") not in ("Application", "ApplicationSet"):
                continue
            specification = document.get("spec", {})
            if document.get("kind") == "ApplicationSet":
                if specification.get("templatePatch") not in (None, "", {}):
                    errors.append(
                        f"rendered ApplicationSet from {source_path!r} has templatePatch"
                    )
                if contains_non_empty_template_override(
                    specification.get("generators", [])
                ):
                    errors.append(
                        f"rendered ApplicationSet from {source_path!r} has generator "
                        "template overrides"
                    )
            _, child_sources = argo_sources(document)
            for child_source in child_sources:
                repository_class = classify_gitops_repository_url(
                    child_source.get("repoURL")
                )
                if repository_class == "unsafe":
                    errors.append(
                        f"rendered child from {source_path!r} uses a noncanonical "
                        "MALIEV GitOps URL"
                    )
                    continue
                if repository_class != "same":
                    continue
                child_path = str(child_source.get("path", ""))
                if "{{" in child_path or "}}" in child_path:
                    errors.append(
                        f"rendered child from {source_path!r} has dynamic source "
                        f"{child_path!r}"
                    )
                    continue
                child_contract = yaml.safe_dump(child_source, sort_keys=True)
                child_key = (child_path, child_contract)
                if child_key not in processed_sources:
                    pending_sources.append((child_key, child_source))

        identities = sorted(
            {
                (
                    str(document.get("kind", "")),
                    str(document.get("metadata", {}).get("name", "")),
                )
                for document in documents
                if rendered_document_activates_country(document)
            }
        )
        if identities:
            errors.append(
                f"active source {source_path!r} renders CountryService {identities!r}"
            )
    return errors


def main() -> int:
    """Run all CountryService GitOps policy checks."""
    errors: list[str] = []
    for environment in ENVIRONMENTS:
        try:
            errors.extend(validate_country_overlay(environment))
        except (OSError, RuntimeError, yaml.YAMLError) as error:
            errors.append(str(error))
    errors.extend(validate_country_applications_remain_disabled())
    if errors:
        print("CountryService secret projection policy failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("CountryService secret projection policy passed for all environments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
