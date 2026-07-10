from __future__ import annotations

import fnmatch
import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from xml.etree import ElementTree


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
        ".zip",
    }
)

_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:/")
_XLSX_EXTENSION = ".xlsx"
_XLSX_MAX_XML_BYTES = 64_000_000
_XLSX_MAX_OUTPUT_CHARACTERS = 2_000_000
_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DRAWING_MAIN_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


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

    def matching_pattern(
        self,
        relative_path: str | Path,
        *,
        is_dir: bool = False,
    ) -> str | None:
        del is_dir

        normalized = normalize_relative_path(relative_path)

        if not normalized:
            return None

        for pattern in self._exclude_patterns:
            if _matches_pattern(normalized, pattern):
                return pattern

        return None

    def is_excluded(
        self,
        relative_path: str | Path,
        *,
        is_dir: bool = False,
    ) -> bool:
        return (
            self.matching_pattern(
                relative_path,
                is_dir=is_dir,
            )
            is not None
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


def _xlsx_xml_text(element: ElementTree.Element) -> str:
    values = [
        node.text or ""
        for node in element.iter()
        if node.tag == f"{{{_XLSX_MAIN_NS}}}t"
        or node.tag == f"{{{_DRAWING_MAIN_NS}}}t"
    ]
    return "".join(values)


def _xlsx_clean_value(value: str) -> str:
    return (
        value.replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def _xlsx_resolve_target(source_path: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")

    source_parent = PurePosixPath(source_path).parent
    return posixpath.normpath(
        posixpath.join(source_parent.as_posix(), target)
    )


def _xlsx_relationships(
    archive: zipfile.ZipFile,
    relationships_path: str,
    source_path: str,
) -> dict[str, str]:
    try:
        data = archive.read(relationships_path)
    except KeyError:
        return {}

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise TextDecodeError(
            f"invalid XLSX relationships XML: {relationships_path}"
        ) from exc

    result: dict[str, str] = {}

    for relationship in root.findall(
        f"{{{_PACKAGE_REL_NS}}}Relationship"
    ):
        relationship_id = relationship.get("Id")
        target = relationship.get("Target")

        if relationship_id and target:
            result[relationship_id] = _xlsx_resolve_target(
                source_path,
                target,
            )

    return result


def _xlsx_shared_strings(
    archive: zipfile.ZipFile,
) -> tuple[str, ...]:
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return ()

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise TextDecodeError("invalid XLSX shared strings XML") from exc

    return tuple(
        _xlsx_xml_text(item)
        for item in root.findall(f"{{{_XLSX_MAIN_NS}}}si")
    )


def _xlsx_cell_value(
    cell: ElementTree.Element,
    shared_strings: tuple[str, ...],
) -> str:
    cell_type = cell.get("t", "")
    formula_node = cell.find(f"{{{_XLSX_MAIN_NS}}}f")
    value_node = cell.find(f"{{{_XLSX_MAIN_NS}}}v")
    inline_node = cell.find(f"{{{_XLSX_MAIN_NS}}}is")
    raw_value = value_node.text if value_node is not None else ""

    if cell_type == "s" and raw_value:
        try:
            value = shared_strings[int(raw_value)]
        except (ValueError, IndexError) as exc:
            raise TextDecodeError(
                f"invalid XLSX shared string index: {raw_value}"
            ) from exc
    elif cell_type == "inlineStr" and inline_node is not None:
        value = _xlsx_xml_text(inline_node)
    elif cell_type == "b":
        value = "TRUE" if raw_value == "1" else "FALSE"
    else:
        value = raw_value

    formula = formula_node.text if formula_node is not None else ""

    if formula:
        formula_text = "=" + formula

        if value:
            return f"{formula_text} => {value}"

        return formula_text

    return value


def _xlsx_drawing_text(
    archive: zipfile.ZipFile,
    worksheet_path: str,
    worksheet_root: ElementTree.Element,
) -> tuple[str, ...]:
    worksheet_name = PurePosixPath(worksheet_path).name
    relationships_path = (
        PurePosixPath(worksheet_path).parent
        / "_rels"
        / f"{worksheet_name}.rels"
    ).as_posix()
    relationships = _xlsx_relationships(
        archive,
        relationships_path,
        worksheet_path,
    )
    result: list[str] = []

    for drawing in worksheet_root.findall(
        f"{{{_XLSX_MAIN_NS}}}drawing"
    ):
        relationship_id = drawing.get(f"{{{_XLSX_REL_NS}}}id")

        if not relationship_id:
            continue

        drawing_path = relationships.get(relationship_id)

        if not drawing_path:
            continue

        try:
            drawing_data = archive.read(drawing_path)
        except KeyError:
            continue

        try:
            drawing_root = ElementTree.fromstring(drawing_data)
        except ElementTree.ParseError as exc:
            raise TextDecodeError(
                f"invalid XLSX drawing XML: {drawing_path}"
            ) from exc

        for text_node in drawing_root.iter(
            f"{{{_DRAWING_MAIN_NS}}}t"
        ):
            text = (text_node.text or "").strip()

            if text:
                result.append(text)

    return tuple(result)


def _decode_xlsx_bytes(
    data: bytes,
    path: str | Path | None,
) -> DecodedText:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise TextDecodeError("invalid XLSX ZIP container") from exc

    with archive:
        xml_size = sum(
            item.file_size
            for item in archive.infolist()
            if item.filename.endswith(".xml")
            or item.filename.endswith(".rels")
        )

        if xml_size > _XLSX_MAX_XML_BYTES:
            raise TextFileTooLargeError(
                "XLSX XML content exceeds safe extraction limit: "
                f"{xml_size} bytes > {_XLSX_MAX_XML_BYTES} bytes"
            )

        try:
            workbook_data = archive.read("xl/workbook.xml")
        except KeyError as exc:
            raise TextDecodeError(
                "invalid XLSX workbook: xl/workbook.xml is missing"
            ) from exc

        try:
            workbook_root = ElementTree.fromstring(workbook_data)
        except ElementTree.ParseError as exc:
            raise TextDecodeError("invalid XLSX workbook XML") from exc

        workbook_relationships = _xlsx_relationships(
            archive,
            "xl/_rels/workbook.xml.rels",
            "xl/workbook.xml",
        )
        shared_strings = _xlsx_shared_strings(archive)
        workbook_name = Path(path).name if path is not None else "workbook.xlsx"
        lines = [f"# XLSX: {workbook_name}"]

        sheets_parent = workbook_root.find(
            f"{{{_XLSX_MAIN_NS}}}sheets"
        )

        if sheets_parent is None:
            raise TextDecodeError("invalid XLSX workbook: sheets are missing")

        for sheet in sheets_parent.findall(f"{{{_XLSX_MAIN_NS}}}sheet"):
            sheet_name = sheet.get("name", "(unnamed)")
            relationship_id = sheet.get(f"{{{_XLSX_REL_NS}}}id")

            if not relationship_id:
                continue

            worksheet_path = workbook_relationships.get(relationship_id)

            if not worksheet_path:
                continue

            try:
                worksheet_data = archive.read(worksheet_path)
            except KeyError as exc:
                raise TextDecodeError(
                    f"XLSX worksheet is missing: {worksheet_path}"
                ) from exc

            try:
                worksheet_root = ElementTree.fromstring(worksheet_data)
            except ElementTree.ParseError as exc:
                raise TextDecodeError(
                    f"invalid XLSX worksheet XML: {worksheet_path}"
                ) from exc

            lines.extend(("", f"## Sheet: {sheet_name}"))
            cell_count = 0

            for cell in worksheet_root.iter(f"{{{_XLSX_MAIN_NS}}}c"):
                cell_reference = cell.get("r", "(unknown)")
                value = _xlsx_cell_value(cell, shared_strings)

                if not value:
                    continue

                lines.append(
                    f"{cell_reference}: {_xlsx_clean_value(value)}"
                )
                cell_count += 1

            drawing_text = _xlsx_drawing_text(
                archive,
                worksheet_path,
                worksheet_root,
            )

            if drawing_text:
                lines.extend(("", "### Drawing text"))
                lines.extend(
                    f"- {_xlsx_clean_value(value)}"
                    for value in drawing_text
                )

            if cell_count == 0 and not drawing_text:
                lines.append("(no readable cell or drawing text)")

        text = "\n".join(lines) + "\n"

        if len(text) > _XLSX_MAX_OUTPUT_CHARACTERS:
            raise TextFileTooLargeError(
                "XLSX extracted text exceeds limit: "
                f"{len(text)} characters > "
                f"{_XLSX_MAX_OUTPUT_CHARACTERS} characters"
            )

        return DecodedText(text=text, encoding="xlsx-xml")


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

    if path is not None and Path(path).suffix.casefold() == _XLSX_EXTENSION:
        return _decode_xlsx_bytes(data, path)

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
