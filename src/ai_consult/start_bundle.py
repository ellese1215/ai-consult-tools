from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

from ai_consult.bundle import (
    BundleCommand,
    BundleItem,
    BundleModel,
    BundleOrigin,
    ContentKind,
    PathResolution,
    SkippedItem,
)
from ai_consult.collection import (
    CollectionResult,
    CollectionStatus,
    ExplicitFileCollector,
)
from ai_consult.config import ConsultConfig, ProjectProfile
from ai_consult.inventory import (
    FolderTreeComparison,
    InventoryError,
    InventoryEntry,
    InventoryEntryType,
    InventoryScanner,
    InventorySnapshot,
    MoveCandidate,
    StructureDiff,
    StructureIndexComparison,
    STRUCTURE_INDEX_RELATIVE_PATH,
    compare_folder_tree,
    compare_structure_index,
    sync_folder_tree,
    sync_structure_index,
)
from ai_consult.path_resolver import (
    PathResolutionError,
    RepoPathResolver,
)


class StartBundleStructureError(ValueError):
    pass


class StartBundleDocumentError(ValueError):
    pass


class StartBundleAssemblyError(RuntimeError):
    pass


REPO_OVERVIEW_PATH = "REPO_OVERVIEW.md"
PROJECT_TREE_PATH = "PROJECT_TREE.md"
STRUCTURE_STATUS_PATH = "STRUCTURE_STATUS.md"
PATH_INDEX_PATH = "PATH_INDEX.md"
SKIPPED_PATH = "SKIPPED.md"
_START_GENERATED_PATHS = (
    REPO_OVERVIEW_PATH,
    PROJECT_TREE_PATH,
    STRUCTURE_STATUS_PATH,
    PATH_INDEX_PATH,
    SKIPPED_PATH,
)


class StructureState(str, Enum):
    CURRENT = "current"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True)
class ProjectTree:
    profile_name: str
    scope_roots: tuple[str, ...]
    entries: tuple[InventoryEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profile_name, str) or not self.profile_name:
            raise StartBundleStructureError(
                "profile_name must be a non-empty string"
            )

        scope_roots = tuple(self.scope_roots)
        entries = tuple(self.entries)
        object.__setattr__(self, "scope_roots", scope_roots)
        object.__setattr__(self, "entries", entries)

        if not all(isinstance(root, str) and root for root in scope_roots):
            raise StartBundleStructureError(
                "scope_roots must contain only non-empty strings"
            )

        if not all(isinstance(entry, InventoryEntry) for entry in entries):
            raise StartBundleStructureError(
                "entries must contain only InventoryEntry values"
            )


@dataclass(frozen=True)
class RepoOverview:
    profile_name: str
    scope_roots: tuple[str, ...]
    top_level_placements: tuple[str, ...]
    profile_entry_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.profile_name, str) or not self.profile_name:
            raise StartBundleDocumentError(
                "profile_name must be a non-empty string"
            )

        scope_roots = tuple(self.scope_roots)
        placements = tuple(self.top_level_placements)
        object.__setattr__(self, "scope_roots", scope_roots)
        object.__setattr__(self, "top_level_placements", placements)

        if not all(isinstance(root, str) and root for root in scope_roots):
            raise StartBundleDocumentError(
                "scope_roots must contain only non-empty strings"
            )

        if not all(
            isinstance(value, str) and value for value in placements
        ):
            raise StartBundleDocumentError(
                "top_level_placements must contain only non-empty strings"
            )

        folded = tuple(value.casefold() for value in placements)
        if len(folded) != len(set(folded)):
            raise StartBundleDocumentError(
                "top_level_placements must not contain duplicates"
            )

        if (
            type(self.profile_entry_count) is not int
            or self.profile_entry_count < 0
        ):
            raise StartBundleDocumentError(
                "profile_entry_count must be a non-negative integer"
            )


@dataclass(frozen=True)
class StructureArtifactStatus:
    before_state: StructureState
    updated: bool
    after_state: StructureState
    format_error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.before_state, StructureState):
            raise StartBundleStructureError(
                "before_state must be a StructureState value"
            )

        if type(self.updated) is not bool:
            raise StartBundleStructureError("updated must be a boolean")

        if not isinstance(self.after_state, StructureState):
            raise StartBundleStructureError(
                "after_state must be a StructureState value"
            )

        if self.after_state is not StructureState.CURRENT:
            raise StartBundleStructureError(
                "after_state must be current after successful sync"
            )

        if self.updated != (self.before_state is not StructureState.CURRENT):
            raise StartBundleStructureError(
                "updated must reflect whether the pre-sync state was current"
            )

        if self.before_state is StructureState.INVALID:
            if (
                not isinstance(self.format_error, str)
                or not self.format_error.strip()
            ):
                raise StartBundleStructureError(
                    "invalid state requires format_error"
                )
        elif self.format_error is not None:
            raise StartBundleStructureError(
                "format_error is valid only for invalid state"
            )


