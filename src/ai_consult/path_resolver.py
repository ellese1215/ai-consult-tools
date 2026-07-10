from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class PathResolutionError(ValueError):
    pass


class RepoRootError(PathResolutionError):
    pass


class PathOutsideRepoError(PathResolutionError):
    pass


class RepoPathNotFoundError(PathResolutionError):
    pass


class UnsupportedPathTypeError(PathResolutionError):
    pass


@dataclass(frozen=True)
class ResolvedRepoPath:
    relative_path: str
    logical_path: Path
    real_path: Path
    is_file: bool
    is_dir: bool


def _normalized_absolute(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_within(child: Path, parent: Path) -> bool:
    child_value = _normalized_absolute(child)
    parent_value = _normalized_absolute(parent)

    try:
        return os.path.commonpath(
            [child_value, parent_value]
        ) == parent_value
    except ValueError:
        return False


class RepoPathResolver:
    def __init__(self, repo_root: str | Path) -> None:
        root = Path(repo_root).expanduser()

        try:
            resolved_root = root.resolve(strict=True)
        except OSError as exc:
            raise RepoRootError(
                f"cannot resolve RepoRoot: {root}: {exc}"
            ) from exc

        if not resolved_root.is_dir():
            raise RepoRootError(
                f"RepoRoot is not a directory: {resolved_root}"
            )

        self._repo_root = resolved_root

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def resolve(
        self,
        value: str | Path,
        *,
        must_exist: bool = True,
        allow_file: bool = True,
        allow_directory: bool = True,
    ) -> ResolvedRepoPath:
        requested = Path(value).expanduser()

        if requested.is_absolute():
            candidate = requested
        else:
            candidate = self._repo_root / requested

        logical_path = Path(os.path.abspath(os.fspath(candidate)))

        if not _is_within(logical_path, self._repo_root):
            raise PathOutsideRepoError(
                f"path is outside RepoRoot: {value}"
            )

        if must_exist and not logical_path.exists():
            raise RepoPathNotFoundError(
                f"path does not exist: {value}"
            )

        try:
            real_path = logical_path.resolve(strict=must_exist)
        except OSError as exc:
            raise PathResolutionError(
                f"cannot resolve path: {value}: {exc}"
            ) from exc

        if not _is_within(real_path, self._repo_root):
            raise PathOutsideRepoError(
                "resolved path is outside RepoRoot: "
                f"{value} -> {real_path}"
            )

        is_file = real_path.is_file()
        is_dir = real_path.is_dir()

        if must_exist and not is_file and not is_dir:
            raise UnsupportedPathTypeError(
                f"unsupported path type: {value}"
            )

        if is_file and not allow_file:
            raise UnsupportedPathTypeError(
                f"file path is not allowed here: {value}"
            )

        if is_dir and not allow_directory:
            raise UnsupportedPathTypeError(
                f"directory path is not allowed here: {value}"
            )

        try:
            relative_path = logical_path.relative_to(
                self._repo_root
            ).as_posix()
        except ValueError as exc:
            raise PathOutsideRepoError(
                f"path is outside RepoRoot: {value}"
            ) from exc

        return ResolvedRepoPath(
            relative_path=relative_path,
            logical_path=logical_path,
            real_path=real_path,
            is_file=is_file,
            is_dir=is_dir,
        )
