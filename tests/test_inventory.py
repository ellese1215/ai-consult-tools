from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.config import ConsultConfig, FilterConfig, InventoryConfig
from ai_consult.filters import PathFilter
from ai_consult.inventory import (
    InventoryError,
    InventoryLinkType,
    InventoryScanner,
    render_folder_tree,
)


def make_config(
    *,
    inventory_exclude_paths: tuple[str, ...] = (),
) -> ConsultConfig:
    return ConsultConfig(
        schema_version=1,
        filters=FilterConfig(),
        inventory=InventoryConfig(
            exclude_paths=inventory_exclude_paths,
        ),
    )


class InventoryScannerTest(unittest.TestCase):
    def test_generates_deterministic_repo_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "zeta.txt").write_text("z", encoding="utf-8")
            (repo / "Alpha").mkdir()
            (repo / "Alpha" / "b.txt").write_text(
                "b",
                encoding="utf-8",
            )
            (repo / "alpha.txt").write_text("a", encoding="utf-8")

            snapshot = InventoryScanner(
                repo,
                PathFilter(),
            ).scan()

        self.assertEqual(
            snapshot.rendered_paths,
            (
                "Alpha/",
                "alpha.txt",
                "Alpha/b.txt",
                "zeta.txt",
            ),
        )
        self.assertTrue(
            all("\\" not in path for path in snapshot.rendered_paths)
        )
        self.assertTrue(
            all(
                not Path(path.rstrip("/")).is_absolute()
                for path in snapshot.rendered_paths
            )
        )

    def test_excludes_generated_and_configured_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / ".git").mkdir()
            (repo / ".git" / "config").write_text(
                "git",
                encoding="utf-8",
            )
            (repo / "node_modules").mkdir()
            (repo / "node_modules" / "pkg.js").write_text(
                "pkg",
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

            snapshot = InventoryScanner.from_config(
                repo,
                make_config(
                    inventory_exclude_paths=(
                        ".git",
                        "node_modules",
                        "private/",
                    )
                ),
            ).scan()

        self.assertEqual(snapshot.rendered_paths, ("visible.txt",))

    def test_root_folder_tree_is_excluded_but_nested_name_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "folder_tree.txt").write_text(
                "generated",
                encoding="utf-8",
            )
            (repo / "docs").mkdir()
            (repo / "docs" / "folder_tree.txt").write_text(
                "project document",
                encoding="utf-8",
            )

            snapshot = InventoryScanner(
                repo,
                PathFilter(),
            ).scan()

        self.assertEqual(
            snapshot.rendered_paths,
            (
                "docs/",
                "docs/folder_tree.txt",
            ),
        )

    def test_records_binary_paths_without_reading_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "image.png").write_bytes(b"\x89PNG\x00")
            (repo / "archive.zip").write_bytes(b"not a zip")
            (repo / "schema.xlsx").write_bytes(b"not an xlsx")

            snapshot = InventoryScanner(
                repo,
                PathFilter(),
            ).scan()

        self.assertEqual(
            snapshot.rendered_paths,
            (
                "archive.zip",
                "image.png",
                "schema.xlsx",
            ),
        )

    def test_symlink_is_recorded_without_recursion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text(
                "secret",
                encoding="utf-8",
            )
            link = repo / "linked"

            try:
                os.symlink(
                    outside,
                    link,
                    target_is_directory=True,
                )
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation failed: {exc}")

            snapshot = InventoryScanner(
                repo,
                PathFilter(),
            ).scan()

        self.assertEqual(snapshot.rendered_paths, ("linked/",))
        self.assertEqual(
            snapshot.entries[0].link_type,
            InventoryLinkType.SYMLINK,
        )

    @unittest.skipUnless(
        os.name == "nt",
        "junctions are supported only on Windows",
    )
    def test_junction_is_recorded_without_recursion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text(
                "secret",
                encoding="utf-8",
            )
            junction = repo / "linked"

            command = subprocess.run(
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

            if command.returncode != 0:
                self.skipTest(
                    "junction creation failed with "
                    f"exit code {command.returncode}"
                )

            try:
                snapshot = InventoryScanner(
                    repo,
                    PathFilter(),
                ).scan()
            finally:
                if junction.exists():
                    os.rmdir(junction)

        self.assertEqual(snapshot.rendered_paths, ("linked/",))
        self.assertEqual(
            snapshot.entries[0].link_type,
            InventoryLinkType.JUNCTION,
        )

    def test_scan_error_is_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scanner = InventoryScanner(
                temp_dir,
                PathFilter(),
            )

            with patch(
                "ai_consult.inventory.os.scandir",
                side_effect=PermissionError("denied"),
            ):
                with self.assertRaises(InventoryError):
                    scanner.scan()

    def test_render_folder_tree_uses_lf_and_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "guide.txt").write_text(
                "guide",
                encoding="utf-8",
            )

            snapshot = InventoryScanner(
                repo,
                PathFilter(),
            ).scan()

        self.assertEqual(
            render_folder_tree(snapshot),
            "docs/\ndocs/guide.txt\n",
        )


if __name__ == "__main__":
    unittest.main()
