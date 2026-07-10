from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BUILTIN_BINARY_EXTENSIONS = frozenset(
    {
        ".7z",
        ".avi",
        ".bin",
        ".bmp",
        ".class",
        ".dll",
        ".doc",
        ".docx",
        ".eot",
        ".exe",
        ".flac",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".otf",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".so",
        ".tar",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".zip",
    }
)

_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:/")


class FilterError(ValueError):
    pass


class BinaryFileError(FilterError):
    pass


class TextDecodeError(FilterError):
    pass


class TextFileTooLargeError(FilterError):
    pass


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str


def normalize_relative_path(value: str | Path) -> str:
    raw = str(value).strip().replace("\\", "/")

    while raw.startswith("./"):
        raw = raw[2:]

    if raw.startswith("/") or _DRIVE_PATTERN.match(raw):
        raise FilterError(f"path must be RepoRoot-relative: {value}")

    normalized = posixpath.normpath(raw)

    if normalized in {"", "."}:
        return ""

    if normalized == ".." or normalized.startswith("../"):
        raise FilterError(f"path escapes RepoRoot: {value}")

    return normalized


def normalize_exclude_pattern(value: str) -> str:
    raw = value.strip().replace("\\", "/")

    if not raw:
        raise FilterError("exclude pattern must not be empty")

    while raw.startswith("./"):
        raw = raw[2:]

    if raw.startswith("/") or _DRIVE_PATTERN.match(raw):
        raise FilterError(
            f"exclude pattern must be RepoRoot-relative: {value}"
        )

    directory_pattern = raw.endswith("/")
    normalized = posixpath.normpath(raw.rstrip("/"))

    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise FilterError(f"invalid exclude pattern: {value}")

    if directory_pattern:
        return normalized + "/"

    return normalized


def _contains_glob(value: str) -> bool:
    return any(character in value for character in "*?[")


def _matches_pattern(relative_path: str, pattern: str) -> bool:
    relative_folded = relative_path.casefold()
    directory_pattern = pattern.endswith("/")
    pattern_core = pattern[:-1] if directory_pattern else pattern
    pattern_folded = pattern_core.casefold()

    if directory_pattern:
        if _contains_glob(pattern_folded):
            return (
                fnmatch.fnmatchcase(relative_folded, pattern_folded)
                or fnmatch.fnmatchcase(
                    relative_folded,
                    pattern_folded + "/*",
                )
            )

        return (
            relative_folded == pattern_folded
            or relative_folded.startswith(pattern_folded + "/")
        )

    if _contains_glob(pattern_folded):
        return fnmatch.fnmatchcase(relative_folded, pattern_folded)

    if "/" not in pattern_folded:
        return pattern_folded in relative_folded.split("/")

    return relative_folded == pattern_folded


class PathFilter:
    def __init__(self, exclude_patterns: Iterable[str] = ()) -> None:
        self._exclude_patterns = tuple(
            normalize_exclude_pattern(pattern)
            for pattern in exclude_patterns
        )

    @property
    def exclude_patterns(self) -> tuple[str, ...]:
        return self._exclude_patterns

    def is_excluded(
        self,
        relative_path: str | Path,
        *,
        is_dir: bool = False,
    ) -> bool:
        del is_dir

        normalized = normalize_relative_path(relative_path)

        if not normalized:
            return False

        return any(
            _matches_pattern(normalized, pattern)
            for pattern in self._exclude_patterns
        )


def normalize_binary_extensions(
    values: Iterable[str],
) -> frozenset[str]:
    normalized: set[str] = set()

    for value in values:
        item = value.strip().casefold()

        if not item:
            raise FilterError("binary extension must not be empty")

        if not item.startswith("."):
            item = "." + item

        if "/" in item or "\\" in item:
            raise FilterError(f"invalid binary extension: {value}")

        normalized.add(item)

    return frozenset(normalized)


def _binary_extension_match(
    path: str | Path | None,
    extra_extensions: Iterable[str],
) -> bool:
    if path is None:
        return False

    extensions = (
        BUILTIN_BINARY_EXTENSIONS
        | normalize_binary_extensions(extra_extensions)
    )

    return Path(path).suffix.casefold() in extensions


def _utf16_without_bom_encoding(data: bytes) -> str | None:
    if len(data) < 4:
        return None

    even = data[0::2]
    odd = data[1::2]

    even_null_ratio = even.count(0) / max(1, len(even))
    odd_null_ratio = odd.count(0) / max(1, len(odd))

    if odd_null_ratio >= 0.30 and even_null_ratio <= 0.10:
        return "utf-16-le"

    if even_null_ratio >= 0.30 and odd_null_ratio <= 0.10:
        return "utf-16-be"

    return None


def _has_excessive_control_bytes(data: bytes) -> bool:
    if not data:
        return False

    allowed = {9, 10, 13}
    controls = sum(
        1
        for value in data
        if value < 32 and value not in allowed
    )

    return controls / len(data) > 0.05


def decode_text_bytes(
    data: bytes,
    *,
    path: str | Path | None = None,
    binary_extensions: Iterable[str] = (),
) -> DecodedText:
    if _binary_extension_match(path, binary_extensions):
        raise BinaryFileError(
            f"binary extension is not eligible for text inclusion: {path}"
        )

    if data.startswith(b"\xef\xbb\xbf"):
        try:
            text = data[3:].decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise TextDecodeError("invalid UTF-8 text") from exc

        return DecodedText(
            text=text,
            encoding="utf-8-sig",
        )

    if data.startswith(b"\xff\xfe"):
        try:
            text = data[2:].decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise TextDecodeError("invalid UTF-16LE text") from exc

        return DecodedText(text=text, encoding="utf-16-le")

    if data.startswith(b"\xfe\xff"):
        try:
            text = data[2:].decode("utf-16-be", errors="strict")
        except UnicodeDecodeError as exc:
            raise TextDecodeError("invalid UTF-16BE text") from exc

        return DecodedText(text=text, encoding="utf-16-be")

    utf16_encoding = _utf16_without_bom_encoding(data)

    if utf16_encoding is not None:
        try:
            text = data.decode(utf16_encoding, errors="strict")
        except UnicodeDecodeError as exc:
            raise TextDecodeError(
                f"invalid {utf16_encoding.upper()} text"
            ) from exc

        return DecodedText(text=text, encoding=utf16_encoding)

    if b"\x00" in data or _has_excessive_control_bytes(data):
        raise BinaryFileError("binary content detected")

    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TextDecodeError(
            "unsupported or invalid text encoding"
        ) from exc

    return DecodedText(text=text, encoding="utf-8")


def read_text_file(
    path: str | Path,
    *,
    max_bytes: int,
    binary_extensions: Iterable[str] = (),
) -> DecodedText:
    file_path = Path(path)

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise FilterError(f"cannot stat file: {file_path}: {exc}") from exc

    if size > max_bytes:
        raise TextFileTooLargeError(
            f"text file exceeds limit: {file_path}: "
            f"{size} bytes > {max_bytes} bytes"
        )

    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise FilterError(f"cannot read file: {file_path}: {exc}") from exc

    return decode_text_bytes(
        data,
        path=file_path,
        binary_extensions=binary_extensions,
    )
