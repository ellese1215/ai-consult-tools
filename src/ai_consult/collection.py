from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ai_consult.config import ConsultConfig
from ai_consult.filters import (
    BinaryFileError,
    FilterError,
    PathFilter,
    TextDecodeError,
    TextFileTooLargeError,
    read_text_file,
)
from ai_consult.path_resolver import (
    PathOutsideRepoError,
    PathResolutionError,
    RepoPathNotFoundError,
    RepoPathResolver,
    UnsupportedPathTypeError,
)


class CollectionStatus(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    MISSING = "missing"
    OUTSIDE_REPO = "outside_repo"
    NOT_FILE = "not_file"
    BINARY = "binary"
    TOO_LARGE = "too_large"
    DECODE_ERROR = "decode_error"
    READ_ERROR = "read_error"
    RESOLUTION_ERROR = "resolution_error"


@dataclass(frozen=True)
class CollectedTextFile:
    requested_path: str
    relative_path: str
    logical_path: Path
    real_path: Path
    size_bytes: int
    encoding: str
    text: str


@dataclass(frozen=True)
class CollectionResult:
    requested_path: str
    status: CollectionStatus
    relative_path: str | None = None
    reason: str | None = None
    file: CollectedTextFile | None = None

    @property
    def included(self) -> bool:
        return self.status is CollectionStatus.INCLUDED


class ExplicitFileCollector:
    def __init__(
        self,
        resolver: RepoPathResolver,
        path_filter: PathFilter,
        *,
        binary_extensions: Iterable[str] = (),
        max_text_bytes: int,
    ) -> None:
        if max_text_bytes <= 0:
            raise ValueError("max_text_bytes must be positive")

        self._resolver = resolver
        self._path_filter = path_filter
        self._binary_extensions = tuple(binary_extensions)
        self._max_text_bytes = max_text_bytes

    @classmethod
    def from_config(
        cls,
        repo_root: str | Path,
        config: ConsultConfig,
    ) -> ExplicitFileCollector:
        return cls(
            resolver=RepoPathResolver(repo_root),
            path_filter=PathFilter(
                config.filters.exclude_paths
            ),
            binary_extensions=(
                config.filters.binary_extensions
            ),
            max_text_bytes=config.filters.max_text_bytes,
        )

    def collect_many(
        self,
        requested_paths: Iterable[str | Path],
    ) -> tuple[CollectionResult, ...]:
        return tuple(
            self.collect_one(requested_path)
            for requested_path in requested_paths
        )

    def collect_one(
        self,
        requested_path: str | Path,
    ) -> CollectionResult:
        requested_text = str(requested_path)

        try:
            resolved = self._resolver.resolve(
                requested_path,
                must_exist=True,
                allow_file=True,
                allow_directory=False,
            )
        except PathOutsideRepoError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.OUTSIDE_REPO,
                reason=str(exc),
            )
        except RepoPathNotFoundError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.MISSING,
                reason=str(exc),
            )
        except UnsupportedPathTypeError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.NOT_FILE,
                reason=str(exc),
            )
        except PathResolutionError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.RESOLUTION_ERROR,
                reason=str(exc),
            )

        logical_pattern = self._path_filter.matching_pattern(
            resolved.relative_path
        )

        if logical_pattern is not None:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.EXCLUDED,
                relative_path=resolved.relative_path,
                reason=(
                    "excluded by configured pattern: "
                    f"{logical_pattern}"
                ),
            )

        real_relative_path = resolved.real_path.relative_to(
            self._resolver.repo_root
        ).as_posix()

        real_pattern = self._path_filter.matching_pattern(
            real_relative_path
        )

        if real_pattern is not None:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.EXCLUDED,
                relative_path=resolved.relative_path,
                reason=(
                    "resolved target is excluded by configured "
                    f"pattern: {real_pattern}; "
                    f"target={real_relative_path}"
                ),
            )

        try:
            decoded = read_text_file(
                resolved.real_path,
                max_bytes=self._max_text_bytes,
                binary_extensions=self._binary_extensions,
            )
        except BinaryFileError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.BINARY,
                relative_path=resolved.relative_path,
                reason=str(exc),
            )
        except TextFileTooLargeError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.TOO_LARGE,
                relative_path=resolved.relative_path,
                reason=str(exc),
            )
        except TextDecodeError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.DECODE_ERROR,
                relative_path=resolved.relative_path,
                reason=str(exc),
            )
        except FilterError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.READ_ERROR,
                relative_path=resolved.relative_path,
                reason=str(exc),
            )

        try:
            size_bytes = resolved.real_path.stat().st_size
        except OSError as exc:
            return CollectionResult(
                requested_path=requested_text,
                status=CollectionStatus.READ_ERROR,
                relative_path=resolved.relative_path,
                reason=(
                    "cannot stat collected file: "
                    f"{resolved.real_path}: {exc}"
                ),
            )

        collected = CollectedTextFile(
            requested_path=requested_text,
            relative_path=resolved.relative_path,
            logical_path=resolved.logical_path,
            real_path=resolved.real_path,
            size_bytes=size_bytes,
            encoding=decoded.encoding,
            text=decoded.text,
        )

        return CollectionResult(
            requested_path=requested_text,
            status=CollectionStatus.INCLUDED,
            relative_path=resolved.relative_path,
            file=collected,
        )
