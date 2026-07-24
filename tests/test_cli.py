from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
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

    def test_structure_sync_uses_literal_output_root_boundaries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            local = repo / "ai-consult-tools" / "local"
            local.mkdir(parents=True)
            (local / "consult.config.json").write_text(
                """{
  "schemaVersion": 1,
  "outputs": {
    "chatgpt": {"outRoot": "project/generated/[chat]"},
    "claude": {"outRoot": "project/generated/Claude 出力"}
  }
}
""",
                encoding="utf-8",
            )
            chatgpt = repo / "project" / "generated" / "[chat]"
            claude = repo / "project" / "generated" / "Claude 出力"
            sibling = repo / "project" / "generated" / "c"

            for directory in (chatgpt, claude, sibling):
                directory.mkdir(parents=True)

            (chatgpt / "old.zip").write_text("zip", encoding="utf-8")
            (claude / "old.md").write_text("output", encoding="utf-8")
            (sibling / "source.txt").write_text(
                "source",
                encoding="utf-8",
            )

            exit_code, output, error = self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            tree = (repo / "folder_tree.txt").read_text(encoding="utf-8")
            index = json.loads(
                (
                    repo
                    / "ai-consult-tools"
                    / "local"
                    / "cache"
                    / "repo_structure_index.json"
                ).read_text(encoding="utf-8")
            )
            index_paths = tuple(
                item["relativePath"] for item in index["entries"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("structure sync: updated", output)
        self.assertEqual(error, "")
        self.assertIn("project/generated/c/source.txt", tree)
        self.assertIn("project/generated/c/source.txt", index_paths)

        for forbidden in (
            "project/generated/[chat]",
            "project/generated/Claude 出力",
        ):
            self.assertNotIn(forbidden, tree)
            self.assertFalse(
                any(
                    path == forbidden
                    or path.startswith(forbidden + "/")
                    for path in index_paths
                )
            )

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

    def test_start_succeeds_after_structure_check_reports_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            project = repo / "project"
            project.mkdir()
            (project / "main.txt").write_text(
                "main\n",
                encoding="utf-8",
            )
            profiles = repo / "ai-consult-tools" / "config"
            profiles.mkdir(parents=True)
            (profiles / "project_profiles.example.json").write_text(
                """{
  "schemaVersion": 1,
  "profiles": {
    "project": {
      "scopeRoots": ["project"]
    }
  }
}
""",
                encoding="utf-8",
            )

            sync_code, _, sync_error = self.run_cli(
                "structure",
                "sync",
                "--repo-root",
                str(repo),
            )
            self.assertEqual(sync_code, 0)
            self.assertEqual(sync_error, "")

            (project / "new.txt").write_text(
                "new\n",
                encoding="utf-8",
            )
            check_code, check_output, check_error = self.run_cli(
                "structure",
                "check",
                "--repo-root",
                str(repo),
            )
            self.assertEqual(check_code, EXIT_STALE)
            self.assertIn("structure check: stale", check_output)
            self.assertEqual(check_error, "")
            tree_path = repo / "folder_tree.txt"
            folder_tree_before = tree_path.read_bytes()

            start_code, start_output, start_error = self.run_cli(
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "project",
                "--case-name",
                "stale_structure",
                "--repo-root",
                str(repo),
                "--include-paths",
                "project/main.txt",
            )
            folder_tree_after = tree_path.read_bytes()
            zip_paths = tuple(
                (
                    repo
                    / "ai-consult-tools"
                    / "chatgpt"
                    / "consult_case"
                ).glob("*/*.zip")
            )
            sidecar_paths = tuple(
                (
                    repo
                    / "ai-consult-tools"
                    / "chatgpt"
                    / "consult_case"
                ).glob("*/*.zip.sha256")
            )
            self.assertEqual(len(zip_paths), 1)
            self.assertEqual(len(sidecar_paths), 1)
            bundle_sha256 = hashlib.sha256(
                zip_paths[0].read_bytes()
            ).hexdigest().upper()
            sidecar = sidecar_paths[0].read_bytes()

            with zipfile.ZipFile(zip_paths[0]) as archive:
                manifest = archive.read("MANIFEST.csv").decode("utf-8")
                part_text = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                    if name.startswith("parts/")
                )

        self.assertEqual(start_code, 0)
        self.assertIn("start: created", start_output)
        self.assertIn("output: ", start_output)
        self.assertEqual(start_error, "")
        self.assertEqual(folder_tree_after, folder_tree_before)
        self.assertIn("folder_tree.txt,text,generated", manifest)
        self.assertIn("Path: folder_tree.txt", part_text)
        self.assertIn("project/new.txt", part_text)
        self.assertEqual(
            sidecar,
            f"{bundle_sha256} *{zip_paths[0].name}\r\n".encode("utf-8"),
        )
        self.assertIn(f"bundle_path: {zip_paths[0]}", start_output)
        self.assertIn(f"bundle_sha256: {bundle_sha256}", start_output)
        self.assertIn(f"sidecar_path: {sidecar_paths[0]}", start_output)
        self.assertIn("sidecar_match: true", start_output)

    def test_two_starts_with_custom_output_root_do_not_self_collect(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            project = repo / "project"
            project.mkdir()
            (project / "main.txt").write_text("main\n", encoding="utf-8")
            local = repo / "ai-consult-tools" / "local"
            local.mkdir(parents=True)
            (local / "consult.config.json").write_text(
                """{
  "schemaVersion": 1,
  "outputs": {
    "chatgpt": {
      "outRoot": "artifacts/chatgpt"
    },
    "claude": {
      "outRoot": "artifacts/claude"
    }
  }
}
""",
                encoding="utf-8",
            )
            (local / "project_profiles.json").write_text(
                """{
  "schemaVersion": 1,
  "profiles": {
    "project": {
      "scopeRoots": ["project"]
    }
  }
}
""",
                encoding="utf-8",
            )

            first_code, first_output, first_error = self.run_cli(
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "project",
                "--case-name",
                "custom_first",
                "--repo-root",
                str(repo),
                "--include-paths",
                "project/main.txt",
            )
            second_code, second_output, second_error = self.run_cli(
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "project",
                "--case-name",
                "custom_second",
                "--repo-root",
                str(repo),
                "--include-paths",
                "project/main.txt",
            )
            bundle_directories = tuple(
                sorted(
                    (repo / "artifacts" / "chatgpt").iterdir(),
                    key=lambda item: item.name,
                )
            )
            first_directory = next(
                item for item in bundle_directories
                if item.name.endswith("_custom_first")
            )
            second_directory = next(
                item for item in bundle_directories
                if item.name.endswith("_custom_second")
            )
            second_zip = next(second_directory.glob("*.zip"))

            with zipfile.ZipFile(second_zip) as archive:
                second_text = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                )

        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual((first_error, second_error), ("", ""))
        self.assertIn("sidecar_match: true", first_output)
        self.assertIn("sidecar_match: true", second_output)
        self.assertEqual(len(bundle_directories), 2)
        self.assertNotIn(first_directory.name, second_text)
        self.assertNotIn(first_directory.name + ".zip", second_text)
        self.assertNotIn(first_directory.name + ".zip.sha256", second_text)

    def test_output_root_include_fails_without_creating_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            local = repo / "ai-consult-tools" / "local"
            local.mkdir(parents=True)
            (local / "consult.config.json").write_text(
                """{
  "schemaVersion": 1,
  "outputs": {
    "chatgpt": {"outRoot": "project/generated/[chat]"},
    "claude": {"outRoot": "project/generated/claude"}
  }
}
""",
                encoding="utf-8",
            )
            (local / "project_profiles.json").write_text(
                """{
  "schemaVersion": 1,
  "profiles": {
    "project": {"scopeRoots": ["project"]}
  }
}
""",
                encoding="utf-8",
            )
            output_root = repo / "project" / "generated" / "[chat]"
            output_root.mkdir(parents=True)
            (output_root / "old.zip").write_text(
                "old",
                encoding="utf-8",
            )

            results = tuple(
                self.run_cli(
                    "start",
                    "--target",
                    "chatgpt",
                    "--profile",
                    "project",
                    "--case-name",
                    "must_fail",
                    "--repo-root",
                    str(repo),
                    "--include-paths",
                    path,
                )
                for path in (
                    "project/generated/[chat]",
                    "project/generated/[chat]/old.zip",
                )
            )
            remaining = tuple(output_root.iterdir())

        self.assertEqual(remaining[0].name, "old.zip")
        self.assertEqual(len(remaining), 1)

        for exit_code, output, error in results:
            self.assertEqual(exit_code, EXIT_ERROR)
            self.assertEqual(output, "")
            self.assertIn(
                "configured output root cannot be included",
                error,
            )
            self.assertNotIn("created", output)
            self.assertNotIn("output:", output)
            self.assertNotIn("bundle_path:", output)

    def test_start_and_review_outputs_never_inherit_output_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            local = repo / "ai-consult-tools" / "local"
            local.mkdir(parents=True)
            (local / "consult.config.json").write_text(
                """{
  "schemaVersion": 1,
  "outputs": {
    "chatgpt": {"outRoot": "project/generated/[chat]"},
    "claude": {"outRoot": "project/generated/claude"}
  }
}
""",
                encoding="utf-8",
            )
            (local / "project_profiles.json").write_text(
                """{
  "schemaVersion": 1,
  "profiles": {
    "project": {"scopeRoots": ["project"]}
  }
}
""",
                encoding="utf-8",
            )
            source = repo / "project" / "source.txt"
            sibling = repo / "project" / "generated" / "c" / "source.txt"
            chatgpt_root = repo / "project" / "generated" / "[chat]"
            claude_root = repo / "project" / "generated" / "claude"

            for path in (source, sibling):
                path.parent.mkdir(parents=True, exist_ok=True)

            chatgpt_root.mkdir(parents=True)
            claude_root.mkdir(parents=True)
            source.write_text("SOURCE_BODY_BASE\n", encoding="utf-8")
            sibling.write_text("SIBLING_BODY_KEEP\n", encoding="utf-8")
            (chatgpt_root / "tracked.txt").write_text(
                "OUTROOT_TRACKED_BASE\n",
                encoding="utf-8",
            )
            (claude_root / "tracked.txt").write_text(
                "CLAUDE_TRACKED_BASE\n",
                encoding="utf-8",
            )

            def run_git(*args: str) -> None:
                result = subprocess.run(
                    ("git", *args),
                    cwd=repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    shell=False,
                )

                if result.returncode != 0:
                    self.fail(
                        result.stderr.decode("utf-8", errors="replace")
                    )

            run_git("init", "-q")
            run_git("config", "user.email", "test@example.com")
            run_git("config", "user.name", "Test User")
            run_git("config", "core.autocrlf", "false")
            run_git("add", "-A")
            run_git("commit", "-qm", "base")

            source.write_text("SOURCE_BODY_CHANGED\n", encoding="utf-8")
            (chatgpt_root / "tracked.txt").write_text(
                "OUTROOT_TRACKED_STAGED\n",
                encoding="utf-8",
            )
            run_git("add", "project/generated/[chat]/tracked.txt")
            (chatgpt_root / "tracked.txt").write_text(
                "OUTROOT_TRACKED_UNSTAGED\n",
                encoding="utf-8",
            )
            (claude_root / "tracked.txt").write_text(
                "CLAUDE_TRACKED_UNSTAGED\n",
                encoding="utf-8",
            )
            old_directory = chatgpt_root / "old"
            old_directory.mkdir()
            (old_directory / "bundle.zip").write_text(
                "OLD_CHATGPT_ZIP_SECRET\n",
                encoding="utf-8",
            )
            (old_directory / "bundle.zip.sha256").write_text(
                "SIDECAR_SECRET\n",
                encoding="utf-8",
            )
            (chatgpt_root / "temporary.v4_tmp").write_text(
                "TEMP_SECRET\n",
                encoding="utf-8",
            )
            (claude_root / "old_bundle.md").write_text(
                "CLAUDE_OLD_SECRET\n",
                encoding="utf-8",
            )

            common_start_args = (
                "--profile",
                "project",
                "--repo-root",
                str(repo),
                "--include-paths",
                "project/source.txt",
                "project/generated/c/source.txt",
            )
            chat_start = self.run_cli(
                "start",
                "--target",
                "chatgpt",
                "--case-name",
                "outroot_start_chatgpt",
                *common_start_args,
            )
            claude_start = self.run_cli(
                "start",
                "--target",
                "claude",
                "--case-name",
                "outroot_start_claude",
                *common_start_args,
            )
            chat_review = self.run_cli(
                "review",
                "--target",
                "chatgpt",
                "--profile",
                "project",
                "--case-name",
                "outroot_review_chatgpt",
                "--repo-root",
                str(repo),
            )
            claude_review = self.run_cli(
                "review",
                "--target",
                "claude",
                "--profile",
                "project",
                "--case-name",
                "outroot_review_claude",
                "--repo-root",
                str(repo),
            )

            def output_value(output: str, label: str) -> Path:
                prefix = label + ": "
                return Path(
                    next(
                        line[len(prefix):]
                        for line in output.splitlines()
                        if line.startswith(prefix)
                    )
                )

            chat_texts: list[str] = []

            for result in (chat_start, chat_review):
                archive_path = output_value(result[1], "bundle_path")

                with zipfile.ZipFile(archive_path) as archive:
                    chat_texts.append(
                        "\n".join(
                            (
                                *archive.namelist(),
                                *(
                                    archive.read(name).decode("utf-8")
                                    for name in archive.namelist()
                                ),
                            )
                        )
                    )

            claude_texts = [
                output_value(result[1], "output").read_text(encoding="utf-8")
                for result in (claude_start, claude_review)
            ]

        for exit_code, output, error in (
            chat_start,
            claude_start,
            chat_review,
            claude_review,
        ):
            self.assertEqual(exit_code, 0)
            self.assertIn("created", output)
            self.assertIn("output: ", output)
            self.assertEqual(error, "")

        for _, output, _ in (chat_start, chat_review):
            self.assertIn("bundle_path: ", output)
            self.assertIn("bundle_sha256: ", output)
            self.assertIn("sidecar_path: ", output)
            self.assertIn("sidecar_match: true", output)

        for _, output, _ in (claude_start, claude_review):
            self.assertNotIn("bundle_path: ", output)
            self.assertNotIn("bundle_sha256: ", output)
            self.assertNotIn("sidecar_path: ", output)
            self.assertNotIn("sidecar_match:", output)

        forbidden = (
            "project/generated/[chat]",
            "project/generated/claude",
            "OUTROOT_TRACKED",
            "CLAUDE_TRACKED",
            "OLD_CHATGPT_ZIP_SECRET",
            "SIDECAR_SECRET",
            "TEMP_SECRET",
            "CLAUDE_OLD_SECRET",
        )

        for rendered in (*chat_texts, *claude_texts):
            for value in forbidden:
                self.assertNotIn(value, rendered)

        for rendered in (chat_texts[0], claude_texts[0]):
            self.assertIn("project/source.txt", rendered)
            self.assertIn("SOURCE_BODY_CHANGED", rendered)
            self.assertIn("project/generated/c/source.txt", rendered)
            self.assertIn("SIBLING_BODY_KEEP", rendered)

        for rendered in (chat_texts[1], claude_texts[1]):
            self.assertIn("project/source.txt", rendered)
            self.assertIn("SOURCE_BODY_CHANGED", rendered)

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
