from __future__ import annotations

import io
import json
import subprocess
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

from ai_consult.legacy import MIGRATION_HINT, main


class LegacyCliTest(unittest.TestCase):
    def run_legacy(
        self,
        *arguments: str,
        target: str = "chatgpt",
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments, target=target)

        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_map_translates_to_structure_only_start(self) -> None:
        with (
            patch(
                "ai_consult.legacy._resolve_repo_root",
                return_value=Path("C:/repo"),
            ),
            patch(
                "ai_consult.legacy.current_main",
                return_value=0,
            ) as current,
        ):
            exit_code, output, error = self.run_legacy(
                "--mode",
                "map",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "")
        self.assertIn("WARNING: legacy entry point", error)
        current.assert_called_once_with(
            (
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "app",
                "--repo-root",
                "C:/repo",
            )
        )

    def test_repo_expands_profile_scope_roots(self) -> None:
        profile = SimpleNamespace(scope_roots=("apps/example", "common"))

        with (
            patch(
                "ai_consult.legacy._resolve_repo_root",
                return_value=Path("C:/repo"),
            ),
            patch(
                "ai_consult.legacy._load_project_profile",
                return_value=profile,
            ),
            patch(
                "ai_consult.legacy.current_main",
                return_value=0,
            ) as current,
        ):
            exit_code, _, _ = self.run_legacy(
                "--mode",
                "repo",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
                target="claude",
            )

        self.assertEqual(exit_code, 0)
        current.assert_called_once_with(
            (
                "start",
                "--target",
                "claude",
                "--profile",
                "app",
                "--repo-root",
                "C:/repo",
                "--include-paths",
                "apps/example",
                "common",
            )
        )

    def test_chatgpt_include_translates_include_sets_and_paths(self) -> None:
        with (
            patch(
                "ai_consult.legacy._resolve_repo_root",
                return_value=Path("C:/repo"),
            ),
            patch(
                "ai_consult.legacy.current_main",
                return_value=0,
            ) as current,
        ):
            exit_code, _, _ = self.run_legacy(
                "--mode",
                "include",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
                "--case-name",
                "case_a",
                "--include-set",
                "common_rules",
                "tool_core",
                "--include-paths",
                "apps/example/README.md",
                "common/src",
            )

        self.assertEqual(exit_code, 0)
        current.assert_called_once_with(
            (
                "start",
                "--target",
                "chatgpt",
                "--profile",
                "app",
                "--repo-root",
                "C:/repo",
                "--case-name",
                "case_a",
                "--include-set",
                "common_rules",
                "--include-set",
                "tool_core",
                "--include-paths",
                "apps/example/README.md",
                "common/src",
            )
        )

    def test_diff_translates_to_review(self) -> None:
        with (
            patch(
                "ai_consult.legacy._resolve_repo_root",
                return_value=Path("C:/repo"),
            ),
            patch("ai_consult.legacy._validate_v4_config_schema"),
            patch(
                "ai_consult.legacy.current_main",
                return_value=0,
            ) as current,
        ):
            exit_code, _, _ = self.run_legacy(
                "--mode",
                "diff",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
                "--config-path",
                "ai-consult-tools/local/consult.config.json",
            )

        self.assertEqual(exit_code, 0)
        current.assert_called_once_with(
            (
                "review",
                "--target",
                "chatgpt",
                "--profile",
                "app",
                "--repo-root",
                "C:/repo",
                "--config-path",
                "ai-consult-tools/local/consult.config.json",
            )
        )

    def test_unsupported_diff_option_is_rejected_before_current_cli(self) -> None:
        with patch("ai_consult.legacy.current_main") as current:
            exit_code, _, error = self.run_legacy(
                "--mode",
                "diff",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
                "--staged",
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("unsupported legacy option(s): --staged", error)
        self.assertIn(MIGRATION_HINT, error)
        current.assert_not_called()

    def test_claude_include_set_is_rejected(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(
                    (
                        "--mode",
                        "include",
                        "--repo-root",
                        "C:/repo",
                        "--profile",
                        "app",
                        "--include-set",
                        "common_rules",
                    ),
                    target="claude",
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "unrecognized arguments: --include-set common_rules",
            stderr.getvalue(),
        )
        self.assertIn(MIGRATION_HINT, stderr.getvalue())

    def test_include_requires_an_explicit_request(self) -> None:
        with patch("ai_consult.legacy.current_main") as current:
            exit_code, _, error = self.run_legacy(
                "--mode",
                "include",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("include mode requires", error)
        current.assert_not_called()

    def test_absolute_include_path_is_rejected(self) -> None:
        with patch("ai_consult.legacy.current_main") as current:
            exit_code, _, error = self.run_legacy(
                "--mode",
                "include",
                "--repo-root",
                "C:/repo",
                "--profile",
                "app",
                "--include-paths",
                "C:/outside/file.txt",
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("absolute include paths are not supported", error)
        current.assert_not_called()

    def test_old_config_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / "legacy.json"
            config_path.write_text(
                json.dumps({"outRoot": "legacy/output"}),
                encoding="utf-8",
            )

            with patch("ai_consult.legacy.current_main") as current:
                exit_code, _, error = self.run_legacy(
                    "--mode",
                    "map",
                    "--repo-root",
                    str(repo),
                    "--profile",
                    "app",
                    "--config-path",
                    "legacy.json",
                )

        self.assertEqual(exit_code, 2)
        self.assertIn("legacy configuration schema is not supported", error)
        current.assert_not_called()

    def test_v4_config_schema_is_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / "current.json"
            config_path.write_text(
                json.dumps({"schemaVersion": 1}),
                encoding="utf-8",
            )

            with patch(
                "ai_consult.legacy.current_main",
                return_value=0,
            ) as current:
                exit_code, _, _ = self.run_legacy(
                    "--mode",
                    "map",
                    "--repo-root",
                    str(repo),
                    "--profile",
                    "app",
                    "--config-path",
                    "current.json",
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(current.call_count, 1)

    def test_missing_profile_is_argparse_exit_two_with_migration_hint(
        self,
    ) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(
                    (
                        "--mode",
                        "map",
                        "--repo-root",
                        "C:/repo",
                    ),
                    target="chatgpt",
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(MIGRATION_HINT, stderr.getvalue())

    def test_target_override_is_not_accepted(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(
                    (
                        "--mode",
                        "map",
                        "--repo-root",
                        "C:/repo",
                        "--profile",
                        "app",
                        "--target",
                        "claude",
                    ),
                    target="chatgpt",
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments: --target claude", stderr.getvalue())
        self.assertIn(MIGRATION_HINT, stderr.getvalue())

    def test_both_wrapper_help_commands_succeed(self) -> None:
        scripts = (
            (
                TOOL_ROOT / "chatgpt" / "consult_bundle_chatgpt.py",
                True,
            ),
            (
                TOOL_ROOT / "claude" / "consult_bundle_claude.py",
                False,
            ),
        )

        for script, supports_include_set in scripts:
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )

                self.assertEqual(completed.returncode, 0)
                self.assertIn("--profile", completed.stdout)
                self.assertEqual(
                    "--include-set" in completed.stdout,
                    supports_include_set,
                )
                self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
