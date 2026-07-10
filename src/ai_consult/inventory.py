from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ai_consult.config import ConsultConfig
from ai_consult.filters import PathFilter
from ai_consult.path_resolver import RepoPathResolver


GENERATED_STRUCTURE_PATHS = frozenset({"folder_tree.txt"})


class InventoryError(RuntimeError):
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


@dataclass(frozen=True)
class InventorySnapshot:
    repo_root: Path
    entries: tuple[InventoryEntry, ...]

    @property
    def rendered_paths(self) -> tuple[str, ...]:
        return tuple(entry.rendered_path for entry in self.entries)


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
    ) -> None:
        self._repo_root = RepoPathResolver(repo_root).repo_root
        self._path_filter = path_filter

    @classmethod
    def from_config(
        cls,
        repo_root: str | Path,
        config: ConsultConfig,
    ) -> InventoryScanner:
        return cls(
            repo_root,
            PathFilter(config.inventory.exclude_paths),
        )

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def scan(self) -> InventorySnapshot:
        entries: list[InventoryEntry] = []
        self._scan_directory(self._repo_root, entries)
        entries.sort(
            key=lambda item: (
                item.relative_path.casefold(),
                item.relative_path,
            )
        )

        return InventorySnapshot(
            repo_root=self._repo_root,
            entries=tuple(entries),
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


def render_folder_tree(snapshot: InventorySnapshot) -> str:
    if not snapshot.entries:
        return ""

    return "\n".join(snapshot.rendered_paths) + "\n"
