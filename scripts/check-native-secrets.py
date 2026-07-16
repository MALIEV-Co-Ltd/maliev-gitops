#!/usr/bin/env python3
"""Fail-closed policy for tracked native Kubernetes Secret manifests."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "scripts" / "native-secret-allowlist.json"
ISSUE_PATTERN = re.compile(
    r"^https://github\.com/MALIEV-Co-Ltd/maliev-ops/issues/[1-9][0-9]*$",
    re.ASCII,
)
ALLOWLIST_KEYS = {
    "path",
    "document",
    "apiVersion",
    "name",
    "namespace",
    "issue",
}


class ScannerFailure(RuntimeError):
    """Raised when the scanner cannot establish a trustworthy result."""


@dataclass(frozen=True, order=True)
class SecretIdentity:
    """Non-sensitive identity of one native Secret document."""

    path: str
    document: int
    api_version: str
    name: str
    namespace: str | None

    def describe(self) -> str:
        """Return safe evidence without serializing Secret data or stringData."""
        namespace = self.namespace if self.namespace is not None else "<unset>"
        return (
            f"{self.path} document {self.document}: "
            f"{self.api_version} Secret {namespace}/{self.name}"
        )


def normalized_relative_path(value: object, *, field: str) -> str:
    """Validate a repository-relative POSIX path without traversal."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ScannerFailure(f"{field} must be a non-empty trimmed path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ScannerFailure(f"{field} must remain inside the repository")
    normalized = path.as_posix()
    if normalized in ("", "."):
        raise ScannerFailure(f"{field} must name a repository file")
    return normalized


def enumerate_tracked_yaml(root: Path) -> list[str]:
    """Return deterministic tracked YAML paths or fail closed on Git errors."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.yaml", "*.yml"],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise ScannerFailure(f"could not enumerate tracked YAML: {error}") from error
    if completed.returncode != 0:
        diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ScannerFailure(
            "could not enumerate tracked YAML"
            + (f": {diagnostic}" if diagnostic else "")
        )
    try:
        paths = [
            normalized_relative_path(item, field="tracked YAML path")
            for item in completed.stdout.decode("utf-8", errors="strict").split("\0")
            if item
        ]
    except UnicodeError as error:
        raise ScannerFailure("could not decode tracked YAML paths as UTF-8") from error
    if len(paths) != len(set(paths)):
        raise ScannerFailure("Git returned duplicate tracked YAML paths")
    return sorted(paths)


def load_allowlist(path: Path) -> dict[SecretIdentity, str]:
    """Load exact native Secret exceptions, each backed by a management issue."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ScannerFailure(f"could not load native Secret allowlist {path}: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"allowedNativeSecrets"}:
        raise ScannerFailure(
            "native Secret allowlist must contain only allowedNativeSecrets"
        )
    entries = payload["allowedNativeSecrets"]
    if not isinstance(entries, list):
        raise ScannerFailure("allowedNativeSecrets must be a list")

    allowlist: dict[SecretIdentity, str] = {}
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != ALLOWLIST_KEYS:
            raise ScannerFailure(
                f"native Secret allowlist entry {index} has an invalid field set"
            )
        relative_path = normalized_relative_path(
            entry["path"], field=f"allowlist entry {index} path"
        )
        document = entry["document"]
        api_version = entry["apiVersion"]
        name = entry["name"]
        namespace = entry["namespace"]
        issue = entry["issue"]
        if not isinstance(document, int) or isinstance(document, bool) or document < 1:
            raise ScannerFailure(f"allowlist entry {index} document must be positive")
        if api_version != "v1":
            raise ScannerFailure(f"allowlist entry {index} apiVersion must be v1")
        if not isinstance(name, str) or not name or name != name.strip():
            raise ScannerFailure(f"allowlist entry {index} name is invalid")
        if namespace is not None and (
            not isinstance(namespace, str)
            or not namespace
            or namespace != namespace.strip()
        ):
            raise ScannerFailure(f"allowlist entry {index} namespace is invalid")
        if not isinstance(issue, str) or ISSUE_PATTERN.fullmatch(issue) is None:
            raise ScannerFailure(
                f"allowlist entry {index} must reference a MALIEV operations issue"
            )
        identity = SecretIdentity(
            relative_path,
            document,
            api_version,
            name,
            namespace,
        )
        if identity in allowlist:
            raise ScannerFailure(
                f"duplicate native Secret allowlist entry: {identity.describe()}"
            )
        allowlist[identity] = issue
    return allowlist


def scan_tracked_yaml(root: Path, paths: list[str]) -> set[SecretIdentity]:
    """Parse every tracked YAML document and return native Secret identities."""
    root_resolved = root.resolve()
    findings: set[SecretIdentity] = set()
    for relative_path in paths:
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as error:
            raise ScannerFailure(
                f"tracked YAML path escapes the repository: {relative_path}"
            ) from error
        if not candidate.is_file():
            raise ScannerFailure(f"tracked YAML file is missing: {relative_path}")
        try:
            documents = list(
                yaml.safe_load_all(candidate.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise ScannerFailure(
                f"could not parse tracked YAML {relative_path}"
            ) from error
        for document_number, document in enumerate(documents, 1):
            if not isinstance(document, dict) or document.get("kind") != "Secret":
                continue
            metadata = document.get("metadata")
            if not isinstance(metadata, dict):
                raise ScannerFailure(
                    f"native Secret metadata is invalid in {relative_path} "
                    f"document {document_number}"
                )
            api_version = document.get("apiVersion")
            name = metadata.get("name")
            namespace = metadata.get("namespace")
            if api_version != "v1" or not isinstance(name, str) or not name.strip():
                raise ScannerFailure(
                    f"native Secret identity is invalid in {relative_path} "
                    f"document {document_number}"
                )
            if namespace is not None and (
                not isinstance(namespace, str) or not namespace.strip()
            ):
                raise ScannerFailure(
                    f"native Secret namespace is invalid in {relative_path} "
                    f"document {document_number}"
                )
            findings.add(
                SecretIdentity(
                    relative_path,
                    document_number,
                    api_version,
                    name.strip(),
                    namespace.strip() if isinstance(namespace, str) else None,
                )
            )
    return findings


def run(root: Path, allowlist_path: Path) -> int:
    """Evaluate policy and print only non-sensitive identity evidence."""
    try:
        allowlist = load_allowlist(allowlist_path)
        findings = scan_tracked_yaml(root, enumerate_tracked_yaml(root))
    except ScannerFailure as error:
        print(f"Native Secret scanner failed closed: {error}", file=sys.stderr)
        return 2

    allowed = set(allowlist)
    unapproved = sorted(findings - allowed)
    stale = sorted(allowed - findings)
    if unapproved or stale:
        print("Native Secret policy failed:", file=sys.stderr)
        for identity in unapproved:
            print(
                f"- unapproved native Secret: {identity.describe()}",
                file=sys.stderr,
            )
        for identity in stale:
            print(
                f"- stale native Secret allowlist entry: {identity.describe()} "
                f"({allowlist[identity]})",
                file=sys.stderr,
            )
        return 1

    count = len(allowed)
    noun = "entry" if count == 1 else "entries"
    print(
        f"Native Secret policy passed: {count} issue-backed native Secret "
        f"allowlist {noun}; No unapproved native Kubernetes Secret resources found."
    )
    return 0


def parse_args() -> argparse.Namespace:
    """Parse command-line paths used by CI and isolated regression tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    return parser.parse_args()


def main() -> int:
    """Run the native Secret policy scanner."""
    arguments = parse_args()
    return run(arguments.root.resolve(), arguments.allowlist.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
