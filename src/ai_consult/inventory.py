from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from ai_consult.config import ConsultConfig
from ai_consult.filters import LiteralDirectoryBoundaryFilter, PathFilter
from ai_consult.path_resolver import RepoPathResolver


GENERATED_STRUCTURE_PATHS = frozenset(
    {"folder_tree.txt", "folder_tree.txt.v4_tmp"}
)
FOLDER_TREE_FILENAME = "folder_tree.txt"
STRUCTURE_INDEX_RELATIVE_PATH = (
    "ai-consult-tools/local/cache/repo_structure_index.json"
)
STRUCTURE_INDEX_SCHEMA_VERSION = 1


class InventoryError(RuntimeError):
    pass


class FolderTreeFormatError(InventoryError):
    pass


class StructureIndexFormatError(InventoryError):
    pass


class InventoryEntryType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    OTHER = "other"


class InventoryLinkType(str, Enum):
    NONE = "none"
    SYMLINK = "symlink"
    JUNCTION = "junction"


@dataclass(frozen=True)
class InventoryEntry:
    relative_path: str
    entry_type: InventoryEntryType
    link_type: InventoryLinkType = InventoryLinkType.NONE

    @property
    def rendered_path(self) -> str:
        if self.entry_type is InventoryEntryType.DIRECTORY:
            return self.relative_path + "/"

        return self.relative_path

    @property
    def name(self) -> str:
        return PurePosixPath(self.relative_path).name

    @property
    def parent_path(self) -> str:
        parent = PurePosixPath(self.relative_path).parent.as_posix()
        return "" if parent == "." else parent

    @property
    def extension(self) -> str:
        if self.entry_type is not InventoryEntryType.FILE:
            return ""

        return PurePosixPath(self.relative_path).suffix.casefold()

    def to_structure_index_entry(self) -> dict[str, str]:
        return {
            "relativePath": self.relative_path,
            "name": self.name,
            "parentPath": self.parent_path,
            "entryType": self.entry_type.value,
            "linkType": self.link_type.value,
            "extension": self.extension,
        }


@dataclass(frozen=True)
class InventorySnapshot:
    repo_root: Path
    entries: tuple[InventoryEntry, ...]
    output_roots: tuple[str, ...] = ()

    @property
    def rendered_paths(self) -> tuple[str, ...]:
        return tuple(entry.rendered_path for entry in self.entries)


@dataclass(frozen=True)
class MoveCandidate:
    previous_path: str
    current_path: str


@dataclass(frozen=True)
class StructureDiff:
    added_paths: tuple[str, ...] = ()
    removed_paths: tuple[str, ...] = ()
    move_candidates: tuple[MoveCandidate, ...] = ()


@dataclass(frozen=True)
class FolderTreeComparison:
    folder_tree_path: Path
    is_current: bool
    previous_exists: bool
    diff: StructureDiff | None
    format_error: str | None = None


@dataclass(frozen=True)
class FolderTreeSyncResult:
    comparison: FolderTreeComparison
    updated: bool


@dataclass(frozen=True)
class StructureIndexComparison:
    structure_index_path: Path
    is_current: bool
    previous_exists: bool
    format_error: str | None = None


@dataclass(frozen=True)
class StructureIndexSyncResult:
    comparison: StructureIndexComparison
    updated: bool


def _is_junction(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", None)

    if callable(is_junction):
        try:
            return bool(is_junction(path))
        except OSError:
            return False

    if os.name != "nt":
        return False

    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag) and not path.is_symlink()


def _linked_entry_type(entry: os.DirEntry[str]) -> InventoryEntryType:
    try:
        if entry.is_dir(follow_symlinks=True):
            return InventoryEntryType.DIRECTORY

        if entry.is_file(follow_symlinks=True):
            return InventoryEntryType.FILE
    except OSError:
        pass

    return InventoryEntryType.OTHER


