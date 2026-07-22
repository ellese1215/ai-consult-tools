from __future__ import annotations

import dataclasses
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.bundle import (
    BundleCommand,
    BundleOrigin,
    ContentKind,
    render_manifest_csv,
)
from ai_consult.collection import (
    CollectedTextFile,
    CollectionResult,
    CollectionStatus,
)
from ai_consult.config import (
    ConsultConfig,
    FilterConfig,
    IncludeSetConfig,
    ProjectProfile,
)
from ai_consult.inventory import (
    FOLDER_TREE_FILENAME,
    FolderTreeComparison,
    InventoryError,
    InventoryEntry,
    InventoryEntryType,
    InventoryScanner,
    InventorySnapshot,
    MoveCandidate,
    StructureDiff,
    StructureIndexComparison,
    sync_structure_index,
)
from ai_consult.start_bundle import (
    PATH_INDEX_PATH,
    PROJECT_TREE_PATH,
    REPO_OVERVIEW_PATH,
    SKIPPED_PATH,
    STRUCTURE_STATUS_PATH,
    StartBundleAssemblyError,
    StartBundleCollectionError,
    StartBundleDocumentError,
    StartBundleStructureError,
    StartCollectionSnapshot,
    StartFileRequest,
    StructureState,
    build_generated_text_item,
    build_project_tree,
    build_repo_overview,
    build_start_collection_snapshot,
    build_start_file_requests,
    build_start_generated_items,
    build_structure_status,
    collect_start_bundle,
    collect_start_files,
    render_path_index,
    render_project_tree,
    render_repo_overview,
    render_skipped,
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


class StartFileCollectionTest(unittest.TestCase):
    def make_config(self) -> ConsultConfig:
        return ConsultConfig(
            schema_version=1,
            filters=FilterConfig(),
            include_sets=(
                IncludeSetConfig(
                    name="common",
                    paths=("project/a.md", "project/b.md"),
                ),
                IncludeSetConfig(
                    name="extra",
                    paths=("project/c.md",),
                ),
            ),
        )

    def test_builds_requests_in_approved_order(self) -> None:
        requests = build_start_file_requests(
            self.make_config(),
            include_set_names=("extra", "common"),
            explicit_paths=("outside/one.md", "outside/two.md"),
        )

        self.assertEqual(
            tuple(
                (
                    item.requested_path,
                    item.origin,
                    item.include_set_name,
                )
                for item in requests
            ),
            (
                ("project/c.md", BundleOrigin.INCLUDE_SET, "extra"),
                ("project/a.md", BundleOrigin.INCLUDE_SET, "common"),
                ("project/b.md", BundleOrigin.INCLUDE_SET, "common"),
                ("outside/one.md", BundleOrigin.EXPLICIT, None),
                ("outside/two.md", BundleOrigin.EXPLICIT, None),
            ),
        )

    def test_rejects_unknown_set_and_invalid_explicit_path(self) -> None:
        with self.assertRaisesRegex(
            StartBundleCollectionError,
            "unknown include set",
        ):
            build_start_file_requests(
                self.make_config(),
                include_set_names=("missing",),
            )

        with self.assertRaises(StartBundleCollectionError):
            build_start_file_requests(
                self.make_config(),
                explicit_paths=("../outside.md",),
            )

    def test_include_set_can_cross_profile_and_explicit_stays_in_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "project").mkdir()
            (repo / "shared").mkdir()
            (repo / "project" / "inside.md").write_text(
                "inside",
                encoding="utf-8",
            )
            (repo / "shared" / "rules.md").write_text(
                "rules",
                encoding="utf-8",
            )
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
                include_sets=(
                    IncludeSetConfig(
                        name="mixed",
                        paths=(
                            "project/inside.md",
                            "shared/rules.md",
                        ),
                    ),
                ),
            )
            snapshot = collect_start_files(
                repo,
                config,
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                include_set_names=("mixed",),
                explicit_paths=("shared/rules.md",),
            )

        self.assertEqual(
            tuple(item.relative_path for item in snapshot.items),
            ("project/inside.md", "shared/rules.md"),
        )
        self.assertEqual(
            tuple(item.origin for item in snapshot.items),
            (BundleOrigin.INCLUDE_SET, BundleOrigin.INCLUDE_SET),
        )
        self.assertEqual(
            tuple(item.status for item in snapshot.path_resolutions),
            (
                CollectionStatus.INCLUDED,
                CollectionStatus.INCLUDED,
                CollectionStatus.EXCLUDED,
            ),
        )
        self.assertEqual(len(snapshot.skipped_items), 1)
        self.assertIn(
            "outside project profile",
            snapshot.skipped_items[0].reason,
        )

    def test_duplicate_requests_keep_all_resolutions_and_one_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "project" / "a.md"
            target.parent.mkdir()
            target.write_text("alpha", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
                include_sets=(
                    IncludeSetConfig(
                        name="common",
                        paths=("project/a.md",),
                    ),
                ),
            )
            snapshot = collect_start_files(
                repo,
                config,
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                include_set_names=("common",),
                explicit_paths=("project/a.md",),
            )

        self.assertEqual(len(snapshot.requests), 2)
        self.assertEqual(len(snapshot.path_resolutions), 2)
        self.assertEqual(len(snapshot.items), 1)
        self.assertEqual(len(snapshot.skipped_items), 0)
        self.assertIs(
            snapshot.items[0].origin,
            BundleOrigin.INCLUDE_SET,
        )
        self.assertIsNone(snapshot.path_resolutions[0].reason)
        self.assertIn(
            "duplicate request",
            snapshot.path_resolutions[1].reason or "",
        )

    def test_case_insensitive_duplicate_uses_first_successful_origin(self) -> None:
        source = b"alpha"
        first_request = StartFileRequest(
            requested_path="project/A.md",
            origin=BundleOrigin.INCLUDE_SET,
            include_set_name="common",
        )
        second_request = StartFileRequest(
            requested_path="project/a.md",
            origin=BundleOrigin.EXPLICIT,
        )
        results = (
            self.included_result(first_request, "project/A.md", source),
            self.included_result(second_request, "project/a.md", source),
        )
        snapshot = build_start_collection_snapshot(
            ProjectProfile(
                name="project",
                scope_roots=("project",),
            ),
            (first_request, second_request),
            results,
        )

        self.assertEqual(len(snapshot.items), 1)
        self.assertEqual(snapshot.items[0].relative_path, "project/A.md")
        self.assertIs(snapshot.items[0].origin, BundleOrigin.INCLUDE_SET)
        self.assertEqual(
            snapshot.path_resolutions[1].resolved_paths,
            ("project/A.md",),
        )

    def test_failure_does_not_claim_first_successful_origin(self) -> None:
        source = b"alpha"
        failed_request = StartFileRequest(
            requested_path="project/a.md",
            origin=BundleOrigin.INCLUDE_SET,
            include_set_name="common",
        )
        successful_request = StartFileRequest(
            requested_path="project/a.md",
            origin=BundleOrigin.EXPLICIT,
        )
        results = (
            CollectionResult(
                requested_path="project/a.md",
                status=CollectionStatus.MISSING,
                reason="missing",
            ),
            self.included_result(
                successful_request,
                "project/a.md",
                source,
            ),
        )
        snapshot = build_start_collection_snapshot(
            ProjectProfile(
                name="project",
                scope_roots=("project",),
            ),
            (failed_request, successful_request),
            results,
        )

        self.assertEqual(len(snapshot.items), 1)
        self.assertIs(snapshot.items[0].origin, BundleOrigin.EXPLICIT)
        self.assertEqual(len(snapshot.skipped_items), 1)

    def test_explicit_path_cannot_escape_profile_through_resolved_target(self) -> None:
        source = b"secret"
        request = StartFileRequest(
            requested_path="project/link.md",
            origin=BundleOrigin.EXPLICIT,
        )
        result = self.included_result(
            request,
            "project/link.md",
            source,
            real_relative_path="other/secret.md",
        )
        snapshot = build_start_collection_snapshot(
            ProjectProfile(
                name="project",
                scope_roots=("project",),
            ),
            (request,),
            (result,),
        )

        self.assertEqual(snapshot.items, ())
        self.assertEqual(len(snapshot.skipped_items), 1)
        self.assertIn("target=other/secret.md", snapshot.skipped_items[0].reason)

    def test_snapshot_is_frozen_and_requires_parallel_resolutions(self) -> None:
        snapshot = build_start_collection_snapshot(
            ProjectProfile(
                name="project",
                scope_roots=("project",),
            ),
            (),
            (),
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.items = ()  # type: ignore[misc]

        with self.assertRaises(StartBundleCollectionError):
            build_start_collection_snapshot(
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                (
                    StartFileRequest(
                        requested_path="project/a.md",
                        origin=BundleOrigin.EXPLICIT,
                    ),
                ),
                (),
            )

    @staticmethod
    def included_result(
        request: StartFileRequest,
        relative_path: str,
        source: bytes,
        *,
        real_relative_path: str | None = None,
    ) -> CollectionResult:
        logical = Path("/repo") / relative_path
        real_relative = real_relative_path or relative_path
        collected = CollectedTextFile(
            requested_path=request.requested_path,
            relative_path=relative_path,
            logical_path=logical,
            real_path=Path("/repo") / real_relative,
            real_relative_path=real_relative,
            size_bytes=len(source),
            source_sha256=hashlib.sha256(source).hexdigest(),
            encoding="utf-8",
            text=source.decode("utf-8"),
        )
        return CollectionResult(
            requested_path=request.requested_path,
            status=CollectionStatus.INCLUDED,
            relative_path=relative_path,
            file=collected,
        )


class StartGeneratedDocumentTest(unittest.TestCase):
    def test_repo_overview_is_minimal_and_deduplicates_placements(self) -> None:
        project_tree = build_project_tree(
            make_snapshot(
                entry("apps/project", InventoryEntryType.DIRECTORY),
                entry("apps/project/main.py"),
                entry("common/project", InventoryEntryType.DIRECTORY),
            ),
            ProjectProfile(
                name="project",
                scope_roots=(
                    "apps/project",
                    "apps/project/shared",
                    "common/project",
                ),
            ),
        )

        overview = build_repo_overview(project_tree)
        rendered = render_repo_overview(overview)

        self.assertEqual(
            overview.top_level_placements,
            ("apps", "common"),
        )
        self.assertIn("- Profile: `project`", rendered)
        self.assertIn("- Profile entries: 3", rendered)
        self.assertIn("- `apps/project/shared`", rendered)
        self.assertEqual(rendered.count("- `apps`"), 1)
        self.assertNotIn("/repo", rendered)
        self.assertNotIn("Git", rendered)
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))

    def test_path_index_preserves_request_order_and_duplicate_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "project" / "a.md"
            target.parent.mkdir()
            target.write_text("alpha", encoding="utf-8")
            snapshot = collect_start_files(
                repo,
                ConsultConfig(
                    schema_version=1,
                    filters=FilterConfig(),
                    include_sets=(
                        IncludeSetConfig(
                            name="common",
                            paths=(
                                "project/a.md",
                                "project/missing.md",
                            ),
                        ),
                    ),
                ),
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                include_set_names=("common",),
                explicit_paths=("project/a.md",),
            )

        rendered = render_path_index(snapshot)

        first = rendered.index("Requested: `project/a.md`")
        second = rendered.index("Requested: `project/missing.md`")
        third = rendered.rindex("Requested: `project/a.md`")
        self.assertLess(first, second)
        self.assertLess(second, third)
        self.assertIn("Source: `include-set:common`", rendered)
        self.assertIn("Source: `include-paths`", rendered)
        self.assertIn("duplicate request", rendered)
        self.assertIn("- Included files: 1", rendered)
        self.assertIn("- Skipped requests: 1", rendered)
        self.assertEqual(
            rendered.count("- `project/a.md` (`include_set`)"),
            1,
        )
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))

    def test_skipped_renders_none_and_failure_details(self) -> None:
        profile = ProjectProfile(
            name="project",
            scope_roots=("project",),
        )
        empty = build_start_collection_snapshot(profile, (), ())
        self.assertIn("(none)\n", render_skipped(empty))

        request = StartFileRequest(
            requested_path="project/missing.md",
            origin=BundleOrigin.INCLUDE_SET,
            include_set_name="common",
        )
        failed = build_start_collection_snapshot(
            profile,
            (request,),
            (
                CollectionResult(
                    requested_path=request.requested_path,
                    status=CollectionStatus.MISSING,
                    relative_path=request.requested_path,
                    reason="file is missing\nfrom repository",
                ),
            ),
        )
        rendered = render_skipped(failed)

        self.assertIn("- Count: 1", rendered)
        self.assertIn("Status: `missing`", rendered)
        self.assertIn("Source: `include-set:common`", rendered)
        self.assertIn("Relative path: `project/missing.md`", rendered)
        self.assertIn("file is missing from repository", rendered)
        self.assertNotIn("file is missing\nfrom repository", rendered)

    def test_generated_items_use_fixed_paths_and_utf8_metadata(self) -> None:
        profile = ProjectProfile(
            name="project",
            scope_roots=("project",),
        )
        project_tree = build_project_tree(
            make_snapshot(
                entry("project", InventoryEntryType.DIRECTORY),
                entry("project/main.py"),
            ),
            profile,
        )
        current_folder = folder_comparison(
            current=True,
            exists=True,
            diff=StructureDiff(),
        )
        current_index = index_comparison(current=True, exists=True)
        status = build_structure_status(
            profile,
            current_folder,
            current_index,
            folder_tree_updated=False,
            structure_index_updated=False,
            folder_tree_after=current_folder,
            structure_index_after=current_index,
        )
        collection = build_start_collection_snapshot(profile, (), ())

        items = build_start_generated_items(
            project_tree,
            status,
            collection,
        )

        self.assertEqual(
            tuple(item.relative_path for item in items),
            (
                REPO_OVERVIEW_PATH,
                PROJECT_TREE_PATH,
                STRUCTURE_STATUS_PATH,
                PATH_INDEX_PATH,
                SKIPPED_PATH,
            ),
        )
        self.assertEqual(
            tuple(item.content.splitlines()[0] for item in items),
            (
                "# REPO_OVERVIEW",
                "# PROJECT_TREE",
                "# STRUCTURE_STATUS",
                "# PATH_INDEX",
                "# SKIPPED",
            ),
        )

        for item in items:
            encoded = item.content.encode("utf-8")
            self.assertIs(item.origin, BundleOrigin.GENERATED)
            self.assertIs(item.content_kind, ContentKind.TEXT)
            self.assertEqual(item.encoding, "utf-8")
            self.assertEqual(item.source_bytes, len(encoded))
            self.assertEqual(
                item.source_sha256,
                hashlib.sha256(encoded).hexdigest(),
            )

    def test_generated_items_require_matching_profiles(self) -> None:
        project_tree = build_project_tree(
            make_snapshot(),
            ProjectProfile(name="one", scope_roots=("one",)),
        )
        other = ProjectProfile(name="two", scope_roots=("two",))
        current_folder = folder_comparison(
            current=True,
            exists=True,
            diff=StructureDiff(),
        )
        current_index = index_comparison(current=True, exists=True)
        status = build_structure_status(
            other,
            current_folder,
            current_index,
            folder_tree_updated=False,
            structure_index_updated=False,
            folder_tree_after=current_folder,
            structure_index_after=current_index,
        )
        collection = build_start_collection_snapshot(other, (), ())

        with self.assertRaisesRegex(
            StartBundleDocumentError,
            "matching profile names",
        ):
            build_start_generated_items(
                project_tree,
                status,
                collection,
            )

    def test_generated_text_item_validates_input(self) -> None:
        with self.assertRaises(StartBundleDocumentError):
            build_generated_text_item("../PATH_INDEX.md", "content")

        with self.assertRaises(StartBundleDocumentError):
            build_generated_text_item(
                PATH_INDEX_PATH,
                b"content",  # type: ignore[arg-type]
            )

    def test_snapshot_requires_profile_and_matching_skipped_records(self) -> None:
        with self.assertRaises(StartBundleCollectionError):
            StartCollectionSnapshot(profile_name="")

        request = StartFileRequest(
            requested_path="project/missing.md",
            origin=BundleOrigin.EXPLICIT,
        )
        resolution = CollectionResult(
            requested_path=request.requested_path,
            status=CollectionStatus.MISSING,
            reason="missing",
        )
        snapshot = build_start_collection_snapshot(
            ProjectProfile(name="project", scope_roots=("project",)),
            (request,),
            (resolution,),
        )

        with self.assertRaises(StartBundleCollectionError):
            StartCollectionSnapshot(
                profile_name="project",
                requests=snapshot.requests,
                path_resolutions=snapshot.path_resolutions,
                skipped_items=(),
            )


