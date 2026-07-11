from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.cli import (
    EXIT_ERROR,
    EXIT_NO_MATCH,
    EXIT_STALE,
    build_parser,
    main,
)
from ai_consult.config import parse_config


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


class BundleCliConnectionTest(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments)

        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_parser_accepts_approved_start_and_review_contract(self) -> None:
        parser = build_parser()
        start = parser.parse_args(
            (
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "ai_consult_tools",
                "--case-name",
                "case_a",
                "--include-set",
                "common_rules",
                "--include-paths",
                "docs/a.md",
                "docs/b.md",
            )
        )
        review = parser.parse_args(
            (
                "review",
                "--target",
                "claude",
                "--profile",
                "ai_consult_tools",
                "--target-paths",
                "src",
                "tests",
            )
        )

        self.assertEqual(start.command, "start")
        self.assertEqual(start.target, "chatgpt")
        self.assertEqual(start.include_set, ["common_rules"])
        self.assertEqual(
            start.include_paths,
            ["docs/a.md", "docs/b.md"],
        )
        self.assertEqual(review.command, "review")
        self.assertEqual(review.target, "claude")
        self.assertEqual(review.target_paths, ["src", "tests"])

    def test_start_collects_once_and_dispatches_selected_target(self) -> None:
        config = parse_config({"schemaVersion": 1})
        profile = SimpleNamespace(name="ai_consult_tools")
        bundle = object()
        context = object()
        result = object()

        with patch(
            "ai_consult.cli._resolve_repo_root",
            return_value=Path("C:/repo"),
        ), patch(
            "ai_consult.cli._load_runtime_config",
            return_value=config,
        ), patch(
            "ai_consult.cli._load_project_profile",
            return_value=profile,
        ), patch(
            "ai_consult.cli.collect_start_bundle",
            return_value=bundle,
        ) as collect, patch(
            "ai_consult.cli._build_output_context",
            return_value=context,
        ) as build_context, patch(
            "ai_consult.cli._write_bundle",
            return_value=result,
        ) as write, patch(
            "ai_consult.cli._print_output_result"
        ) as print_result:
            exit_code, output, error = self.run_cli(
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "ai_consult_tools",
                "--include-set",
                "common_rules",
                "--include-paths",
                "docs/a.md",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "")
        self.assertEqual(error, "")
        collect.assert_called_once_with(
            Path("C:/repo"),
            config,
            profile,
            include_set_names=["common_rules"],
            explicit_paths=["docs/a.md"],
        )
        build_context.assert_called_once()
        write.assert_called_once_with(bundle, context)
        print_result.assert_called_once_with("start", result)

    def test_empty_review_returns_without_creating_output(self) -> None:
        config = parse_config({"schemaVersion": 1})
        profile = SimpleNamespace(name="ai_consult_tools")
        bundle = SimpleNamespace(items=(), skipped_items=())

        with patch(
            "ai_consult.cli._resolve_repo_root",
            return_value=Path("C:/repo"),
        ), patch(
            "ai_consult.cli._load_runtime_config",
            return_value=config,
        ), patch(
            "ai_consult.cli._load_project_profile",
            return_value=profile,
        ), patch(
            "ai_consult.cli.collect_review_bundle",
            return_value=bundle,
        ) as collect, patch(
            "ai_consult.cli._build_output_context"
        ) as build_context, patch(
            "ai_consult.cli._write_bundle"
        ) as write:
            exit_code, output, error = self.run_cli(
                "review",
                "--target",
                "claude",
                "--profile",
                "ai_consult_tools",
                "--target-paths",
                "src",
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("review: no changes", output)
        self.assertEqual(error, "")
        collect.assert_called_once_with(
            Path("C:/repo"),
            config,
            profile,
            target_paths=["src"],
        )
        build_context.assert_not_called()
        write.assert_not_called()


    def test_skip_only_review_creates_output(self) -> None:
        config = parse_config({"schemaVersion": 1})
        profile = SimpleNamespace(name="ai_consult_tools")
        bundle = SimpleNamespace(items=(), skipped_items=(object(),))
        context = object()
        result = object()

        with patch(
            "ai_consult.cli._resolve_repo_root",
            return_value=Path("C:/repo"),
        ), patch(
            "ai_consult.cli._load_runtime_config",
            return_value=config,
        ), patch(
            "ai_consult.cli._load_project_profile",
            return_value=profile,
        ), patch(
            "ai_consult.cli.collect_review_bundle",
            return_value=bundle,
        ), patch(
            "ai_consult.cli._build_output_context",
            return_value=context,
        ) as build_context, patch(
            "ai_consult.cli._write_bundle",
            return_value=result,
        ) as write, patch(
            "ai_consult.cli._print_output_result"
        ) as print_result:
            exit_code, output, error = self.run_cli(
                "review",
                "--target",
                "chatgpt",
                "--profile",
                "ai_consult_tools",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "")
        self.assertEqual(error, "")
        build_context.assert_called_once()
        write.assert_called_once_with(bundle, context)
        print_result.assert_called_once_with("review", result)