class InventoryScanner:
    def __init__(
        self,
        repo_root: str | Path,
        path_filter: PathFilter,
        output_root_filter: LiteralDirectoryBoundaryFilter | None = None,
    ) -> None:
        self._repo_root = RepoPathResolver(repo_root).repo_root
        self._path_filter = path_filter
        self._output_root_filter = (
            output_root_filter or LiteralDirectoryBoundaryFilter()
        )

    @classmethod
    def from_config(
        cls,
        repo_root: str | Path,
        config: ConsultConfig,
    ) -> InventoryScanner:
        return cls(
            repo_root,
            PathFilter(config.inventory.exclude_paths),
            LiteralDirectoryBoundaryFilter(config.output_roots),
        )

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def scan(self) -> InventorySnapshot:
        entries: list[InventoryEntry] = []
        self._scan_directory(self._repo_root, entries)
        entries.sort(key=_inventory_entry_sort_key)

        return InventorySnapshot(
            repo_root=self._repo_root,
            entries=tuple(entries),
            output_roots=self._output_root_filter.directory_roots,
        )

    def _scan_directory(
        self,
        directory: Path,
        entries: list[InventoryEntry],
    ) -> None:
        try:
            iterator = os.scandir(directory)
        except OSError as exc:
            raise InventoryError(
                f"cannot scan directory: {directory}: {exc}"
            ) from exc

        try:
            with iterator:
                for entry in iterator:
                    self._scan_entry(entry, entries)
        except InventoryError:
            raise
        except OSError as exc:
            raise InventoryError(
                f"cannot scan directory entry: {directory}: {exc}"
            ) from exc

    def _scan_entry(
        self,
        entry: os.DirEntry[str],
        entries: list[InventoryEntry],
    ) -> None:
        logical_path = Path(entry.path)

        try:
            relative_path = logical_path.relative_to(
                self._repo_root
            ).as_posix()
        except ValueError as exc:
            raise InventoryError(
                f"scanned path escaped RepoRoot: {logical_path}"
            ) from exc

        if relative_path in GENERATED_STRUCTURE_PATHS:
            return

        if self._output_root_filter.is_within(relative_path):
            return

        if self._path_filter.is_excluded(relative_path):
            return

        if entry.is_symlink():
            entries.append(
                InventoryEntry(
                    relative_path=relative_path,
                    entry_type=_linked_entry_type(entry),
                    link_type=InventoryLinkType.SYMLINK,
                )
            )
            return

        if _is_junction(logical_path):
            entries.append(
                InventoryEntry(
                    relative_path=relative_path,
                    entry_type=InventoryEntryType.DIRECTORY,
                    link_type=InventoryLinkType.JUNCTION,
                )
            )
            return

        try:
            is_directory = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError as exc:
            raise InventoryError(
                f"cannot inspect path: {logical_path}: {exc}"
            ) from exc

        if is_directory:
            entries.append(
                InventoryEntry(
                    relative_path=relative_path,
                    entry_type=InventoryEntryType.DIRECTORY,
                )
            )
            self._scan_directory(logical_path, entries)
            return

        if is_file:
            entries.append(
                InventoryEntry(
                    relative_path=relative_path,
                    entry_type=InventoryEntryType.FILE,
                )
            )
            return

        entries.append(
            InventoryEntry(
                relative_path=relative_path,
                entry_type=InventoryEntryType.OTHER,
            )
        )


def _inventory_entry_sort_key(
    entry: InventoryEntry,
) -> tuple[str, str]:
    return entry.relative_path.casefold(), entry.relative_path


def render_folder_tree(snapshot: InventorySnapshot) -> str:
    if not snapshot.entries:
        return ""

    return "\n".join(snapshot.rendered_paths) + "\n"


