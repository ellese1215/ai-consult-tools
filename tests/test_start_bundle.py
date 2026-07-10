from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.config import ProjectProfile
from ai_consult.inventory import (
    FolderTreeComparison,
    InventoryEntry,
    InventoryEntryType,
    InventorySnapshot,
    MoveCandidate,
    StructureDiff,
    StructureIndexComparison,
)
from ai_consult.start_bundle import (
    StartBundleStructureError,
    StructureState,
    build_project_tree,
    build_structure_status,
    render_project_tree,
    render_structure_status,
    select_profile_entries,
)


def make_snapshot(*entries: InventoryEntry) -> InventorySnapshot:
    return InventorySnapshot(
        repo_root=Path("/repo"),
        entries=tuple(entries),
    )


def entry(
    path: str,
    entry_type: InventoryEntryType = InventoryEntryType.FILE,
) -> InventoryEntry:
    return InventoryEntry(
        relative_path=path,
        entry_type=entry_type,
    )


def folder_comparison(
    *,
    current: bool,
    exists: bool,
    diff: StructureDiff | None,
    error: str | None = None,
) -> FolderTreeComparison:
    return FolderTreeComparison(
        folder_tree_path=Path("/repo/folder_tree.txt"),
        is_current=current,
        previous_exists=exists,
        diff=diff,
        format_error=error,
    )


def index_comparison(
    *,
    current: bool,
    exists: bool,
    error: str | None = None,
) -> StructureIndexComparison:
    return StructureIndexComparison(
        structure_index_path=Path("/repo/index.json"),
        is_current=current,
        previous_exists=exists,
        format_error=error,
    )


