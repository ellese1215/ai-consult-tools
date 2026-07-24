from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ai_consult import __version__
from ai_consult.bundle import BundleModel
from ai_consult.config import (
    ConfigError,
    ConsultConfig,
    ProjectProfile,
    load_config,
    load_project_profiles,
    parse_config,
)
from ai_consult.filters import FilterError
from ai_consult.git_diff import GitDiffError, collect_review_bundle
from ai_consult.renderers import (
    OutputAdapterError,
    OutputTarget,
    create_output_context,
    write_chatgpt_bundle,
    write_claude_bundle,
)
from ai_consult.renderers.common import (
    JST,
    OutputContext,
    OutputResult,
)
from ai_consult.start_bundle import (
    StartBundleAssemblyError,
    collect_start_bundle,
)
from ai_consult.inventory import (
    FolderTreeComparison,
    InventoryError,
    InventoryScanner,
    InventorySnapshot,
    StructureDiff,
    StructureIndexComparison,
    compare_folder_tree,
    compare_structure_index,
    prepare_structure_index_parent,
    read_structure_index,
    sync_folder_tree,
    sync_structure_index,
)
from ai_consult.path_resolver import PathResolutionError, RepoPathResolver
from ai_consult.search import (
    StructureSearchError,
    find_structure_entries,
    normalize_structure_query,
)


TOOL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO_ROOT = TOOL_ROOT.parent
DEFAULT_LOCAL_CONFIG_PATH = Path("ai-consult-tools/local/consult.config.json")
DEFAULT_LOCAL_PROJECT_PROFILES_PATH = Path(
    "ai-consult-tools/local/project_profiles.json"
)
DEFAULT_PROJECT_PROFILES_EXAMPLE_PATH = Path(
    "ai-consult-tools/config/project_profiles.example.json"
)
EXIT_CURRENT = 0
EXIT_STALE = 1
EXIT_NO_MATCH = 1
EXIT_ERROR = 2


def _add_runtime_arguments(
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


def _add_bundle_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--target",
        required=True,
        choices=tuple(target.value for target in OutputTarget),
        help="physical output target",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="named project profile",
    )
    parser.add_argument(
        "--case-name",
        help="optional ASCII case name appended to BundleLabel",
    )
    _add_runtime_arguments(parser)


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

    find_parser = commands.add_parser(
        "find",
        help="search file paths in the current local structure index",
    )
    find_parser.add_argument("query", help="file name or partial path")
    find_parser.add_argument(
        "--profile",
        help="limit results to a named project profile",
    )
    _add_runtime_arguments(find_parser)
    find_parser.set_defaults(handler=_run_find)

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
        help=(
            "update folder_tree.txt and the local structure index when "
            "the repository structure changed"
        ),
    )
    _add_runtime_arguments(sync_parser)
    sync_parser.set_defaults(handler=_run_structure_sync)

    check_parser = structure_commands.add_parser(
        "check",
        help=(
            "check folder_tree.txt and the local structure index without "
            "modifying files"
        ),
    )
    _add_runtime_arguments(check_parser)
    check_parser.set_defaults(handler=_run_structure_check)

    start_parser = commands.add_parser(
        "start",
        help="collect and write a start consultation bundle",
    )
    _add_bundle_arguments(start_parser)
    start_parser.add_argument(
        "--include-set",
        action="append",
        default=[],
        help="named include set; may be specified more than once",
    )
    start_parser.add_argument(
        "--include-paths",
        nargs="*",
        default=[],
        help="explicit RepoRoot-relative files or directories",
    )
    start_parser.set_defaults(handler=_run_start)

    review_parser = commands.add_parser(
        "review",
        help="collect and write a review consultation bundle",
    )
    _add_bundle_arguments(review_parser)
    review_parser.add_argument(
        "--target-paths",
        nargs="*",
        default=[],
        help="optional RepoRoot-relative review targets",
    )
    review_parser.set_defaults(handler=_run_review)

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


