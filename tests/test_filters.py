from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.filters import (
    BinaryFileError,
    PathFilter,
    TextDecodeError,
    TextFileTooLargeError,
    decode_text_bytes,
    normalize_relative_path,
    read_text_file,
)


class PathFilterTest(unittest.TestCase):
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

    def test_large_text_file_is_not_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.txt"
            path.write_text("abcdefghij", encoding="utf-8")

            with self.assertRaises(TextFileTooLargeError):
                read_text_file(path, max_bytes=5)


if __name__ == "__main__":
    unittest.main()
