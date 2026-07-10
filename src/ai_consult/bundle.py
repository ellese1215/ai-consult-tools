from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from enum import Enum

from ai_consult.collection import CollectionStatus


_MANIFEST_HEADER = (
    "relative_path",
    "content_kind",
    "origin",
    "git_change",
    "previous_path",
    "source_bytes",
    "source_sha256",
    "encoding",
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class BundleModelError(ValueError):
    pass


class BundleCommand(str, Enum):
    START = "start"
    REVIEW = "review"
    INSPECT = "inspect"


class ContentKind(str, Enum):
    TEXT = "text"
    DIFF = "diff"
    INSPECTION = "inspection"


class BundleOrigin(str, Enum):
    EXPLICIT = "explicit"
    INCLUDE_SET = "include_set"
    STAGED = "staged"
    UNSTAGED = "unstaged"
    UNTRACKED = "untracked"
    GENERATED = "generated"


class GitChange(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"
    UNMERGED = "unmerged"


def _validate_relative_path(value: str, context: str) -> None:
    if not isinstance(value, str) or not value:
        raise BundleModelError(
            f"{context} must be a non-empty string"
        )

    if value != value.strip():
        raise BundleModelError(
            f"{context} must not contain leading or trailing whitespace"
        )

    if "\\" in value:
        raise BundleModelError(
            f"{context} must use / separators: {value}"
        )

    if value.startswith("/") or (
        len(value) >= 3 and value[1:3] == ":/"
    ):
        raise BundleModelError(
            f"{context} must be RepoRoot-relative: {value}"
        )

    if value.endswith("/"):
        raise BundleModelError(
            f"{context} must not end with /: {value}"
        )

    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise BundleModelError(
            f"{context} is not a canonical path: {value}"
        )


def _validate_non_empty_text(value: str, context: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BundleModelError(
            f"{context} must be a non-empty string"
        )

    if value != value.strip():
        raise BundleModelError(
            f"{context} must not contain leading or trailing whitespace"
        )


def _validate_source_metadata(
    source_bytes: int,
    source_sha256: str,
    encoding: str,
) -> None:
    if type(source_bytes) is not int or source_bytes < 0:
        raise BundleModelError(
            "source_bytes must be a non-negative integer"
        )

    if not isinstance(source_sha256, str) or not _SHA256_PATTERN.fullmatch(
        source_sha256
    ):
        raise BundleModelError(
            "source_sha256 must be a lowercase SHA-256 hex digest"
        )

    _validate_non_empty_text(encoding, "encoding")


@dataclass(frozen=True)
class BundleItem:
    relative_path: str
    content_kind: ContentKind
    origin: BundleOrigin
    content: str
    encoding: str
    source_bytes: int
    source_sha256: str
    git_change: GitChange | None = None
    previous_path: str | None = None

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path, "relative_path")

        if not isinstance(self.content_kind, ContentKind):
            raise BundleModelError(
                "content_kind must be a ContentKind value"
            )

        if not isinstance(self.origin, BundleOrigin):
            raise BundleModelError(
                "origin must be a BundleOrigin value"
            )

        if not isinstance(self.content, str):
            raise BundleModelError("content must be a string")

        _validate_source_metadata(
            self.source_bytes,
            self.source_sha256,
            self.encoding,
        )

        if self.git_change is not None and not isinstance(
            self.git_change,
            GitChange,
        ):
            raise BundleModelError(
                "git_change must be a GitChange value or None"
            )

        if self.previous_path is not None:
            _validate_relative_path(
                self.previous_path,
                "previous_path",
            )

        self._validate_origin_and_content_kind()
        self._validate_previous_path()

    def _validate_origin_and_content_kind(self) -> None:
        if self.origin in {
            BundleOrigin.STAGED,
            BundleOrigin.UNSTAGED,
        }:
            if self.content_kind is not ContentKind.DIFF:
                raise BundleModelError(
                    "staged and unstaged items must use diff content"
                )

            if self.git_change is None:
                raise BundleModelError(
                    "staged and unstaged items require git_change"
                )

            return

        if self.origin is BundleOrigin.UNTRACKED:
            if self.content_kind is not ContentKind.TEXT:
                raise BundleModelError(
                    "untracked items must use text content"
                )

            if self.git_change is not GitChange.ADDED:
                raise BundleModelError(
                    "untracked items must use git_change=added"
                )

            return

        if self.git_change is not None:
            raise BundleModelError(
                "non-Git bundle origins must not set git_change"
            )

        if self.content_kind is ContentKind.DIFF:
            raise BundleModelError(
                "diff content must originate from staged or unstaged"
            )

        if (
            self.content_kind is ContentKind.INSPECTION
            and self.origin is not BundleOrigin.GENERATED
        ):
            raise BundleModelError(
                "inspection content must use generated origin"
            )

    def _validate_previous_path(self) -> None:
        change_uses_previous_path = self.git_change in {
            GitChange.RENAMED,
            GitChange.COPIED,
        }

        if change_uses_previous_path and self.previous_path is None:
            raise BundleModelError(
                "renamed and copied items require previous_path"
            )

        if not change_uses_previous_path and self.previous_path is not None:
            raise BundleModelError(
                "previous_path is only valid for renamed or copied items"
            )


@dataclass(frozen=True)
class PathResolution:
    requested_path: str
    status: CollectionStatus
    origin: BundleOrigin
    resolved_paths: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        _validate_relative_path(
            self.requested_path,
            "requested_path",
        )

        if not isinstance(self.status, CollectionStatus):
            raise BundleModelError(
                "status must be a CollectionStatus value"
            )

        if not isinstance(self.origin, BundleOrigin):
            raise BundleModelError(
                "origin must be a BundleOrigin value"
            )

        resolved_paths = tuple(self.resolved_paths)
        object.__setattr__(self, "resolved_paths", resolved_paths)

        for index, path in enumerate(resolved_paths):
            _validate_relative_path(
                path,
                f"resolved_paths[{index}]",
            )

        folded_paths = tuple(path.casefold() for path in resolved_paths)

        if len(folded_paths) != len(set(folded_paths)):
            raise BundleModelError(
                "resolved_paths contains duplicate paths"
            )

        if (
            self.status is CollectionStatus.INCLUDED
            and not resolved_paths
        ):
            raise BundleModelError(
                "included path resolution requires resolved_paths"
            )

        if self.status is not CollectionStatus.INCLUDED:
            _validate_non_empty_text(self.reason or "", "reason")
        elif self.reason is not None:
            _validate_non_empty_text(self.reason, "reason")


@dataclass(frozen=True)
class SkippedItem:
    requested_path: str
    status: CollectionStatus
    origin: BundleOrigin
    reason: str
    relative_path: str | None = None

    def __post_init__(self) -> None:
        _validate_relative_path(
            self.requested_path,
            "requested_path",
        )
        _validate_non_empty_text(self.reason, "reason")

        if not isinstance(self.status, CollectionStatus):
            raise BundleModelError(
                "status must be a CollectionStatus value"
            )

        if self.status is CollectionStatus.INCLUDED:
            raise BundleModelError(
                "skipped item status must not be included"
            )

        if not isinstance(self.origin, BundleOrigin):
            raise BundleModelError(
                "origin must be a BundleOrigin value"
            )

        if self.relative_path is not None:
            _validate_relative_path(
                self.relative_path,
                "relative_path",
            )


@dataclass(frozen=True)
class ManifestRow:
    relative_path: str
    content_kind: ContentKind
    origin: BundleOrigin
    git_change: GitChange | None
    previous_path: str | None
    source_bytes: int
    source_sha256: str
    encoding: str

    @classmethod
    def from_item(cls, item: BundleItem) -> ManifestRow:
        return cls(
            relative_path=item.relative_path,
            content_kind=item.content_kind,
            origin=item.origin,
            git_change=item.git_change,
            previous_path=item.previous_path,
            source_bytes=item.source_bytes,
            source_sha256=item.source_sha256,
            encoding=item.encoding,
        )

    def as_csv_row(self) -> tuple[str, ...]:
        return (
            self.relative_path,
            self.content_kind.value,
            self.origin.value,
            self.git_change.value if self.git_change else "",
            self.previous_path or "",
            str(self.source_bytes),
            self.source_sha256,
            self.encoding,
        )


@dataclass(frozen=True)
class BundleModel:
    command: BundleCommand
    profile_name: str
    items: tuple[BundleItem, ...] = ()
    path_resolutions: tuple[PathResolution, ...] = ()
    skipped_items: tuple[SkippedItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.command, BundleCommand):
            raise BundleModelError(
                "command must be a BundleCommand value"
            )

        _validate_non_empty_text(
            self.profile_name,
            "profile_name",
        )

        items = tuple(self.items)
        path_resolutions = tuple(self.path_resolutions)
        skipped_items = tuple(self.skipped_items)

        object.__setattr__(self, "items", items)
        object.__setattr__(
            self,
            "path_resolutions",
            path_resolutions,
        )
        object.__setattr__(
            self,
            "skipped_items",
            skipped_items,
        )

        if not all(isinstance(item, BundleItem) for item in items):
            raise BundleModelError(
                "items must contain only BundleItem values"
            )

        if not all(
            isinstance(item, PathResolution)
            for item in path_resolutions
        ):
            raise BundleModelError(
                "path_resolutions must contain only PathResolution values"
            )

        if not all(
            isinstance(item, SkippedItem)
            for item in skipped_items
        ):
            raise BundleModelError(
                "skipped_items must contain only SkippedItem values"
            )

        seen: set[tuple[BundleOrigin, str, str | None]] = set()

        for item in items:
            key = (
                item.origin,
                item.relative_path.casefold(),
                (
                    item.previous_path.casefold()
                    if item.previous_path is not None
                    else None
                ),
            )

            if key in seen:
                raise BundleModelError(
                    "duplicate bundle item: "
                    f"origin={item.origin.value}; "
                    f"path={item.relative_path}; "
                    f"previous_path={item.previous_path or ''}"
                )

            seen.add(key)

    @property
    def included_count(self) -> int:
        return len(self.items)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_items)

    @property
    def manifest_rows(self) -> tuple[ManifestRow, ...]:
        ordered_items = sorted(
            self.items,
            key=_bundle_item_sort_key,
        )
        return tuple(
            ManifestRow.from_item(item)
            for item in ordered_items
        )


def _bundle_item_sort_key(
    item: BundleItem,
) -> tuple[str, str, str, str, str, str]:
    return (
        item.relative_path.casefold(),
        item.relative_path,
        item.origin.value,
        item.content_kind.value,
        (item.previous_path or "").casefold(),
        item.previous_path or "",
    )


def render_manifest_csv(bundle: BundleModel) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_MANIFEST_HEADER)

    for row in bundle.manifest_rows:
        writer.writerow(row.as_csv_row())

    return output.getvalue()