@dataclass(frozen=True)
class ProjectStructureStatus:
    profile_name: str
    folder_tree: StructureArtifactStatus
    structure_index: StructureArtifactStatus
    profile_diff: StructureDiff | None

    def __post_init__(self) -> None:
        if not isinstance(self.profile_name, str) or not self.profile_name:
            raise StartBundleStructureError(
                "profile_name must be a non-empty string"
            )

        if not isinstance(self.folder_tree, StructureArtifactStatus):
            raise StartBundleStructureError(
                "folder_tree must be a StructureArtifactStatus value"
            )

        if not isinstance(self.structure_index, StructureArtifactStatus):
            raise StartBundleStructureError(
                "structure_index must be a StructureArtifactStatus value"
            )

        if self.profile_diff is not None and not isinstance(
            self.profile_diff,
            StructureDiff,
        ):
            raise StartBundleStructureError(
                "profile_diff must be a StructureDiff value or None"
            )

        if (
            self.folder_tree.before_state is StructureState.INVALID
            and self.profile_diff is not None
        ):
            raise StartBundleStructureError(
                "invalid folder tree must not contain a profile diff"
            )


@dataclass
class _TreeNode:
    name: str
    explicit_type: InventoryEntryType | None = None
    children: dict[str, _TreeNode] | None = None

    def __post_init__(self) -> None:
        if self.children is None:
            self.children = {}

    @property
    def is_directory(self) -> bool:
        return (
            self.explicit_type is InventoryEntryType.DIRECTORY
            or bool(self.children)
        )


def select_profile_entries(
    snapshot: InventorySnapshot,
    profile: ProjectProfile,
) -> tuple[InventoryEntry, ...]:
    _require_type(snapshot, InventorySnapshot, "snapshot")
    _require_type(profile, ProjectProfile, "profile")

    entries = tuple(snapshot.entries)

    if not all(isinstance(entry, InventoryEntry) for entry in entries):
        raise StartBundleStructureError(
            "snapshot.entries must contain only InventoryEntry values"
        )

    selected = tuple(
        sorted(
            (
                entry
                for entry in entries
                if profile.contains(entry.relative_path)
            ),
            key=lambda entry: (
                entry.relative_path.casefold(),
                entry.relative_path,
            ),
        )
    )
    seen: set[str] = set()

    for entry in selected:
        folded = entry.relative_path.casefold()

        if folded in seen:
            raise StartBundleStructureError(
                "snapshot contains duplicate project paths: "
                f"{entry.relative_path}"
            )

        seen.add(folded)

    return selected


def build_project_tree(
    snapshot: InventorySnapshot,
    profile: ProjectProfile,
) -> ProjectTree:
    entries = select_profile_entries(snapshot, profile)
    return ProjectTree(
        profile_name=profile.name,
        scope_roots=profile.scope_roots,
        entries=entries,
    )


def render_project_tree(project_tree: ProjectTree) -> str:
    _require_type(project_tree, ProjectTree, "project_tree")
    lines = [
        "# PROJECT_TREE",
        "",
        f"- Profile: `{project_tree.profile_name}`",
    ]

    if project_tree.scope_roots:
        lines.append("- Scope roots:")
        lines.extend(
            f"  - `{scope_root}`"
            for scope_root in project_tree.scope_roots
        )
    else:
        lines.append("- Scope roots: (none)")

    lines.extend(
        [
            f"- Entries: {len(project_tree.entries)}",
            "",
        ]
    )
    tree_lines = _render_tree_lines(project_tree.entries)

    if tree_lines:
        lines.extend(f"    {line}" for line in tree_lines)
    else:
        lines.append("    (empty)")

    return "\n".join(lines) + "\n"


def build_repo_overview(project_tree: ProjectTree) -> RepoOverview:
    _require_type(project_tree, ProjectTree, "project_tree")
    placements: list[str] = []
    seen: set[str] = set()

    for scope_root in project_tree.scope_roots:
        top_level = PurePosixPath(scope_root).parts[0]
        folded = top_level.casefold()

        if folded in seen:
            continue

        seen.add(folded)
        placements.append(top_level)

    return RepoOverview(
        profile_name=project_tree.profile_name,
        scope_roots=project_tree.scope_roots,
        top_level_placements=tuple(placements),
        profile_entry_count=len(project_tree.entries),
    )


def render_repo_overview(overview: RepoOverview) -> str:
    _require_type(overview, RepoOverview, "overview")
    lines = [
        "# REPO_OVERVIEW",
        "",
        f"- Profile: `{overview.profile_name}`",
        f"- Profile entries: {overview.profile_entry_count}",
        "",
        "## Scope Roots",
        "",
    ]
    lines.extend(
        (f"- `{root}`" for root in overview.scope_roots),
    )

    if not overview.scope_roots:
        lines.append("- (none)")

    lines.extend(["", "## Top-level Placements", ""])
    lines.extend(
        (f"- `{value}`" for value in overview.top_level_placements),
    )

    if not overview.top_level_placements:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


