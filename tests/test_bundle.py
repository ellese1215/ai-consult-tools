from __future__ import annotations

import dataclasses
import hashlib
import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.bundle import (
    BundleCommand,
    BundleItem,
    BundleModel,
    BundleModelError,
    BundleOrigin,
    ContentKind,
    GitChange,
    PathResolution,
    SkippedItem,
    render_manifest_csv,
)
from ai_consult.collection import CollectionStatus


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def make_text_item(
    relative_path: str = "docs/guide.md",
    *,
    origin: BundleOrigin = BundleOrigin.EXPLICIT,
    content: str = "guide\n",
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
    )


def make_diff_item(
    origin: BundleOrigin,
    relative_path: str = "src/app.py",
    *,
    git_change: GitChange = GitChange.MODIFIED,
    previous_path: str | None = None,
) -> BundleItem:
    content = "diff --git a/src/app.py b/src/app.py\n"
    source = content.encode("utf-8")
    return BundleItem(
        relative_path=relative_path,
        content_kind=ContentKind.DIFF,
        origin=origin,
        content=content,
        encoding="utf-8",
        source_bytes=len(source),
        source_sha256=sha256(source),
        git_change=git_change,
        previous_path=previous_path,
    )


class BundleItemTest(unittest.TestCase):
    def test_accepts_utf16_text_metadata(self) -> None:
        content = "日本語"
        source = b"\xff\xfe" + content.encode("utf-16-le")
        item = BundleItem(
            relative_path="docs/guide.txt",
            content_kind=ContentKind.TEXT,
            origin=BundleOrigin.INCLUDE_SET,
            content=content,
            encoding="utf-16-le",
            source_bytes=len(source),
            source_sha256=sha256(source),
        )

        self.assertEqual(item.encoding, "utf-16-le")
        self.assertEqual(item.source_bytes, len(source))

    def test_rejects_non_canonical_relative_paths(self) -> None:
        invalid_paths = (
            "",
            " docs/guide.md",
            "docs/guide.md ",
            "/docs/guide.md",
            "C:/docs/guide.md",
            "docs\\guide.md",
            ".",
            "..",
            "docs/../guide.md",
            "docs/./guide.md",
            "docs//guide.md",
            "docs/",
        )

        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(BundleModelError):
                    make_text_item(path)

    def test_staged_and_unstaged_items_require_diff_content(self) -> None:
        with self.assertRaises(BundleModelError):
            make_text_item(
                origin=BundleOrigin.STAGED,
            )

        with self.assertRaises(BundleModelError):
            BundleItem(
                relative_path="src/app.py",
                content_kind=ContentKind.DIFF,
                origin=BundleOrigin.STAGED,
                content="diff\n",
                encoding="utf-8",
                source_bytes=5,
                source_sha256=sha256(b"diff\n"),
            )

    def test_untracked_item_requires_text_added_state(self) -> None:
        content = "new\n"
        source = content.encode("utf-8")
        item = BundleItem(
            relative_path="src/new.py",
            content_kind=ContentKind.TEXT,
            origin=BundleOrigin.UNTRACKED,
            content=content,
            encoding="utf-8",
            source_bytes=len(source),
            source_sha256=sha256(source),
            git_change=GitChange.ADDED,
        )

        self.assertEqual(item.git_change, GitChange.ADDED)

        with self.assertRaises(BundleModelError):
            dataclasses.replace(
                item,
                git_change=GitChange.MODIFIED,
            )

    def test_rename_requires_canonical_previous_path(self) -> None:
        item = make_diff_item(
            BundleOrigin.STAGED,
            relative_path="src/current.py",
            git_change=GitChange.RENAMED,
            previous_path="src/previous.py",
        )

        self.assertEqual(item.previous_path, "src/previous.py")

        with self.assertRaises(BundleModelError):
            make_diff_item(
                BundleOrigin.STAGED,
                git_change=GitChange.RENAMED,
            )

        with self.assertRaises(BundleModelError):
            make_diff_item(
                BundleOrigin.STAGED,
                git_change=GitChange.MODIFIED,
                previous_path="src/previous.py",
            )

        with self.assertRaises(BundleModelError):
            make_diff_item(
                BundleOrigin.STAGED,
                git_change=GitChange.RENAMED,
                previous_path="src\\previous.py",
            )

    def test_rejects_invalid_source_metadata(self) -> None:
        valid = make_text_item()

        invalid_values = (
            {"source_bytes": -1},
            {"source_bytes": True},
            {"source_sha256": "A" * 64},
            {"source_sha256": "0" * 63},
            {"encoding": ""},
            {"encoding": " utf-8"},
        )

        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(BundleModelError):
                    dataclasses.replace(valid, **values)

    def test_item_is_frozen(self) -> None:
        item = make_text_item()

        with self.assertRaises(dataclasses.FrozenInstanceError):
            item.relative_path = "other.md"  # type: ignore[misc]


