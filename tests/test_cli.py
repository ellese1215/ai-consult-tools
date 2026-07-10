from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.cli import EXIT_ERROR, EXIT_NO_MATCH, EXIT_STALE, main


class StructureCliTest(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments)

        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_sync_and_check_use_builtin_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "guide.md").write_text(
                "guide",
                encoding="utf-8",
            )

            sync_code, sync_output, sync_error = self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            check_code, check_output, check_error = self.run_cli(
                "structure",
                "check",
                "--repo-root",
                str(repo),
            )

        self.assertEqual(sync_code, 0)
        self.assertIn("structure sync: updated", sync_output)
        self.assertIn("folder tree: updated", sync_output)
        self.assertIn("structure index: updated", sync_output)
        self.assertEqual(sync_error, "")
        self.assertEqual(check_code, 0)
        self.assertIn("structure check: current", check_output)
        self.assertIn("folder tree: current", check_output)
        self.assertIn("structure index: current", check_output)
        self.assertEqual(check_error, "")

    def test_check_returns_stale_without_modifying_folder_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            tree_path = repo / "folder_tree.txt"
            previous = tree_path.read_bytes()
            (repo / "two.txt").write_text("two", encoding="utf-8")

            exit_code, output, error = self.run_cli(
                "structure",
                "check",
                "--repo-root",
                str(repo),
            )
            after = tree_path.read_bytes()

        self.assertEqual(exit_code, EXIT_STALE)
        self.assertIn("structure check: stale", output)
        self.assertIn("  + two.txt", output)
        self.assertEqual(error, "")
        self.assertEqual(after, previous)

    def test_default_local_config_is_loaded_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            local = repo / "ai-consult-tools" / "local"
            local.mkdir(parents=True)
            (local / "consult.config.json").write_text(
                """{
  "schemaVersion": 1,
  "inventory": {
    "excludePaths": ["private/"]
  }
}
""",
                encoding="utf-8",
            )
            (repo / "private").mkdir()
            (repo / "private" / "secret.txt").write_text(
                "secret",
                encoding="utf-8",
            )
            (repo / "visible.txt").write_text(
                "visible",
                encoding="utf-8",
            )

            exit_code, _, error = self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            tree = (repo / "folder_tree.txt").read_text(
                encoding="utf-8"
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error, "")
        self.assertEqual(tree, "ai-consult-tools/\nvisible.txt\n")

    def test_explicit_config_outside_repo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                outside_config = Path(outside_dir) / "config.json"
                outside_config.write_text(
                    '{"schemaVersion": 1}',
                    encoding="utf-8",
                )

                exit_code, _, error = self.run_cli(
                    "structure",
                    "check",
                    "--repo-root",
                    repo_dir,
                    "--config-path",
                    str(outside_config),
                )

        self.assertEqual(exit_code, EXIT_ERROR)
        self.assertIn("ERROR:", error)
        self.assertIn("outside RepoRoot", error)


    def test_check_reports_missing_index_without_modifying_folder_tree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            tree_path = repo / "folder_tree.txt"
            index_path = (
                repo
                / "ai-consult-tools"
                / "local"
                / "cache"
                / "repo_structure_index.json"
            )
            previous_tree = tree_path.read_bytes()
            index_path.unlink()

            exit_code, output, error = self.run_cli(
                "structure",
                "check",
                "--repo-root",
                str(repo),
            )
            after_tree = tree_path.read_bytes()
            index_exists = index_path.exists()

        self.assertEqual(exit_code, EXIT_STALE)
        self.assertIn("folder tree: current", output)
        self.assertIn("structure index: stale", output)
        self.assertEqual(error, "")
        self.assertEqual(after_tree, previous_tree)
        self.assertFalse(index_exists)

    def test_sync_repairs_only_corrupt_structure_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            tree_path = repo / "folder_tree.txt"
            index_path = (
                repo
                / "ai-consult-tools"
                / "local"
                / "cache"
                / "repo_structure_index.json"
            )
            previous_tree = tree_path.read_bytes()
            index_path.write_text("not json\n", encoding="utf-8")

            exit_code, output, error = self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            after_tree = tree_path.read_bytes()
            repaired_index = index_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("structure sync: updated", output)
        self.assertIn("folder tree: current", output)
        self.assertIn("structure index: updated", output)
        self.assertIn("structure index comparison unavailable", output)
        self.assertEqual(error, "")
        self.assertEqual(after_tree, previous_tree)
        self.assertTrue(repaired_index.endswith("\n"))

    def test_check_does_not_create_missing_index_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            cache_path = repo / "ai-consult-tools" / "local" / "cache"

            exit_code, output, error = self.run_cli(
                "structure",
                "check",
                "--repo-root",
                str(repo),
            )
            cache_exists = cache_path.exists()

        self.assertEqual(exit_code, EXIT_STALE)
        self.assertIn("structure index: stale", output)
        self.assertEqual(error, "")
        self.assertFalse(cache_exists)

    def test_find_uses_current_index_and_deterministic_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "archive" / "guide").mkdir(parents=True)
            (repo / "guide.md").write_text("root", encoding="utf-8")
            (repo / "docs" / "guide.md").write_text(
                "docs",
                encoding="utf-8",
            )
            (repo / "docs" / "guide-notes.md").write_text(
                "notes",
                encoding="utf-8",
            )
            (repo / "archive" / "guide" / "source.txt").write_text(
                "source",
                encoding="utf-8",
            )
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )

            exit_code, output, error = self.run_cli(
                "find",
                "GUIDE.MD",
                "--repo-root",
                str(repo),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error, "")
        self.assertIn("find: 2 matches", output)
        self.assertIn("query: GUIDE.MD", output)
        self.assertIn("profile: (all)", output)
        self.assertLess(
            output.index("  [file] guide.md"),
            output.index("  [file] docs/guide.md"),
        )
        self.assertNotIn("guide-notes.md", output)

    def test_find_returns_no_match_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )

            exit_code, output, error = self.run_cli(
                "find",
                "missing",
                "--repo-root",
                str(repo),
            )

        self.assertEqual(exit_code, EXIT_NO_MATCH)
        self.assertIn("find: no matches", output)
        self.assertEqual(error, "")

    def test_find_rejects_stale_index_without_modifying_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            index_path = (
                repo
                / "ai-consult-tools"
                / "local"
                / "cache"
                / "repo_structure_index.json"
            )
            previous = index_path.read_bytes()
            (repo / "two.txt").write_text("two", encoding="utf-8")

            exit_code, output, error = self.run_cli(
                "find",
                "one.txt",
                "--repo-root",
                str(repo),
            )
            after = index_path.read_bytes()

        self.assertEqual(exit_code, EXIT_ERROR)
        self.assertEqual(output, "")
        self.assertIn("structure index is stale", error)
        self.assertIn("structure sync", error)
        self.assertEqual(after, previous)

    def test_find_rejects_missing_index_without_recreating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "one.txt").write_text("one", encoding="utf-8")
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            index_path = (
                repo
                / "ai-consult-tools"
                / "local"
                / "cache"
                / "repo_structure_index.json"
            )
            index_path.unlink()

            exit_code, output, error = self.run_cli(
                "find",
                "one.txt",
                "--repo-root",
                str(repo),
            )
            index_exists = index_path.exists()

        self.assertEqual(exit_code, EXIT_ERROR)
        self.assertEqual(output, "")
        self.assertIn("structure index is missing", error)
        self.assertFalse(index_exists)

    def test_find_filters_by_local_project_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "apps" / "alpha").mkdir(parents=True)
            (repo / "apps" / "beta").mkdir(parents=True)
            (repo / "apps" / "alpha" / "readme.md").write_text(
                "alpha",
                encoding="utf-8",
            )
            (repo / "apps" / "beta" / "readme.md").write_text(
                "beta",
                encoding="utf-8",
            )
            local = repo / "ai-consult-tools" / "local"
            local.mkdir(parents=True)
            (local / "project_profiles.json").write_text(
                """{
  "schemaVersion": 1,
  "profiles": {
    "alpha": {
      "scopeRoots": ["apps/alpha"]
    }
  }
}
""",
                encoding="utf-8",
            )
            self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )

            exit_code, output, error = self.run_cli(
                "find",
                "readme.md",
                "--profile",
                "ALPHA",
                "--repo-root",
                str(repo),
            )
            unknown_code, _, unknown_error = self.run_cli(
                "find",
                "readme.md",
                "--profile",
                "missing",
                "--repo-root",
                str(repo),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error, "")
        self.assertIn("profile: alpha", output)
        self.assertIn("apps/alpha/readme.md", output)
        self.assertNotIn("apps/beta/readme.md", output)
        self.assertEqual(unknown_code, EXIT_ERROR)
        self.assertIn("unknown project profile", unknown_error)


if __name__ == "__main__":
    unittest.main()
