from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.collection import (
    CollectionStatus,
    ExplicitFileCollector,
    OutputRootPathError,
)
from ai_consult.config import ConsultConfig, FilterConfig, parse_config


def make_config(
    *,
    exclude_paths: tuple[str, ...] = (),
    binary_extensions: tuple[str, ...] = (),
    max_text_bytes: int = 2_000_000,
) -> ConsultConfig:
    return ConsultConfig(
        schema_version=1,
        filters=FilterConfig(
            exclude_paths=exclude_paths,
            binary_extensions=binary_extensions,
            max_text_bytes=max_text_bytes,
        ),
    )


def make_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="ER" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>users</t></is></c></row></sheetData>
</worksheet>""",
        )

    return buffer.getvalue()


class ExplicitFileCollectorTest(unittest.TestCase):
    def test_configured_output_roots_are_excluded_from_start_collection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            paths = (
                "artifacts/chatgpt/old/bundle.zip.sha256",
                "artifacts/claude/old/bundle.md",
            )

            for relative_path in paths:
                target = repo / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("generated output", encoding="utf-8")

            config = parse_config(
                {
                    "schemaVersion": 1,
                    "outputs": {
                        "chatgpt": {"outRoot": "artifacts/chatgpt"},
                        "claude": {"outRoot": "artifacts/claude"},
                    },
                }
            )
            collector = ExplicitFileCollector.from_config(repo, config)
            for path in paths:
                with self.subTest(path=path):
                    with self.assertRaisesRegex(
                        OutputRootPathError,
                        "configured output root cannot be collected",
                    ):
                        collector.collect_one(path)

    def test_includes_utf16_text_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "docs" / "guide.txt"
            target.parent.mkdir()
            target.write_bytes(
                b"\xff\xfe"
                + "日本語ガイド".encode("utf-16-le")
            )

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            result = collector.collect_one("docs/guide.txt")

            self.assertEqual(
                result.status,
                CollectionStatus.INCLUDED,
            )
            self.assertTrue(result.included)
            self.assertIsNotNone(result.file)

            assert result.file is not None

            self.assertEqual(
                result.file.relative_path,
                "docs/guide.txt",
            )
            self.assertEqual(
                result.file.encoding,
                "utf-16-le",
            )
            self.assertEqual(
                result.file.text,
                "日本語ガイド",
            )
            source = target.read_bytes()
            self.assertEqual(
                result.file.size_bytes,
                len(source),
            )
            self.assertEqual(
                result.file.source_sha256,
                hashlib.sha256(source).hexdigest(),
            )
            self.assertEqual(
                result.file.real_relative_path,
                "docs/guide.txt",
            )

    def test_excluded_explicit_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "private" / "secret.txt"
            target.parent.mkdir()
            target.write_text("secret", encoding="utf-8")

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(exclude_paths=("private/",)),
            )
            result = collector.collect_one(
                "private/secret.txt"
            )

            self.assertEqual(
                result.status,
                CollectionStatus.EXCLUDED,
            )
            self.assertFalse(result.included)
            self.assertIn("private/", result.reason or "")

    def test_root_shared_is_included_without_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "shared" / "rules.md"
            target.parent.mkdir()
            target.write_text("rules", encoding="utf-8")

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            result = collector.collect_one("shared/rules.md")

            self.assertEqual(
                result.status,
                CollectionStatus.INCLUDED,
            )

    def test_missing_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            collector = ExplicitFileCollector.from_config(
                temp_dir,
                make_config(),
            )
            result = collector.collect_one("missing.txt")

            self.assertEqual(
                result.status,
                CollectionStatus.MISSING,
            )

    def test_outside_absolute_path_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                outside = Path(outside_dir) / "outside.txt"
                outside.write_text(
                    "outside",
                    encoding="utf-8",
                )

                collector = ExplicitFileCollector.from_config(
                    repo_dir,
                    make_config(),
                )
                result = collector.collect_one(outside)

                self.assertEqual(
                    result.status,
                    CollectionStatus.OUTSIDE_REPO,
                )

    def test_directory_request_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            result = collector.collect_one("docs")

            self.assertEqual(
                result.status,
                CollectionStatus.NOT_FILE,
            )

    def test_binary_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "image.png"
            target.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            )

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            result = collector.collect_one("image.png")

            self.assertEqual(
                result.status,
                CollectionStatus.BINARY,
            )

    def test_configured_binary_extension_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "drawing.clip"
            target.write_text(
                "text-shaped binary",
                encoding="utf-8",
            )

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(
                    binary_extensions=(".clip",)
                ),
            )
            result = collector.collect_one("drawing.clip")

            self.assertEqual(
                result.status,
                CollectionStatus.BINARY,
            )

    def test_xlsx_file_is_included_as_extracted_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "schema.xlsx"
            target.write_bytes(make_xlsx_bytes())

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            result = collector.collect_one("schema.xlsx")

            self.assertEqual(
                result.status,
                CollectionStatus.INCLUDED,
            )
            self.assertIsNotNone(result.file)

            assert result.file is not None

            self.assertEqual(result.file.encoding, "xlsx-xml")
            self.assertIn("## Sheet: ER", result.file.text)
            self.assertIn("A1: users", result.file.text)

    def test_large_file_is_reported_without_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "large.txt"
            target.write_text(
                "abcdefghij",
                encoding="utf-8",
            )

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(max_text_bytes=5),
            )
            result = collector.collect_one("large.txt")

            self.assertEqual(
                result.status,
                CollectionStatus.TOO_LARGE,
            )
            self.assertIsNone(result.file)

    def test_decode_error_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            target = repo / "invalid.txt"
            target.write_bytes(b"\xff\xff")

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            result = collector.collect_one("invalid.txt")

            self.assertEqual(
                result.status,
                CollectionStatus.DECODE_ERROR,
            )

    def test_collect_many_preserves_request_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "first.txt").write_text(
                "first",
                encoding="utf-8",
            )
            (repo / "second.txt").write_text(
                "second",
                encoding="utf-8",
            )

            collector = ExplicitFileCollector.from_config(
                repo,
                make_config(),
            )
            results = collector.collect_many(
                [
                    "second.txt",
                    "missing.txt",
                    "first.txt",
                ]
            )

            self.assertEqual(
                tuple(result.requested_path for result in results),
                (
                    "second.txt",
                    "missing.txt",
                    "first.txt",
                ),
            )
            self.assertEqual(
                tuple(result.status for result in results),
                (
                    CollectionStatus.INCLUDED,
                    CollectionStatus.MISSING,
                    CollectionStatus.INCLUDED,
                ),
            )

    @unittest.skipUnless(
        os.name == "nt",
        "junctions are supported only on Windows",
    )
    def test_junction_cannot_bypass_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            private = repo / "private"
            private.mkdir()
            (private / "secret.txt").write_text(
                "secret",
                encoding="utf-8",
            )

            junction = repo / "visible"

            command = subprocess.run(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(junction),
                    str(private),
                ],
                capture_output=True,
                check=False,
            )

            if command.returncode != 0:
                self.skipTest(
                    "junction creation failed with "
                    f"exit code {command.returncode}"
                )

            try:
                collector = (
                    ExplicitFileCollector.from_config(
                        repo,
                        make_config(
                            exclude_paths=("private/",)
                        ),
                    )
                )
                result = collector.collect_one(
                    "visible/secret.txt"
                )

                self.assertEqual(
                    result.status,
                    CollectionStatus.EXCLUDED,
                )
                self.assertIn(
                    "target=private/secret.txt",
                    result.reason or "",
                )
            finally:
                if junction.exists():
                    os.rmdir(junction)


if __name__ == "__main__":
    unittest.main()