def _load_project_profile(
    repo_root: Path,
    name: str | None,
) -> ProjectProfile | None:
    if name is None:
        return None

    resolver = RepoPathResolver(repo_root)
    local_path = repo_root / DEFAULT_LOCAL_PROJECT_PROFILES_PATH
    requested = (
        DEFAULT_LOCAL_PROJECT_PROFILES_PATH
        if local_path.exists() or local_path.is_symlink()
        else DEFAULT_PROJECT_PROFILES_EXAMPLE_PATH
    )
    resolved = resolver.resolve(
        requested,
        must_exist=True,
        allow_file=True,
        allow_directory=False,
    )
    return load_project_profiles(resolved.logical_path).get(name)


def _create_snapshot(
    args: argparse.Namespace,
    *,
    prepare_index_parent: bool = False,
) -> InventorySnapshot:
    repo_root = _resolve_repo_root(args.repo_root)
    config = _load_runtime_config(repo_root, args.config_path)

    if prepare_index_parent:
        prepare_structure_index_parent(repo_root)

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


def _print_index_comparison_details(
    comparison: StructureIndexComparison,
) -> None:
    if comparison.format_error is not None:
        print(
            "structure index comparison unavailable: "
            f"{comparison.format_error}"
        )


def _status(updated: bool) -> str:
    return "updated" if updated else "current"


def _run_find(args: argparse.Namespace) -> int:
    query = normalize_structure_query(args.query)
    snapshot = _create_snapshot(args)
    comparison = compare_structure_index(snapshot)

    if not comparison.is_current:
        if not comparison.previous_exists:
            state = "missing"
        elif comparison.format_error is not None:
            state = "invalid"
        else:
            state = "stale"

        raise StructureSearchError(
            f"structure index is {state}; run: "
            "python ai-consult-tools/consult.py structure sync"
        )

    entries = read_structure_index(comparison.structure_index_path)
    profile = _load_project_profile(snapshot.repo_root, args.profile)
    matches = find_structure_entries(
        entries,
        query,
        profile=profile,
    )
    profile_name = profile.name if profile is not None else "(all)"

    if matches:
        print(f"find: {len(matches)} matches")
    else:
        print("find: no matches")

    print(f"query: {query}")
    print(f"profile: {profile_name}")

    for match in matches:
        print(f"  [file] {match.entry.relative_path}")

    return EXIT_CURRENT if matches else EXIT_NO_MATCH


def _run_structure_sync(args: argparse.Namespace) -> int:
    snapshot = _create_snapshot(args, prepare_index_parent=True)
    folder_tree_result = sync_folder_tree(snapshot)
    structure_index_result = sync_structure_index(snapshot)
    updated = folder_tree_result.updated or structure_index_result.updated

    print(f"structure sync: {_status(updated)}")
    print(f"folder tree: {_status(folder_tree_result.updated)}")
    print(f"structure index: {_status(structure_index_result.updated)}")

    if folder_tree_result.updated:
        _print_comparison_details(folder_tree_result.comparison)

    if structure_index_result.updated:
        _print_index_comparison_details(structure_index_result.comparison)

    print(f"entries: {len(snapshot.entries)}")
    print(
        "folder tree path: "
        f"{folder_tree_result.comparison.folder_tree_path}"
    )
    print(
        "structure index path: "
        f"{structure_index_result.comparison.structure_index_path}"
    )
    return EXIT_CURRENT