class BundleResolutionTest(unittest.TestCase):
    def test_included_resolution_requires_resolved_paths(self) -> None:
        resolution = PathResolution(
            requested_path="docs/guide.md",
            status=CollectionStatus.INCLUDED,
            origin=BundleOrigin.EXPLICIT,
            resolved_paths=["docs/guide.md"],
        )

        self.assertEqual(
            resolution.resolved_paths,
            ("docs/guide.md",),
        )

        with self.assertRaises(BundleModelError):
            PathResolution(
                requested_path="docs/guide.md",
                status=CollectionStatus.INCLUDED,
                origin=BundleOrigin.EXPLICIT,
            )

    def test_resolution_rejects_non_canonical_requested_path(self) -> None:
        with self.assertRaises(BundleModelError):
            PathResolution(
                requested_path="C:/outside.txt",
                status=CollectionStatus.OUTSIDE_REPO,
                origin=BundleOrigin.EXPLICIT,
                reason="outside RepoRoot",
            )

        with self.assertRaises(BundleModelError):
            SkippedItem(
                requested_path="docs\\guide.md",
                status=CollectionStatus.RESOLUTION_ERROR,
                origin=BundleOrigin.EXPLICIT,
                reason="invalid path",
            )

    def test_failed_resolution_requires_reason(self) -> None:
        resolution = PathResolution(
            requested_path="missing.md",
            status=CollectionStatus.MISSING,
            origin=BundleOrigin.EXPLICIT,
            reason="file does not exist",
        )

        self.assertEqual(resolution.status, CollectionStatus.MISSING)

        with self.assertRaises(BundleModelError):
            dataclasses.replace(resolution, reason=None)

    def test_resolution_rejects_duplicate_or_invalid_paths(self) -> None:
        with self.assertRaises(BundleModelError):
            PathResolution(
                requested_path="docs/guide.md",
                status=CollectionStatus.INCLUDED,
                origin=BundleOrigin.EXPLICIT,
                resolved_paths=(
                    "docs/guide.md",
                    "DOCS/GUIDE.MD",
                ),
            )

        with self.assertRaises(BundleModelError):
            PathResolution(
                requested_path="docs/guide.md",
                status=CollectionStatus.INCLUDED,
                origin=BundleOrigin.EXPLICIT,
                resolved_paths=("docs\\guide.md",),
            )

    def test_skipped_item_rejects_included_status(self) -> None:
        skipped = SkippedItem(
            requested_path="image.png",
            status=CollectionStatus.BINARY,
            origin=BundleOrigin.EXPLICIT,
            reason="binary file",
            relative_path="image.png",
        )

        self.assertEqual(skipped.relative_path, "image.png")

        with self.assertRaises(BundleModelError):
            dataclasses.replace(
                skipped,
                status=CollectionStatus.INCLUDED,
            )


