from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from ai_consult.cli import (
    EXIT_ERROR,
    _load_project_profile,
    _resolve_repo_root,
    main as current_main,
)
from ai_consult.config import ConfigError
from ai_consult.path_resolver import PathResolutionError, RepoPathResolver


LEGACY_WARNING: Final[str] = (
    "WARNING: legacy entry point; use ai-consult-tools/consult.py "
    "for new commands."
)
MIGRATION_HINT: Final[str] = (
    "MIGRATION: use python ai-consult-tools/consult.py start|review "
    "with the common V4 configuration."
)
_SUPPORTED_TARGETS: Final[tuple[str, ...]] = ("chatgpt", "claude")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


class LegacyCliError(ValueError):
    pass


class LegacyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        print(MIGRATION_HINT, file=sys.stderr)
        raise SystemExit(EXIT_ERROR)


def build_legacy_parser(target: str) -> argparse.ArgumentParser:
    normalized_target = _normalize_target(target)
    parser = LegacyArgumentParser(
        prog=f"consult_bundle_{normalized_target}.py",
        description=(
            f"Legacy {normalized_target} compatibility entry point for "
            "AI consultation platform v4"
        ),
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("map", "repo", "include", "diff"),
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--case-name")
    parser.add_argument("--config-path")
    parser.set_defaults(include_set=[])

    if normalized_target == "chatgpt":
        parser.add_argument(
            "--include-set",
            nargs="+",
            action="append",
        )

    parser.add_argument("--include-paths", nargs="+", default=[])

    parser.add_argument(
        "--allow-docset-folders",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep-bundle-dir",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--diag",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-bytes-per-part",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-chars-per-part",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--unstaged-only",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--diff-base",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--diff-target",
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def translate_legacy_arguments(
    args: argparse.Namespace,
    *,
    target: str,
) -> tuple[str, ...]:
    normalized_target = _normalize_target(target)
    _validate_legacy_arguments(args, target=normalized_target)
    repo_root = _resolve_repo_root(args.repo_root)
    _validate_v4_config_schema(repo_root, args.config_path)

    command = "review" if args.mode == "diff" else "start"
    translated: list[str] = [
        command,
        "--target",
        normalized_target,
        "--profile",
        args.profile,
        "--repo-root",
        args.repo_root,
    ]

    if args.case_name:
        translated.extend(("--case-name", args.case_name))

    if args.config_path:
        translated.extend(("--config-path", args.config_path))

    if args.mode == "repo":
        profile = _load_project_profile(repo_root, args.profile)

        if profile is None:
            raise LegacyCliError("repo mode requires a project profile")

        translated.append("--include-paths")
        translated.extend(profile.scope_roots)
    elif args.mode == "include":
        for include_set_name in _flatten(args.include_set):
            translated.extend(("--include-set", include_set_name))

        if args.include_paths:
            translated.append("--include-paths")
            translated.extend(args.include_paths)

    return tuple(translated)


def main(
    argv: Sequence[str] | None = None,
    *,
    target: str,
) -> int:
    normalized_target = _normalize_target(target)
    parser = build_legacy_parser(normalized_target)
    args = parser.parse_args(argv)
    print(LEGACY_WARNING, file=sys.stderr)

    try:
        translated = translate_legacy_arguments(
            args,
            target=normalized_target,
        )
    except (
        ConfigError,
        LegacyCliError,
        OSError,
        PathResolutionError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(MIGRATION_HINT, file=sys.stderr)
        return EXIT_ERROR

    return current_main(translated)


def _normalize_target(target: str) -> str:
    if target not in _SUPPORTED_TARGETS:
        raise ValueError(
            "legacy target must be one of: " + ", ".join(_SUPPORTED_TARGETS)
        )

    return target


def _validate_legacy_arguments(
    args: argparse.Namespace,
    *,
    target: str,
) -> None:
    unsupported = tuple(
        option
        for attribute, option in (
            ("allow_docset_folders", "--allow-docset-folders"),
            ("keep_bundle_dir", "--keep-bundle-dir"),
            ("diag", "--diag"),
            ("max_bytes_per_part", "--max-bytes-per-part"),
            ("max_chars_per_part", "--max-chars-per-part"),
            ("max_chars_per_file", "--max-chars-per-file"),
            ("staged", "--staged"),
            ("unstaged_only", "--unstaged-only"),
            ("diff_base", "--diff-base"),
            ("diff_target", "--diff-target"),
        )
        if getattr(args, attribute) is not None
    )

    if unsupported:
        raise LegacyCliError(
            "unsupported legacy option(s): " + ", ".join(unsupported)
        )

    include_set_names = _flatten(args.include_set)
    has_include_requests = bool(include_set_names or args.include_paths)

    if target == "claude" and include_set_names:
        raise LegacyCliError(
            "--include-set is not maintained by the legacy Claude entry point"
        )

    if args.mode == "include" and not has_include_requests:
        raise LegacyCliError(
            "include mode requires --include-set or --include-paths"
        )

    if args.mode != "include" and has_include_requests:
        raise LegacyCliError(
            "--include-set and --include-paths are valid only with "
            "--mode include"
        )

    for path in args.include_paths:
        if (
            path.startswith(("/", "\\"))
            or _WINDOWS_ABSOLUTE.match(path)
        ):
            raise LegacyCliError(
                "absolute include paths are not supported by the V4 "
                f"compatibility entry point: {path}"
            )

        if "\\" in path:
            raise LegacyCliError(
                "include paths must be RepoRoot-relative and use / "
                f"separators: {path}"
            )


def _validate_v4_config_schema(
    repo_root: Path,
    config_path: str | None,
) -> None:
    if not config_path:
        return

    resolver = RepoPathResolver(repo_root)
    resolved = resolver.resolve(
        config_path,
        must_exist=True,
        allow_file=True,
        allow_directory=False,
    )

    try:
        value = json.loads(resolved.logical_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    if not isinstance(value, dict):
        return

    schema_version = value.get("schemaVersion")

    if type(schema_version) is not int or schema_version != 1:
        raise LegacyCliError(
            "legacy configuration schema is not supported; migrate to "
            "ai-consult-tools/local/consult.config.json"
        )


def _flatten(values: Sequence[Sequence[str]]) -> tuple[str, ...]:
    return tuple(item for group in values for item in group)
