from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.filters import (
    BinaryFileError,
    LiteralDirectoryBoundaryFilter,
    PathFilter,
    TextDecodeError,
    TextFileTooLargeError,
    decode_text_bytes,
    normalize_relative_path,
    read_text_file,
)


def make_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="ER" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>users</t></si>
</sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c></row>
    <row r="2"><c r="B2"><f>1+2</f><v>3</v></c></row>
    <row r="3"><c r="C3" t="inlineStr"><is><t>primary key</t></is></c></row>
  </sheetData>
  <drawing r:id="rIdDrawing"/>
</worksheet>""",
        )
        archive.writestr(
            "xl/worksheets/_rels/sheet1.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdDrawing" Target="../drawings/drawing1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/drawings/drawing1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <xdr:sp><xdr:txBody><a:p><a:r><a:t>orders</a:t></a:r></a:p></xdr:txBody></xdr:sp>
</xdr:wsDr>""",
        )

    return buffer.getvalue()


class PathFilterTest(unittest.TestCase):
    def test_literal_directory_boundaries_do_not_use_glob_syntax(
        self,
    ) -> None:
        path_filter = LiteralDirectoryBoundaryFilter(
            (
                "project/generated/[chat]",
                "project/generated/[chat]",
                "project/generated/[chat]/nested",
                "project/generated/Claude 出力",
            )
        )

        excluded = (
            "project/generated/[chat]",
            "project/generated/[chat]/bundle.zip",
            r"PROJECT\GENERATED\[CHAT]\nested\old.md",
            "project/generated/Claude 出力/結果.md",
        )
        included = (
            "project/generated/c",
            "project/generated/c/source.txt",
            "project/generated/[chat]-backup/file.txt",
            "project/generated/chat/file.txt",
        )

        for path in excluded:
            with self.subTest(path=path):
                self.assertTrue(path_filter.is_within(path))

        for path in included:
            with self.subTest(path=path):
                self.assertFalse(path_filter.is_within(path))

        self.assertEqual(
            path_filter.directory_roots,
            (
                "project/generated/[chat]",
                "project/generated/[chat]/nested",
                "project/generated/Claude 出力",
            ),
        )

    def test_directory_exclusion_is_path_aware(self) -> None:
        path_filter = PathFilter(["apps/example/generated/"])

        self.assertTrue(
            path_filter.is_excluded(
                "apps/example/generated/file.txt"
            )
        )
        self.assertFalse(
            path_filter.is_excluded(
                "apps/other/generated/file.txt"
            )
        )

    def test_segment_exclusion_matches_any_depth(self) -> None:
        path_filter = PathFilter(["node_modules"])

        self.assertTrue(
            path_filter.is_excluded(
                "apps/site/node_modules/pkg/index.js"
            )
        )
        self.assertFalse(
            path_filter.is_excluded(
                "apps/site/node_modules_backup/index.js"
            )
        )

    def test_shared_is_not_hardcoded(self) -> None:
        path_filter = PathFilter([])

        self.assertFalse(
            path_filter.is_excluded("shared/rules.md")
        )

    def test_specific_shared_path_does_not_hide_root_shared(self) -> None:
        path_filter = PathFilter(["apps/example/shared/"])

        self.assertTrue(
            path_filter.is_excluded(
                "apps/example/shared/local.md"
            )
        )
        self.assertFalse(
            path_filter.is_excluded("shared/rules.md")
        )

    def test_normalizes_windows_separator(self) -> None:
        self.assertEqual(
            normalize_relative_path(
                r"apps\example\src\main.py"
            ),
            "apps/example/src/main.py",
        )


class TextFilterTest(unittest.TestCase):
    def test_decodes_utf8(self) -> None:
        result = decode_text_bytes(
            "日本語テキスト".encode("utf-8")
        )

        self.assertEqual(result.text, "日本語テキスト")
        self.assertEqual(result.encoding, "utf-8")

    def test_decodes_utf8_bom(self) -> None:
        result = decode_text_bytes(
            b"\xef\xbb\xbf" + "text".encode("utf-8")
        )

        self.assertEqual(result.text, "text")
        self.assertEqual(result.encoding, "utf-8-sig")

    def test_invalid_utf8_bom_uses_text_decode_error(self) -> None:
        with self.assertRaises(TextDecodeError):
            decode_text_bytes(b"\xef\xbb\xbf\xff")

    def test_decodes_utf16_le_bom(self) -> None:
        result = decode_text_bytes(
            b"\xff\xfe" + "folder tree".encode("utf-16-le")
        )

        self.assertEqual(result.text, "folder tree")
        self.assertEqual(result.encoding, "utf-16-le")

    def test_decodes_utf16_le_without_bom(self) -> None:
        result = decode_text_bytes(
            "folder tree".encode("utf-16-le")
        )

        self.assertEqual(result.text, "folder tree")
        self.assertEqual(result.encoding, "utf-16-le")

    def test_decodes_utf16_be_bom(self) -> None:
        result = decode_text_bytes(
            b"\xfe\xff" + "folder tree".encode("utf-16-be")
        )

        self.assertEqual(result.text, "folder tree")
        self.assertEqual(result.encoding, "utf-16-be")

    def test_decodes_utf16_be_without_bom(self) -> None:
        result = decode_text_bytes(
            "folder tree".encode("utf-16-be")
        )

        self.assertEqual(result.text, "folder tree")
        self.assertEqual(result.encoding, "utf-16-be")

    def test_detects_binary_content(self) -> None:
        with self.assertRaises(BinaryFileError):
            decode_text_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            )

    def test_binary_extension_is_rejected(self) -> None:
        with self.assertRaises(BinaryFileError):
            decode_text_bytes(
                b"plain text",
                path="image.png",
            )

    def test_configured_binary_extension_is_rejected(self) -> None:
        with self.assertRaises(BinaryFileError):
            decode_text_bytes(
                b"plain text",
                path="drawing.clip",
                binary_extensions=[".clip"],
            )

    def test_xlsx_is_extracted_as_deterministic_text(self) -> None:
        result = decode_text_bytes(
            make_xlsx_bytes(),
            path="schema.xlsx",
        )

        self.assertEqual(result.encoding, "xlsx-xml")
        self.assertIn("# XLSX: schema.xlsx", result.text)
        self.assertIn("## Sheet: ER", result.text)
        self.assertIn("A1: users", result.text)
        self.assertIn("B2: =1+2 => 3", result.text)
        self.assertIn("C3: primary key", result.text)
        self.assertIn("### Drawing text", result.text)
        self.assertIn("- orders", result.text)

    def test_invalid_xlsx_is_decode_error(self) -> None:
        with self.assertRaises(TextDecodeError):
            decode_text_bytes(
                b"not an xlsx",
                path="schema.xlsx",
            )

    def test_large_text_file_is_not_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.txt"
            path.write_text("abcdefghij", encoding="utf-8")

            with self.assertRaises(TextFileTooLargeError):
                read_text_file(path, max_bytes=5)


if __name__ == "__main__":
    unittest.main()