def build_structure_status(
    profile: ProjectProfile,
    folder_tree_before: FolderTreeComparison,
    structure_index_before: StructureIndexComparison,
    *,
    folder_tree_updated: bool,
    structure_index_updated: bool,
    folder_tree_after: FolderTreeComparison,
    structure_index_after: StructureIndexComparison,
) -> ProjectStructureStatus:
    _require_type(profile, ProjectProfile, "profile")
    _require_type(
        folder_tree_before,
        FolderTreeComparison,
        "folder_tree_before",
    )
    _require_type(
        structure_index_before,
        StructureIndexComparison,
        "structure_index_before",
    )
    _require_type(
        folder_tree_after,
        FolderTreeComparison,
        "folder_tree_after",
    )
    _require_type(
        structure_index_after,
        StructureIndexComparison,
        "structure_index_after",
    )

    folder_tree_status = _build_artifact_status(
        folder_tree_before,
        folder_tree_updated,
        folder_tree_after,
    )
    structure_index_status = _build_artifact_status(
        structure_index_before,
        structure_index_updated,
        structure_index_after,
    )
    profile_diff = None

    if folder_tree_before.diff is not None:
        profile_diff = _filter_structure_diff(
            folder_tree_before.diff,
            profile,
        )
    elif folder_tree_status.before_state is not StructureState.INVALID:
        raise StartBundleStructureError(
            "non-invalid folder tree comparison requires a diff"
        )

    return ProjectStructureStatus(
        profile_name=profile.name,
        folder_tree=folder_tree_status,
        structure_index=structure_index_status,
        profile_diff=profile_diff,
    )


