from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ai_consult.bundle import (
    BundleCommand,
    BundleItem,
    BundleModel,
    BundleOrigin,
    ContentKind,
    GitChange,
    SkippedItem,
)
from ai_consult.collection import (
    CollectionResult,
    CollectionStatus,
    ExplicitFileCollector,
)
from ai_consult.config import ConsultConfig, ProjectProfile
from ai_consult.filters import FilterError, PathFilter
from ai_consult.path_resolver import (
    PathResolutionError,
    RepoPathResolver,
)


class GitDiffError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitReviewSnapshot:
    staged_items: tuple[BundleItem, ...] = ()
    unstaged_items: tuple[BundleItem, ...] = ()
    untracked_items: tuple[BundleItem, ...] = ()
    skipped_items: tuple[SkippedItem, ...] = ()

    def __post_init__(self) -> None:
        staged_items = tuple(self.staged_items)
        unstaged_items = tuple(self.unstaged_items)
        untracked_items = tuple(self.untracked_items)
        skipped_items = tuple(self.skipped_items)

        object.__setattr__(self, "staged_items", staged_items)
        object.__setattr__(self, "unstaged_items", unstaged_items)
        object.__setattr__(self, "untracked_items", untracked_items)
        object.__setattr__(self, "skipped_items", skipped_items)

        self._validate_items(
            staged_items,
            BundleOrigin.STAGED,
            "staged_items",
        )
        self._validate_items(
            unstaged_items,
            BundleOrigin.UNSTAGED,
            "unstaged_items",
        )
        self._validate_items(
            untracked_items,
            BundleOrigin.UNTRACKED,
            "untracked_items",
        )

        if not all(
            isinstance(item, SkippedItem)
            for item in skipped_items
        ):
            raise GitDiffError(
                "skipped_items must contain only SkippedItem values"
            )

    @staticmethod
    def _validate_items(
        items: tuple[BundleItem, ...],
        origin: BundleOrigin,
        context: str,
    ) -> None:
        for item in items:
            if not isinstance(item, BundleItem):
                raise GitDiffError(
                    f"{context} must contain only BundleItem values"
                )

            if item.origin is not origin:
                raise GitDiffError(
                    f"{context} item has invalid origin: "
                    f"{item.origin.value}"
                )

    @property
    def items(self) -> tuple[BundleItem, ...]:
        return (
            self.staged_items
            + self.unstaged_items
            + self.untracked_items
        )


def collect_review_bundle(
    repo_root: str | Path,
    config: ConsultConfig,
    profile: ProjectProfile,
    *,
    target_paths: Iterable[str] = (),
) -> BundleModel:
    collector = GitDiffCollector(
        repo_root,
        config,
        profile,
        target_paths=target_paths,
    )
    snapshot = collector.collect()

    return BundleModel(
        command=BundleCommand.REVIEW,
        profile_name=collector.profile.name,
        target_paths=collector.target_paths,
        items=snapshot.items,
        skipped_items=snapshot.skipped_items,
    )


@dataclass(frozen=True)
class _RawChange:
    change: GitChange
    relative_path: str
    previous_path: str | None = None