def _run_structure_check(args: argparse.Namespace) -> int:
    snapshot = _create_snapshot(args)
    folder_tree_comparison = compare_folder_tree(snapshot)
    structure_index_comparison = compare_structure_index(snapshot)
    is_current = (
        folder_tree_comparison.is_current
        and structure_index_comparison.is_current
    )

    print(
        "structure check: "
        f"{'current' if is_current else 'stale'}"
    )
    print(
        "folder tree: "
        f"{'current' if folder_tree_comparison.is_current else 'stale'}"
    )
    print(
        "structure index: "
        f"{'current' if structure_index_comparison.is_current else 'stale'}"
    )

    if not folder_tree_comparison.is_current:
        _print_comparison_details(folder_tree_comparison)

    if not structure_index_comparison.is_current:
        _print_index_comparison_details(structure_index_comparison)

    print(f"entries: {len(snapshot.entries)}")
    print(f"folder tree path: {folder_tree_comparison.folder_tree_path}")
    print(
        "structure index path: "
        f"{structure_index_comparison.structure_index_path}"
    )

    if is_current:
        return EXIT_CURRENT

    print("run: python ai-consult-tools/consult.py structure sync")
    return EXIT_STALE


def _build_output_context(
    args: argparse.Namespace,
    repo_root: Path,
    config: ConsultConfig,
) -> OutputContext:
    target = OutputTarget(args.target)
    generated_at = datetime.now(tz=JST)

    if target is OutputTarget.CHATGPT:
        settings = config.outputs.chatgpt
        return create_output_context(
            target=target,
            repo_root=repo_root,
            output_root=repo_root / settings.out_root,
            generated_at=generated_at,
            case_name=args.case_name,
            max_chars_per_part=settings.max_chars_per_part,
            max_bytes_per_part=settings.max_bytes_per_part,
        )

    settings = config.outputs.claude
    return create_output_context(
        target=target,
        repo_root=repo_root,
        output_root=repo_root / settings.out_root,
        generated_at=generated_at,
        case_name=args.case_name,
        max_chars_per_part=settings.max_chars_per_part,
    )


def _write_bundle(
    bundle: BundleModel,
    context: OutputContext,
) -> OutputResult:
    if context.target is OutputTarget.CHATGPT:
        return write_chatgpt_bundle(bundle, context)

    return write_claude_bundle(bundle, context)


def _print_output_result(
    command: str,
    result: OutputResult,
) -> None:
    if result.target is OutputTarget.CHATGPT and (
        result.bundle_path is None
        or result.bundle_sha256 is None
        or result.sidecar_path is None
        or result.sidecar_match is not True
    ):
        raise OutputAdapterError(
            "ChatGPT output result is missing verified ZIP sidecar metadata"
        )

    print(f"{command}: created")
    print(f"target: {result.target.value}")
    print(f"bundle: {result.bundle_label}")

    for path in result.output_paths:
        print(f"output: {path}")

    if result.target is OutputTarget.CHATGPT:
        print(f"bundle_path: {result.bundle_path}")
        print(f"bundle_sha256: {result.bundle_sha256}")
        print(f"sidecar_path: {result.sidecar_path}")
        print("sidecar_match: true")


def _run_start(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo_root)
    config = _load_runtime_config(repo_root, args.config_path)
    profile = _load_project_profile(repo_root, args.profile)

    if profile is None:
        raise ConfigError("start requires a project profile")

    bundle = collect_start_bundle(
        repo_root,
        config,
        profile,
        include_set_names=args.include_set,
        explicit_paths=args.include_paths,
    )
    context = _build_output_context(args, repo_root, config)
    result = _write_bundle(bundle, context)
    _print_output_result("start", result)
    return EXIT_CURRENT


def _run_review(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo_root)
    config = _load_runtime_config(repo_root, args.config_path)
    profile = _load_project_profile(repo_root, args.profile)

    if profile is None:
        raise ConfigError("review requires a project profile")

    bundle = collect_review_bundle(
        repo_root,
        config,
        profile,
        target_paths=args.target_paths,
    )

    if not bundle.items and not bundle.skipped_items:
        print("review: no changes")
        print(f"target: {args.target}")
        print(f"profile: {profile.name}")
        return EXIT_CURRENT

    context = _build_output_context(args, repo_root, config)
    result = _write_bundle(bundle, context)
    _print_output_result("review", result)
    return EXIT_CURRENT


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
        StructureSearchError,
        GitDiffError,
        StartBundleAssemblyError,
        OutputAdapterError,
        OSError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