def render_structure_status(status: ProjectStructureStatus) -> str:
    _require_type(status, ProjectStructureStatus, "status")
    lines = [
        "# STRUCTURE_STATUS",
        "",
        f"- Profile: `{status.profile_name}`",
        "",
        "## Before Sync",
        "",
        "| Source | Status | Detail |",
        "|---|---|---|",
        _render_before_status_row("folder_tree.txt", status.folder_tree),
        _render_before_status_row(
            STRUCTURE_INDEX_RELATIVE_PATH,
            status.structure_index,
        ),
        "",
        "## Profile Changes",
        "",
    ]

    if status.profile_diff is None:
        lines.append(
            "- Difference unavailable because folder_tree.txt is invalid."
        )
    else:
        lines.extend(_render_diff(status.profile_diff))

    lines.extend(
        [
            "",
            "## Sync Result",
            "",
            "| Source | Updated | Status After Sync |",
            "|---|---|---|",
            _render_after_status_row("folder_tree.txt", status.folder_tree),
            _render_after_status_row(
                STRUCTURE_INDEX_RELATIVE_PATH,
                status.structure_index,
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _require_type(value: object, expected: type[object], name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__} value")


def _render_tree_lines(
    entries: tuple[InventoryEntry, ...],
) -> tuple[str, ...]:
    root = _TreeNode(name="")

    for entry in entries:
        parts = PurePosixPath(entry.relative_path).parts
        node = root

        for index, part in enumerate(parts):
            if (
                index > 0
                and node.explicit_type is not None
                and node.explicit_type is not InventoryEntryType.DIRECTORY
            ):
                parent_path = "/".join(parts[:index])
                raise StartBundleStructureError(
                    "non-directory project tree entry contains descendants: "
                    f"{parent_path}"
                )

            assert node.children is not None
            child = node.children.get(part)

            if child is None:
                child = _TreeNode(name=part)
                node.children[part] = child

            node = child

        if node.explicit_type is not None:
            raise StartBundleStructureError(
                f"duplicate project tree path: {entry.relative_path}"
            )

        node.explicit_type = entry.entry_type

        if node.children and entry.entry_type is not InventoryEntryType.DIRECTORY:
            raise StartBundleStructureError(
                "non-directory project tree entry contains descendants: "
                f"{entry.relative_path}"
            )

    lines: list[str] = []
    _append_tree_lines(root, 0, lines)
    return tuple(lines)


def _append_tree_lines(
    node: _TreeNode,
    depth: int,
    lines: list[str],
) -> None:
    assert node.children is not None
    children = sorted(
        node.children.values(),
        key=lambda child: (
            not child.is_directory,
            child.name.casefold(),
            child.name,
        ),
    )

    for child in children:
        suffix = "/" if child.is_directory else ""
        lines.append("  " * depth + child.name + suffix)
        _append_tree_lines(child, depth + 1, lines)


def _build_artifact_status(
    before: FolderTreeComparison | StructureIndexComparison,
    updated: bool,
    after: FolderTreeComparison | StructureIndexComparison,
) -> StructureArtifactStatus:
    if type(updated) is not bool:
        raise StartBundleStructureError("updated must be a boolean")

    before_state = _comparison_state(before)
    after_state = _comparison_state(after)
    return StructureArtifactStatus(
        before_state=before_state,
        updated=updated,
        after_state=after_state,
        format_error=before.format_error,
    )


def _comparison_state(
    comparison: FolderTreeComparison | StructureIndexComparison,
) -> StructureState:
    if comparison.is_current:
        return StructureState.CURRENT

    if not comparison.previous_exists:
        return StructureState.MISSING

    if comparison.format_error is not None:
        return StructureState.INVALID

    return StructureState.STALE


def _filter_structure_diff(
    diff: StructureDiff,
    profile: ProjectProfile,
) -> StructureDiff:
    added_paths = tuple(
        path
        for path in diff.added_paths
        if _profile_contains_rendered_path(profile, path)
    )
    removed_paths = tuple(
        path
        for path in diff.removed_paths
        if _profile_contains_rendered_path(profile, path)
    )
    move_candidates = tuple(
        candidate
        for candidate in diff.move_candidates
        if _profile_contains_rendered_path(profile, candidate.previous_path)
        and _profile_contains_rendered_path(profile, candidate.current_path)
    )
    return StructureDiff(
        added_paths=added_paths,
        removed_paths=removed_paths,
        move_candidates=move_candidates,
    )


def _profile_contains_rendered_path(
    profile: ProjectProfile,
    path: str,
) -> bool:
    logical_path = path[:-1] if path.endswith("/") else path
    return profile.contains(logical_path)


def _render_before_status_row(
    source: str,
    status: StructureArtifactStatus,
) -> str:
    detail = _escape_table_cell(status.format_error or "-")
    return f"| `{source}` | `{status.before_state.value}` | {detail} |"


def _render_after_status_row(
    source: str,
    status: StructureArtifactStatus,
) -> str:
    updated = "yes" if status.updated else "no"
    return (
        f"| `{source}` | `{updated}` | "
        f"`{status.after_state.value}` |"
    )


def _render_diff(diff: StructureDiff) -> list[str]:
    lines = ["### Added", ""]
    lines.extend(_render_path_list(diff.added_paths))
    lines.extend(["", "### Removed", ""])
    lines.extend(_render_path_list(diff.removed_paths))
    lines.extend(["", "### Move Candidates", ""])

    if diff.move_candidates:
        lines.extend(
            "- "
            f"`{candidate.previous_path}` -> `{candidate.current_path}`"
            for candidate in diff.move_candidates
        )
    else:
        lines.append("- (none)")

    return lines


def _render_path_list(paths: tuple[str, ...]) -> list[str]:
    if not paths:
        return ["- (none)"]

    return [f"- `{path}`" for path in paths]


def _escape_table_cell(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("|", "\\|")


class StartBundleCollectionError(ValueError):
    pass


@dataclass(frozen=True)
class StartFileRequest:
    requested_path: str
    origin: BundleOrigin
    include_set_name: str | None = None

    def __post_init__(self) -> None:
        _validate_start_relative_path(
            self.requested_path,
            "requested_path",
        )

        if self.origin not in {
            BundleOrigin.EXPLICIT,
            BundleOrigin.INCLUDE_SET,
        }:
            raise StartBundleCollectionError(
                "start request origin must be explicit or include_set"
            )

        if self.origin is BundleOrigin.INCLUDE_SET:
            if (
                not isinstance(self.include_set_name, str)
                or not self.include_set_name
                or self.include_set_name != self.include_set_name.strip()
            ):
                raise StartBundleCollectionError(
                    "include_set request requires include_set_name"
                )
        elif self.include_set_name is not None:
            raise StartBundleCollectionError(
                "explicit request must not set include_set_name"
            )

    @property
    def source_label(self) -> str:
        if self.origin is BundleOrigin.INCLUDE_SET:
            assert self.include_set_name is not None
            return f"include-set:{self.include_set_name}"

        return "include-paths"


@dataclass(frozen=True)
class StartCollectionSnapshot:
    profile_name: str
    requests: tuple[StartFileRequest, ...] = ()
    items: tuple[BundleItem, ...] = ()
    path_resolutions: tuple[PathResolution, ...] = ()
    skipped_items: tuple[SkippedItem, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_name, str)
            or not self.profile_name
            or self.profile_name != self.profile_name.strip()
        ):
            raise StartBundleCollectionError(
                "profile_name must be a non-empty trimmed string"
            )

        requests = tuple(self.requests)
        items = tuple(self.items)
        resolutions = tuple(self.path_resolutions)
        skipped_items = tuple(self.skipped_items)
        object.__setattr__(self, "requests", requests)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "path_resolutions", resolutions)
        object.__setattr__(self, "skipped_items", skipped_items)

        if not all(isinstance(item, StartFileRequest) for item in requests):
            raise StartBundleCollectionError(
                "requests must contain only StartFileRequest values"
            )

        if not all(isinstance(item, BundleItem) for item in items):
            raise StartBundleCollectionError(
                "items must contain only BundleItem values"
            )

        if not all(isinstance(item, PathResolution) for item in resolutions):
            raise StartBundleCollectionError(
                "path_resolutions must contain only PathResolution values"
            )

        if not all(isinstance(item, SkippedItem) for item in skipped_items):
            raise StartBundleCollectionError(
                "skipped_items must contain only SkippedItem values"
            )

        if len(requests) != len(resolutions):
            raise StartBundleCollectionError(
                "each start request requires one path resolution"
            )

        for request, resolution in zip(requests, resolutions, strict=True):
            if request.requested_path != resolution.requested_path:
                raise StartBundleCollectionError(
                    "request and path resolution paths must match"
                )

            if request.origin is not resolution.origin:
                raise StartBundleCollectionError(
                    "request and path resolution origins must match"
                )

        failed_pairs = tuple(
            (request, resolution)
            for request, resolution in zip(
                requests,
                resolutions,
                strict=True,
            )
            if resolution.status is not CollectionStatus.INCLUDED
        )

        if len(failed_pairs) != len(skipped_items):
            raise StartBundleCollectionError(
                "each failed start request requires one skipped item"
            )

        for (request, resolution), skipped in zip(
            failed_pairs,
            skipped_items,
            strict=True,
        ):
            if (
                skipped.requested_path != request.requested_path
                or skipped.status is not resolution.status
                or skipped.origin is not request.origin
                or skipped.reason != resolution.reason
            ):
                raise StartBundleCollectionError(
                    "failed request, resolution, and skipped item must match"
                )

        seen_items: set[str] = set()

        for item in items:
            if item.origin not in {
                BundleOrigin.EXPLICIT,
                BundleOrigin.INCLUDE_SET,
            }:
                raise StartBundleCollectionError(
                    "start collection items must use explicit or include_set origin"
                )

            folded = item.relative_path.casefold()

            if folded in seen_items:
                raise StartBundleCollectionError(
                    "start collection contains duplicate bundle items: "
                    f"{item.relative_path}"
                )

            seen_items.add(folded)


def build_start_file_requests(
    config: ConsultConfig,
    *,
    include_set_names: Iterable[str] = (),
    explicit_paths: Iterable[str] = (),
) -> tuple[StartFileRequest, ...]:
    _require_type(config, ConsultConfig, "config")
    names = _normalize_start_strings(
        include_set_names,
        "include_set_names",
    )
    paths = _normalize_start_strings(
        explicit_paths,
        "explicit_paths",
    )
    requests: list[StartFileRequest] = []

    for name in names:
        try:
            include_set = config.get_include_set(name)
        except ValueError as exc:
            raise StartBundleCollectionError(str(exc)) from exc

        requests.extend(
            StartFileRequest(
                requested_path=path,
                origin=BundleOrigin.INCLUDE_SET,
                include_set_name=include_set.name,
            )
            for path in include_set.paths
        )

    requests.extend(
        StartFileRequest(
            requested_path=path,
            origin=BundleOrigin.EXPLICIT,
        )
        for path in paths
    )
    return tuple(requests)


def collect_start_files(
    repo_root: str | Path,
    config: ConsultConfig,
    profile: ProjectProfile,
    *,
    include_set_names: Iterable[str] = (),
    explicit_paths: Iterable[str] = (),
) -> StartCollectionSnapshot:
    _require_type(config, ConsultConfig, "config")
    _require_type(profile, ProjectProfile, "profile")
    requests = build_start_file_requests(
        config,
        include_set_names=include_set_names,
        explicit_paths=explicit_paths,
    )

    try:
        resolver = RepoPathResolver(repo_root)
        collector = ExplicitFileCollector.from_config(repo_root, config)
    except (ValueError, OSError) as exc:
        raise StartBundleCollectionError(
            f"cannot initialize start file collection: {exc}"
        ) from exc

    results: list[CollectionResult] = []

    for request in requests:
        if request.origin is BundleOrigin.INCLUDE_SET:
            if not profile.contains(request.requested_path):
                results.append(
                    CollectionResult(
                        requested_path=request.requested_path,
                        status=CollectionStatus.EXCLUDED,
                        relative_path=request.requested_path,
                        reason=_outside_profile_reason(
                            request.requested_path,
                            profile,
                        ),
                    )
                )
                continue

            try:
                resolved = resolver.resolve(
                    request.requested_path,
                    must_exist=True,
                    allow_file=True,
                    allow_directory=False,
                )
            except PathResolutionError:
                pass
            else:
                real_relative_path = resolved.real_path.relative_to(
                    resolver.repo_root
                ).as_posix()

                if not profile.contains(real_relative_path):
                    results.append(
                        CollectionResult(
                            requested_path=request.requested_path,
                            status=CollectionStatus.EXCLUDED,
                            relative_path=resolved.relative_path,
                            reason=_outside_profile_reason(
                                resolved.relative_path,
                                profile,
                                real_relative_path=real_relative_path,
                            ),
                        )
                    )
                    continue

        results.append(collector.collect_one(request.requested_path))

    return build_start_collection_snapshot(
        profile,
        requests,
        tuple(results),
    )


def build_start_collection_snapshot(
    profile: ProjectProfile,
    requests: Iterable[StartFileRequest],
    results: Iterable[CollectionResult],
) -> StartCollectionSnapshot:
    _require_type(profile, ProjectProfile, "profile")
    request_values = tuple(requests)
    result_values = tuple(results)

    if len(request_values) != len(result_values):
        raise StartBundleCollectionError(
            "requests and collection results must have the same length"
        )

    items: list[BundleItem] = []
    resolutions: list[PathResolution] = []
    skipped_items: list[SkippedItem] = []
    included_by_path: dict[str, tuple[BundleItem, StartFileRequest]] = {}

    for request, result in zip(request_values, result_values, strict=True):
        if not isinstance(request, StartFileRequest):
            raise StartBundleCollectionError(
                "requests must contain only StartFileRequest values"
            )

        if not isinstance(result, CollectionResult):
            raise StartBundleCollectionError(
                "results must contain only CollectionResult values"
            )

        if result.requested_path != request.requested_path:
            raise StartBundleCollectionError(
                "collection result does not match start request: "
                f"request={request.requested_path}; "
                f"result={result.requested_path}"
            )

        if not result.included:
            reason = result.reason or "collection failed without a reason"
            resolutions.append(
                PathResolution(
                    requested_path=request.requested_path,
                    status=result.status,
                    origin=request.origin,
                    reason=reason,
                )
            )
            skipped_items.append(
                SkippedItem(
                    requested_path=request.requested_path,
                    status=result.status,
                    origin=request.origin,
                    reason=reason,
                    relative_path=result.relative_path,
                )
            )
            continue

        if result.file is None or result.relative_path is None:
            raise StartBundleCollectionError(
                "included collection result requires file metadata"
            )

        collected = result.file

        if (
            collected.relative_path != result.relative_path
            or collected.requested_path != request.requested_path
        ):
            raise StartBundleCollectionError(
                "included collection metadata is inconsistent"
            )

        if request.origin is BundleOrigin.INCLUDE_SET and (
            not profile.contains(collected.relative_path)
            or not profile.contains(collected.real_relative_path)
        ):
            reason = _outside_profile_reason(
                collected.relative_path,
                profile,
                real_relative_path=collected.real_relative_path,
            )
            resolutions.append(
                PathResolution(
                    requested_path=request.requested_path,
                    status=CollectionStatus.EXCLUDED,
                    origin=request.origin,
                    reason=reason,
                )
            )
            skipped_items.append(
                SkippedItem(
                    requested_path=request.requested_path,
                    status=CollectionStatus.EXCLUDED,
                    origin=request.origin,
                    reason=reason,
                    relative_path=collected.relative_path,
                )
            )
            continue

        folded_path = collected.relative_path.casefold()
        previous = included_by_path.get(folded_path)

        if previous is not None:
            previous_item, previous_request = previous
            resolutions.append(
                PathResolution(
                    requested_path=request.requested_path,
                    status=CollectionStatus.INCLUDED,
                    origin=request.origin,
                    resolved_paths=(previous_item.relative_path,),
                    reason=(
                        "duplicate request; content already included by "
                        f"{previous_request.source_label}: "
                        f"{previous_request.requested_path}"
                    ),
                )
            )
            continue

        item = BundleItem(
            relative_path=collected.relative_path,
            content_kind=ContentKind.TEXT,
            origin=request.origin,
            content=collected.text,
            encoding=collected.encoding,
            source_bytes=collected.size_bytes,
            source_sha256=collected.source_sha256,
        )
        items.append(item)
        included_by_path[folded_path] = (item, request)
        resolutions.append(
            PathResolution(
                requested_path=request.requested_path,
                status=CollectionStatus.INCLUDED,
                origin=request.origin,
                resolved_paths=(collected.relative_path,),
            )
        )

    return StartCollectionSnapshot(
        profile_name=profile.name,
        requests=request_values,
        items=tuple(items),
        path_resolutions=tuple(resolutions),
        skipped_items=tuple(skipped_items),
    )


def render_path_index(snapshot: StartCollectionSnapshot) -> str:
    _require_type(snapshot, StartCollectionSnapshot, "snapshot")
    lines = [
        "# PATH_INDEX",
        "",
        f"- Profile: `{snapshot.profile_name}`",
        f"- Requests: {len(snapshot.requests)}",
        f"- Included files: {len(snapshot.items)}",
        f"- Skipped requests: {len(snapshot.skipped_items)}",
        "",
        "## Resolution Results",
        "",
    ]

    if not snapshot.requests:
        lines.append("- (none)")
    else:
        for index, (request, resolution) in enumerate(
            zip(
                snapshot.requests,
                snapshot.path_resolutions,
                strict=True,
            ),
            start=1,
        ):
            lines.extend(
                [
                    f"{index}. Status: `{resolution.status.value}`",
                    f"   - Source: `{request.source_label}`",
                    f"   - Requested: `{request.requested_path}`",
                ]
            )

            if resolution.resolved_paths:
                lines.append("   - Resolved:")
                lines.extend(
                    f"     - `{path}`"
                    for path in resolution.resolved_paths
                )
            else:
                lines.append("   - Resolved: (none)")

            if resolution.reason is not None:
                lines.append(
                    "   - Reason: " + _inline_text(resolution.reason)
                )

    lines.extend(["", "## Included Paths", ""])

    if snapshot.items:
        lines.extend(
            f"- `{item.relative_path}` (`{item.origin.value}`)"
            for item in snapshot.items
        )
    else:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


def render_skipped(snapshot: StartCollectionSnapshot) -> str:
    _require_type(snapshot, StartCollectionSnapshot, "snapshot")
    lines = [
        "# SKIPPED",
        "",
        f"- Profile: `{snapshot.profile_name}`",
        f"- Count: {len(snapshot.skipped_items)}",
        "",
    ]

    if not snapshot.skipped_items:
        lines.append("(none)")
        return "\n".join(lines) + "\n"

    skipped_index = 0

    for request, resolution in zip(
        snapshot.requests,
        snapshot.path_resolutions,
        strict=True,
    ):
        if resolution.status is CollectionStatus.INCLUDED:
            continue

        skipped = snapshot.skipped_items[skipped_index]
        skipped_index += 1
        lines.extend(
            [
                f"{skipped_index}. Status: `{skipped.status.value}`",
                f"   - Source: `{request.source_label}`",
                f"   - Requested: `{skipped.requested_path}`",
            ]
        )

        if skipped.relative_path is not None:
            lines.append(
                f"   - Relative path: `{skipped.relative_path}`"
            )

        lines.append("   - Reason: " + _inline_text(skipped.reason))

    return "\n".join(lines) + "\n"


def build_generated_text_item(
    relative_path: str,
    content: str,
) -> BundleItem:
    _validate_generated_relative_path(relative_path)

    if not isinstance(content, str):
        raise StartBundleDocumentError("content must be a string")

    encoded = content.encode("utf-8")
    return BundleItem(
        relative_path=relative_path,
        content_kind=ContentKind.TEXT,
        origin=BundleOrigin.GENERATED,
        content=content,
        encoding="utf-8",
        source_bytes=len(encoded),
        source_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def build_start_generated_items(
    project_tree: ProjectTree,
    structure_status: ProjectStructureStatus,
    collection_snapshot: StartCollectionSnapshot,
) -> tuple[BundleItem, ...]:
    _require_type(project_tree, ProjectTree, "project_tree")
    _require_type(
        structure_status,
        ProjectStructureStatus,
        "structure_status",
    )
    _require_type(
        collection_snapshot,
        StartCollectionSnapshot,
        "collection_snapshot",
    )

    profile_names = {
        project_tree.profile_name,
        structure_status.profile_name,
        collection_snapshot.profile_name,
    }

    if len(profile_names) != 1:
        raise StartBundleDocumentError(
            "generated start documents require matching profile names"
        )

    contents = (
        render_repo_overview(build_repo_overview(project_tree)),
        render_project_tree(project_tree),
        render_structure_status(structure_status),
        render_path_index(collection_snapshot),
        render_skipped(collection_snapshot),
    )
    return tuple(
        build_generated_text_item(path, content)
        for path, content in zip(
            _START_GENERATED_PATHS,
            contents,
            strict=True,
        )
    )


def collect_start_bundle(
    repo_root: str | Path,
    config: ConsultConfig,
    profile: ProjectProfile,
    *,
    include_set_names: Iterable[str] = (),
    explicit_paths: Iterable[str] = (),
) -> BundleModel:
    _require_type(config, ConsultConfig, "config")
    _require_type(profile, ProjectProfile, "profile")

    try:
        scanner = InventoryScanner.from_config(repo_root, config)
        inventory_snapshot = scanner.scan()
        folder_tree_before = compare_folder_tree(inventory_snapshot)
        structure_index_before = compare_structure_index(inventory_snapshot)
        folder_tree_sync = sync_folder_tree(inventory_snapshot)
        structure_index_sync = sync_structure_index(inventory_snapshot)
    except (InventoryError, OSError, ValueError) as exc:
        raise StartBundleAssemblyError(
            f"cannot synchronize start bundle structure: {exc}"
        ) from exc

    if folder_tree_sync.comparison != folder_tree_before:
        raise StartBundleAssemblyError(
            "folder_tree.txt changed while the start bundle was being assembled"
        )

    if structure_index_sync.comparison != structure_index_before:
        raise StartBundleAssemblyError(
            "structure index changed while the start bundle was being assembled"
        )

    try:
        folder_tree_after = compare_folder_tree(inventory_snapshot)
        structure_index_after = compare_structure_index(inventory_snapshot)
        structure_status = build_structure_status(
            profile,
            folder_tree_before,
            structure_index_before,
            folder_tree_updated=folder_tree_sync.updated,
            structure_index_updated=structure_index_sync.updated,
            folder_tree_after=folder_tree_after,
            structure_index_after=structure_index_after,
        )
        project_tree = build_project_tree(inventory_snapshot, profile)
        collection_snapshot = collect_start_files(
            scanner.repo_root,
            config,
            profile,
            include_set_names=include_set_names,
            explicit_paths=explicit_paths,
        )
        generated_items = build_start_generated_items(
            project_tree,
            structure_status,
            collection_snapshot,
        )
        items = _merge_start_items(
            generated_items,
            collection_snapshot.items,
        )
    except (
        StartBundleCollectionError,
        StartBundleDocumentError,
        StartBundleStructureError,
        InventoryError,
        OSError,
        ValueError,
    ) as exc:
        raise StartBundleAssemblyError(
            f"cannot assemble start bundle: {exc}"
        ) from exc

    return BundleModel(
        command=BundleCommand.START,
        profile_name=profile.name,
        items=items,
        path_resolutions=collection_snapshot.path_resolutions,
        skipped_items=collection_snapshot.skipped_items,
    )


def _merge_start_items(
    generated_items: Iterable[BundleItem],
    collected_items: Iterable[BundleItem],
) -> tuple[BundleItem, ...]:
    generated = tuple(generated_items)
    collected = tuple(collected_items)

    if not all(isinstance(item, BundleItem) for item in generated):
        raise StartBundleAssemblyError(
            "generated_items must contain only BundleItem values"
        )

    if not all(isinstance(item, BundleItem) for item in collected):
        raise StartBundleAssemblyError(
            "collected_items must contain only BundleItem values"
        )

    seen: dict[str, BundleItem] = {}

    for item in (*generated, *collected):
        folded = item.relative_path.casefold()
        previous = seen.get(folded)

        if previous is not None:
            raise StartBundleAssemblyError(
                "start bundle item path collision: "
                f"{previous.relative_path} ({previous.origin.value}) and "
                f"{item.relative_path} ({item.origin.value})"
            )

        seen[folded] = item

    return generated + collected


def _inline_text(value: str) -> str:
    return " ".join(value.replace("|", "\\|").splitlines()).strip()


def _validate_generated_relative_path(value: str) -> None:
    try:
        _validate_start_relative_path(value, "relative_path")
    except StartBundleCollectionError as exc:
        raise StartBundleDocumentError(str(exc)) from exc


def _normalize_start_strings(
    values: Iterable[str],
    context: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise StartBundleCollectionError(
            f"{context} must be an iterable of strings"
        )

    result = tuple(values)

    for index, value in enumerate(result):
        if not isinstance(value, str):
            raise StartBundleCollectionError(
                f"{context}[{index}] must be a string"
            )

        if context == "explicit_paths":
            _validate_start_relative_path(
                value,
                f"{context}[{index}]",
            )
        elif not value or value != value.strip():
            raise StartBundleCollectionError(
                f"{context}[{index}] must be a non-empty trimmed string"
            )

    return result


def _validate_start_relative_path(value: str, context: str) -> None:
    if not isinstance(value, str) or not value:
        raise StartBundleCollectionError(
            f"{context} must be a non-empty string"
        )

    if value != value.strip():
        raise StartBundleCollectionError(
            f"{context} must not contain leading or trailing whitespace"
        )

    if "\\" in value:
        raise StartBundleCollectionError(
            f"{context} must use / separators: {value}"
        )

    if value.startswith("/") or (len(value) >= 3 and value[1:3] == ":/"):
        raise StartBundleCollectionError(
            f"{context} must be RepoRoot-relative: {value}"
        )

    if value.endswith("/"):
        raise StartBundleCollectionError(
            f"{context} must not end with /: {value}"
        )

    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise StartBundleCollectionError(
            f"{context} is not a canonical path: {value}"
        )

    if any(character in value for character in "*?["):
        raise StartBundleCollectionError(
            f"{context} must not contain wildcards: {value}"
        )


def _outside_profile_reason(
    relative_path: str,
    profile: ProjectProfile,
    *,
    real_relative_path: str | None = None,
) -> str:
    reason = (
        "include-set path is outside project profile: "
        f"profile={profile.name}; path={relative_path}"
    )

    if (
        real_relative_path is not None
        and real_relative_path.casefold() != relative_path.casefold()
    ):
        reason += f"; target={real_relative_path}"

    return reason
