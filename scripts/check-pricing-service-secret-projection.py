#!/usr/bin/env python3
"""Validate PricingService's least-privilege runtime secret projection."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
PRICING_ROOT = ROOT / "3-apps" / "maliev-pricing-service"
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
        "Services__MaterialService__BaseUrl": "https://dev.api.maliev.com",
        "Services__JobService__BaseUrl": "https://dev.api.maliev.com",
        "Services__CurrencyService__BaseUrl": "https://dev.api.maliev.com",
    },
    "staging": {
        "ASPNETCORE_ENVIRONMENT": "Staging",
        "Services__AuthService__BaseUrl": "https://staging.api.maliev.com",
        "Services__IAMService__BaseUrl": "https://staging.api.maliev.com",
        "Services__MaterialService__BaseUrl": "https://staging.api.maliev.com",
        "Services__JobService__BaseUrl": "https://staging.api.maliev.com",
        "Services__CurrencyService__BaseUrl": "https://staging.api.maliev.com",
    },
    "production": {
        "ASPNETCORE_ENVIRONMENT": "Production",
        "Services__AuthService__BaseUrl": "https://api.maliev.com",
        "Services__IAMService__BaseUrl": "https://api.maliev.com",
        "Services__MaterialService__BaseUrl": "https://api.maliev.com",
        "Services__JobService__BaseUrl": "https://api.maliev.com",
        "Services__CurrencyService__BaseUrl": "https://api.maliev.com",
    },
}
EXPECTED_HPA_BOUNDS = {
    "development": (1, 1),
    "staging": (1, 3),
    "production": (1, 3),
}


def expected_probe_contracts(environment: str) -> dict[str, dict[str, object]]:
    """Return the complete reviewed Kubernetes probe objects for one environment."""
    if environment == "development":
        initial_delay = 60
        period = 10
        timeout = 5
    elif environment in ("staging", "production"):
        initial_delay = 10
        period = 5
        timeout = 3
    else:
        raise ValueError(f"unsupported environment: {environment}")
    common = {
        "initialDelaySeconds": initial_delay,
        "periodSeconds": period,
        "timeoutSeconds": timeout,
        "failureThreshold": 3,
    }
    return {
        "livenessProbe": {
            "httpGet": {"path": "/pricing/liveness", "port": 8080},
            **common,
        },
        "readinessProbe": {
            "httpGet": {"path": "/pricing/readiness", "port": 8080},
            **common,
            "successThreshold": 1,
        },
    }


def expected_startup_probe_contract() -> dict[str, object]:
    """Return the reviewed five-minute migration and seed startup budget."""
    return {
        "httpGet": {"path": "/pricing/liveness", "port": 8080},
        "periodSeconds": 5,
        "timeoutSeconds": 3,
        "failureThreshold": 60,
    }


REQUIRED_SECRET_KEYS = {
    "Jwt__PublicKey",
    "Jwt__Issuer",
    "Jwt__Audience",
    "ServiceAuthentication__ClientSecret",
    "ConnectionStrings__PricingDbContext",
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
        ("Service", "maliev-pricing-service"): 1,
        ("Deployment", "maliev-pricing-service"): 1,
        ("HorizontalPodAutoscaler", "maliev-pricing-service-hpa"): 1,
        ("ExternalSecret", "maliev-pricing-service-secrets"): 1,
        ("ServiceMonitor", "maliev-pricing-service"): 1,
    }
)
PRICING_RENDERED_IDENTITIES = set(EXPECTED_RENDERED_INVENTORY)
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
ACTIVE_GITOPS_TARGET_REVISION = "main"
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

    try:
        decoded_repository_path = unquote(repository_path, errors="strict")
    except UnicodeDecodeError:
        return "unsafe" if "maliev-gitops" in repository_url.casefold() else "other"

    normalized_path = decoded_repository_path.strip("/")
    if normalized_path.casefold().endswith(".git"):
        normalized_path = normalized_path[:-4]
    parts = normalized_path.split("/")
    is_this_repository = len(parts) == 2 and (
        parts[0].casefold() == GITOPS_REPOSITORY_OWNER
        and parts[1].casefold() == GITOPS_REPOSITORY_NAME
    )
    if not is_this_repository:
        return "other"
    return (
        "same"
        if approved_transport and repository_url == GITOPS_REPOSITORY_URL
        else "unsafe"
    )


def validate_active_same_repository_revision(
    source: dict[str, object], source_label: str
) -> list[str]:
    """Require active same-repository sources to select the reviewed Argo branch."""
    if classify_gitops_repository_url(source.get("repoURL")) not in ("same", "unsafe"):
        return []
    revision = source.get("targetRevision")
    if revision == ACTIVE_GITOPS_TARGET_REVISION:
        return []
    return [
        f"active same-repository source {source_label} must target "
        f"{ACTIVE_GITOPS_TARGET_REVISION!r}; found {revision!r}"
    ]


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


def source_can_activate_pricing(source: object) -> bool:
    """Fail closed when an Argo source directly or recursively reaches PricingService."""
    if not isinstance(source, dict):
        return False
    source_path = str(source.get("path", "")).strip("/")
    if source_path == ".":
        source_path = ""
    pricing_path = "3-apps/maliev-pricing-service"
    if "{{" in source_path or "}}" in source_path:
        return True
    if ".." in source_path.split("/"):
        return True
    if source_path == pricing_path or source_path.startswith(f"{pricing_path}/"):
        return True

    directory = source.get("directory")
    is_pricing_ancestor = not source_path or pricing_path.startswith(f"{source_path}/")
    if is_pricing_ancestor and isinstance(directory, dict):
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


def image_is_pricing_runtime(value: object) -> bool:
    """Match the canonical PricingService image regardless of registry, tag, or digest."""
    image = str(value or "").strip()
    if not image:
        return False
    image_name = image.rsplit("/", 1)[-1].split("@", 1)[0].split(":", 1)[0]
    return image_name.casefold() == "maliev-pricing-service"


def workload_uses_pricing_runtime(document: dict[str, object]) -> bool:
    """Detect Pricing runtime identity even when workload resources are renamed."""
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
    if any(image_is_pricing_runtime(container.get("image")) for container in containers):
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
    if "maliev-pricing-service" in label_values:
        return True

    return "maliev-pricing-service-secrets" in yaml.safe_dump(
        pod_spec, sort_keys=True
    )


def rendered_document_activates_pricing(document: dict[str, object]) -> bool:
    """Return true when a rendered resource activates PricingService."""
    identity = (
        document.get("kind"),
        document.get("metadata", {}).get("name"),
    )
    if identity in PRICING_RENDERED_IDENTITIES:
        return True
    if workload_uses_pricing_runtime(document):
        return True
    if document.get("kind") not in ("Application", "ApplicationSet"):
        return False
    names, sources = argo_sources(document)
    return any("maliev-pricing-service" in name for name in names) or any(
        source_can_activate_pricing(source) for source in sources
    )


def expected_external_secret(environment: str) -> dict[str, object]:
    """Return the complete reviewed ExternalSecret contract for one environment."""
    shared_key = f"{ENVIRONMENT_PREFIXES[environment]}-shared-config"
    pricing_key = f"{ENVIRONMENT_PREFIXES[environment]}-pricing-service-config"
    remote_keys = {
        "Jwt__PublicKey": shared_key,
        "Jwt__Issuer": shared_key,
        "Jwt__Audience": shared_key,
        "ConnectionStrings__rabbitmq": shared_key,
        "ConnectionStrings__redis": shared_key,
        "CORS__AllowedOrigins": shared_key,
        "ConnectionStrings__PricingDbContext": pricing_key,
        "ServiceAuthentication__ClientSecret": pricing_key,
    }
    return {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {
            "name": "maliev-pricing-service-secrets",
            "namespace": ENVIRONMENT_NAMESPACES[environment],
        },
        "spec": {
            "secretStoreRef": {
                "kind": "ClusterSecretStore",
                "name": "gcp-secret-manager",
            },
            "target": {
                "name": "maliev-pricing-service-secrets",
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


def resolve_kustomize_source_documents(
    kustomize_root: Path,
) -> tuple[
    list[tuple[str, dict[str, object]]],
    list[tuple[str, dict[str, object], list[dict[str, object]]]],
    list[str],
]:
    """Resolve the reviewed local Kustomize graph without leaving this repository."""
    documents: list[tuple[str, dict[str, object]]] = []
    json_patches: list[
        tuple[str, dict[str, object], list[dict[str, object]]]
    ] = []
    errors: list[str] = []
    repository_root = ROOT.resolve()
    visited_kustomizations: set[Path] = set()
    active_kustomizations: set[Path] = set()

    def safe_reference(parent: Path, value: object, context: str) -> Path | None:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{context}: local path must be a non-empty string")
            return None
        reference = value.strip()
        if any(token in reference for token in ("{{", "}}", "*", "?", "[", "]")):
            errors.append(f"{context}: ambiguous local path {reference!r}")
            return None
        reference_path = Path(reference)
        if reference_path.is_absolute() or "://" in reference or reference.startswith("git@"):
            errors.append(f"{context}: non-local path {reference!r} is forbidden")
            return None
        unresolved = parent / reference_path
        if any(candidate.is_symlink() for candidate in [unresolved, *unresolved.parents]):
            errors.append(f"{context}: symlinked path {reference!r} is forbidden")
            return None
        candidate = unresolved.resolve()
        try:
            candidate.relative_to(repository_root)
        except ValueError:
            errors.append(f"{context}: path escapes repository: {reference!r}")
            return None
        if not candidate.exists():
            errors.append(f"{context}: referenced path does not exist: {reference!r}")
            return None
        return candidate

    def load_yaml_documents(path: Path, label: str) -> list[dict[str, object]]:
        if path.suffix.casefold() not in (".yaml", ".yml") and path.name not in (
            "Kustomization",
        ):
            errors.append(f"{label}: referenced file is not YAML")
            return []
        loaded = [
            document
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if isinstance(document, dict)
        ]
        documents.extend((label, document) for document in loaded)
        return loaded

    def resolve_reference(parent: Path, value: object, context: str) -> None:
        candidate = safe_reference(parent, value, context)
        if candidate is None:
            return
        if candidate.is_dir():
            candidates = [
                candidate / filename
                for filename in KUSTOMIZATION_FILENAMES
                if (candidate / filename).is_file()
                or (candidate / filename).is_symlink()
            ]
            if len(candidates) != 1:
                errors.append(
                    f"{context}: directory must contain exactly one Kustomization file: "
                    f"{candidate.relative_to(repository_root)}"
                )
                return
            if candidates[0].is_symlink():
                errors.append(
                    f"{context}: implicit Kustomization file is symlinked: "
                    f"{candidates[0].relative_to(repository_root)}"
                )
                return
            visit_kustomization(candidates[0])
            return
        label = str(candidate.relative_to(repository_root)).replace("\\", "/")
        loaded = load_yaml_documents(candidate, label)
        if any(
            document.get("kind") in ("Kustomization", "Component")
            for document in loaded
        ):
            visit_kustomization(candidate, loaded)

    def record_json_patch(
        value: object,
        context: str,
        target: object,
    ) -> bool:
        if not isinstance(value, list):
            return False
        if not value:
            errors.append(f"{context}: JSON6902 patch must contain operations")
            return True
        operations: list[dict[str, object]] = []
        for index, operation in enumerate(value):
            if not isinstance(operation, dict):
                errors.append(
                    f"{context}[{index}]: JSON6902 operation must be an object"
                )
                continue
            if not isinstance(operation.get("op"), str) or not isinstance(
                operation.get("path"), str
            ):
                errors.append(
                    f"{context}[{index}]: JSON6902 operation needs string op and path"
                )
                continue
            operations.append(operation)
        if operations:
            json_patches.append(
                (context, target if isinstance(target, dict) else {}, operations)
            )
        return True

    def resolve_inline_patch(
        value: object,
        context: str,
        target: object = None,
    ) -> None:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{context}: inline patch must be non-empty YAML")
            return
        loaded = list(yaml.safe_load_all(value))
        if len(loaded) == 1 and record_json_patch(loaded[0], context, target):
            return
        object_documents = [
            document for document in loaded if isinstance(document, dict)
        ]
        if not object_documents or len(object_documents) != len(loaded):
            errors.append(f"{context}: inline patch must contain a YAML object")
            return
        documents.extend((context, document) for document in object_documents)

    def resolve_patch_reference(
        parent: Path,
        value: object,
        context: str,
        target: object,
    ) -> None:
        candidate = safe_reference(parent, value, context)
        if candidate is None:
            return
        if not candidate.is_file():
            errors.append(f"{context}: patch path must reference a file")
            return
        label = str(candidate.relative_to(repository_root)).replace("\\", "/")
        if candidate.suffix.casefold() not in (".json", ".yaml", ".yml"):
            errors.append(f"{label}: patch file must be JSON or YAML")
            return
        loaded = list(yaml.safe_load_all(candidate.read_text(encoding="utf-8")))
        if len(loaded) == 1 and record_json_patch(loaded[0], label, target):
            return
        object_documents = [
            document for document in loaded if isinstance(document, dict)
        ]
        if not object_documents or len(object_documents) != len(loaded):
            errors.append(
                f"{label}: patch must contain YAML objects or JSON6902 operations"
            )
            return
        documents.extend((label, document) for document in object_documents)

    def visit_kustomization(
        path: Path,
        loaded_documents: list[dict[str, object]] | None = None,
    ) -> None:
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(repository_root)
        except ValueError:
            errors.append(f"Kustomization escapes repository: {path}")
            return
        if resolved_path in active_kustomizations:
            errors.append(
                f"cyclic Kustomization graph: {resolved_path.relative_to(repository_root)}"
            )
            return
        if resolved_path in visited_kustomizations:
            return
        visited_kustomizations.add(resolved_path)
        active_kustomizations.add(resolved_path)
        label = str(resolved_path.relative_to(repository_root)).replace("\\", "/")
        loaded = loaded_documents or load_yaml_documents(resolved_path, label)
        kustomizations = [
            document
            for document in loaded
            if document.get("kind") in ("Kustomization", "Component")
        ]
        if len(kustomizations) != 1:
            errors.append(f"{label}: expected exactly one Kustomization or Component")
            active_kustomizations.remove(resolved_path)
            return
        kustomization = kustomizations[0]
        parent = resolved_path.parent
        for field in ("resources", "bases", "components"):
            references = kustomization.get(field, [])
            if not isinstance(references, list):
                errors.append(f"{label}: {field} must be a list")
                continue
            for index, reference in enumerate(references):
                resolve_reference(parent, reference, f"{label}:{field}[{index}]")

        patches = kustomization.get("patches", [])
        if not isinstance(patches, list):
            errors.append(f"{label}: patches must be a list")
        else:
            for index, patch in enumerate(patches):
                context = f"{label}:patches[{index}]"
                if not isinstance(patch, dict):
                    errors.append(f"{context}: patch must be an object")
                    continue
                has_path = patch.get("path") not in (None, "")
                has_inline = patch.get("patch") not in (None, "")
                if has_path == has_inline:
                    errors.append(f"{context}: patch must have exactly one of path or patch")
                elif has_path:
                    resolve_patch_reference(
                        parent, patch["path"], context, patch.get("target")
                    )
                else:
                    resolve_inline_patch(
                        patch["patch"], f"{context}:inline", patch.get("target")
                    )

        json_6902_patches = kustomization.get("patchesJson6902", [])
        if not isinstance(json_6902_patches, list):
            errors.append(f"{label}: patchesJson6902 must be a list")
        else:
            for index, patch in enumerate(json_6902_patches):
                context = f"{label}:patchesJson6902[{index}]"
                if not isinstance(patch, dict):
                    errors.append(f"{context}: patch must be an object")
                    continue
                has_path = patch.get("path") not in (None, "")
                has_inline = patch.get("patch") not in (None, "")
                if has_path == has_inline:
                    errors.append(f"{context}: patch must have exactly one of path or patch")
                elif has_path:
                    resolve_patch_reference(
                        parent, patch["path"], context, patch.get("target")
                    )
                else:
                    resolve_inline_patch(
                        patch["patch"], f"{context}:inline", patch.get("target")
                    )

        strategic_merges = kustomization.get("patchesStrategicMerge", [])
        if not isinstance(strategic_merges, list):
            errors.append(f"{label}: patchesStrategicMerge must be a list")
        else:
            for index, patch in enumerate(strategic_merges):
                context = f"{label}:patchesStrategicMerge[{index}]"
                if isinstance(patch, dict):
                    documents.append((f"{context}:inline", patch))
                elif isinstance(patch, str) and "\n" in patch:
                    resolve_inline_patch(patch, f"{context}:inline")
                else:
                    resolve_reference(parent, patch, context)
        active_kustomizations.remove(resolved_path)

    root_candidate = safe_reference(
        repository_root,
        str(kustomize_root.resolve().relative_to(repository_root)),
        "Pricing Kustomize root",
    )
    if root_candidate is not None:
        resolve_reference(
            repository_root,
            str(root_candidate.relative_to(repository_root)),
            "Pricing Kustomize root",
        )
    return documents, json_patches, errors


def json_patch_touches_secret_boundary(
    target: dict[str, object], operation: dict[str, object]
) -> bool:
    """Identify source operations that mutate a reviewed secret projection boundary."""
    raw_path = str(operation.get("path", ""))
    path_parts = [
        part.replace("~1", "/").replace("~0", "~")
        for part in raw_path.split("/")[1:]
    ]
    folded_parts = {part.casefold() for part in path_parts}
    target_kind = str(target.get("kind", "")).casefold()
    if folded_parts.intersection(
        {
            "envfrom",
            "remoteref",
            "secret",
            "secretkeyref",
            "secretname",
            "secrets",
            "secretstoreref",
        }
    ):
        return True
    if len(path_parts) >= 2 and path_parts[0] == "spec" and path_parts[1] in {
        "data",
        "dataFrom",
        "secretStoreRef",
        "target",
    }:
        return True
    if target_kind == "deployment" and "env" in folded_parts:
        return True
    if target_kind == "externalsecret" and (
        raw_path.startswith("/spec/data/")
        or raw_path in ("/spec/data", "/spec/dataFrom")
        or raw_path.startswith("/spec/dataFrom/")
    ):
        return True

    def contains_secret_value(value: object) -> bool:
        if isinstance(value, dict):
            if any(
                str(key).casefold()
                in {
                    "datafrom",
                    "envfrom",
                    "remoteref",
                    "secretkeyref",
                    "secretname",
                    "secretstoreref",
                }
                for key in value
            ):
                return True
            return any(contains_secret_value(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_secret_value(item) for item in value)
        return False

    return contains_secret_value(operation.get("value"))


def validate_source_environment_lists(environment: str) -> list[str]:
    """Reject duplicate env names across the real source graph before rendering."""
    source_documents, json_patches, errors = resolve_kustomize_source_documents(
        PRICING_ROOT / "overlays" / environment
    )
    for source_label, target, operations in json_patches:
        for index, operation in enumerate(operations):
            if json_patch_touches_secret_boundary(target, operation):
                errors.append(
                    f"{environment}: {source_label}[{index}] touches a "
                    "secret-bearing JSON6902 boundary"
                )
    for source_label, document in source_documents:
        if (
            document.get("kind") != "Deployment"
            or document.get("metadata", {}).get("name")
            != "maliev-pricing-service"
        ):
            continue
        pod_spec = document.get("spec", {}).get("template", {}).get("spec", {})
        for container_set in ("containers", "initContainers", "ephemeralContainers"):
            containers = pod_spec.get(container_set, [])
            if not isinstance(containers, list):
                errors.append(f"{environment}: {source_label} {container_set} must be a list")
                continue
            for container in containers:
                if not isinstance(container, dict) or "env" not in container:
                    continue
                environment_entries = container.get("env")
                if not isinstance(environment_entries, list):
                    errors.append(f"{environment}: {source_label} source env must be a list")
                    continue
                names = [
                    str(entry.get("name", ""))
                    for entry in environment_entries
                    if isinstance(entry, dict)
                ]
                duplicate_names = sorted(
                    name
                    for name, count in Counter(names).items()
                    if name and count > 1
                )
                if duplicate_names:
                    errors.append(
                        f"{environment}: {source_label} source env list has duplicate "
                        f"names {duplicate_names!r}"
                    )
    return errors


def validate_pricing_overlay(environment: str) -> list[str]:
    """Validate exact rendered inventory, pod projection, and ExternalSecret."""
    errors = validate_source_environment_lists(environment)
    if errors:
        return errors
    rendered = render(PRICING_ROOT / "overlays" / environment)
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
        and document.get("metadata", {}).get("name") == "maliev-pricing-service"
    ]
    services = [
        document
        for document in documents
        if document.get("kind") == "Service"
        and document.get("metadata", {}).get("name") == "maliev-pricing-service"
    ]
    horizontal_pod_autoscalers = [
        document
        for document in documents
        if document.get("kind") == "HorizontalPodAutoscaler"
        and document.get("metadata", {}).get("name")
        == "maliev-pricing-service-hpa"
    ]
    external_secrets = [
        document
        for document in documents
        if document.get("kind") == "ExternalSecret"
        and document.get("metadata", {}).get("name")
        == "maliev-pricing-service-secrets"
    ]
    if (
        len(deployments) != 1
        or len(services) != 1
        or len(horizontal_pod_autoscalers) != 1
        or len(external_secrets) != 1
    ):
        errors.append(
            f"{environment}: exactly one Pricing Deployment, Service, HPA, and "
            "ExternalSecret must render"
        )
        return errors

    deployment = deployments[0]
    service = services[0]
    horizontal_pod_autoscaler = horizontal_pod_autoscalers[0]
    external_secret = external_secrets[0]
    if "replicas" in deployment.get("spec", {}):
        errors.append(f"{environment}: deployment replicas must remain HPA-owned")

    expected_service_spec = {
        "type": "ClusterIP",
        "selector": {"app": "maliev-pricing-service"},
        "ports": [{"name": "http", "port": 80, "targetPort": 8080}],
    }
    if service.get("spec") != expected_service_spec:
        errors.append(f"{environment}: Service contract is not exact")

    expected_minimum, expected_maximum = EXPECTED_HPA_BOUNDS[environment]
    hpa_spec = horizontal_pod_autoscaler.get("spec", {})
    expected_hpa_contract = {
        "scaleTargetRef": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "maliev-pricing-service",
        },
        "minReplicas": expected_minimum,
        "maxReplicas": expected_maximum,
        "metrics": [
            {
                "type": "Resource",
                "resource": {
                    "name": "cpu",
                    "target": {
                        "type": "Utilization",
                        "averageUtilization": 80,
                    },
                },
            }
        ],
    }
    if hpa_spec != expected_hpa_contract:
        errors.append(f"{environment}: HPA contract is not exact")

    pod_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", [])
    if [container.get("name") for container in containers] != ["maliev-pricing-service"]:
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
        errors.append(f"{environment}: PricingService must not use envFrom")
    if container.get("volumeMounts"):
        errors.append(f"{environment}: PricingService volumeMounts are not allowlisted")

    expected_probes = expected_probe_contracts(environment)
    actual_probes = {
        probe_name: container.get(probe_name) for probe_name in expected_probes
    }
    if actual_probes != expected_probes:
        errors.append(f"{environment}: health probe contract is not exact")
    if container.get("startupProbe") != expected_startup_probe_contract():
        errors.append(f"{environment}: startup probe contract is not exact")

    raw_environment_entries = container.get("env", [])
    if not isinstance(raw_environment_entries, list):
        errors.append(f"{environment}: environment entries must be a list")
        raw_environment_entries = []
    environment_entries = [
        item for item in raw_environment_entries if isinstance(item, dict)
    ]
    if len(environment_entries) != len(raw_environment_entries):
        errors.append(f"{environment}: every environment entry must be an object")
    environment_name_counts = Counter(
        str(item.get("name", "")) for item in environment_entries
    )
    duplicate_environment_names = sorted(
        name for name, count in environment_name_counts.items() if name and count > 1
    )
    if duplicate_environment_names:
        errors.append(
            f"{environment}: duplicate environment variable names "
            f"{duplicate_environment_names!r} are forbidden"
        )
    environment_variables = {
        item.get("name"): item for item in environment_entries if item.get("name")
    }
    expected_non_secret_values = {
        "ServiceAuthentication__ClientId": "service-pricing-service",
        **EXPECTED_ENVIRONMENT_VALUES[environment],
    }
    expected_names = REQUIRED_SECRET_KEYS | set(expected_non_secret_values)
    expected_environment_entries = [
        {
            "name": key,
            "valueFrom": {
                "secretKeyRef": {
                    "name": "maliev-pricing-service-secrets",
                    "key": key,
                }
            },
        }
        for key in sorted(REQUIRED_SECRET_KEYS)
    ] + [
        {"name": key, "value": value}
        for key, value in sorted(expected_non_secret_values.items())
    ]
    actual_entry_contract = Counter(
        yaml.safe_dump(item, sort_keys=True) for item in environment_entries
    )
    expected_entry_contract = Counter(
        yaml.safe_dump(item, sort_keys=True) for item in expected_environment_entries
    )
    if actual_entry_contract != expected_entry_contract:
        errors.append(f"{environment}: environment entry projection is not exact")
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
        key: {"name": "maliev-pricing-service-secrets", "key": key}
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
            errors.append(f"{environment}: forbidden PricingService projection {token!r}")

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


def validate_pricing_applications_remain_disabled() -> list[str]:
    """Validate disabled app contracts and reject direct or transitive activation."""
    errors: list[str] = []
    disabled = ROOT / "argocd" / "environments" / "_disabled_apps"
    disabled_contracts = {
        "dev": {
            "name": "maliev-pricing-service-dev",
            "environment": "development",
            "namespace": "maliev-dev",
            "revision": "main",
        },
        "staging": {
            "name": "maliev-pricing-service-staging",
            "environment": "staging",
            "namespace": "maliev-staging",
            "revision": "main",
        },
        "prod": {
            "name": "maliev-pricing-service-prod",
            "environment": "production",
            "namespace": "maliev-prod",
            "revision": "v1.0.0",
        },
    }
    for folder, contract in disabled_contracts.items():
        path = disabled / folder / "maliev-pricing-service.yaml"
        if not path.is_file():
            errors.append(f"missing disabled PricingService Application: {path}")
            continue
        documents = [
            document
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if isinstance(document, dict)
        ]
        if len(documents) != 1:
            errors.append(f"disabled Pricing manifest must contain one Application: {path}")
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
            "app": "maliev-pricing-service",
            "environment": contract["environment"],
            "repoURL": GITOPS_REPOSITORY_URL,
            "revision": contract["revision"],
            "path": f"3-apps/maliev-pricing-service/overlays/{contract['environment']}",
            "server": "https://kubernetes.default.svc",
            "destination": contract["namespace"],
        }
        if actual != expected:
            errors.append(f"disabled Pricing Application contract is not exact: {path}")

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
            direct_reference = any("maliev-pricing-service" in name for name in names) or any(
                source_can_activate_pricing(source) for source in sources
            )
            unresolved = kind == "ApplicationSet" and (
                any("{{" in name or "}}" in name for name in names)
                or any("{{" in path or "}}" in path for path in source_paths)
            )
            if direct_reference or unresolved:
                errors.append(
                    f"active {kind} can activate PricingService: {manifest.relative_to(ROOT)}"
                )

            for source in sources:
                repository_class = classify_gitops_repository_url(source.get("repoURL"))
                errors.extend(
                    validate_active_same_repository_revision(
                        source, str(manifest.relative_to(ROOT))
                    )
                )
                if repository_class == "unsafe":
                    errors.append(
                        "noncanonical MALIEV GitOps URL in active source: "
                        f"{manifest.relative_to(ROOT)}"
                    )
                if repository_class in ("same", "unsafe"):
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
                errors.extend(
                    validate_active_same_repository_revision(
                        child_source, f"rendered child from {source_path!r}"
                    )
                )
                if repository_class == "unsafe":
                    errors.append(
                        f"rendered child from {source_path!r} uses a noncanonical "
                        "MALIEV GitOps URL"
                    )
                if repository_class not in ("same", "unsafe"):
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
                if rendered_document_activates_pricing(document)
            }
        )
        if identities:
            errors.append(
                f"active source {source_path!r} renders PricingService {identities!r}"
            )
    return errors


def main() -> int:
    """Run all PricingService GitOps policy checks."""
    errors: list[str] = []
    for environment in ENVIRONMENTS:
        try:
            errors.extend(validate_pricing_overlay(environment))
        except (OSError, RuntimeError, yaml.YAMLError) as error:
            errors.append(str(error))
    errors.extend(validate_pricing_applications_remain_disabled())
    if errors:
        print("PricingService secret projection policy failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PricingService secret projection policy passed for all environments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
