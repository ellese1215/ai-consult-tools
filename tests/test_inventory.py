from __future__ import annotations

import json
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
    FolderTreeFormatError,
    InventoryEntryType,
    InventoryError,
    InventoryLinkType,
    InventoryScanner,
    StructureIndexFormatError,
    build_structure_diff,
    compare_folder_tree,
    compare_structure_index,
    parse_folder_tree,
    parse_structure_index,
    prepare_structure_index_parent,
    render_folder_tree,
    render_structure_index,
    sync_folder_tree,
    sync_structure_index,
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
            (repo / "folder_tree.txt.v4_tmp").write_text(
                "temporary",
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


class FolderTreeManagementTest(unittest.TestCase):
    def test_parse_folder_tree_accepts_new_format(self) -> None:
        self.assertEqual(
            parse_folder_tree(
                "Alpha/\nalpha.txt\nAlpha/b.txt\nzeta.txt\n"
            ),
            (
                "Alpha/",
                "alpha.txt",
                "Alpha/b.txt",
                "zeta.txt",
            ),
        )

    def test_parse_folder_tree_rejects_legacy_or_noncanonical_format(
        self,
    ) -> None:
        invalid_values = (
            "\ufeffdocs/\n",
            "docs/\r\n",
            "docs/",
            "C:/repo/file.txt\n",
            "docs\\file.txt\n",
            "z.txt\na.txt\n",
            "a.txt\na.txt\n",
            "docs/../secret.txt\n",
            "docs//guide.txt\n",
            "docs/./guide.txt\n",
        )

        for value in invalid_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(FolderTreeFormatError):
                    parse_folder_tree(value)

    def test_build_structure_diff_reports_unique_move_candidate(
        self,
    ) -> None:
        diff = build_structure_diff(
            (
                "docs/old/",
                "docs/old/guide.md",
                "keep.txt",
            ),
            (
                "docs/new/",
                "docs/new/guide.md",
                "keep.txt",
            ),
        )

        self.assertEqual(
            diff.added_paths,
            ("docs/new/", "docs/new/guide.md"),
        )
        self.assertEqual(
            diff.removed_paths,
            ("docs/old/", "docs/old/guide.md"),
        )
        self.assertEqual(len(diff.move_candidates), 1)
        self.assertEqual(
            diff.move_candidates[0].previous_path,
            "docs/old/guide.md",
        )
        self.assertEqual(
            diff.move_candidates[0].current_path,
            "docs/new/guide.md",
        )

    def test_compare_missing_folder_tree_reports_all_paths_added(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "guide.md").write_text(
                "guide",
                encoding="utf-8",
            )
            snapshot = InventoryScanner(repo, PathFilter()).scan()
            comparison = compare_folder_tree(snapshot)

        self.assertFalse(comparison.is_current)
        self.assertFalse(comparison.previous_exists)
        self.assertIsNotNone(comparison.diff)
        self.assertEqual(
            comparison.diff.added_paths,
            ("docs/", "docs/guide.md"),
        )

    def test_sync_writes_utf8_lf_and_does_not_rewrite_current_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "資料").mkdir()
            (repo / "資料" / "設計.md").write_text(
                "design",
                encoding="utf-8",
            )
            snapshot = InventoryScanner(repo, PathFilter()).scan()

            first = sync_folder_tree(snapshot)
            tree_path = repo / "folder_tree.txt"
            first_bytes = tree_path.read_bytes()

            with patch(
                "ai_consult.inventory._write_folder_tree"
            ) as write_mock:
                second = sync_folder_tree(snapshot)

        self.assertTrue(first.updated)
        self.assertFalse(second.updated)
        self.assertEqual(
            first_bytes,
            "資料/\n資料/設計.md\n".encode("utf-8"),
        )
        self.assertFalse(first_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", first_bytes)
        write_mock.assert_not_called()

    def test_sync_replaces_legacy_folder_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "visible.txt").write_text(
                "visible",
                encoding="utf-8",
            )
            (repo / "folder_tree.txt").write_bytes(
                "legacy".encode("utf-16-le")
            )
            snapshot = InventoryScanner(repo, PathFilter()).scan()
            result = sync_folder_tree(snapshot)
            written = (repo / "folder_tree.txt").read_bytes()

        self.assertTrue(result.updated)
        self.assertIsNotNone(result.comparison.format_error)
        self.assertEqual(written, b"visible.txt\n")


