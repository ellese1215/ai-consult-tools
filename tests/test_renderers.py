from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import ai_consult.renderers.chatgpt as chatgpt_renderer
from ai_consult.bundle import (
    BundleCommand,
    BundleItem,
    BundleModel,
    BundleOrigin,
    ContentKind,
    GitChange,
    SkippedItem,
)
from ai_consult.collection import CollectionStatus
from ai_consult.renderers import (
    OutputAdapterError,
    OutputContext,
    OutputTarget,
    write_chatgpt_bundle,
    write_claude_bundle,
)


JST = timezone(timedelta(hours=9))
START_DOCUMENTS = (
    "REPO_OVERVIEW.md",
    "PROJECT_TREE.md",
    "STRUCTURE_STATUS.md",
    "PATH_INDEX.md",
    "SKIPPED.md",
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def make_text_item(
    relative_path: str,
    content: str,
    *,
    origin: BundleOrigin = BundleOrigin.EXPLICIT,
    encoding: str = "utf-8",
) -> BundleItem:
    source = content.encode("utf-8")
    return BundleItem(
        relative_path=relative_path,
        content_kind=ContentKind.TEXT,
        origin=origin,
        content=content,
        encoding=encoding,
        source_bytes=len(source),
        source_sha256=sha256(source),
        git_change=(
            GitChange.ADDED
            if origin is BundleOrigin.UNTRACKED
            else None
        ),
    )


def make_generated_item(relative_path: str) -> BundleItem:
    return make_text_item(
        relative_path,
        f"# {relative_path.removesuffix('.md')}\n\nbody\n",
        origin=BundleOrigin.GENERATED,
    )


def make_diff_item(
    origin: BundleOrigin,
    *,
    relative_path: str = "src/app.py",
    change: GitChange = GitChange.MODIFIED,
    previous_path: str | None = None,
) -> BundleItem:
    content = (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        "--- a/file\n"
        "+++ b/file\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    source = content.encode("utf-8")
    return BundleItem(
        relative_path=relative_path,
        content_kind=ContentKind.DIFF,
        origin=origin,
        content=content,
        encoding="utf-8",
        source_bytes=len(source),
        source_sha256=sha256(source),
        git_change=change,
        previous_path=previous_path,
    )


def make_start_bundle(*items: BundleItem) -> BundleModel:
    generated = tuple(
        make_generated_item(path)
        for path in START_DOCUMENTS
    )
    return BundleModel(
        command=BundleCommand.START,
        profile_name="ai_consult_tools",
        items=generated + items,
    )


def make_context(
    repo: Path,
    target: OutputTarget,
    *,
    out_name: str,
    max_chars: int = 300_000,
    max_bytes: int | None = None,
    case_name: str = "renderer_test",
) -> OutputContext:
    return OutputContext(
        target=target,
        repo_root=repo,
        output_root=repo / out_name,
        docset="20260711153000",
        generated_at=datetime(2026, 7, 11, 15, 30, tzinfo=JST),
        case_name=case_name,
        max_chars_per_part=max_chars,
        max_bytes_per_part=max_bytes,
    )


class ChatGPTOutputAdapterTest(unittest.TestCase):
    def assert_valid_sidecar(self, result) -> None:
        self.assertEqual(len(result.output_paths), 2)
        archive_path, sidecar_path = result.output_paths
        archive_sha256 = hashlib.sha256(
            archive_path.read_bytes()
        ).hexdigest().upper()
        expected = f"{archive_sha256} *{archive_path.name}\r\n".encode(
            "utf-8"
        )

        self.assertEqual(sidecar_path.name, archive_path.name + ".sha256")
        self.assertEqual(sidecar_path.read_bytes(), expected)
        self.assertIs(result.bundle_path, archive_path)
        self.assertEqual(result.bundle_sha256, archive_sha256)
        self.assertIs(result.sidecar_path, sidecar_path)
        self.assertIs(result.sidecar_match, True)

    def assert_atomic_failure_preserves_siblings(
        self,
        failure_patch,
        *,
        expected_exception=OutputAdapterError,
    ) -> None:
        bundle = make_start_bundle()

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            output_root = repo / "chatgpt"
            output_root.mkdir()
            sentinel = output_root / "keep.txt"
            sentinel.write_bytes(b"keep")
            previous = output_root / "previous_bundle"
            previous.mkdir()
            previous_archive = previous / "previous_bundle.zip"
            previous_sidecar = previous / "previous_bundle.zip.sha256"
            previous_archive.write_bytes(b"previous archive")
            previous_sidecar.write_bytes(b"previous sidecar")
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
            )
            final_directory = output_root / context.bundle_label(bundle)

            with failure_patch:
                with self.assertRaises(expected_exception):
                    write_chatgpt_bundle(bundle, context)

            self.assertEqual(sentinel.read_bytes(), b"keep")
            self.assertEqual(
                previous_archive.read_bytes(),
                b"previous archive",
            )
            self.assertEqual(
                previous_sidecar.read_bytes(),
                b"previous sidecar",
            )
            self.assertFalse(
                final_directory.exists()
                or final_directory.is_symlink()
            )
            self.assertEqual(
                tuple(sorted(path.name for path in output_root.iterdir())),
                ("keep.txt", "previous_bundle"),
            )

    def test_writes_expected_zip_layout_and_safe_fence(self) -> None:
        source = make_text_item(
            "docs/guide.md",
            "before\n```python\ninside\n```\nafter\n",
        )
        bundle = make_start_bundle(source)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
            )
            result = write_chatgpt_bundle(bundle, context)
            self.assert_valid_sidecar(result)

            with zipfile.ZipFile(result.output_paths[0]) as archive:
                names = archive.namelist()
                part_name = next(
                    name
                    for name in names
                    if name.startswith("parts/")
                )
                part = archive.read(part_name).decode("utf-8")
                manifest = archive.read("MANIFEST.csv").decode("utf-8")

        self.assertEqual(
            names[:7],
            [
                "INDEX.md",
                "REPO_OVERVIEW.md",
                "PROJECT_TREE.md",
                "STRUCTURE_STATUS.md",
                "PATH_INDEX.md",
                "SKIPPED.md",
                "MANIFEST.csv",
            ],
        )
        self.assertIn("Path: docs/guide.md", part)
        self.assertIn("Origin: explicit", part)
        self.assertIn("SourceSHA256:", part)
        self.assertIn("````markdown", part)
        self.assertIn("relative_path,content_kind,origin", manifest)
        self.assertNotIn("\r", manifest)

    def test_start_zip_renders_generated_folder_tree_as_content(self) -> None:
        bundle = make_start_bundle(
            make_text_item(
                "folder_tree.txt",
                "project/\nproject/main.txt\n",
                origin=BundleOrigin.GENERATED,
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            result = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_bytes=1_000_000,
                ),
            )

            with zipfile.ZipFile(result.output_paths[0]) as archive:
                part = archive.read(
                    "parts/snapshot_docs_part_001.md"
                ).decode("utf-8")
                manifest = archive.read("MANIFEST.csv").decode("utf-8")

        self.assertIn("Path: folder_tree.txt", part)
        self.assertIn("Origin: generated", part)
        self.assertIn("project/main.txt", part)
        self.assertIn("folder_tree.txt,text,generated", manifest)

    def test_zip_bytes_are_deterministic_for_same_input_context(self) -> None:
        bundle = make_start_bundle(
            make_text_item("docs/guide.md", "guide\n")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            first = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="one",
                    max_bytes=1_000_000,
                ),
            )
            second = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="two",
                    max_bytes=1_000_000,
                ),
            )
            first_bytes = first.output_paths[0].read_bytes()
            second_bytes = second.output_paths[0].read_bytes()
            first_sidecar_hash = first.output_paths[1].read_text(
                encoding="utf-8"
            ).split(" ", 1)[0]
            second_sidecar_hash = second.output_paths[1].read_text(
                encoding="utf-8"
            ).split(" ", 1)[0]

        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_sidecar_hash, second_sidecar_hash)

    def test_splits_only_between_item_blocks(self) -> None:
        bundle = make_start_bundle(
            make_text_item("docs/a.md", "a" * 400),
            make_text_item("docs/b.md", "b" * 400),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            result = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_chars=700,
                    max_bytes=10_000,
                ),
            )

            with zipfile.ZipFile(result.output_paths[0]) as archive:
                part_names = tuple(
                    name
                    for name in archive.namelist()
                    if name.startswith("parts/")
                )
                contents = tuple(
                    archive.read(name).decode("utf-8")
                    for name in part_names
                )

        self.assertEqual(
            part_names,
            (
                "parts/snapshot_docs_part_001.md",
                "parts/snapshot_docs_part_002.md",
            ),
        )
        self.assertEqual(sum(text.count("BEGIN BUNDLE ITEM") for text in contents), 2)
        self.assertTrue(all(text.count("BEGIN BUNDLE ITEM") == 1 for text in contents))

    def test_byte_limit_splits_multibyte_content(self) -> None:
        bundle = make_start_bundle(
            make_text_item("docs/a.md", "あ" * 120),
            make_text_item("docs/b.md", "い" * 120),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            result = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_chars=10_000,
                    max_bytes=900,
                ),
            )

            with zipfile.ZipFile(result.output_paths[0]) as archive:
                part_names = tuple(
                    name
                    for name in archive.namelist()
                    if name.startswith("parts/")
                )

        self.assertEqual(len(part_names), 2)

    def test_existing_final_output_is_not_overwritten(self) -> None:
        bundle = make_start_bundle()

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
            )
            first = write_chatgpt_bundle(bundle, context)
            previous = first.output_paths[0].read_bytes()
            previous_sidecar = first.output_paths[1].read_bytes()

            with self.assertRaises(OutputAdapterError):
                write_chatgpt_bundle(bundle, context)

            after = first.output_paths[0].read_bytes()
            after_sidecar = first.output_paths[1].read_bytes()

        self.assertEqual(after, previous)
        self.assertEqual(after_sidecar, previous_sidecar)

    def test_review_zip_contains_diff_documents_and_rename_metadata(self) -> None:
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
            items=(
                make_diff_item(
                    BundleOrigin.STAGED,
                    relative_path="src/new.py",
                    change=GitChange.RENAMED,
                    previous_path="src/old.py",
                ),
                make_text_item(
                    "src/untracked.py",
                    "new file\n",
                    origin=BundleOrigin.UNTRACKED,
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            result = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_bytes=1_000_000,
                ),
            )
            self.assert_valid_sidecar(result)

            with zipfile.ZipFile(result.output_paths[0]) as archive:
                names = archive.namelist()
                text = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in names
                )

        self.assertEqual(
            names[:4],
            ["INDEX.md", "DIFF_INDEX.md", "SKIPPED.md", "MANIFEST.csv"],
        )
        self.assertIn("PreviousPath: src/old.py", text)
        self.assertIn("Origin: untracked", text)
        self.assertIn("git_change,previous_path", text)

    def test_zip_failure_leaves_no_final_or_temp_bundle(self) -> None:
        bundle = make_start_bundle()

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
            )

            with patch(
                "ai_consult.renderers.chatgpt._write_deterministic_zip",
                side_effect=OutputAdapterError("failed"),
            ):
                with self.assertRaises(OutputAdapterError):
                    write_chatgpt_bundle(bundle, context)

            output_root = repo / "chatgpt"
            leftovers = tuple(output_root.iterdir())

        self.assertEqual(leftovers, ())

    def test_sidecar_write_failure_leaves_no_final_or_temp_bundle(
        self,
    ) -> None:
        bundle = make_start_bundle()

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
            )

            with patch(
                "ai_consult.renderers.chatgpt._write_sha256_sidecar",
                side_effect=OutputAdapterError("failed"),
            ):
                with self.assertRaises(OutputAdapterError):
                    write_chatgpt_bundle(bundle, context)

            leftovers = tuple((repo / "chatgpt").iterdir())

        self.assertEqual(leftovers, ())

    def test_sidecar_verification_failure_is_not_published(self) -> None:
        bundle = make_start_bundle()

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
            )

            with patch(
                "ai_consult.renderers.chatgpt._verify_sha256_sidecar",
                side_effect=OutputAdapterError("mismatch"),
            ):
                with self.assertRaises(OutputAdapterError):
                    write_chatgpt_bundle(bundle, context)

            leftovers = tuple((repo / "chatgpt").iterdir())

        self.assertEqual(leftovers, ())

    def test_partial_zip_write_failure_preserves_atomic_boundary(
        self,
    ) -> None:
        def write_partial_then_fail(archive_path, entries) -> None:
            del entries
            archive_path.write_bytes(b"partial ZIP")
            raise OutputAdapterError("ZIP write failed")

        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.chatgpt._write_deterministic_zip",
                side_effect=write_partial_then_fail,
            )
        )

    def test_corrupt_zip_verification_preserves_atomic_boundary(
        self,
    ) -> None:
        def write_corrupt_zip(archive_path, entries) -> None:
            del entries
            archive_path.write_bytes(b"not a ZIP")

        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.chatgpt._write_deterministic_zip",
                side_effect=write_corrupt_zip,
            )
        )

    def test_archive_hash_failure_preserves_atomic_boundary(self) -> None:
        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.chatgpt._calculate_archive_sha256",
                side_effect=OutputAdapterError("hash failed"),
            )
        )

    def test_sidecar_rehash_failure_preserves_atomic_boundary(self) -> None:
        calculate_archive_sha256 = (
            chatgpt_renderer._calculate_archive_sha256
        )
        call_count = 0

        def fail_on_second_hash(archive_path):
            nonlocal call_count
            call_count += 1

            if call_count == 2:
                raise OutputAdapterError("sidecar rehash failed")

            return calculate_archive_sha256(archive_path)

        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.chatgpt._calculate_archive_sha256",
                side_effect=fail_on_second_hash,
            )
        )
        self.assertEqual(call_count, 2)

    def test_partial_sidecar_write_failure_preserves_atomic_boundary(
        self,
    ) -> None:
        def write_partial_then_fail(
            sidecar_path,
            archive_path,
            archive_sha256,
        ) -> None:
            del archive_path, archive_sha256
            sidecar_path.write_bytes(b"partial sidecar")
            raise OutputAdapterError("sidecar write failed")

        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.chatgpt._write_sha256_sidecar",
                side_effect=write_partial_then_fail,
            )
        )

    def test_sidecar_mismatch_preserves_atomic_boundary(self) -> None:
        def write_mismatched_sidecar(
            sidecar_path,
            archive_path,
            archive_sha256,
        ) -> None:
            del archive_path, archive_sha256
            sidecar_path.write_bytes(
                b"0" * 64 + b" *wrong.zip\r\n"
            )

        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.chatgpt._write_sha256_sidecar",
                side_effect=write_mismatched_sidecar,
            )
        )

    def test_publish_rename_failure_preserves_atomic_boundary(
        self,
    ) -> None:
        self.assert_atomic_failure_preserves_siblings(
            patch(
                "ai_consult.renderers.common.Path.rename",
                side_effect=OSError("publish failed"),
            ),
            expected_exception=OSError,
        )

    def test_post_publish_pair_check_removes_incomplete_bundle(
        self,
    ) -> None:
        rename = Path.rename

        def publish_without_sidecar(source, target):
            result = rename(source, target)
            sidecars = tuple(target.glob("*.zip.sha256"))
            self.assertEqual(len(sidecars), 1)
            sidecars[0].unlink()
            return result

        self.assert_atomic_failure_preserves_siblings(
            patch.object(
                Path,
                "rename",
                autospec=True,
                side_effect=publish_without_sidecar,
            )
        )

    def test_long_case_name_uses_short_fixed_temp_prefix(self) -> None:
        bundle = make_start_bundle()
        original_mkdtemp = tempfile.mkdtemp

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CHATGPT,
                out_name="chatgpt",
                max_bytes=1_000_000,
                case_name="long_" + ("x" * 120),
            )

            with patch(
                "ai_consult.renderers.common.tempfile.mkdtemp",
                wraps=original_mkdtemp,
            ) as mkdtemp:
                result = write_chatgpt_bundle(bundle, context)

            self.assert_valid_sidecar(result)

        self.assertEqual(mkdtemp.call_args.kwargs["prefix"], ".bundle-tmp-")
        self.assertNotIn(context.case_name or "", mkdtemp.call_args.kwargs["prefix"])


