from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPOSITORY_ROOT / "scripts" / "check-native-secrets.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "native-secrets"


class NativeSecretScannerTests(unittest.TestCase):
    def test_scanner_exists(self) -> None:
        self.assertTrue(SCANNER.is_file(), f"Missing policy scanner: {SCANNER}")

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_native_secret_is_rejected_without_printing_values(self) -> None:
        with self.create_repository() as root:
            self.copy_fixture(root, "native-secret.txt", "manifests/secret.yaml")
            result = self.run_scanner(root)

            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("manifests/secret.yaml document 1", result.stderr)
            self.assertIn("fixture-native-secret", result.stderr)
            self.assertNotIn("bm90LWEtcmVhbC1zZWNyZXQ", result.stderr)

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_multi_document_yaml_reports_exact_secret_document(self) -> None:
        with self.create_repository() as root:
            self.copy_fixture(root, "multi-document-secret.txt", "manifests/bundle.yml")
            result = self.run_scanner(root)

            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("manifests/bundle.yml document 2", result.stderr)
            self.assertNotIn("document 1", result.stderr)

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_comments_documentation_and_non_yaml_files_do_not_match(self) -> None:
        with self.create_repository() as root:
            self.copy_fixture(root, "comments-and-docs.txt", "manifests/config.yaml")
            (root / "README.md").write_text("Example: kind: Secret\n", encoding="utf-8")
            self.git_add(root)

            result = self.run_scanner(root)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("No unapproved native Kubernetes Secret", result.stdout)

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_malformed_yaml_fails_closed(self) -> None:
        with self.create_repository() as root:
            self.copy_fixture(root, "malformed.txt", "manifests/broken.yaml")
            result = self.run_scanner(root)

            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("could not parse tracked YAML manifests/broken.yaml", result.stderr)
            self.assertNotIn("SENSITIVE_PARSE_MARKER", result.stderr)

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_git_enumeration_failure_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_allowlist(root, [])

            result = self.run_scanner(root)

            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("could not enumerate tracked YAML", result.stderr)

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_exact_issue_backed_allowlist_entry_is_accepted(self) -> None:
        with self.create_repository() as root:
            self.copy_fixture(root, "native-secret.txt", "manifests/secret.yaml")
            self.write_allowlist(
                root,
                [
                    {
                        "path": "manifests/secret.yaml",
                        "document": 1,
                        "apiVersion": "v1",
                        "name": "fixture-native-secret",
                        "namespace": "fixture",
                        "issue": "https://github.com/MALIEV-Co-Ltd/maliev-ops/issues/83",
                    }
                ],
            )
            self.git_add(root)

            result = self.run_scanner(root)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("1 issue-backed native Secret allowlist entry", result.stdout)

    @unittest.skipUnless(SCANNER.is_file(), "scanner not implemented yet")
    def test_stale_allowlist_entry_fails_closed(self) -> None:
        with self.create_repository() as root:
            self.write_allowlist(
                root,
                [
                    {
                        "path": "manifests/missing.yaml",
                        "document": 1,
                        "apiVersion": "v1",
                        "name": "missing",
                        "namespace": None,
                        "issue": "https://github.com/MALIEV-Co-Ltd/maliev-ops/issues/83",
                    }
                ],
            )
            self.git_add(root)

            result = self.run_scanner(root)

            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("stale native Secret allowlist entry", result.stderr)

    @staticmethod
    @contextmanager
    def create_repository() -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            NativeSecretScannerTests.write_allowlist(root, [])
            NativeSecretScannerTests.git_add(root)
            yield root

    @staticmethod
    def copy_fixture(root: Path, fixture: str, destination: str) -> None:
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURES / fixture, target)
        NativeSecretScannerTests.git_add(root)

    @staticmethod
    def write_allowlist(root: Path, entries: list[dict[str, object]]) -> None:
        path = root / "scripts" / "native-secret-allowlist.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"allowedNativeSecrets": entries}, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def git_add(root: Path) -> None:
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)

    @staticmethod
    def run_scanner(root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCANNER),
                "--root",
                str(root),
                "--allowlist",
                str(root / "scripts" / "native-secret-allowlist.json"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