class StartBundleAssemblyTest(unittest.TestCase):
    def test_collects_complete_start_bundle_and_syncs_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "project" / "main.txt"
            source.parent.mkdir()
            source.write_text("main\n", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
            )
            profile = ProjectProfile(
                name="project",
                scope_roots=("project",),
            )

            bundle = collect_start_bundle(
                repo,
                config,
                profile,
                explicit_paths=("project/main.txt",),
            )

            self.assertIs(bundle.command, BundleCommand.START)
            self.assertEqual(bundle.profile_name, "project")
            self.assertEqual(bundle.target_paths, ())
            self.assertEqual(
                tuple(item.relative_path for item in bundle.items),
                (
                    REPO_OVERVIEW_PATH,
                    PROJECT_TREE_PATH,
                    STRUCTURE_STATUS_PATH,
                    PATH_INDEX_PATH,
                    SKIPPED_PATH,
                    FOLDER_TREE_FILENAME,
                    "project/main.txt",
                ),
            )
            self.assertEqual(len(bundle.path_resolutions), 1)
            self.assertEqual(bundle.skipped_items, ())
            self.assertTrue((repo / "folder_tree.txt").is_file())
            self.assertTrue(
                (
                    repo
                    / "ai-consult-tools"
                    / "local"
                    / "cache"
                    / "repo_structure_index.json"
                ).is_file()
            )

            status_item = next(
                item
                for item in bundle.items
                if item.relative_path == STRUCTURE_STATUS_PATH
            )
            self.assertIn("| `folder_tree.txt` | `missing` |", status_item.content)
            self.assertIn(
                "| `ai-consult-tools/local/cache/repo_structure_index.json` "
                "| `missing` |",
                status_item.content,
            )
            self.assertIn("| `folder_tree.txt` | `yes` | `current` |", status_item.content)

            manifest = render_manifest_csv(bundle)
            manifest_lines = manifest.splitlines()
            self.assertEqual(len(manifest_lines), 8)
            self.assertEqual(
                {line.split(",", 1)[0] for line in manifest_lines[1:]},
                {
                    REPO_OVERVIEW_PATH,
                    PROJECT_TREE_PATH,
                    STRUCTURE_STATUS_PATH,
                    PATH_INDEX_PATH,
                    SKIPPED_PATH,
                    FOLDER_TREE_FILENAME,
                    "project/main.txt",
                },
            )
            self.assertIn("REPO_OVERVIEW.md,text,generated", manifest)
            self.assertIn("folder_tree.txt,text,generated", manifest)
            self.assertIn("project/main.txt,text,explicit", manifest)
            self.assertNotIn("MANIFEST.csv", manifest)

            folder_tree_item = bundle.items[5]
            folder_tree_source = (repo / FOLDER_TREE_FILENAME).read_bytes()
            self.assertEqual(
                folder_tree_item.content.encode("utf-8"),
                folder_tree_source,
            )
            self.assertEqual(
                folder_tree_item.source_sha256,
                hashlib.sha256(folder_tree_source).hexdigest(),
            )

    def test_empty_requests_and_empty_profile_tree_build_generated_only_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            outside = repo / "outside" / "ignored.txt"
            outside.parent.mkdir()
            outside.write_text("ignored\n", encoding="utf-8")

            bundle = collect_start_bundle(
                repo,
                ConsultConfig(
                    schema_version=1,
                    filters=FilterConfig(),
                ),
                ProjectProfile(
                    name="empty",
                    scope_roots=("project",),
                ),
            )

        self.assertEqual(
            tuple(item.relative_path for item in bundle.items),
            (
                REPO_OVERVIEW_PATH,
                PROJECT_TREE_PATH,
                STRUCTURE_STATUS_PATH,
                PATH_INDEX_PATH,
                SKIPPED_PATH,
                FOLDER_TREE_FILENAME,
            ),
        )
        self.assertEqual(bundle.target_paths, ())
        self.assertEqual(bundle.path_resolutions, ())
        self.assertEqual(bundle.skipped_items, ())

        contents = {item.relative_path: item.content for item in bundle.items}
        self.assertIn("- Entries: 0", contents[PROJECT_TREE_PATH])
        self.assertIn("    (empty)\n", contents[PROJECT_TREE_PATH])
        self.assertIn("- Requests: 0", contents[PATH_INDEX_PATH])
        self.assertIn("- (none)\n", contents[PATH_INDEX_PATH])
        self.assertIn("- Count: 0", contents[SKIPPED_PATH])
        self.assertIn("(none)\n", contents[SKIPPED_PATH])
        self.assertEqual(len(render_manifest_csv(bundle).splitlines()), 7)

    def test_profile_boundaries_and_duplicate_requests_reach_final_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            inside = repo / "project" / "inside.txt"
            outside = repo / "outside" / "shared.txt"
            inside.parent.mkdir()
            outside.parent.mkdir()
            inside.write_text("inside\n", encoding="utf-8")
            outside.write_text("outside\n", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
                include_sets=(
                    IncludeSetConfig(
                        name="common",
                        paths=(
                            "project/inside.txt",
                            "outside/shared.txt",
                        ),
                    ),
                ),
            )

            bundle = collect_start_bundle(
                repo,
                config,
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                include_set_names=("common",),
                explicit_paths=(
                    "project/inside.txt",
                    "outside/shared.txt",
                    "outside/shared.txt",
                ),
            )

        self.assertEqual(
            tuple(
                resolution.status
                for resolution in bundle.path_resolutions
            ),
            (
                CollectionStatus.INCLUDED,
                CollectionStatus.INCLUDED,
                CollectionStatus.INCLUDED,
                CollectionStatus.EXCLUDED,
                CollectionStatus.EXCLUDED,
            ),
        )
        self.assertEqual(
            tuple(item.relative_path for item in bundle.skipped_items),
            ("outside/shared.txt", "outside/shared.txt"),
        )
        self.assertEqual(
            tuple(item.relative_path for item in bundle.items[6:]),
            ("project/inside.txt", "outside/shared.txt"),
        )
        self.assertIs(bundle.items[6].origin, BundleOrigin.INCLUDE_SET)
        self.assertIn(
            "duplicate request; content already included by "
            "include-set:common",
            bundle.path_resolutions[2].reason or "",
        )
        self.assertIn(
            "include-paths path is outside project profile",
            bundle.path_resolutions[3].reason or "",
        )
        self.assertIn(
            "include-paths path is outside project profile",
            bundle.path_resolutions[4].reason or "",
        )

        path_index = next(
            item.content
            for item in bundle.items
            if item.relative_path == PATH_INDEX_PATH
        )
        self.assertIn("Source: `include-set:common`", path_index)
        self.assertIn("Source: `include-paths`", path_index)
        self.assertIn("outside project profile", path_index)
        self.assertEqual(path_index.count("duplicate request"), 1)

        manifest = render_manifest_csv(bundle)
        self.assertEqual(
            manifest.count("project/inside.txt,text,include_set"),
            1,
        )
        self.assertEqual(
            manifest.count("outside/shared.txt,text,include_set"),
            1,
        )

    def test_arcane_common_rules_cross_profile_but_tree_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            roots = (
                "apps/games/arcane_warmaiden_eriya",
                "apps/games/arcane_warmaiden_eriya_trial",
                "docs/arcane_eriya",
            )
            for root in roots:
                (repo / root).mkdir(parents=True)

            arcane_doc = repo / "docs/arcane_eriya/game_rules.md"
            shared_rule = (
                repo
                / "ai-consult-tools/shared/00_ai_consult_operation_rules.md"
            )
            local_rule = repo / "ai-consult-tools/local/consult.local.md"
            outside_doc = repo / "docs/other/note.md"
            shared_rule.parent.mkdir(parents=True)
            local_rule.parent.mkdir(parents=True)
            outside_doc.parent.mkdir(parents=True)
            arcane_doc.write_text("arcane\n", encoding="utf-8")
            shared_rule.write_text("shared\n", encoding="utf-8")
            local_rule.write_text("local\n", encoding="utf-8")
            outside_doc.write_text("outside\n", encoding="utf-8")

            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
                include_sets=(
                    IncludeSetConfig(
                        name="common_rules",
                        paths=(
                            "ai-consult-tools/shared/"
                            "00_ai_consult_operation_rules.md",
                            "ai-consult-tools/local/consult.local.md",
                        ),
                    ),
                ),
            )
            bundle = collect_start_bundle(
                repo,
                config,
                ProjectProfile(name="arcane_eriya", scope_roots=roots),
                include_set_names=("common_rules",),
                explicit_paths=(
                    "docs/arcane_eriya/game_rules.md",
                    "docs/other/note.md",
                ),
            )

        self.assertEqual(
            tuple(item.relative_path for item in bundle.items[6:]),
            (
                "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
                "ai-consult-tools/local/consult.local.md",
                "docs/arcane_eriya/game_rules.md",
            ),
        )
        self.assertEqual(
            tuple(resolution.status for resolution in bundle.path_resolutions),
            (
                CollectionStatus.INCLUDED,
                CollectionStatus.INCLUDED,
                CollectionStatus.INCLUDED,
                CollectionStatus.EXCLUDED,
            ),
        )
        self.assertFalse(
            any(
                "outside project profile" in (resolution.reason or "")
                for resolution in bundle.path_resolutions[:2]
            )
        )
        project_tree = next(
            item.content
            for item in bundle.items
            if item.relative_path == PROJECT_TREE_PATH
        )
        self.assertEqual(project_tree.count("  - `"), 3)
        for root in roots:
            self.assertIn(f"  - `{root}`", project_tree)
        self.assertNotIn("ai-consult-tools/shared", project_tree)
        self.assertNotIn("ai-consult-tools/local", project_tree)
        self.assertNotIn("docs/other", project_tree)

    def test_collection_failures_reach_path_index_skipped_and_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            project = repo / "project"
            project.mkdir()
            (project / "good.txt").write_text("ok\n", encoding="utf-8")
            (project / "excluded.txt").write_text(
                "excluded\n",
                encoding="utf-8",
            )
            (project / "binary.bin").write_text(
                "x",
                encoding="utf-8",
            )
            (project / "large.txt").write_text(
                "abcdefghij",
                encoding="utf-8",
            )
            (project / "invalid.txt").write_bytes(b"\xff\xff")

            bundle = collect_start_bundle(
                repo,
                ConsultConfig(
                    schema_version=1,
                    filters=FilterConfig(
                        exclude_paths=("project/excluded.txt",),
                        binary_extensions=(".bin",),
                        max_text_bytes=5,
                    ),
                ),
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                explicit_paths=(
                    "project/good.txt",
                    "project/missing.txt",
                    "project/excluded.txt",
                    "project/binary.bin",
                    "project/large.txt",
                    "project/invalid.txt",
                ),
            )

        expected_statuses = (
            CollectionStatus.INCLUDED,
            CollectionStatus.MISSING,
            CollectionStatus.EXCLUDED,
            CollectionStatus.BINARY,
            CollectionStatus.TOO_LARGE,
            CollectionStatus.DECODE_ERROR,
        )
        self.assertEqual(
            tuple(
                resolution.status
                for resolution in bundle.path_resolutions
            ),
            expected_statuses,
        )
        self.assertEqual(
            tuple(item.status for item in bundle.skipped_items),
            expected_statuses[1:],
        )
        self.assertEqual(
            tuple(item.relative_path for item in bundle.items[6:]),
            ("project/good.txt",),
        )

        path_index = next(
            item.content
            for item in bundle.items
            if item.relative_path == PATH_INDEX_PATH
        )
        skipped = next(
            item.content
            for item in bundle.items
            if item.relative_path == SKIPPED_PATH
        )

        for status in expected_statuses:
            self.assertIn(f"Status: `{status.value}`", path_index)

        for status in expected_statuses[1:]:
            self.assertIn(f"Status: `{status.value}`", skipped)

        manifest = render_manifest_csv(bundle)
        self.assertIn("project/good.txt,text,explicit", manifest)

        for failed_path in (
            "project/missing.txt",
            "project/excluded.txt",
            "project/binary.bin",
            "project/large.txt",
            "project/invalid.txt",
        ):
            self.assertNotIn(f"\n{failed_path},", manifest)

    def test_current_structure_sources_remain_current_without_updates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "project" / "main.txt"
            source.parent.mkdir()
            source.write_text("main\n", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
            )
            profile = ProjectProfile(
                name="project",
                scope_roots=("project",),
            )
            collect_start_bundle(repo, config, profile)
            collect_start_bundle(repo, config, profile)

            bundle = collect_start_bundle(repo, config, profile)

        status = next(
            item.content
            for item in bundle.items
            if item.relative_path == STRUCTURE_STATUS_PATH
        )
        self.assertIn("| `folder_tree.txt` | `current` |", status)
        self.assertIn(
            "| `ai-consult-tools/local/cache/repo_structure_index.json` "
            "| `current` |",
            status,
        )
        self.assertIn("| `folder_tree.txt` | `no` | `current` |", status)
        self.assertIn(
            "| `ai-consult-tools/local/cache/repo_structure_index.json` "
            "| `no` | `current` |",
            status,
        )

    def test_stale_folder_tree_filters_outside_profile_diff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "project" / "main.txt"
            source.parent.mkdir()
            source.write_text("main\n", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
            )
            profile = ProjectProfile(
                name="project",
                scope_roots=("project",),
            )
            collect_start_bundle(repo, config, profile)
            collect_start_bundle(repo, config, profile)
            outside = repo / "outside" / "new.txt"
            outside.parent.mkdir()
            outside.write_text("outside\n", encoding="utf-8")
            snapshot = InventoryScanner.from_config(repo, config).scan()
            sync_structure_index(snapshot)

            bundle = collect_start_bundle(repo, config, profile)

        status = next(
            item.content
            for item in bundle.items
            if item.relative_path == STRUCTURE_STATUS_PATH
        )
        project_tree = next(
            item.content
            for item in bundle.items
            if item.relative_path == PROJECT_TREE_PATH
        )
        self.assertIn("| `folder_tree.txt` | `stale` |", status)
        self.assertIn(
            "| `ai-consult-tools/local/cache/repo_structure_index.json` "
            "| `current` |",
            status,
        )
        self.assertNotIn("outside/new.txt", status)
        self.assertNotIn("outside/new.txt", project_tree)
        self.assertIn("- (none)", status)

    def test_invalid_structure_sources_are_reported_and_repaired(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "project" / "main.txt"
            source.parent.mkdir()
            source.write_text("main\n", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
            )
            profile = ProjectProfile(
                name="project",
                scope_roots=("project",),
            )
            collect_start_bundle(repo, config, profile)
            collect_start_bundle(repo, config, profile)
            (repo / "folder_tree.txt").write_bytes(
                b"\xef\xbb\xbfinvalid\n"
            )
            structure_index = (
                repo
                / "ai-consult-tools"
                / "local"
                / "cache"
                / "repo_structure_index.json"
            )
            structure_index.write_bytes(b"{broken\n")

            bundle = collect_start_bundle(repo, config, profile)

        status = next(
            item.content
            for item in bundle.items
            if item.relative_path == STRUCTURE_STATUS_PATH
        )
        self.assertIn("| `folder_tree.txt` | `invalid` |", status)
        self.assertIn("must not contain a BOM", status)
        self.assertIn(
            "| `ai-consult-tools/local/cache/repo_structure_index.json` "
            "| `invalid` |",
            status,
        )
        self.assertIn("invalid structure index JSON", status)
        self.assertIn("| `folder_tree.txt` | `yes` | `current` |", status)
        self.assertIn(
            "| `ai-consult-tools/local/cache/repo_structure_index.json` "
            "| `yes` | `current` |",
            status,
        )

    def test_same_current_input_is_deterministic_across_multiple_scope_roots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            first = repo / "apps" / "project" / "a.txt"
            second = repo / "common" / "project" / "b.txt"
            outside = repo / "outside" / "ignored.txt"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            outside.parent.mkdir()
            first.write_text("a\n", encoding="utf-8")
            second.write_text("b\n", encoding="utf-8")
            outside.write_text("ignored\n", encoding="utf-8")
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
            )
            profile = ProjectProfile(
                name="project",
                scope_roots=(
                    "apps/project",
                    "common/project",
                    "apps/project",
                ),
            )
            explicit_paths = (
                "apps/project/a.txt",
                "common/project/b.txt",
            )
            collect_start_bundle(repo, config, profile)
            collect_start_bundle(repo, config, profile)

            first_bundle = collect_start_bundle(
                repo,
                config,
                profile,
                explicit_paths=explicit_paths,
            )
            second_bundle = collect_start_bundle(
                repo,
                config,
                profile,
                explicit_paths=explicit_paths,
            )

        self.assertEqual(first_bundle, second_bundle)
        self.assertEqual(
            render_manifest_csv(first_bundle),
            render_manifest_csv(second_bundle),
        )
        self.assertEqual(
            tuple(item.relative_path for item in first_bundle.items),
            (
                REPO_OVERVIEW_PATH,
                PROJECT_TREE_PATH,
                STRUCTURE_STATUS_PATH,
                PATH_INDEX_PATH,
                SKIPPED_PATH,
                FOLDER_TREE_FILENAME,
                "apps/project/a.txt",
                "common/project/b.txt",
            ),
        )
        project_tree = next(
            item.content
            for item in first_bundle.items
            if item.relative_path == PROJECT_TREE_PATH
        )
        self.assertEqual(project_tree.count("a.txt"), 1)
        self.assertEqual(project_tree.count("b.txt"), 1)
        self.assertNotIn("outside/ignored.txt", project_tree)

    def test_scans_inventory_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            project = repo / "project"
            project.mkdir()
            config = ConsultConfig(
                schema_version=1,
                filters=FilterConfig(),
            )
            profile = ProjectProfile(
                name="project",
                scope_roots=("project",),
            )
            original_scan = InventoryScanner.scan

            with mock.patch.object(
                InventoryScanner,
                "scan",
                autospec=True,
                side_effect=original_scan,
            ) as scan:
                collect_start_bundle(repo, config, profile)

        self.assertEqual(scan.call_count, 1)

    def test_include_set_folder_tree_reuses_automatic_generated_item(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "project" / "main.txt"
            source.parent.mkdir()
            source.write_text("main\n", encoding="utf-8")

            bundle = collect_start_bundle(
                repo,
                ConsultConfig(
                    schema_version=1,
                    filters=FilterConfig(),
                    include_sets=(
                        IncludeSetConfig(
                            name="structure",
                            paths=("folder_tree.txt",),
                        ),
                    ),
                ),
                ProjectProfile(
                    name="project",
                    scope_roots=("project",),
                ),
                include_set_names=("structure",),
            )

        folder_tree_item = next(
            item
            for item in bundle.items
            if item.relative_path == "folder_tree.txt"
        )
        self.assertEqual(
            sum(
                item.relative_path == FOLDER_TREE_FILENAME
                for item in bundle.items
            ),
            1,
        )
        self.assertIs(folder_tree_item.origin, BundleOrigin.GENERATED)
        self.assertIn("project/\n", folder_tree_item.content)
        self.assertIn("project/main.txt\n", folder_tree_item.content)
        self.assertEqual(len(bundle.path_resolutions), 1)
        self.assertIs(
            bundle.path_resolutions[0].status,
            CollectionStatus.INCLUDED,
        )
        self.assertIs(
            bundle.path_resolutions[0].origin,
            BundleOrigin.INCLUDE_SET,
        )

    def test_generated_document_path_collision_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "project").mkdir()
            (repo / PATH_INDEX_PATH).write_text(
                "repository file\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                StartBundleAssemblyError,
                "path collision",
            ):
                collect_start_bundle(
                    repo,
                    ConsultConfig(
                        schema_version=1,
                        filters=FilterConfig(),
                        include_sets=(
                            IncludeSetConfig(
                                name="collision",
                                paths=(PATH_INDEX_PATH,),
                            ),
                        ),
                    ),
                    ProjectProfile(
                        name="project",
                        scope_roots=("project",),
                    ),
                    include_set_names=("collision",),
                )

    def test_structure_sync_failure_aborts_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "project").mkdir()

            with mock.patch(
                "ai_consult.start_bundle.sync_structure_index",
                side_effect=InventoryError("write failed"),
            ):
                with self.assertRaisesRegex(
                    StartBundleAssemblyError,
                    "cannot synchronize",
                ):
                    collect_start_bundle(
                        repo,
                        ConsultConfig(
                            schema_version=1,
                            filters=FilterConfig(),
                        ),
                        ProjectProfile(
                            name="project",
                            scope_roots=("project",),
                        ),
                    )

    def test_structure_change_during_sync_aborts_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "project").mkdir()
            stale = folder_comparison(
                current=False,
                exists=True,
                diff=StructureDiff(added_paths=("project",)),
            )

            with mock.patch(
                "ai_consult.start_bundle.compare_folder_tree",
                return_value=stale,
            ):
                with self.assertRaisesRegex(
                    StartBundleAssemblyError,
                    "changed while",
                ):
                    collect_start_bundle(
                        repo,
                        ConsultConfig(
                            schema_version=1,
                            filters=FilterConfig(),
                        ),
                        ProjectProfile(
                            name="project",
                            scope_roots=("project",),
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