class GitDiffCollector:
    def __init__(
        self,
        repo_root: str | Path,
        config: ConsultConfig,
        profile: ProjectProfile,
        *,
        target_paths: Iterable[str] = (),
    ) -> None:
        if not isinstance(config, ConsultConfig):
            raise GitDiffError("config must be a ConsultConfig value")

        if not isinstance(profile, ProjectProfile):
            raise GitDiffError("profile must be a ProjectProfile value")

        if not profile.name or profile.name != profile.name.strip():
            raise GitDiffError(
                "profile name must be non-empty and trimmed"
            )

        for index, scope_root in enumerate(profile.scope_roots):
            _validate_relative_path(
                scope_root,
                f"profile.scope_roots[{index}]",
            )

        try:
            self._resolver = RepoPathResolver(repo_root)
            self._repo_root = self._resolver.repo_root
            self._path_filter = PathFilter(
                config.filters.exclude_paths
            )
            self._file_collector = (
                ExplicitFileCollector.from_config(
                    self._repo_root,
                    config,
                )
            )
        except (PathResolutionError, FilterError, ValueError) as exc:
            raise GitDiffError(
                f"cannot initialize Git diff collection: {exc}"
            ) from exc

        self._profile = profile
        self._target_paths = _normalize_target_paths(
            target_paths,
            profile,
        )

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def profile(self) -> ProjectProfile:
        return self._profile

    @property
    def target_paths(self) -> tuple[str, ...]:
        return self._target_paths

    def collect(self) -> GitReviewSnapshot:
        self._verify_git_root()

        staged_items, staged_skips = self._collect_tracked_changes(
            BundleOrigin.STAGED
        )
        unstaged_items, unstaged_skips = self._collect_tracked_changes(
            BundleOrigin.UNSTAGED
        )
        untracked_items, untracked_skips = self._collect_untracked()

        return GitReviewSnapshot(
            staged_items=tuple(sorted(staged_items, key=_item_sort_key)),
            unstaged_items=tuple(
                sorted(unstaged_items, key=_item_sort_key)
            ),
            untracked_items=tuple(
                sorted(untracked_items, key=_item_sort_key)
            ),
            skipped_items=tuple(
                sorted(
                    staged_skips
                    + unstaged_skips
                    + untracked_skips,
                    key=_skip_sort_key,
                )
            ),
        )

    def _verify_git_root(self) -> None:
        output = self._run_git_text(
            ("rev-parse", "--show-toplevel"),
            description="resolve Git worktree root",
        ).strip()

        if not output:
            raise GitDiffError("Git returned an empty worktree root")

        try:
            git_root = Path(output).resolve(strict=True)
        except OSError as exc:
            raise GitDiffError(
                f"cannot resolve Git worktree root: {output}: {exc}"
            ) from exc

        if _normalized_absolute(git_root) != _normalized_absolute(
            self._repo_root
        ):
            raise GitDiffError(
                "Git worktree root does not match RepoRoot: "
                f"git={git_root}; repo={self._repo_root}"
            )

    def _collect_tracked_changes(
        self,
        origin: BundleOrigin,
    ) -> tuple[list[BundleItem], list[SkippedItem]]:
        raw_changes = self._list_tracked_changes(origin)
        items: list[BundleItem] = []
        skipped: list[SkippedItem] = []

        for raw_change in raw_changes:
            change_items, change_skips = self._materialize_change(
                origin,
                raw_change,
            )
            items.extend(change_items)
            skipped.extend(change_skips)

        return items, skipped

    def _list_tracked_changes(
        self,
        origin: BundleOrigin,
    ) -> tuple[_RawChange, ...]:
        args = ["diff"]

        if origin is BundleOrigin.STAGED:
            args.append("--cached")
        elif origin is not BundleOrigin.UNSTAGED:
            raise GitDiffError(
                "tracked change origin must be staged or unstaged"
            )

        args.extend(
            (
                "--name-status",
                "-z",
                "--no-ext-diff",
                "--no-textconv",
                "--find-renames",
                "--find-copies",
                "--find-copies-harder",
                "--",
            )
        )
        output = self._run_git_bytes(
            tuple(args),
            description=f"list {origin.value} Git changes",
        )
        return _deduplicate_raw_changes(_parse_name_status(output))

    def _materialize_change(
        self,
        origin: BundleOrigin,
        raw_change: _RawChange,
    ) -> tuple[list[BundleItem], list[SkippedItem]]:
        if raw_change.change is GitChange.RENAMED:
            assert raw_change.previous_path is not None
            return self._materialize_rename(
                origin,
                raw_change.previous_path,
                raw_change.relative_path,
            )

        if raw_change.change is GitChange.COPIED:
            assert raw_change.previous_path is not None
            return self._materialize_copy(
                origin,
                raw_change.previous_path,
                raw_change.relative_path,
            )

        path = raw_change.relative_path

        if not self._is_selected(path):
            return [], []

        pattern = self._path_filter.matching_pattern(path)

        if pattern is not None:
            return [], [
                _excluded_skip(path, origin, pattern)
            ]

        return [
            self._build_diff_item(
                origin=origin,
                relative_path=path,
                git_change=raw_change.change,
                diff_paths=(path,),
                detect_moves=True,
            )
        ], []

    def _materialize_rename(
        self,
        origin: BundleOrigin,
        previous_path: str,
        relative_path: str,
    ) -> tuple[list[BundleItem], list[SkippedItem]]:
        previous_selected = self._is_selected(previous_path)
        current_selected = self._is_selected(relative_path)
        previous_pattern = (
            self._path_filter.matching_pattern(previous_path)
            if previous_selected
            else None
        )
        current_pattern = (
            self._path_filter.matching_pattern(relative_path)
            if current_selected
            else None
        )
        previous_included = previous_selected and previous_pattern is None
        current_included = current_selected and current_pattern is None
        skipped = self._move_skips(
            origin,
            previous_path,
            previous_selected,
            previous_pattern,
            relative_path,
            current_selected,
            current_pattern,
        )

        if previous_included and current_included:
            return [
                self._build_diff_item(
                    origin=origin,
                    relative_path=relative_path,
                    git_change=GitChange.RENAMED,
                    previous_path=previous_path,
                    diff_paths=(previous_path, relative_path),
                    detect_moves=True,
                )
            ], skipped

        if previous_included:
            return [
                self._build_diff_item(
                    origin=origin,
                    relative_path=previous_path,
                    git_change=GitChange.DELETED,
                    diff_paths=(previous_path,),
                    detect_moves=False,
                )
            ], skipped

        if current_included:
            return [
                self._build_diff_item(
                    origin=origin,
                    relative_path=relative_path,
                    git_change=GitChange.ADDED,
                    diff_paths=(relative_path,),
                    detect_moves=False,
                )
            ], skipped

        return [], skipped

    def _materialize_copy(
        self,
        origin: BundleOrigin,
        previous_path: str,
        relative_path: str,
    ) -> tuple[list[BundleItem], list[SkippedItem]]:
        previous_selected = self._is_selected(previous_path)
        current_selected = self._is_selected(relative_path)
        previous_pattern = (
            self._path_filter.matching_pattern(previous_path)
            if previous_selected
            else None
        )
        current_pattern = (
            self._path_filter.matching_pattern(relative_path)
            if current_selected
            else None
        )
        previous_included = previous_selected and previous_pattern is None
        current_included = current_selected and current_pattern is None
        skipped = self._move_skips(
            origin,
            previous_path,
            previous_selected,
            previous_pattern,
            relative_path,
            current_selected,
            current_pattern,
        )

        if previous_included and current_included:
            return [
                self._build_diff_item(
                    origin=origin,
                    relative_path=relative_path,
                    git_change=GitChange.COPIED,
                    previous_path=previous_path,
                    diff_paths=(previous_path, relative_path),
                    detect_moves=True,
                )
            ], skipped

        if current_included:
            return [
                self._build_diff_item(
                    origin=origin,
                    relative_path=relative_path,
                    git_change=GitChange.ADDED,
                    diff_paths=(relative_path,),
                    detect_moves=False,
                )
            ], skipped

        return [], skipped

    @staticmethod
    def _move_skips(
        origin: BundleOrigin,
        previous_path: str,
        previous_selected: bool,
        previous_pattern: str | None,
        relative_path: str,
        current_selected: bool,
        current_pattern: str | None,
    ) -> list[SkippedItem]:
        skipped: list[SkippedItem] = []

        if previous_selected and previous_pattern is not None:
            skipped.append(
                _excluded_skip(
                    previous_path,
                    origin,
                    previous_pattern,
                )
            )

        if current_selected and current_pattern is not None:
            skipped.append(
                _excluded_skip(
                    relative_path,
                    origin,
                    current_pattern,
                )
            )

        return skipped

    def _build_diff_item(
        self,
        *,
        origin: BundleOrigin,
        relative_path: str,
        git_change: GitChange,
        diff_paths: tuple[str, ...],
        detect_moves: bool,
        previous_path: str | None = None,
    ) -> BundleItem:
        args = ["diff"]

        if origin is BundleOrigin.STAGED:
            args.append("--cached")
        elif origin is not BundleOrigin.UNSTAGED:
            raise GitDiffError(
                "diff item origin must be staged or unstaged"
            )

        args.extend(
            (
                "--no-color",
                "--no-ext-diff",
                "--no-textconv",
                "--full-index",
                "--diff-algorithm=histogram",
                "--no-indent-heuristic",
                "--unified=3",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                "--submodule=short",
            )
        )

        if detect_moves:
            args.extend(
                (
                    "--find-renames",
                    "--find-copies",
                    "--find-copies-harder",
                )
            )
        else:
            args.append("--no-renames")

        args.append("--")
        args.extend(diff_paths)
        raw_output = self._run_git_bytes(
            tuple(args),
            description=(
                f"collect {origin.value} diff for "
                f"{relative_path}"
            ),
        )
        content = _decode_diff(raw_output, relative_path)
        source = content.encode("utf-8")

        return BundleItem(
            relative_path=relative_path,
            content_kind=ContentKind.DIFF,
            origin=origin,
            content=content,
            encoding="utf-8",
            source_bytes=len(source),
            source_sha256=hashlib.sha256(source).hexdigest(),
            git_change=git_change,
            previous_path=previous_path,
        )

    def _collect_untracked(
        self,
    ) -> tuple[list[BundleItem], list[SkippedItem]]:
        output = self._run_git_bytes(
            (
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
            ),
            description="list untracked files",
        )
        paths = _parse_nul_paths(output, "untracked file list")
        items: list[BundleItem] = []
        skipped: list[SkippedItem] = []

        for path in paths:
            if not self._is_selected(path):
                continue

            result = self._file_collector.collect_one(path)

            if not result.included:
                skipped.append(
                    _collection_skip(
                        result,
                        BundleOrigin.UNTRACKED,
                    )
                )
                continue

            assert result.file is not None

            try:
                source = result.file.real_path.read_bytes()
            except OSError as exc:
                skipped.append(
                    SkippedItem(
                        requested_path=path,
                        status=CollectionStatus.READ_ERROR,
                        origin=BundleOrigin.UNTRACKED,
                        reason=(
                            "cannot read collected file bytes: "
                            f"{result.file.real_path}: {exc}"
                        ),
                        relative_path=result.file.relative_path,
                    )
                )
                continue

            if len(source) != result.file.size_bytes:
                skipped.append(
                    SkippedItem(
                        requested_path=path,
                        status=CollectionStatus.READ_ERROR,
                        origin=BundleOrigin.UNTRACKED,
                        reason=(
                            "file changed while it was being collected: "
                            f"expected {result.file.size_bytes} bytes; "
                            f"read {len(source)} bytes"
                        ),
                        relative_path=result.file.relative_path,
                    )
                )
                continue

            items.append(
                BundleItem(
                    relative_path=result.file.relative_path,
                    content_kind=ContentKind.TEXT,
                    origin=BundleOrigin.UNTRACKED,
                    content=result.file.text,
                    encoding=result.file.encoding,
                    source_bytes=len(source),
                    source_sha256=(
                        hashlib.sha256(source).hexdigest()
                    ),
                    git_change=GitChange.ADDED,
                )
            )

        return items, skipped

    def _is_selected(self, relative_path: str) -> bool:
        if not self._profile.contains(relative_path):
            return False

        if not self._target_paths:
            return True

        folded = relative_path.casefold()

        return any(
            folded == target.casefold()
            or folded.startswith(target.casefold() + "/")
            for target in self._target_paths
        )

    def _run_git_text(
        self,
        args: tuple[str, ...],
        *,
        description: str,
    ) -> str:
        output = self._run_git_bytes(args, description=description)

        try:
            return output.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitDiffError(
                f"Git output is not UTF-8 while attempting to "
                f"{description}"
            ) from exc

    def _run_git_bytes(
        self,
        args: tuple[str, ...],
        *,
        description: str,
    ) -> bytes:
        command = (
            "git",
            "-c",
            "core.quotepath=false",
            *args,
        )
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "LC_ALL": "C",
                "LANG": "C",
            }
        )

        try:
            result = subprocess.run(
                command,
                cwd=self._repo_root,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except OSError as exc:
            raise GitDiffError(
                f"cannot execute Git while attempting to "
                f"{description}: {exc}"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            raise GitDiffError(
                f"Git failed while attempting to {description} "
                f"(exit {result.returncode}){detail}"
            )

        return result.stdout


def _normalize_target_paths(
    values: Iterable[str],
    profile: ProjectProfile,
) -> tuple[str, ...]:
    candidates: list[str] = []

    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise GitDiffError(
                f"target_paths[{index}] must be a string"
            )

        _validate_relative_path(value, f"target_paths[{index}]")

        if not profile.contains(value):
            raise GitDiffError(
                "target path is outside the project profile: "
                f"{value}"
            )

        candidates.append(value)

    ordered = sorted(candidates, key=lambda item: (item.casefold(), item))
    result: list[str] = []
    seen: set[str] = set()

    for value in ordered:
        folded = value.casefold()

        if folded in seen:
            continue

        seen.add(folded)
        result.append(value)

    return tuple(result)


def _validate_relative_path(value: str, context: str) -> None:
    if not value:
        raise GitDiffError(f"{context} must be a non-empty string")

    if value != value.strip():
        raise GitDiffError(
            f"{context} must not contain leading or trailing whitespace"
        )

    if "\\" in value:
        raise GitDiffError(
            f"{context} must use / separators: {value}"
        )

    if value.startswith("/") or (
        len(value) >= 3 and value[1:3] == ":/"
    ):
        raise GitDiffError(
            f"{context} must be RepoRoot-relative: {value}"
        )

    if value.endswith("/"):
        raise GitDiffError(
            f"{context} must not end with /: {value}"
        )

    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise GitDiffError(
            f"{context} is not a canonical path: {value}"
        )


def _parse_name_status(data: bytes) -> tuple[_RawChange, ...]:
    fields = _split_nul_fields(data, "Git name-status output")
    changes: list[_RawChange] = []
    index = 0

    while index < len(fields):
        status = _decode_utf8(fields[index], "Git change status")
        index += 1

        if not status:
            raise GitDiffError("Git returned an empty change status")

        code = status[0]

        if code in {"R", "C"}:
            if index + 1 >= len(fields):
                raise GitDiffError(
                    f"Git returned an incomplete {code} status record"
                )

            previous_path = _decode_git_path(fields[index])
            relative_path = _decode_git_path(fields[index + 1])
            index += 2
            change = (
                GitChange.RENAMED
                if code == "R"
                else GitChange.COPIED
            )
            changes.append(
                _RawChange(
                    change=change,
                    relative_path=relative_path,
                    previous_path=previous_path,
                )
            )
            continue

        mapped = {
            "A": GitChange.ADDED,
            "M": GitChange.MODIFIED,
            "D": GitChange.DELETED,
            "T": GitChange.TYPE_CHANGED,
            "U": GitChange.UNMERGED,
        }.get(code)

        if mapped is None:
            raise GitDiffError(
                f"unsupported Git change status: {status}"
            )

        if index >= len(fields):
            raise GitDiffError(
                f"Git returned an incomplete {status} status record"
            )

        changes.append(
            _RawChange(
                change=mapped,
                relative_path=_decode_git_path(fields[index]),
            )
        )
        index += 1

    return tuple(changes)



def _deduplicate_raw_changes(
    changes: tuple[_RawChange, ...],
) -> tuple[_RawChange, ...]:
    ordered: list[_RawChange] = []
    positions: dict[tuple[str, str | None], int] = {}

    for change in changes:
        key = (
            change.relative_path.casefold(),
            (
                change.previous_path.casefold()
                if change.previous_path is not None
                else None
            ),
        )
        existing_index = positions.get(key)

        if existing_index is None:
            positions[key] = len(ordered)
            ordered.append(change)
            continue

        existing = ordered[existing_index]

        if existing.change is GitChange.UNMERGED:
            continue

        if change.change is GitChange.UNMERGED:
            ordered[existing_index] = change
            continue

        if existing != change:
            raise GitDiffError(
                "Git returned conflicting statuses for path: "
                f"{change.relative_path}"
            )

    return tuple(ordered)

def _parse_nul_paths(data: bytes, context: str) -> tuple[str, ...]:
    return tuple(
        _decode_git_path(field)
        for field in _split_nul_fields(data, context)
    )


def _split_nul_fields(data: bytes, context: str) -> tuple[bytes, ...]:
    if not data:
        return ()

    if not data.endswith(b"\0"):
        raise GitDiffError(f"{context} is not NUL-terminated")

    fields = tuple(data[:-1].split(b"\0"))

    if any(field == b"" for field in fields):
        raise GitDiffError(f"{context} contains an empty field")

    return fields


def _decode_git_path(value: bytes) -> str:
    path = _decode_utf8(value, "Git path")
    _validate_relative_path(path, "Git path")
    return path


def _decode_utf8(value: bytes, context: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GitDiffError(f"{context} is not UTF-8") from exc


def _decode_diff(value: bytes, relative_path: str) -> str:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GitDiffError(
            f"Git diff is not UTF-8: {relative_path}"
        ) from exc

    return text.replace("\r\n", "\n").replace("\r", "\n")


def _excluded_skip(
    relative_path: str,
    origin: BundleOrigin,
    pattern: str,
) -> SkippedItem:
    return SkippedItem(
        requested_path=relative_path,
        status=CollectionStatus.EXCLUDED,
        origin=origin,
        reason=f"excluded by configured pattern: {pattern}",
        relative_path=relative_path,
    )


def _collection_skip(
    result: CollectionResult,
    origin: BundleOrigin,
) -> SkippedItem:
    return SkippedItem(
        requested_path=result.requested_path,
        status=result.status,
        origin=origin,
        reason=result.reason or "file collection failed",
        relative_path=result.relative_path,
    )


def _item_sort_key(
    item: BundleItem,
) -> tuple[str, str, str, str]:
    return (
        item.relative_path.casefold(),
        item.relative_path,
        (item.previous_path or "").casefold(),
        item.previous_path or "",
    )


def _skip_sort_key(
    item: SkippedItem,
) -> tuple[str, str, str, str]:
    path = item.relative_path or item.requested_path
    return (
        item.origin.value,
        path.casefold(),
        path,
        item.status.value,
    )


def _normalized_absolute(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))
