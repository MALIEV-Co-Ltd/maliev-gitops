#!/usr/bin/env python3
"""Validate ContactService's least-privilege runtime secret projection."""

from __future__ import annotations

import subprocess
import sys
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
    deployment = next(
        (
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "maliev-contact-service"
        ),
        None,
    )
    external_secret = next(
        (
            document
            for document in documents
            if document.get("kind") == "ExternalSecret"
            and document.get("metadata", {}).get("name")
            == "maliev-contact-service-secrets"
        ),
        None,
    )

    if deployment is None:
        return [f"{environment}: ContactService Deployment did not render"]
    if external_secret is None:
        return [f"{environment}: ContactService ExternalSecret did not render"]

    containers = deployment["spec"]["template"]["spec"].get("containers", [])
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

    contact_projection = yaml.safe_dump(
        {"env": container.get("env", []), "envFrom": container.get("envFrom", [])},
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
    actual_non_secret_values = {
        key: environment_variables.get(key, {}).get("value")
        for key in expected_non_secret_values
    }
    if actual_non_secret_values != expected_non_secret_values:
        errors.append(
            f"{environment}: ContactService non-secret runtime configuration does not "
            "match the reviewed environment contract"
        )

    if external_secret.get("spec", {}).get("dataFrom"):
        errors.append(f"{environment}: ContactService ExternalSecret must not use dataFrom")

    mapped_secret_keys = {
        item.get("secretKey")
        for item in external_secret.get("spec", {}).get("data", [])
    }
    if mapped_secret_keys != REQUIRED_SECRET_KEYS:
        errors.append(
            f"{environment}: ContactService ExternalSecret keys are "
            f"{sorted(key for key in mapped_secret_keys if key)!r}; expected "
            f"{sorted(REQUIRED_SECRET_KEYS)!r}"
        )

    expected_remote_mappings = {
        "Jwt__PublicKey": (
            f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "Jwt__PublicKey",
        ),
        "Jwt__Issuer": (
            f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "Jwt__Issuer",
        ),
        "Jwt__Audience": (
            f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "Jwt__Audience",
        ),
        "ServiceAuthentication__ClientSecret": (
            f"{ENVIRONMENT_PREFIXES[environment]}-contact-service-config",
            "ServiceAuthentication__ClientSecret",
        ),
        "ConnectionStrings__ContactDbContext": (
            f"{ENVIRONMENT_PREFIXES[environment]}-contact-service-config",
            "ConnectionStrings__ContactDbContext",
        ),
        "ConnectionStrings__rabbitmq": (
            f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "ConnectionStrings__rabbitmq",
        ),
        "ConnectionStrings__redis": (
            f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "ConnectionStrings__redis",
        ),
        "CORS__AllowedOrigins": (
            f"{ENVIRONMENT_PREFIXES[environment]}-shared-config",
            "CORS__AllowedOrigins",
        ),
    }
    actual_remote_mappings = {
        item.get("secretKey"): (
            item.get("remoteRef", {}).get("key"),
            item.get("remoteRef", {}).get("property"),
        )
        for item in external_secret.get("spec", {}).get("data", [])
    }
    if actual_remote_mappings != expected_remote_mappings:
        errors.append(
            f"{environment}: ContactService ExternalSecret remote mappings do not "
            "match the environment-specific property allowlist"
        )

    return errors


def validate_contact_applications_remain_disabled() -> list[str]:
    errors: list[str] = []
    disabled = ROOT / "argocd" / "environments" / "_disabled_apps"
    for environment in ("dev", "staging", "prod"):
        expected = disabled / environment / "maliev-contact-service.yaml"
        if not expected.is_file():
            errors.append(f"missing disabled ContactService Application: {expected}")

        active_root = ROOT / "argocd" / "environments" / environment
        for manifest in active_root.rglob("*.yaml"):
            if "maliev-contact-service" in manifest.read_text(encoding="utf-8"):
                errors.append(
                    "ContactService Application must remain disabled; active reference found "
                    f"in {manifest.relative_to(ROOT)}"
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
