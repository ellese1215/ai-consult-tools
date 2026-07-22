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
) -> OutputContext:
    return OutputContext(
        target=target,
        repo_root=repo,
        output_root=repo / out_name,
        docset="20260711153000",
        generated_at=datetime(2026, 7, 11, 15, 30, tzinfo=JST),
        case_name="renderer_test",
        max_chars_per_part=max_chars,
        max_bytes_per_part=max_bytes,
    )


class ChatGPTOutputAdapterTest(unittest.TestCase):
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

        self.assertEqual(first_bytes, second_bytes)

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

            with self.assertRaises(OutputAdapterError):
                write_chatgpt_bundle(bundle, context)

            after = first.output_paths[0].read_bytes()

        self.assertEqual(after, previous)

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
