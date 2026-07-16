#!/usr/bin/env python3
"""Render and validate the disabled AuthService ingress route manifests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROUTES = {
    "staging": {
        "source": ROOT / "2-environments" / "2-staging" / "ingress.yaml",
        "namespace": "maliev-staging",
        "host": "staging.api.maliev.com",
    },
    "production": {
        "source": ROOT / "2-environments" / "3-production" / "ingress.yaml",
        "namespace": "maliev-prod",
        "host": "api.maliev.com",
    },
}


def render(source: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="auth-ingress-") as directory:
        render_root = Path(directory)
        (render_root / "ingress.yaml").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (render_root / "kustomization.yaml").write_text(
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            "  - ingress.yaml\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            ["kustomize", "build", str(render_root)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    if completed.returncode != 0:
        raise AssertionError(
            f"kustomize could not render {source.relative_to(ROOT)}:\n{completed.stderr}"
        )

    manifests = list(yaml.safe_load_all(completed.stdout))
    if len(manifests) != 1 or manifests[0].get("kind") != "Ingress":
        raise AssertionError(
            f"{source.relative_to(ROOT)} must render exactly one Ingress"
        )
    return manifests[0]


def validate_route(environment: str, expected: dict) -> None:
    manifest = render(expected["source"])
    assert manifest.get("apiVersion") == "networking.k8s.io/v1", (
        f"{environment}: expected networking.k8s.io/v1 Ingress"
    )
    assert manifest.get("metadata", {}).get("namespace") == expected["namespace"], (
        f"{environment}: unexpected ingress namespace"
    )

    rules = manifest.get("spec", {}).get("rules", [])
    matching_rules = [rule for rule in rules if rule.get("host") == expected["host"]]
    assert len(matching_rules) == 1, (
        f"{environment}: expected exactly one rule for {expected['host']}"
    )

    paths = matching_rules[0].get("http", {}).get("paths", [])
    auth_paths = [path for path in paths if path.get("path") == "/auth"]
    assert len(auth_paths) == 1, (
        f"{environment}: expected exactly one /auth path entry"
    )

    auth_path = auth_paths[0]
    assert auth_path.get("pathType") == "Prefix", (
        f"{environment}: /auth pathType must be nested in the /auth path entry"
    )
    service = auth_path.get("backend", {}).get("service", {})
    assert service.get("name") == "maliev-auth-service", (
        f"{environment}: /auth backend must target maliev-auth-service"
    )
    assert service.get("port", {}).get("number") == 8080, (
        f"{environment}: /auth backend must target service port 8080"
    )


def main() -> int:
    failures: list[str] = []
    for environment, expected in EXPECTED_ROUTES.items():
        try:
            validate_route(environment, expected)
        except (AssertionError, OSError, yaml.YAMLError) as error:
            failures.append(str(error))

    if failures:
        print("AuthService ingress route validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("AuthService staging and production ingress routes are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
