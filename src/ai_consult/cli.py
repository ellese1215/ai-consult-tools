from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ai_consult import __version__
from ai_consult.config import ConfigError, ConsultConfig, load_config, parse_config
from ai_consult.filters import FilterError
from ai_consult.inventory import (
    FolderTreeComparison,
    InventoryError,
    InventoryScanner,
    InventorySnapshot,
    StructureDiff,
    compare_folder_tree,
    sync_folder_tree,
)
from ai_consult.path_resolver import PathResolutionError, RepoPathResolver


TOOL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO_ROOT = TOOL_ROOT.parent
DEFAULT_LOCAL_CONFIG_PATH = Path("ai-consult-tools/local/consult.config.json")
EXIT_CURRENT = 0
EXIT_STALE = 1
EXIT_ERROR = 2


def _add_structure_runtime_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--repo-root",
        help=(
            "RepoRoot path. Defaults to the parent directory of "
            "ai-consult-tools."
        ),
    )
    parser.add_argument(
        "--config-path",
        help=(
            "RepoRoot-relative configuration path. Defaults to "
            "ai-consult-tools/local/consult.config.json when it exists."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="consult.py",
        description="AI相談運用基盤 v4",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    commands = parser.add_subparsers(dest="command")
    structure_parser = commands.add_parser(
        "structure",
        help="manage the repository structure inventory",
    )
    structure_commands = structure_parser.add_subparsers(
        dest="structure_command",
        required=True,
    )

    sync_parser = structure_commands.add_parser(
        "sync",
        help="update folder_tree.txt when the repository structure changed",
    )
    _add_structure_runtime_arguments(sync_parser)
    sync_parser.set_defaults(handler=_run_structure_sync)

    check_parser = structure_commands.add_parser(
        "check",
        help="check folder_tree.txt without modifying files",
    )
    _add_structure_runtime_arguments(check_parser)
    check_parser.set_defaults(handler=_run_structure_check)

    return parser


def _resolve_repo_root(value: str | None) -> Path:
    candidate = Path(value) if value is not None else DEFAULT_REPO_ROOT
    return RepoPathResolver(candidate).repo_root


def _load_runtime_config(
    repo_root: Path,
    config_path: str | None,
) -> ConsultConfig:
    resolver = RepoPathResolver(repo_root)

    if config_path is not None:
        resolved = resolver.resolve(
            config_path,
            must_exist=True,
            allow_file=True,
            allow_directory=False,
        )
        return load_config(resolved.logical_path)

    default_path = repo_root / DEFAULT_LOCAL_CONFIG_PATH

    if default_path.exists() or default_path.is_symlink():
        resolved = resolver.resolve(
            DEFAULT_LOCAL_CONFIG_PATH,
            must_exist=True,
            allow_file=True,
            allow_directory=False,
        )
        return load_config(resolved.logical_path)

    return parse_config({"schemaVersion": 1})


def _create_snapshot(args: argparse.Namespace) -> InventorySnapshot:
    repo_root = _resolve_repo_root(args.repo_root)
    config = _load_runtime_config(repo_root, args.config_path)
    return InventoryScanner.from_config(repo_root, config).scan()


def _print_diff(diff: StructureDiff) -> None:
    print(f"added: {len(diff.added_paths)}")

    for path in diff.added_paths:
        print(f"  + {path}")

    print(f"removed: {len(diff.removed_paths)}")

    for path in diff.removed_paths:
        print(f"  - {path}")

    print(f"move candidates: {len(diff.move_candidates)}")

    for candidate in diff.move_candidates:
        print(
            "  ~ "
            f"{candidate.previous_path} -> {candidate.current_path}"
        )


def _print_comparison_details(comparison: FolderTreeComparison) -> None:
    if comparison.format_error is not None:
        print(
            "previous comparison unavailable: "
            f"{comparison.format_error}"
        )
        return

    if comparison.diff is not None:
        _print_diff(comparison.diff)


def _run_structure_sync(args: argparse.Namespace) -> int:
    snapshot = _create_snapshot(args)
    result = sync_folder_tree(snapshot)

    if result.updated:
        print("structure sync: updated")
        _print_comparison_details(result.comparison)
    else:
        print("structure sync: current")

    print(f"entries: {len(snapshot.entries)}")
    print(f"folder tree: {result.comparison.folder_tree_path}")
    return EXIT_CURRENT


def _run_structure_check(args: argparse.Namespace) -> int:
    snapshot = _create_snapshot(args)
    comparison = compare_folder_tree(snapshot)

    if comparison.is_current:
        print("structure check: current")
        print(f"entries: {len(snapshot.entries)}")
        print(f"folder tree: {comparison.folder_tree_path}")
        return EXIT_CURRENT

    print("structure check: stale")
    _print_comparison_details(comparison)
    print(f"entries: {len(snapshot.entries)}")
    print(f"folder tree: {comparison.folder_tree_path}")
    print("run: python ai-consult-tools/consult.py structure sync")
    return EXIT_STALE


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)

    if handler is None:
        parser.print_help()
        return EXIT_CURRENT

    try:
        return int(handler(args))
    except (
        ConfigError,
        FilterError,
        InventoryError,
        PathResolutionError,
        OSError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
