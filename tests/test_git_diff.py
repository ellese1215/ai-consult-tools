from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.bundle import BundleCommand, BundleOrigin, GitChange
from ai_consult.collection import CollectionStatus
from ai_consult.config import (
    ConsultConfig,
    FilterConfig,
    ProjectProfile,
    parse_config,
)
from ai_consult.git_diff import (
    GitDiffCollector,
    GitDiffError,
    GitReviewSnapshot,
    collect_review_bundle,
)


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


def make_profile(*scope_roots: str) -> ProjectProfile:
    return ProjectProfile(
        name="test_profile",
        scope_roots=tuple(scope_roots),
    )


class GitRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("config", "core.autocrlf", "false")

    def git(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            ("git", *args),
            cwd=self.root,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )

        if check and result.returncode != 0:
            self.fail_command(args, result)

        return result

    @staticmethod
    def fail_command(
        args: tuple[str, ...],
        result: subprocess.CompletedProcess[bytes],
    ) -> None:
        raise AssertionError(
            "Git command failed: "
            f"git {' '.join(args)}\n"
            f"stdout={result.stdout.decode('utf-8', errors='replace')}\n"
            f"stderr={result.stderr.decode('utf-8', errors='replace')}"
        )

    def write_text(self, relative_path: str, text: str) -> None:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def write_bytes(self, relative_path: str, data: bytes) -> None:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit_all(self, message: str = "commit") -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def status_bytes(self) -> bytes:
        return self.git(
            "status",
            "--porcelain=v1",
            "-z",
        ).stdout


