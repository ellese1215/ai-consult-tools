from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from ai_consult.config import ProjectProfile
from ai_consult.inventory import (
    FolderTreeComparison,
    InventoryEntry,
    InventoryEntryType,
    InventorySnapshot,
    MoveCandidate,
    StructureDiff,
    StructureIndexComparison,
    STRUCTURE_INDEX_RELATIVE_PATH,
)


class StartBundleStructureError(ValueError):
    pass


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
