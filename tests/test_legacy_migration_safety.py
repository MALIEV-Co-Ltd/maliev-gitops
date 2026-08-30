from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(os.environ.get("MALIEV_WORKSPACE_ROOT", Path(__file__).resolve().parents[2]))
REPOSITORY_PREFIX = "Legacy.Maliev."
MIGRATIONS_PART = "Migrations"
FORBIDDEN_UP_OPERATIONS = (
    "DropTable",
    "DeleteData",
    "DropForeignKey",
    "DropIndex",
    "InsertData",
    "RenameIndex",
    "RenameTable",
    "UpdateData",
)
FORBIDDEN_SQLSERVER_TOKENS = (
    "GETDATE",
    "GETUTCDATE",
    "datetime2",
    "nvarchar",
    "[dbo]",
    "IDENTITY(",
    "sp_",
)
TURNAROUND_MIGRATION = (
    "Legacy.Maliev.OrderService",
    "Legacy.Maliev.OrderService.Data/Migrations/Order/"
    "20260721030103_FixTimestampColumnType.cs",
)


def canonical_repositories() -> list[Path]:
    return sorted(
        path
        for path in WORKSPACE_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith(REPOSITORY_PREFIX)
        and "worktree" not in path.name.lower()
        and (path / ".git").is_dir()
    )


def tracked_migration_files(repository: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "*Migrations/*.cs"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        repository / relative
        for relative in result.stdout.splitlines()
        if not relative.endswith(".Designer.cs")
        and not relative.endswith("ModelSnapshot.cs")
    ]


def up_body(source: str) -> str:
    match = re.search(
        r"protected override void Up\(MigrationBuilder migrationBuilder\)(.*?)(?=protected override void Down|\Z)",
        source,
        re.DOTALL,
    )
    return match.group(1) if match else ""


class LegacyMigrationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repositories = canonical_repositories()
        if "MALIEV_WORKSPACE_ROOT" in os.environ:
            if not WORKSPACE_ROOT.is_dir():
                raise AssertionError(f"Legacy workspace is not mounted: {WORKSPACE_ROOT}")
            if not cls.repositories:
                raise AssertionError(f"No canonical Legacy repositories found in {WORKSPACE_ROOT}")
        elif not cls.repositories:
            raise unittest.SkipTest(f"Legacy workspace is not mounted: {WORKSPACE_ROOT}")

    def test_every_migration_has_a_tracked_up_operation(self) -> None:
        migrations = [
            (repository, path, path.read_text(encoding="utf-8", errors="replace"))
            for repository in self.repositories
            for path in tracked_migration_files(repository)
        ]
        self.assertGreaterEqual(len(migrations), 39)
        self.assertTrue(all(up_body(source).strip() for _, _, source in migrations))

    def test_up_operations_are_data_preserving_or_explicitly_allowlisted(self) -> None:
        for repository, path, source in (
            (repository, path, path.read_text(encoding="utf-8", errors="replace"))
            for repository in self.repositories
            for path in tracked_migration_files(repository)
        ):
            up = up_body(source)
            for operation in FORBIDDEN_UP_OPERATIONS:
                self.assertNotRegex(
                    up,
                    rf"migrationBuilder\.{operation}\(",
                    f"destructive {operation} in {repository.name}/{path.relative_to(repository)}",
                )

            drop_columns = re.findall(r"migrationBuilder\.DropColumn\(\s*name:\s*\"([^\"]+)\"", up)
            if drop_columns:
                self.assertEqual(
                    (repository.name, path.relative_to(repository).as_posix()),
                    TURNAROUND_MIGRATION,
                )
                self.assertEqual(drop_columns, ["Turnaround"])

    def test_migrations_do_not_reintroduce_sql_server_ddl(self) -> None:
        for repository in self.repositories:
            for path in tracked_migration_files(repository):
                source = path.read_text(encoding="utf-8", errors="replace")
                for token in FORBIDDEN_SQLSERVER_TOKENS:
                    self.assertNotIn(
                        token.lower(),
                        source.lower(),
                        f"SQL Server token {token!r} in {repository.name}/{path.relative_to(repository)}",
                    )


if __name__ == "__main__":
    unittest.main()