class ClaudeOutputAdapterTest(unittest.TestCase):
    def test_writes_split_markdown_without_placeholders(self) -> None:
        bundle = make_start_bundle(
            make_text_item("docs/a.md", "a" * 500),
            make_text_item("docs/b.md", "b" * 500),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            result = write_claude_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CLAUDE,
                    out_name="claude",
                    max_chars=1_500,
                ),
            )
            names = tuple(path.name for path in result.output_paths)
            contents = tuple(
                path.read_text(encoding="utf-8")
                for path in result.output_paths
            )
            metadata = (
                result.bundle_path,
                result.bundle_sha256,
                result.sidecar_path,
                result.sidecar_match,
            )

        self.assertGreater(len(names), 1)
        self.assertEqual(names[0], "20260711153000_start_renderer_test_part1.md")
        self.assertIn(names[-1], contents[0])
        self.assertIn("# INDEX", contents[0])
        self.assertIn("# REPO_OVERVIEW", contents[0])
        self.assertIn("# CONTENT PART 2", contents[1])
        self.assertNotIn("(see below)", "".join(contents))
        self.assertNotIn("DocSet placeholder", "".join(contents))
        self.assertEqual(
            sum(text.count("--- BEGIN BUNDLE ITEM ---") for text in contents),
            2,
        )
        self.assertTrue(all("\r" not in text for text in contents))
        self.assertEqual(metadata, (None, None, None, None))

    def test_review_preserves_staged_and_unstaged_same_path(self) -> None:
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
            target_paths=("src",),
            items=(
                make_diff_item(BundleOrigin.STAGED),
                make_diff_item(BundleOrigin.UNSTAGED),
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            result = write_claude_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CLAUDE,
                    out_name="claude",
                ),
            )
            content = result.output_paths[0].read_text(encoding="utf-8")

        self.assertIn("# DIFF_INDEX", content)
        self.assertIn("Origin: staged", content)
        self.assertIn("Origin: unstaged", content)
        self.assertEqual(content.count("Path: src/app.py"), 2)
        self.assertNotIn("part_file", content)

    def test_markdown_failure_leaves_no_final_or_temp_bundle(self) -> None:
        bundle = make_start_bundle()

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            context = make_context(
                repo,
                OutputTarget.CLAUDE,
                out_name="claude",
            )

            with patch.object(
                Path,
                "write_text",
                side_effect=OSError("failed"),
            ):
                with self.assertRaises(OutputAdapterError):
                    write_claude_bundle(bundle, context)

            output_root = repo / "claude"
            leftovers = tuple(output_root.iterdir())

        self.assertEqual(leftovers, ())