class BundleModelTest(unittest.TestCase):
    def test_allows_staged_and_unstaged_for_same_path(self) -> None:
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
            items=(
                make_diff_item(BundleOrigin.STAGED),
                make_diff_item(BundleOrigin.UNSTAGED),
            ),
        )

        self.assertEqual(bundle.included_count, 2)
        self.assertEqual(
            tuple(row.origin for row in bundle.manifest_rows),
            (BundleOrigin.STAGED, BundleOrigin.UNSTAGED),
        )

    def test_rejects_duplicate_origin_path_and_previous_path(self) -> None:
        first = make_diff_item(BundleOrigin.STAGED)
        second = make_diff_item(
            BundleOrigin.STAGED,
            relative_path="SRC/APP.PY",
        )

        with self.assertRaises(BundleModelError):
            BundleModel(
                command=BundleCommand.REVIEW,
                profile_name="ai_consult_tools",
                items=(first, second),
            )

    def test_skipped_items_do_not_increase_included_count(self) -> None:
        skipped = SkippedItem(
            requested_path="image.png",
            status=CollectionStatus.BINARY,
            origin=BundleOrigin.EXPLICIT,
            reason="binary file",
            relative_path="image.png",
        )
        bundle = BundleModel(
            command=BundleCommand.START,
            profile_name="ai_consult_tools",
            items=(make_text_item(),),
            skipped_items=[skipped],
        )

        self.assertEqual(bundle.included_count, 1)
        self.assertEqual(bundle.skipped_count, 1)
        self.assertIsInstance(bundle.skipped_items, tuple)

    def test_empty_bundle_can_hold_resolution_and_skip_results(self) -> None:
        resolution = PathResolution(
            requested_path="missing.md",
            status=CollectionStatus.MISSING,
            origin=BundleOrigin.EXPLICIT,
            reason="file does not exist",
        )
        skipped = SkippedItem(
            requested_path="missing.md",
            status=CollectionStatus.MISSING,
            origin=BundleOrigin.EXPLICIT,
            reason="file does not exist",
        )
        bundle = BundleModel(
            command=BundleCommand.START,
            profile_name="ai_consult_tools",
            path_resolutions=[resolution],
            skipped_items=[skipped],
        )

        self.assertEqual(bundle.included_count, 0)
        self.assertEqual(bundle.manifest_rows, ())
        self.assertEqual(len(bundle.path_resolutions), 1)

    def test_manifest_is_deterministic_and_uses_lf(self) -> None:
        utf16_content = "日本語"
        utf16_source = b"\xff\xfe" + utf16_content.encode(
            "utf-16-le"
        )
        utf16_item = BundleItem(
            relative_path="docs/zeta.txt",
            content_kind=ContentKind.TEXT,
            origin=BundleOrigin.INCLUDE_SET,
            content=utf16_content,
            encoding="utf-16-le",
            source_bytes=len(utf16_source),
            source_sha256=sha256(utf16_source),
        )
        alpha_item = make_text_item("docs/alpha.md")

        first = BundleModel(
            command=BundleCommand.START,
            profile_name="ai_consult_tools",
            items=(utf16_item, alpha_item),
        )
        second = BundleModel(
            command=BundleCommand.START,
            profile_name="ai_consult_tools",
            items=(alpha_item, utf16_item),
        )

        first_csv = render_manifest_csv(first)
        second_csv = render_manifest_csv(second)

        self.assertEqual(first_csv, second_csv)
        self.assertNotIn("\r", first_csv)
        self.assertTrue(first_csv.endswith("\n"))
        self.assertEqual(
            first_csv.splitlines()[0],
            "relative_path,content_kind,origin,git_change,"
            "previous_path,source_bytes,source_sha256,encoding",
        )
        self.assertEqual(
            first_csv.splitlines()[1].split(",")[0],
            "docs/alpha.md",
        )
        self.assertIn("utf-16-le", first_csv)
        self.assertNotIn("repo_root", first_csv)
        self.assertNotIn("part_file", first_csv)

    def test_manifest_contains_separate_staged_and_unstaged_rows(self) -> None:
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
            items=(
                make_diff_item(BundleOrigin.UNSTAGED),
                make_diff_item(BundleOrigin.STAGED),
            ),
        )
        lines = render_manifest_csv(bundle).splitlines()

        self.assertEqual(len(lines), 3)
        self.assertIn(",staged,modified,", lines[1])
        self.assertIn(",unstaged,modified,", lines[2])

    def test_review_target_paths_are_sorted_and_frozen(self) -> None:
        bundle = BundleModel(
            command=BundleCommand.REVIEW,
            profile_name="ai_consult_tools",
            target_paths=[
                "ai-consult-tools/tests",
                "ai-consult-tools/src",
            ],
        )

        self.assertEqual(
            bundle.target_paths,
            (
                "ai-consult-tools/src",
                "ai-consult-tools/tests",
            ),
        )
        self.assertIsInstance(bundle.target_paths, tuple)

    def test_rejects_invalid_or_duplicate_target_paths(self) -> None:
        invalid_values = (
            "",
            "ai-consult-tools\\src",
            "/ai-consult-tools/src",
            "C:/xampp/htdocs",
            "ai-consult-tools/src/",
            "ai-consult-tools/../src",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(BundleModelError):
                    BundleModel(
                        command=BundleCommand.REVIEW,
                        profile_name="ai_consult_tools",
                        target_paths=(value,),
                    )

        with self.assertRaisesRegex(
            BundleModelError,
            "duplicate path",
        ):
            BundleModel(
                command=BundleCommand.REVIEW,
                profile_name="ai_consult_tools",
                target_paths=(
                    "ai-consult-tools/src",
                    "AI-CONSULT-TOOLS/SRC",
                ),
            )

        with self.assertRaises(BundleModelError):
            BundleModel(
                command=BundleCommand.REVIEW,
                profile_name="ai_consult_tools",
                target_paths="ai-consult-tools/src",  # type: ignore[arg-type]
            )

    def test_non_review_bundle_rejects_target_paths(self) -> None:
        for command in (BundleCommand.START, BundleCommand.INSPECT):
            with self.subTest(command=command):
                with self.assertRaisesRegex(
                    BundleModelError,
                    "only valid for review",
                ):
                    BundleModel(
                        command=command,
                        profile_name="ai_consult_tools",
                        target_paths=("ai-consult-tools/src",),
                    )

    def test_rejects_invalid_profile_name_or_member_types(self) -> None:
        with self.assertRaises(BundleModelError):
            BundleModel(
                command=BundleCommand.START,
                profile_name="",
            )

        with self.assertRaises(BundleModelError):
            BundleModel(
                command=BundleCommand.START,
                profile_name="ai_consult_tools",
                items=("not an item",),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