class GitDiffCollectorTest(unittest.TestCase):
    def test_configured_output_roots_are_excluded_from_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("project/main.txt", "base\n")
            repo.write_text("artifacts/[chat]/tracked.txt", "base\n")
            repo.write_text("artifacts/claude/tracked.txt", "base\n")
            repo.write_text("artifacts/c/source.txt", "base\n")
            repo.commit_all("base")
            repo.write_text("project/main.txt", "changed\n")
            repo.write_text("artifacts/c/source.txt", "source changed\n")
            repo.write_text("artifacts/[chat]/tracked.txt", "staged\n")
            repo.git("add", "artifacts/[chat]/tracked.txt")
            repo.write_text(
                "artifacts/[chat]/tracked.txt",
                "unstaged\n",
            )
            repo.write_text("artifacts/claude/tracked.txt", "changed\n")
            repo.write_text("artifacts/[chat]/old/bundle.zip", "zip\n")
            repo.write_text(
                "artifacts/[chat]/old/bundle.zip.sha256",
                "hash\n",
            )
            repo.write_text(
                "artifacts/[chat]/temporary.v4_tmp",
                "temporary\n",
            )
            repo.write_text("artifacts/claude/old_bundle.md", "output\n")
            config = parse_config(
                {
                    "schemaVersion": 1,
                    "outputs": {
                        "chatgpt": {"outRoot": "artifacts/[chat]"},
                        "claude": {"outRoot": "artifacts/claude"},
                    },
                }
            )

            bundle = collect_review_bundle(
                repo.root,
                config,
                make_profile("project", "artifacts"),
            )

        self.assertEqual(
            tuple(item.relative_path for item in bundle.items),
            ("artifacts/c/source.txt", "project/main.txt"),
        )
        self.assertEqual(bundle.skipped_items, ())
        combined = "\n".join(
            (
                *(item.relative_path for item in bundle.items),
                *(item.content for item in bundle.items),
                *(
                    item.previous_path or ""
                    for item in bundle.items
                ),
            )
        )

        for forbidden in (
            "artifacts/[chat]",
            "artifacts/claude",
            "bundle.zip",
            "bundle.zip.sha256",
            "old_bundle.md",
            "temporary.v4_tmp",
        ):
            self.assertNotIn(forbidden, combined)

    def test_configured_output_root_cannot_be_an_explicit_review_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            config = parse_config(
                {
                    "schemaVersion": 1,
                    "outputs": {
                        "chatgpt": {
                            "outRoot": "project/generated/[chat]",
                        },
                    },
                }
            )

            for target in (
                "project/generated/[chat]",
                "project/generated/[chat]/old.zip",
            ):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(
                        GitDiffError,
                        "cannot be a review target",
                    ):
                        GitDiffCollector(
                            repo.root,
                            config,
                            make_profile("project"),
                            target_paths=(target,),
                        )

    def test_renames_across_output_root_boundary_hide_output_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("project/to_output.txt", "to output\n")
            repo.write_text(
                "project/generated/[chat]/to_source.txt",
                "to source\n",
            )
            repo.commit_all("base")
            repo.git(
                "mv",
                "project/to_output.txt",
                "project/generated/[chat]/from_source.txt",
            )
            repo.git(
                "mv",
                "project/generated/[chat]/to_source.txt",
                "project/from_output.txt",
            )
            config = parse_config(
                {
                    "schemaVersion": 1,
                    "outputs": {
                        "chatgpt": {
                            "outRoot": "project/generated/[chat]",
                        },
                    },
                }
            )

            snapshot = GitDiffCollector(
                repo.root,
                config,
                make_profile("project"),
            ).collect()

        self.assertEqual(
            tuple(item.relative_path for item in snapshot.staged_items),
            ("project/from_output.txt", "project/to_output.txt"),
        )
        self.assertEqual(snapshot.skipped_items, ())
        combined = "\n".join(
            (
                *(item.relative_path for item in snapshot.items),
                *(item.content for item in snapshot.items),
            )
        )
        self.assertNotIn("project/generated/[chat]", combined)

    def test_collects_staged_unstaged_and_untracked_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/file.txt", "base\n")
            repo.commit_all("base")

            repo.write_text("app/file.txt", "staged\n")
            repo.git("add", "app/file.txt")
            repo.write_text("app/file.txt", "worktree\n")
            repo.write_text("app/new.txt", "new file\n")
            before = repo.status_bytes()

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(repo.status_bytes(), before)
            self.assertEqual(len(snapshot.staged_items), 1)
            self.assertEqual(len(snapshot.unstaged_items), 1)
            self.assertEqual(len(snapshot.untracked_items), 1)

            staged = snapshot.staged_items[0]
            unstaged = snapshot.unstaged_items[0]
            untracked = snapshot.untracked_items[0]

            self.assertEqual(staged.origin, BundleOrigin.STAGED)
            self.assertEqual(unstaged.origin, BundleOrigin.UNSTAGED)
            self.assertEqual(untracked.origin, BundleOrigin.UNTRACKED)
            self.assertIn("+staged", staged.content)
            self.assertNotIn("+worktree", staged.content)
            self.assertIn("-staged", unstaged.content)
            self.assertIn("+worktree", unstaged.content)
            self.assertEqual(untracked.content, "new file\n")
            self.assertEqual(
                untracked.source_sha256,
                hashlib.sha256(b"new file\n").hexdigest(),
            )
            self.assertNotEqual(
                staged.source_sha256,
                unstaged.source_sha256,
            )


    def test_collect_review_bundle_preserves_scope_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/file.txt", "base\n")
            repo.commit_all("base")

            repo.write_text("app/file.txt", "staged\n")
            repo.git("add", "app/file.txt")
            repo.write_text("app/file.txt", "worktree\n")
            repo.write_text("app/new.txt", "new file\n")
            repo.write_text("app/private/secret.txt", "secret\n")
            before = repo.status_bytes()

            bundle = collect_review_bundle(
                repo.root,
                make_config(exclude_paths=("app/private/",)),
                make_profile("app"),
                target_paths=["app"],
            )

            self.assertEqual(repo.status_bytes(), before)
            self.assertEqual(bundle.command, BundleCommand.REVIEW)
            self.assertEqual(bundle.profile_name, "test_profile")
            self.assertEqual(bundle.target_paths, ("app",))
            self.assertEqual(
                tuple(item.origin for item in bundle.items),
                (
                    BundleOrigin.STAGED,
                    BundleOrigin.UNSTAGED,
                    BundleOrigin.UNTRACKED,
                ),
            )
            self.assertEqual(bundle.included_count, 3)
            self.assertEqual(bundle.skipped_count, 1)
            self.assertEqual(
                bundle.skipped_items[0].relative_path,
                "app/private/secret.txt",
            )
            self.assertEqual(len(bundle.manifest_rows), 3)

    def test_collect_review_bundle_allows_empty_full_profile_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))

            bundle = collect_review_bundle(
                repo.root,
                make_config(),
                make_profile("app"),
            )

            self.assertEqual(bundle.command, BundleCommand.REVIEW)
            self.assertEqual(bundle.profile_name, "test_profile")
            self.assertEqual(bundle.target_paths, ())
            self.assertEqual(bundle.items, ())
            self.assertEqual(bundle.skipped_items, ())

    def test_collect_review_bundle_rejects_external_target_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))

            with self.assertRaisesRegex(
                GitDiffError,
                "outside the project profile",
            ):
                collect_review_bundle(
                    repo.root,
                    make_config(),
                    make_profile("app"),
                    target_paths=("other",),
                )

    def test_collects_initial_staged_file_without_head_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/initial.txt", "initial\n")
            repo.git("add", "app/initial.txt")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(len(snapshot.staged_items), 1)
            self.assertEqual(
                snapshot.staged_items[0].git_change,
                GitChange.ADDED,
            )
            self.assertIn("+initial", snapshot.staged_items[0].content)

    def test_untracked_utf16_preserves_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            source = b"\xff\xfe" + "日本語".encode("utf-16-le")
            repo.write_bytes("app/utf16.txt", source)

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            item = snapshot.untracked_items[0]
            self.assertEqual(item.content, "日本語")
            self.assertEqual(item.encoding, "utf-16-le")
            self.assertEqual(item.source_bytes, len(source))
            self.assertEqual(
                item.source_sha256,
                hashlib.sha256(source).hexdigest(),
            )

    def test_profile_and_target_paths_limit_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/one/a.txt", "a\n")
            repo.write_text("app/two/b.txt", "b\n")
            repo.write_text("other/c.txt", "c\n")
            repo.commit_all("base")

            repo.write_text("app/one/a.txt", "a changed\n")
            repo.write_text("app/two/b.txt", "b changed\n")
            repo.write_text("other/c.txt", "c changed\n")
            repo.git("add", "-A")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
                target_paths=("app/one", "APP/ONE"),
            ).collect()

            self.assertEqual(
                tuple(item.relative_path for item in snapshot.items),
                ("app/one/a.txt",),
            )
            self.assertEqual(snapshot.skipped_items, ())
            self.assertNotIn("other/c.txt", snapshot.items[0].content)

    def test_rejects_invalid_or_profile_external_target_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            profile = make_profile("app")

            invalid_paths = (
                "",
                " app",
                "app/",
                "app\\file.txt",
                "app/../other",
                "other",
            )

            for path in invalid_paths:
                with self.subTest(path=path):
                    with self.assertRaises(GitDiffError):
                        GitDiffCollector(
                            repo.root,
                            make_config(),
                            profile,
                            target_paths=(path,),
                        )

    def test_deleted_file_can_be_selected_by_nonexistent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/deleted.txt", "delete me\n")
            repo.commit_all("base")
            (repo.root / "app" / "deleted.txt").unlink()

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
                target_paths=("app/deleted.txt",),
            ).collect()

            self.assertEqual(len(snapshot.unstaged_items), 1)
            self.assertEqual(
                snapshot.unstaged_items[0].git_change,
                GitChange.DELETED,
            )

    def test_excluded_changes_are_skipped_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/public.txt", "public\n")
            repo.write_text("app/private/secret.txt", "secret\n")
            repo.commit_all("base")

            repo.write_text("app/public.txt", "public changed\n")
            repo.write_text(
                "app/private/secret.txt",
                "secret changed\n",
            )
            repo.git("add", "-A")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(exclude_paths=("app/private/",)),
                make_profile("app"),
            ).collect()

            self.assertEqual(
                tuple(item.relative_path for item in snapshot.staged_items),
                ("app/public.txt",),
            )
            self.assertEqual(len(snapshot.skipped_items), 1)
            skipped = snapshot.skipped_items[0]
            self.assertEqual(skipped.status, CollectionStatus.EXCLUDED)
            self.assertEqual(
                skipped.relative_path,
                "app/private/secret.txt",
            )
            self.assertIn("app/private/", skipped.reason)

    def test_ignored_files_and_profile_external_changes_are_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text(".gitignore", "app/ignored.txt\n")
            repo.write_text("app/in.txt", "inside\n")
            repo.write_text("other/out.txt", "outside\n")
            repo.commit_all("base")

            repo.write_text("app/in.txt", "inside changed\n")
            repo.write_text("other/out.txt", "outside changed\n")
            repo.write_text("app/ignored.txt", "ignored\n")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(
                tuple(item.relative_path for item in snapshot.items),
                ("app/in.txt",),
            )
            self.assertEqual(snapshot.skipped_items, ())
            self.assertNotIn("other/out.txt", snapshot.items[0].content)

    def test_exact_ignored_file_target_is_included_without_siblings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text(".gitignore", "app/local/\n")
            repo.write_text("app/tracked.txt", "tracked\n")
            repo.commit_all("base")
            repo.write_text("app/local/config.json", "{\"ok\": true}\n")
            repo.write_text("app/local/secret.env", "SECRET=value\n")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
                target_paths=("app/local/config.json",),
            ).collect()

            self.assertEqual(snapshot.staged_items, ())
            self.assertEqual(snapshot.unstaged_items, ())
            self.assertEqual(len(snapshot.untracked_items), 1)
            item = snapshot.untracked_items[0]
            self.assertEqual(
                item.relative_path,
                "app/local/config.json",
            )
            self.assertEqual(item.content, "{\"ok\": true}\n")
            self.assertNotIn("SECRET=value", item.content)
            self.assertEqual(snapshot.skipped_items, ())

    def test_ignored_directory_target_does_not_expand_private_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text(".gitignore", "app/local/\n")
            repo.write_text("app/tracked.txt", "tracked\n")
            repo.commit_all("base")
            repo.write_text("app/local/secret.env", "SECRET=value\n")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
                target_paths=("app/local",),
            ).collect()

            self.assertEqual(snapshot.items, ())
            self.assertEqual(len(snapshot.skipped_items), 1)
            self.assertEqual(
                snapshot.skipped_items[0].status,
                CollectionStatus.NO_CHANGES,
            )
            self.assertNotIn(
                "SECRET=value",
                snapshot.skipped_items[0].reason,
            )

    def test_explicit_unchanged_target_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/file.txt", "unchanged\n")
            repo.commit_all("base")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
                target_paths=("app/file.txt",),
            ).collect()

            self.assertEqual(snapshot.items, ())
            self.assertEqual(len(snapshot.skipped_items), 1)
            skipped = snapshot.skipped_items[0]
            self.assertEqual(
                skipped.status,
                CollectionStatus.NO_CHANGES,
            )
            self.assertEqual(skipped.origin, BundleOrigin.EXPLICIT)
            self.assertEqual(skipped.requested_path, "app/file.txt")

    def test_explicit_missing_target_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
                target_paths=("app/missing.txt",),
            ).collect()

            self.assertEqual(snapshot.items, ())
            self.assertEqual(len(snapshot.skipped_items), 1)
            skipped = snapshot.skipped_items[0]
            self.assertEqual(skipped.status, CollectionStatus.MISSING)
            self.assertEqual(skipped.requested_path, "app/missing.txt")

    def test_untracked_binary_is_skipped_without_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_bytes(
                "app/image.png",
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            )

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(snapshot.untracked_items, ())
            self.assertEqual(len(snapshot.skipped_items), 1)
            self.assertEqual(
                snapshot.skipped_items[0].status,
                CollectionStatus.BINARY,
            )

    def test_preserves_internal_rename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/old.txt", "same content\n")
            repo.commit_all("base")
            (repo.root / "app" / "old.txt").rename(
                repo.root / "app" / "new.txt"
            )
            repo.git("add", "-A")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(len(snapshot.staged_items), 1)
            item = snapshot.staged_items[0]
            self.assertEqual(item.git_change, GitChange.RENAMED)
            self.assertEqual(item.previous_path, "app/old.txt")
            self.assertEqual(item.relative_path, "app/new.txt")
            self.assertIn("rename from app/old.txt", item.content)
            self.assertIn("rename to app/new.txt", item.content)

    def test_rename_from_profile_to_outside_becomes_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/old.txt", "same content\n")
            repo.commit_all("base")
            (repo.root / "other").mkdir()
            (repo.root / "app" / "old.txt").rename(
                repo.root / "other" / "new.txt"
            )
            repo.git("add", "-A")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(len(snapshot.staged_items), 1)
            item = snapshot.staged_items[0]
            self.assertEqual(item.git_change, GitChange.DELETED)
            self.assertEqual(item.relative_path, "app/old.txt")
            self.assertNotIn("other/new.txt", item.content)

    def test_rename_from_outside_to_profile_becomes_addition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("other/old.txt", "same content\n")
            repo.commit_all("base")
            (repo.root / "app").mkdir()
            (repo.root / "other" / "old.txt").rename(
                repo.root / "app" / "new.txt"
            )
            repo.git("add", "-A")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(len(snapshot.staged_items), 1)
            item = snapshot.staged_items[0]
            self.assertEqual(item.git_change, GitChange.ADDED)
            self.assertEqual(item.relative_path, "app/new.txt")
            self.assertNotIn("other/old.txt", item.content)

    def test_copy_boundary_rules(self) -> None:
        with self.subTest(case="inside_to_inside"):
            with tempfile.TemporaryDirectory() as temp_dir:
                repo = GitRepository(Path(temp_dir))
                repo.write_text("app/source.txt", "copy source\n")
                repo.commit_all("base")
                repo.write_text("app/copy.txt", "copy source\n")
                repo.git("add", "app/copy.txt")

                snapshot = GitDiffCollector(
                    repo.root,
                    make_config(),
                    make_profile("app"),
                ).collect()

                self.assertEqual(
                    snapshot.staged_items[0].git_change,
                    GitChange.COPIED,
                )
                self.assertEqual(
                    snapshot.staged_items[0].previous_path,
                    "app/source.txt",
                )

        with self.subTest(case="outside_to_inside"):
            with tempfile.TemporaryDirectory() as temp_dir:
                repo = GitRepository(Path(temp_dir))
                repo.write_text("other/source.txt", "outside source\n")
                repo.commit_all("base")
                repo.write_text("app/copy.txt", "outside source\n")
                repo.git("add", "app/copy.txt")

                snapshot = GitDiffCollector(
                    repo.root,
                    make_config(),
                    make_profile("app"),
                ).collect()

                self.assertEqual(
                    snapshot.staged_items[0].git_change,
                    GitChange.ADDED,
                )
                self.assertIsNone(
                    snapshot.staged_items[0].previous_path
                )
                self.assertNotIn(
                    "other/source.txt",
                    snapshot.staged_items[0].content,
                )

        with self.subTest(case="inside_to_outside"):
            with tempfile.TemporaryDirectory() as temp_dir:
                repo = GitRepository(Path(temp_dir))
                repo.write_text("app/source.txt", "inside source\n")
                repo.commit_all("base")
                repo.write_text("other/copy.txt", "inside source\n")
                repo.git("add", "other/copy.txt")

                snapshot = GitDiffCollector(
                    repo.root,
                    make_config(),
                    make_profile("app"),
                ).collect()

                self.assertEqual(snapshot.staged_items, ())

    def test_handles_spaces_and_japanese_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            path = "app/日本語 folder/資料 file.txt"
            repo.write_text(path, "before\n")
            repo.commit_all("base")
            repo.write_text(path, "after\n")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            self.assertEqual(
                snapshot.unstaged_items[0].relative_path,
                path,
            )
            self.assertIn("+after", snapshot.unstaged_items[0].content)

    def test_tracked_binary_uses_textual_git_diff_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_bytes("app/data.bin", b"\x00\x01\x02")
            repo.commit_all("base")
            repo.write_bytes("app/data.bin", b"\x00\x01\x03")
            repo.git("add", "app/data.bin")

            snapshot = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            ).collect()

            item = snapshot.staged_items[0]
            self.assertIn("Binary files", item.content)
            self.assertNotIn("GIT binary patch", item.content)

    def test_type_changed_and_unmerged_are_represented(self) -> None:
        with self.subTest(case="type_changed"):
            with tempfile.TemporaryDirectory() as temp_dir:
                repo = GitRepository(Path(temp_dir))
                repo.write_text("app/value", "regular\n")
                repo.commit_all("base")
                blob = repo.git(
                    "hash-object",
                    "-w",
                    "--stdin",
                    input_bytes=b"target.txt",
                ).stdout.decode("ascii").strip()
                repo.git(
                    "update-index",
                    "--cacheinfo",
                    f"120000,{blob},app/value",
                )

                snapshot = GitDiffCollector(
                    repo.root,
                    make_config(),
                    make_profile("app"),
                ).collect()

                self.assertEqual(
                    snapshot.staged_items[0].git_change,
                    GitChange.TYPE_CHANGED,
                )

        with self.subTest(case="unmerged"):
            with tempfile.TemporaryDirectory() as temp_dir:
                repo = GitRepository(Path(temp_dir))
                repo.write_text("app/conflict.txt", "base\n")
                repo.commit_all("base")
                repo.git("checkout", "-qb", "other")
                repo.write_text("app/conflict.txt", "other\n")
                repo.commit_all("other")
                repo.git("checkout", "-q", "master")
                repo.write_text("app/conflict.txt", "master\n")
                repo.commit_all("master")
                merge = repo.git("merge", "other", check=False)
                self.assertNotEqual(merge.returncode, 0)

                snapshot = GitDiffCollector(
                    repo.root,
                    make_config(),
                    make_profile("app"),
                ).collect()

                self.assertEqual(len(snapshot.staged_items), 1)
                self.assertEqual(len(snapshot.unstaged_items), 1)
                self.assertEqual(
                    snapshot.staged_items[0].git_change,
                    GitChange.UNMERGED,
                )
                self.assertEqual(
                    snapshot.unstaged_items[0].git_change,
                    GitChange.UNMERGED,
                )

    def test_rejects_repo_root_that_is_only_a_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            (repo.root / "nested" / "app").mkdir(parents=True)

            collector = GitDiffCollector(
                repo.root / "nested",
                make_config(),
                make_profile("app"),
            )

            with self.assertRaisesRegex(
                GitDiffError,
                "does not match RepoRoot",
            ):
                collector.collect()

    def test_result_is_deterministic_and_snapshot_validates_origins(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = GitRepository(Path(temp_dir))
            repo.write_text("app/z.txt", "z\n")
            repo.write_text("app/a.txt", "a\n")
            repo.commit_all("base")
            repo.write_text("app/z.txt", "z changed\n")
            repo.write_text("app/a.txt", "a changed\n")
            repo.git("add", "-A")

            collector = GitDiffCollector(
                repo.root,
                make_config(),
                make_profile("app"),
            )
            first = collector.collect()
            second = collector.collect()

            self.assertEqual(first, second)
            self.assertEqual(
                tuple(item.relative_path for item in first.staged_items),
                ("app/a.txt", "app/z.txt"),
            )

            with self.assertRaises(GitDiffError):
                GitReviewSnapshot(
                    unstaged_items=first.staged_items,
                )


if __name__ == "__main__":
    unittest.main()