class OutputAdapterBoundaryTest(unittest.TestCase):
    def test_empty_review_can_be_rendered_by_both_adapters(self) -> None:
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            chatgpt = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_bytes=1_000_000,
                ),
            )
            claude = write_claude_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CLAUDE,
                    out_name="claude",
                ),
            )

            with zipfile.ZipFile(chatgpt.output_paths[0]) as archive:
                names = archive.namelist()
            claude_text = claude.output_paths[0].read_text(encoding="utf-8")

        self.assertEqual(
            names,
            ["INDEX.md", "DIFF_INDEX.md", "SKIPPED.md", "MANIFEST.csv"],
        )
        self.assertIn("- Staged: 0", claude_text)
        self.assertIn("(none)", claude_text)

    def test_skip_only_review_is_rendered(self) -> None:
        skipped = SkippedItem(
            requested_path="docs/image.png",
            status=CollectionStatus.BINARY,
            origin=BundleOrigin.UNTRACKED,
            reason="binary file",
            relative_path="docs/image.png",
        )
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
            skipped_items=(skipped,),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            chatgpt = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_bytes=1_000_000,
                ),
            )
            claude = write_claude_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CLAUDE,
                    out_name="claude",
                ),
            )

            with zipfile.ZipFile(chatgpt.output_paths[0]) as archive:
                skipped_text = archive.read("SKIPPED.md").decode("utf-8")
            claude_text = claude.output_paths[0].read_text(encoding="utf-8")

        self.assertIn("binary file", skipped_text)
        self.assertIn("binary file", claude_text)

    def test_chatgpt_and_claude_use_identical_item_blocks(self) -> None:
        bundle = make_start_bundle(
            make_text_item("docs/guide.md", "guide\n")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            chatgpt = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_bytes=1_000_000,
                ),
            )
            claude = write_claude_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CLAUDE,
                    out_name="claude",
                ),
            )

            with zipfile.ZipFile(chatgpt.output_paths[0]) as archive:
                chatgpt_text = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                    if name.startswith("parts/")
                )
            claude_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in claude.output_paths
            )

        begin = "--- BEGIN BUNDLE ITEM ---"
        end = "--- END BUNDLE ITEM ---"
        chatgpt_block = (
            begin
            + chatgpt_text.split(begin, 1)[1].split(end, 1)[0]
            + end
        )
        claude_block = (
            begin
            + claude_text.split(begin, 1)[1].split(end, 1)[0]
            + end
        )
        self.assertEqual(chatgpt_block, claude_block)

    def test_placeholder_words_inside_source_content_are_preserved(self) -> None:
        source = make_text_item(
            "docs/legacy.md",
            "(see below)\nDocSet placeholder\n",
        )
        bundle = make_start_bundle(source)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            chatgpt = write_chatgpt_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CHATGPT,
                    out_name="chatgpt",
                    max_bytes=1_000_000,
                ),
            )
            claude = write_claude_bundle(
                bundle,
                make_context(
                    repo,
                    OutputTarget.CLAUDE,
                    out_name="claude",
                ),
            )

            with zipfile.ZipFile(chatgpt.output_paths[0]) as archive:
                chatgpt_text = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                )
            claude_text = claude.output_paths[0].read_text(encoding="utf-8")

        self.assertIn("DocSet placeholder", chatgpt_text)
        self.assertIn("DocSet placeholder", claude_text)

    def test_output_root_outside_repo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                with self.assertRaises(OutputAdapterError):
                    OutputContext(
                        target=OutputTarget.CLAUDE,
                        repo_root=Path(repo_dir),
                        output_root=Path(outside_dir),
                        docset="20260711153000",
                        generated_at=datetime(
                            2026,
                            7,
                            11,
                            15,
                            30,
                            tzinfo=JST,
                        ),
                    )
