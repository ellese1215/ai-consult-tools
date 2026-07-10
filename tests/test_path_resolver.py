from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.path_resolver import (
    PathOutsideRepoError,
    RepoPathNotFoundError,
    RepoPathResolver,
    UnsupportedPathTypeError,
)


class RepoPathResolverTest(unittest.TestCase):
    def test_resolves_relative_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "docs" / "guide.md"
            target.parent.mkdir()
            target.write_text("guide", encoding="utf-8")

            resolver = RepoPathResolver(repo)
            result = resolver.resolve("docs/guide.md")

            self.assertEqual(
                result.relative_path,
                "docs/guide.md",
            )
            self.assertEqual(result.real_path, target.resolve())
            self.assertTrue(result.is_file)
            self.assertFalse(result.is_dir)

    def test_resolves_absolute_path_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "inside.txt"
            target.write_text("inside", encoding="utf-8")

            resolver = RepoPathResolver(repo)
            result = resolver.resolve(target)

            self.assertEqual(result.relative_path, "inside.txt")

    def test_rejects_absolute_path_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                outside = Path(outside_dir) / "outside.txt"
                outside.write_text("outside", encoding="utf-8")

                resolver = RepoPathResolver(repo_dir)

                with self.assertRaises(PathOutsideRepoError):
                    resolver.resolve(outside)

    def test_rejects_dotdot_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()

            outside = repo.parent / "outside.txt"
            outside.write_text("outside", encoding="utf-8")

            resolver = RepoPathResolver(repo)

            with self.assertRaises(PathOutsideRepoError):
                resolver.resolve("../outside.txt")

    def test_reports_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = RepoPathResolver(temp_dir)

            with self.assertRaises(RepoPathNotFoundError):
                resolver.resolve("missing.txt")

    def test_rejects_directory_when_file_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            directory = repo / "docs"
            directory.mkdir()

            resolver = RepoPathResolver(repo)

            with self.assertRaises(UnsupportedPathTypeError):
                resolver.resolve(
                    "docs",
                    allow_directory=False,
                )

    @unittest.skipUnless(
        os.name == "nt",
        "junctions are supported only on Windows",
    )
    def test_rejects_junction_escape(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                repo = Path(repo_dir)
                outside = Path(outside_dir)
                secret = outside / "secret.txt"
                secret.write_text("secret", encoding="utf-8")

                junction = repo / "escape"

                result = subprocess.run(
                    [
                        "cmd.exe",
                        "/d",
                        "/c",
                        "mklink",
                        "/J",
                        str(junction),
                        str(outside),
                    ],
                    capture_output=True,
                    check=False,
                )

                if result.returncode != 0:
                    self.skipTest(
                        "junction creation failed with "
                        f"exit code {result.returncode}"
                    )

                try:
                    resolver = RepoPathResolver(repo)

                    with self.assertRaises(PathOutsideRepoError):
                        resolver.resolve("escape/secret.txt")
                finally:
                    if junction.exists():
                        os.rmdir(junction)

    def test_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                repo = Path(repo_dir)
                outside = Path(outside_dir) / "secret.txt"
                outside.write_text("secret", encoding="utf-8")

                link = repo / "escape.txt"

                try:
                    os.symlink(outside, link)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(
                        f"symlink creation is unavailable: {exc}"
                    )

                resolver = RepoPathResolver(repo)

                with self.assertRaises(PathOutsideRepoError):
                    resolver.resolve("escape.txt")


if __name__ == "__main__":
    unittest.main()