class StructureIndexManagementTest(unittest.TestCase):
    def test_render_structure_index_uses_minimal_deterministic_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "Archive.ZIP").write_bytes(b"binary")
            (repo / "README").write_text("readme", encoding="utf-8")
            (repo / "docs").mkdir()
            (repo / "docs" / "Guide.MD").write_text(
                "guide",
                encoding="utf-8",
            )
            snapshot = InventoryScanner(repo, PathFilter()).scan()
            rendered = render_structure_index(snapshot)
            payload = json.loads(rendered)

        self.assertEqual(tuple(payload), ("schemaVersion", "entries"))
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertFalse(rendered.startswith("\ufeff"))
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(
            payload["entries"],
            [
                {
                    "relativePath": "Archive.ZIP",
                    "name": "Archive.ZIP",
                    "parentPath": "",
                    "entryType": "file",
                    "linkType": "none",
                    "extension": ".zip",
                },
                {
                    "relativePath": "docs",
                    "name": "docs",
                    "parentPath": "",
                    "entryType": "directory",
                    "linkType": "none",
                    "extension": "",
                },
                {
                    "relativePath": "docs/Guide.MD",
                    "name": "Guide.MD",
                    "parentPath": "docs",
                    "entryType": "file",
                    "linkType": "none",
                    "extension": ".md",
                },
                {
                    "relativePath": "README",
                    "name": "README",
                    "parentPath": "",
                    "entryType": "file",
                    "linkType": "none",
                    "extension": "",
                },
            ],
        )

    def test_parse_structure_index_rejects_noncanonical_values(self) -> None:
        valid = """{
  "schemaVersion": 1,
  "entries": []
}
"""
        invalid_values = (
            "\ufeff" + valid,
            valid.replace("\n", "\r\n"),
            valid.rstrip("\n"),
            '{"schemaVersion": 99, "entries": []}\n',
            """{
  "entries": [],
  "schemaVersion": 1
}
""",
            """{
  "schemaVersion": 1,
  "entries": [
    {
      "relativePath": "docs/guide.md",
      "name": "wrong.md",
      "parentPath": "docs",
      "entryType": "file",
      "linkType": "none",
      "extension": ".md"
    }
  ]
}
""",
        )

        self.assertEqual(parse_structure_index(valid), ())

        for value in invalid_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(StructureIndexFormatError):
                    parse_structure_index(value)

    def test_structure_index_sync_repairs_missing_and_corrupt_index(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "visible.txt").write_text(
                "visible",
                encoding="utf-8",
            )
            snapshot = InventoryScanner(repo, PathFilter()).scan()
            index_path = repo / "cache" / "index.json"

            missing = compare_structure_index(snapshot, index_path)
            first = sync_structure_index(snapshot, index_path)
            first_bytes = index_path.read_bytes()
            index_path.write_text("not json\n", encoding="utf-8")
            corrupt = compare_structure_index(snapshot, index_path)
            repaired = sync_structure_index(snapshot, index_path)
            repaired_bytes = index_path.read_bytes()

        self.assertFalse(missing.is_current)
        self.assertFalse(missing.previous_exists)
        self.assertTrue(first.updated)
        self.assertFalse(first_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", first_bytes)
        self.assertFalse(corrupt.is_current)
        self.assertIsNotNone(corrupt.format_error)
        self.assertTrue(repaired.updated)
        self.assertEqual(repaired_bytes, first_bytes)

    def test_structure_index_does_not_rewrite_current_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "visible.txt").write_text(
                "visible",
                encoding="utf-8",
            )
            snapshot = InventoryScanner(repo, PathFilter()).scan()
            index_path = repo / "cache" / "index.json"
            sync_structure_index(snapshot, index_path)

            with patch(
                "ai_consult.inventory._write_structure_index"
            ) as write_mock:
                result = sync_structure_index(snapshot, index_path)

        self.assertFalse(result.updated)
        write_mock.assert_not_called()

    def test_structure_index_preserves_link_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            link = repo / "linked.txt"
            target = outside / "target.txt"
            target.write_text("target", encoding="utf-8")

            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation failed: {exc}")

            snapshot = InventoryScanner(repo, PathFilter()).scan()
            parsed = parse_structure_index(
                render_structure_index(snapshot)
            )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].entry_type, InventoryEntryType.FILE)
        self.assertEqual(parsed[0].link_type, InventoryLinkType.SYMLINK)
        self.assertEqual(parsed[0].extension, ".txt")

    def test_prepare_structure_index_parent_stays_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            index_path = prepare_structure_index_parent(repo)

        self.assertEqual(
            index_path.relative_to(repo).as_posix(),
            "ai-consult-tools/local/cache/repo_structure_index.json",
        )


if __name__ == "__main__":
    unittest.main()