def render_structure_index(snapshot: InventorySnapshot) -> str:
    payload = {
        "schemaVersion": STRUCTURE_INDEX_SCHEMA_VERSION,
        "entries": [
            entry.to_structure_index_entry()
            for entry in snapshot.entries
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def _folder_tree_sort_key(path: str) -> tuple[str, str]:
    logical_path = path[:-1] if path.endswith("/") else path
    return logical_path.casefold(), logical_path


def _validate_structure_path(
    path: str,
    *,
    context: str,
    allow_directory_suffix: bool,
) -> str:
    if not path:
        raise ValueError(f"{context} contains an empty path")

    if "\\" in path:
        raise ValueError(f"{context} contains a backslash path: {path}")

    if path.endswith("/") and not allow_directory_suffix:
        raise ValueError(f"{context} path must not end with /: {path}")

    logical_path = path[:-1] if path.endswith("/") else path

    if not logical_path or logical_path.startswith("/"):
        raise ValueError(
            f"{context} contains an absolute or empty path: {path}"
        )

    if len(logical_path) >= 3 and logical_path[1:3] == ":/":
        raise ValueError(f"{context} contains an absolute path: {path}")

    parts = logical_path.split("/")

    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(
            f"{context} contains an invalid relative path: {path}"
        )

    return logical_path


def _validate_folder_tree_path(path: str) -> None:
    try:
        _validate_structure_path(
            path,
            context="folder_tree.txt",
            allow_directory_suffix=True,
        )
    except ValueError as exc:
        raise FolderTreeFormatError(str(exc)) from exc


def parse_folder_tree(text: str) -> tuple[str, ...]:
    if text.startswith("\ufeff"):
        raise FolderTreeFormatError("folder_tree.txt must not contain a BOM")

    if "\r" in text:
        raise FolderTreeFormatError("folder_tree.txt must use LF line endings")

    if "\x00" in text:
        raise FolderTreeFormatError(
            "folder_tree.txt contains NUL bytes or a legacy encoding"
        )

    if not text:
        return ()

    if not text.endswith("\n"):
        raise FolderTreeFormatError(
            "non-empty folder_tree.txt must end with LF"
        )

    paths = tuple(text[:-1].split("\n"))

    for path in paths:
        _validate_folder_tree_path(path)

    if len(paths) != len(set(paths)):
        raise FolderTreeFormatError(
            "folder_tree.txt contains duplicate paths"
        )

    expected = tuple(sorted(paths, key=_folder_tree_sort_key))

    if paths != expected:
        raise FolderTreeFormatError(
            "folder_tree.txt paths are not in deterministic order"
        )

    return paths


def read_folder_tree(path: str | Path) -> tuple[str, ...]:
    folder_tree_path = Path(path)

    try:
        raw = folder_tree_path.read_bytes()
    except OSError as exc:
        raise InventoryError(
            f"cannot read folder_tree.txt: {folder_tree_path}: {exc}"
        ) from exc

    if raw.startswith(b"\xef\xbb\xbf"):
        raise FolderTreeFormatError("folder_tree.txt must not contain a BOM")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FolderTreeFormatError(
            "folder_tree.txt is not UTF-8"
        ) from exc

    return parse_folder_tree(text)


def _validate_index_object_keys(
    value: dict[str, Any],
    expected: tuple[str, ...],
    context: str,
) -> None:
    actual = tuple(value)

    if actual != expected:
        raise StructureIndexFormatError(
            f"{context} keys must be in this order: {', '.join(expected)}"
        )


def _parse_structure_index_entry(
    value: Any,
    index: int,
) -> InventoryEntry:
    context = f"structure index entries[{index}]"

    if not isinstance(value, dict):
        raise StructureIndexFormatError(f"{context} must be an object")

    _validate_index_object_keys(
        value,
        (
            "relativePath",
            "name",
            "parentPath",
            "entryType",
            "linkType",
            "extension",
        ),
        context,
    )

    if not all(isinstance(item, str) for item in value.values()):
        raise StructureIndexFormatError(
            f"{context} values must all be strings"
        )

    relative_path = value["relativePath"]

    try:
        _validate_structure_path(
            relative_path,
            context=context,
            allow_directory_suffix=False,
        )
    except ValueError as exc:
        raise StructureIndexFormatError(str(exc)) from exc

    try:
        entry_type = InventoryEntryType(value["entryType"])
    except ValueError as exc:
        raise StructureIndexFormatError(
            f"{context}.entryType is invalid: {value['entryType']}"
        ) from exc

    try:
        link_type = InventoryLinkType(value["linkType"])
    except ValueError as exc:
        raise StructureIndexFormatError(
            f"{context}.linkType is invalid: {value['linkType']}"
        ) from exc

    if (
        link_type is InventoryLinkType.JUNCTION
        and entry_type is not InventoryEntryType.DIRECTORY
    ):
        raise StructureIndexFormatError(
            f"{context} junction must have directory entryType"
        )

    entry = InventoryEntry(
        relative_path=relative_path,
        entry_type=entry_type,
        link_type=link_type,
    )
    expected = entry.to_structure_index_entry()

    for key, expected_value in expected.items():
        if value[key] != expected_value:
            raise StructureIndexFormatError(
                f"{context}.{key} does not match relativePath: "
                f"expected {expected_value!r}, got {value[key]!r}"
            )

    return entry


def parse_structure_index(text: str) -> tuple[InventoryEntry, ...]:
    if text.startswith("\ufeff"):
        raise StructureIndexFormatError(
            "structure index must not contain a BOM"
        )

    if "\r" in text:
        raise StructureIndexFormatError(
            "structure index must use LF line endings"
        )

    if "\x00" in text:
        raise StructureIndexFormatError(
            "structure index contains NUL bytes or a legacy encoding"
        )

    if not text.endswith("\n"):
        raise StructureIndexFormatError("structure index must end with LF")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StructureIndexFormatError(
            "invalid structure index JSON: "
            f"{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise StructureIndexFormatError(
            "structure index root must be an object"
        )

    _validate_index_object_keys(
        payload,
        ("schemaVersion", "entries"),
        "structure index",
    )
    schema_version = payload["schemaVersion"]

    if type(schema_version) is not int:
        raise StructureIndexFormatError(
            "structure index schemaVersion must be an integer"
        )

    if schema_version != STRUCTURE_INDEX_SCHEMA_VERSION:
        raise StructureIndexFormatError(
            "unsupported structure index schemaVersion: "
            f"{schema_version}; expected {STRUCTURE_INDEX_SCHEMA_VERSION}"
        )

    raw_entries = payload["entries"]

    if not isinstance(raw_entries, list):
        raise StructureIndexFormatError(
            "structure index entries must be an array"
        )

    entries = tuple(
        _parse_structure_index_entry(value, index)
        for index, value in enumerate(raw_entries)
    )
    paths = tuple(entry.relative_path for entry in entries)

    if len(paths) != len(set(paths)):
        raise StructureIndexFormatError(
            "structure index contains duplicate relativePath values"
        )

    expected = tuple(sorted(entries, key=_inventory_entry_sort_key))

    if entries != expected:
        raise StructureIndexFormatError(
            "structure index entries are not in deterministic order"
        )

    return entries


def read_structure_index(
    path: str | Path,
) -> tuple[InventoryEntry, ...]:
    structure_index_path = Path(path)

    try:
        raw = structure_index_path.read_bytes()
    except OSError as exc:
        raise InventoryError(
            f"cannot read structure index: {structure_index_path}: {exc}"
        ) from exc

    if raw.startswith(b"\xef\xbb\xbf"):
        raise StructureIndexFormatError(
            "structure index must not contain a BOM"
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StructureIndexFormatError(
            "structure index is not UTF-8"
        ) from exc

    return parse_structure_index(text)


def _build_move_candidates(
    removed_paths: tuple[str, ...],
    added_paths: tuple[str, ...],
) -> tuple[MoveCandidate, ...]:
    removed_groups: dict[tuple[bool, str], list[str]] = {}
    added_groups: dict[tuple[bool, str], list[str]] = {}

    for path in removed_paths:
        logical_path = path[:-1] if path.endswith("/") else path
        key = (path.endswith("/"), PurePosixPath(logical_path).name.casefold())
        removed_groups.setdefault(key, []).append(path)

    for path in added_paths:
        logical_path = path[:-1] if path.endswith("/") else path
        key = (path.endswith("/"), PurePosixPath(logical_path).name.casefold())
        added_groups.setdefault(key, []).append(path)

    candidates: list[MoveCandidate] = []

    for key in sorted(set(removed_groups) & set(added_groups)):
        previous = removed_groups[key]
        current = added_groups[key]

        if len(previous) != 1 or len(current) != 1:
            continue

        candidates.append(
            MoveCandidate(
                previous_path=previous[0],
                current_path=current[0],
            )
        )

    candidates.sort(
        key=lambda item: (
            _folder_tree_sort_key(item.previous_path),
            _folder_tree_sort_key(item.current_path),
        )
    )
    return tuple(candidates)


def build_structure_diff(
    previous_paths: tuple[str, ...],
    current_paths: tuple[str, ...],
) -> StructureDiff:
    previous_set = set(previous_paths)
    current_set = set(current_paths)
    added_paths = tuple(
        sorted(current_set - previous_set, key=_folder_tree_sort_key)
    )
    removed_paths = tuple(
        sorted(previous_set - current_set, key=_folder_tree_sort_key)
    )

    return StructureDiff(
        added_paths=added_paths,
        removed_paths=removed_paths,
        move_candidates=_build_move_candidates(
            removed_paths,
            added_paths,
        ),
    )


def compare_folder_tree(
    snapshot: InventorySnapshot,
    folder_tree_path: str | Path | None = None,
) -> FolderTreeComparison:
    target = (
        Path(folder_tree_path)
        if folder_tree_path is not None
        else snapshot.repo_root / FOLDER_TREE_FILENAME
    )
    desired = render_folder_tree(snapshot).encode("utf-8")

    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return FolderTreeComparison(
            folder_tree_path=target,
            is_current=False,
            previous_exists=False,
            diff=build_structure_diff((), snapshot.rendered_paths),
        )
    except OSError as exc:
        raise InventoryError(
            f"cannot read folder_tree.txt: {target}: {exc}"
        ) from exc

    if raw == desired:
        return FolderTreeComparison(
            folder_tree_path=target,
            is_current=True,
            previous_exists=True,
            diff=StructureDiff(),
        )

    try:
        previous_paths = read_folder_tree(target)
    except FolderTreeFormatError as exc:
        return FolderTreeComparison(
            folder_tree_path=target,
            is_current=False,
            previous_exists=True,
            diff=None,
            format_error=str(exc),
        )

    output_root_filter = LiteralDirectoryBoundaryFilter(
        snapshot.output_roots
    )
    visible_previous_paths = tuple(
        path
        for path in previous_paths
        if not output_root_filter.is_within(path)
    )

    return FolderTreeComparison(
        folder_tree_path=target,
        is_current=False,
        previous_exists=True,
        diff=build_structure_diff(
            visible_previous_paths,
            snapshot.rendered_paths,
        ),
    )


def _resolve_structure_index_path(
    snapshot: InventorySnapshot,
    structure_index_path: str | Path | None,
) -> Path:
    requested = (
        structure_index_path
        if structure_index_path is not None
        else STRUCTURE_INDEX_RELATIVE_PATH
    )
    resolved = RepoPathResolver(snapshot.repo_root).resolve(
        requested,
        must_exist=False,
        allow_file=True,
        allow_directory=False,
    )
    return resolved.logical_path


def prepare_structure_index_parent(repo_root: str | Path) -> Path:
    resolver = RepoPathResolver(repo_root)
    resolved = resolver.resolve(
        STRUCTURE_INDEX_RELATIVE_PATH,
        must_exist=False,
        allow_file=True,
        allow_directory=False,
    )

    try:
        resolved.logical_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InventoryError(
            "cannot create structure index directory: "
            f"{resolved.logical_path.parent}: {exc}"
        ) from exc

    verified = resolver.resolve(
        STRUCTURE_INDEX_RELATIVE_PATH,
        must_exist=False,
        allow_file=True,
        allow_directory=False,
    )
    return verified.logical_path


def compare_structure_index(
    snapshot: InventorySnapshot,
    structure_index_path: str | Path | None = None,
) -> StructureIndexComparison:
    target = _resolve_structure_index_path(snapshot, structure_index_path)
    desired = render_structure_index(snapshot).encode("utf-8")

    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return StructureIndexComparison(
            structure_index_path=target,
            is_current=False,
            previous_exists=False,
        )
    except OSError as exc:
        raise InventoryError(
            f"cannot read structure index: {target}: {exc}"
        ) from exc

    if raw == desired:
        return StructureIndexComparison(
            structure_index_path=target,
            is_current=True,
            previous_exists=True,
        )

    try:
        read_structure_index(target)
    except StructureIndexFormatError as exc:
        return StructureIndexComparison(
            structure_index_path=target,
            is_current=False,
            previous_exists=True,
            format_error=str(exc),
        )

    return StructureIndexComparison(
        structure_index_path=target,
        is_current=False,
        previous_exists=True,
    )


def _write_atomic_text(
    path: Path,
    text: str,
    description: str,
) -> None:
    temporary_path = path.with_name(path.name + ".v4_tmp")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.unlink(missing_ok=True)

        with temporary_path.open("xb") as stream:
            stream.write(text.encode("utf-8"))

        os.replace(temporary_path, path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass

        raise InventoryError(
            f"cannot write {description}: {path}: {exc}"
        ) from exc


def _write_folder_tree(path: Path, text: str) -> None:
    _write_atomic_text(path, text, "folder_tree.txt")


def _write_structure_index(path: Path, text: str) -> None:
    _write_atomic_text(path, text, "structure index")


def sync_folder_tree(
    snapshot: InventorySnapshot,
    folder_tree_path: str | Path | None = None,
) -> FolderTreeSyncResult:
    comparison = compare_folder_tree(snapshot, folder_tree_path)

    if comparison.is_current:
        return FolderTreeSyncResult(
            comparison=comparison,
            updated=False,
        )

    text = render_folder_tree(snapshot)
    _write_folder_tree(comparison.folder_tree_path, text)

    try:
        written = comparison.folder_tree_path.read_bytes()
    except OSError as exc:
        raise InventoryError(
            "cannot verify written folder_tree.txt: "
            f"{comparison.folder_tree_path}: {exc}"
        ) from exc

    if written != text.encode("utf-8"):
        raise InventoryError(
            "folder_tree.txt verification failed after write: "
            f"{comparison.folder_tree_path}"
        )

    return FolderTreeSyncResult(
        comparison=comparison,
        updated=True,
    )


def sync_structure_index(
    snapshot: InventorySnapshot,
    structure_index_path: str | Path | None = None,
) -> StructureIndexSyncResult:
    comparison = compare_structure_index(snapshot, structure_index_path)

    if comparison.is_current:
        return StructureIndexSyncResult(
            comparison=comparison,
            updated=False,
        )

    text = render_structure_index(snapshot)
    _write_structure_index(comparison.structure_index_path, text)

    try:
        written = comparison.structure_index_path.read_bytes()
    except OSError as exc:
        raise InventoryError(
            "cannot verify written structure index: "
            f"{comparison.structure_index_path}: {exc}"
        ) from exc

    if written != text.encode("utf-8"):
        raise InventoryError(
            "structure index verification failed after write: "
            f"{comparison.structure_index_path}"
        )

    return StructureIndexSyncResult(
        comparison=comparison,
        updated=True,
    )