class ProjectTreeTest(unittest.TestCase):
    def test_selects_only_profile_entries_across_multiple_roots(self) -> None:
        snapshot = make_snapshot(
            entry("apps/project", InventoryEntryType.DIRECTORY),
            entry("apps/project/main.py"),
            entry("common/project", InventoryEntryType.DIRECTORY),
            entry("common/project/config.json"),
            entry("apps/other/secret.txt"),
        )
        profile = ProjectProfile(
            name="project",
            scope_roots=("apps/project", "common/project"),
        )

        selected = select_profile_entries(snapshot, profile)

        self.assertEqual(
            tuple(item.relative_path for item in selected),
            (
                "apps/project",
                "apps/project/main.py",
                "common/project",
                "common/project/config.json",
            ),
        )

    def test_renders_hierarchy_with_directories_before_files(self) -> None:
        snapshot = make_snapshot(
            entry("project/Zeta.txt"),
            entry("project/alpha.txt"),
            entry("project/Beta", InventoryEntryType.DIRECTORY),
            entry("project/alpha", InventoryEntryType.DIRECTORY),
            entry("project/Beta/file.txt"),
            entry("project", InventoryEntryType.DIRECTORY),
        )
        profile = ProjectProfile(
            name="project",
            scope_roots=("project",),
        )

        rendered = render_project_tree(build_project_tree(snapshot, profile))

        self.assertIn(
            "    project/\n"
            "      alpha/\n"
            "      Beta/\n"
            "        file.txt\n"
            "      alpha.txt\n"
            "      Zeta.txt\n",
            rendered,
        )
        self.assertNotIn("\\", rendered)
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))

    def test_overlapping_scope_roots_do_not_duplicate_entries(self) -> None:
        snapshot = make_snapshot(
            entry("project", InventoryEntryType.DIRECTORY),
            entry("project/src", InventoryEntryType.DIRECTORY),
            entry("project/src/main.py"),
        )
        profile = ProjectProfile(
            name="project",
            scope_roots=("project", "project/src"),
        )

        project_tree = build_project_tree(snapshot, profile)
        rendered = render_project_tree(project_tree)

        self.assertEqual(len(project_tree.entries), 3)
        self.assertEqual(rendered.count("main.py"), 1)

    def test_empty_profile_tree_is_valid(self) -> None:
        project_tree = build_project_tree(
            make_snapshot(entry("other/file.txt")),
            ProjectProfile(name="empty", scope_roots=("project",)),
        )

        self.assertEqual(project_tree.entries, ())
        self.assertIn("- Entries: 0", render_project_tree(project_tree))
        self.assertIn("    (empty)\n", render_project_tree(project_tree))

    def test_rejects_invalid_api_types(self) -> None:
        profile = ProjectProfile(name="project", scope_roots=("project",))
        snapshot = make_snapshot()

        with self.assertRaises(TypeError):
            select_profile_entries("not a snapshot", profile)  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            select_profile_entries(snapshot, "not a profile")  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            render_project_tree("not a tree")  # type: ignore[arg-type]

    def test_project_tree_model_is_frozen(self) -> None:
        project_tree = build_project_tree(
            make_snapshot(),
            ProjectProfile(name="project", scope_roots=("project",)),
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            project_tree.profile_name = "other"  # type: ignore[misc]


class StructureStatusTest(unittest.TestCase):
    def test_distinguishes_all_pre_sync_states(self) -> None:
        profile = ProjectProfile(name="project", scope_roots=("project",))
        current = folder_comparison(
            current=True,
            exists=True,
            diff=StructureDiff(),
        )
        missing = folder_comparison(
            current=False,
            exists=False,
            diff=StructureDiff(added_paths=("project/new.py",)),
        )
        stale = folder_comparison(
            current=False,
            exists=True,
            diff=StructureDiff(added_paths=("project/new.py",)),
        )
        invalid = folder_comparison(
            current=False,
            exists=True,
            diff=None,
            error="folder_tree.txt must use LF line endings",
        )
        after_folder = current
        after_index = index_comparison(current=True, exists=True)
        cases = (
            (current, False, StructureState.CURRENT),
            (missing, True, StructureState.MISSING),
            (stale, True, StructureState.STALE),
            (invalid, True, StructureState.INVALID),
        )

        for before, updated, expected in cases:
            with self.subTest(expected=expected):
                status = build_structure_status(
                    profile,
                    before,
                    index_comparison(
                        current=expected is StructureState.CURRENT,
                        exists=expected is not StructureState.MISSING,
                        error=(
                            "invalid index"
                            if expected is StructureState.INVALID
                            else None
                        ),
                    ),
                    folder_tree_updated=updated,
                    structure_index_updated=updated,
                    folder_tree_after=after_folder,
                    structure_index_after=after_index,
                )

                self.assertEqual(status.folder_tree.before_state, expected)
                self.assertEqual(
                    status.structure_index.before_state,
                    expected,
                )

    def test_invalid_folder_tree_does_not_invent_diff(self) -> None:
        status = build_structure_status(
            ProjectProfile(name="project", scope_roots=("project",)),
            folder_comparison(
                current=False,
                exists=True,
                diff=None,
                error="invalid folder tree",
            ),
            index_comparison(current=True, exists=True),
            folder_tree_updated=True,
            structure_index_updated=False,
            folder_tree_after=folder_comparison(
                current=True,
                exists=True,
                diff=StructureDiff(),
            ),
            structure_index_after=index_comparison(
                current=True,
                exists=True,
            ),
        )

        rendered = render_structure_status(status)

        self.assertIsNone(status.profile_diff)
        self.assertIn("`invalid`", rendered)
        self.assertIn("invalid folder tree", rendered)
        self.assertIn("Difference unavailable", rendered)
        self.assertNotIn("### Added", rendered)

    def test_filters_diff_and_hides_cross_boundary_move_paths(self) -> None:
        diff = StructureDiff(
            added_paths=(
                "project/new.py",
                "outside/moved.py",
            ),
            removed_paths=(
                "outside/old.py",
                "project/removed.py",
            ),
            move_candidates=(
                MoveCandidate(
                    previous_path="project/inside.py",
                    current_path="project/renamed.py",
                ),
                MoveCandidate(
                    previous_path="project/old.py",
                    current_path="outside/old.py",
                ),
                MoveCandidate(
                    previous_path="outside/moved.py",
                    current_path="project/moved.py",
                ),
            ),
        )
        status = build_structure_status(
            ProjectProfile(name="project", scope_roots=("project",)),
            folder_comparison(
                current=False,
                exists=True,
                diff=diff,
            ),
            index_comparison(current=False, exists=True),
            folder_tree_updated=True,
            structure_index_updated=True,
            folder_tree_after=folder_comparison(
                current=True,
                exists=True,
                diff=StructureDiff(),
            ),
            structure_index_after=index_comparison(
                current=True,
                exists=True,
            ),
        )

        rendered = render_structure_status(status)

        self.assertEqual(
            status.profile_diff,
            StructureDiff(
                added_paths=("project/new.py",),
                removed_paths=("project/removed.py",),
                move_candidates=(
                    MoveCandidate(
                        previous_path="project/inside.py",
                        current_path="project/renamed.py",
                    ),
                ),
            ),
        )
        self.assertNotIn("outside/", rendered)
        self.assertIn("project/new.py", rendered)
        self.assertIn("project/removed.py", rendered)
        self.assertIn(
            "`project/inside.py` -> `project/renamed.py`",
            rendered,
        )

    def test_render_is_deterministic_lf_with_sync_result(self) -> None:
        status = build_structure_status(
            ProjectProfile(name="project", scope_roots=("project",)),
            folder_comparison(
                current=False,
                exists=False,
                diff=StructureDiff(added_paths=("project/new.py",)),
            ),
            index_comparison(current=True, exists=True),
            folder_tree_updated=True,
            structure_index_updated=False,
            folder_tree_after=folder_comparison(
                current=True,
                exists=True,
                diff=StructureDiff(),
            ),
            structure_index_after=index_comparison(
                current=True,
                exists=True,
            ),
        )

        first = render_structure_status(status)
        second = render_structure_status(status)

        self.assertEqual(first, second)
        self.assertNotIn("\r", first)
        self.assertTrue(first.endswith("\n"))
        self.assertIn("| `folder_tree.txt` | `yes` | `current` |", first)
        self.assertIn(
            "| `ai-consult-tools/local/cache/repo_structure_index.json` | "
            "`no` | `current` |",
            first,
        )

    def test_rejects_inconsistent_or_failed_sync_state(self) -> None:
        profile = ProjectProfile(name="project", scope_roots=("project",))
        stale_folder = folder_comparison(
            current=False,
            exists=True,
            diff=StructureDiff(),
        )
        current_index = index_comparison(current=True, exists=True)

        with self.assertRaises(StartBundleStructureError):
            build_structure_status(
                profile,
                stale_folder,
                current_index,
                folder_tree_updated=False,
                structure_index_updated=False,
                folder_tree_after=folder_comparison(
                    current=True,
                    exists=True,
                    diff=StructureDiff(),
                ),
                structure_index_after=current_index,
            )

        with self.assertRaises(StartBundleStructureError):
            build_structure_status(
                profile,
                stale_folder,
                current_index,
                folder_tree_updated=True,
                structure_index_updated=False,
                folder_tree_after=stale_folder,
                structure_index_after=current_index,
            )

    def test_structure_status_model_is_frozen(self) -> None:
        status = build_structure_status(
            ProjectProfile(name="project", scope_roots=("project",)),
            folder_comparison(
                current=True,
                exists=True,
                diff=StructureDiff(),
            ),
            index_comparison(current=True, exists=True),
            folder_tree_updated=False,
            structure_index_updated=False,
            folder_tree_after=folder_comparison(
                current=True,
                exists=True,
                diff=StructureDiff(),
            ),
            structure_index_after=index_comparison(
                current=True,
                exists=True,
            ),
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            status.profile_name = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
