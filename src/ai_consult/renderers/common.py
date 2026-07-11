from __future__ import annotations

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator

from ai_consult.bundle import (
    BundleCommand,
    BundleItem,
    BundleModel,
    BundleOrigin,
    ContentKind,
    SkippedItem,
    render_manifest_csv,
)


JST = timezone(timedelta(hours=9))
START_DOCUMENT_PATHS = (
    "REPO_OVERVIEW.md",
    "PROJECT_TREE.md",
    "STRUCTURE_STATUS.md",
    "PATH_INDEX.md",
    "SKIPPED.md",
)
_GROUP_EXTENSIONS = {
    "php": {".php", ".phtml", ".inc"},
    "ts": {".ts", ".tsx"},
    "js": {".js", ".mjs", ".cjs", ".jsx"},
    "sql": {".sql"},
    "styles": {".css", ".scss", ".sass", ".less"},
    "docs": {".md", ".txt"},
    "config": {
        ".json",
        ".yml",
        ".yaml",
        ".ini",
        ".conf",
        ".htaccess",
    },
}
_GROUP_ORDER = {
    name: index
    for index, name in enumerate(
        ("config", "docs", "js", "misc", "php", "sql", "styles", "ts")
    )
}
_ORIGIN_ORDER = {
    origin: index
    for index, origin in enumerate(
        (
            BundleOrigin.GENERATED,
            BundleOrigin.INCLUDE_SET,
            BundleOrigin.EXPLICIT,
            BundleOrigin.STAGED,
            BundleOrigin.UNSTAGED,
            BundleOrigin.UNTRACKED,
        )
    )
}
_DOCSET_PATTERN = re.compile(r"\d{14}")
_INVALID_CASE_NAME = re.compile(r"[^A-Za-z0-9._-]")
_BACKTICK_RUN = re.compile(r"`+")
_PLACEHOLDER_MARKERS = (
    "(see below)",
    "DocSet placeholder",
)


class OutputAdapterError(RuntimeError):
    pass


class OutputTarget(str, Enum):
    CHATGPT = "chatgpt"
    CLAUDE = "claude"


@dataclass(frozen=True)
class OutputContext:
    target: OutputTarget
    repo_root: Path
    output_root: Path
    docset: str
    generated_at: datetime
    case_name: str | None = None
    max_chars_per_part: int = 300_000
    max_bytes_per_part: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, OutputTarget):
            raise OutputAdapterError(
                "target must be an OutputTarget value"
            )

        repo_root = Path(self.repo_root).resolve()
        output_root = Path(self.output_root).resolve(strict=False)
        object.__setattr__(self, "repo_root", repo_root)
        object.__setattr__(self, "output_root", output_root)

        try:
            common = Path(os.path.commonpath((repo_root, output_root)))
        except ValueError as exc:
            raise OutputAdapterError(
                "output_root must be inside RepoRoot"
            ) from exc

        if common != repo_root:
            raise OutputAdapterError(
                "output_root must be inside RepoRoot"
            )

        if not isinstance(self.docset, str) or not _DOCSET_PATTERN.fullmatch(
            self.docset
        ):
            raise OutputAdapterError(
                "docset must contain exactly 14 digits"
            )

        if not isinstance(self.generated_at, datetime):
            raise OutputAdapterError(
                "generated_at must be a datetime value"
            )

        if self.generated_at.tzinfo is None:
            raise OutputAdapterError(
                "generated_at must be timezone-aware"
            )

        normalized_case_name = normalize_case_name(self.case_name)
        object.__setattr__(self, "case_name", normalized_case_name)

        if (
            type(self.max_chars_per_part) is not int
            or self.max_chars_per_part <= 0
        ):
            raise OutputAdapterError(
                "max_chars_per_part must be a positive integer"
            )

        if self.max_bytes_per_part is not None and (
            type(self.max_bytes_per_part) is not int
            or self.max_bytes_per_part <= 0
        ):
            raise OutputAdapterError(
                "max_bytes_per_part must be a positive integer or None"
            )

    @property
    def generated_at_jst(self) -> str:
        return self.generated_at.astimezone(JST).strftime(
            "%Y-%m-%d %H:%M:%S %z"
        )

    def bundle_label(self, bundle: BundleModel) -> str:
        if not isinstance(bundle, BundleModel):
            raise OutputAdapterError(
                "bundle must be a BundleModel value"
            )

        label = f"{self.docset}_{bundle.command.value}"

        if self.case_name:
            label += f"_{self.case_name}"

        return label


@dataclass(frozen=True)
class RenderedItem:
    item: BundleItem
    group: str
    block: str


@dataclass(frozen=True)
class PartFile:
    relative_path: str
    content: str


@dataclass(frozen=True)
class OutputResult:
    target: OutputTarget
    bundle_label: str
    bundle_directory: Path
    output_paths: tuple[Path, ...]


@dataclass(frozen=True)
class OutputDocuments:
    start_documents: tuple[tuple[str, str], ...]
    skipped: str
    manifest: str
    diff_index: str | None


def normalize_case_name(value: str | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise OutputAdapterError(
            "case_name must be a string or None"
        )

    normalized = re.sub(r"\s+", "_", value.strip())
    normalized = _INVALID_CASE_NAME.sub("", normalized)

    if not normalized:
        raise OutputAdapterError(
            "case_name does not contain a usable ASCII name"
        )

    return normalized


def create_output_context(
    *,
    target: OutputTarget,
    repo_root: str | Path,
    output_root: str | Path,
    generated_at: datetime,
    case_name: str | None,
    max_chars_per_part: int,
    max_bytes_per_part: int | None = None,
) -> OutputContext:
    generated_jst = generated_at.astimezone(JST)
    return OutputContext(
        target=target,
        repo_root=Path(repo_root),
        output_root=Path(output_root),
        docset=generated_jst.strftime("%Y%m%d%H%M%S"),
        generated_at=generated_at,
        case_name=case_name,
        max_chars_per_part=max_chars_per_part,
        max_bytes_per_part=max_bytes_per_part,
    )


def get_group(relative_path: str) -> str:
    lower = relative_path.lower()
    name = Path(lower).name

    if name == ".htaccess":
        return "config"

    suffix = Path(lower).suffix

    for group, extensions in _GROUP_EXTENSIONS.items():
        if suffix in extensions:
            return group

    return "misc"


def get_fence_language(item: BundleItem) -> str:
    if item.content_kind is ContentKind.DIFF:
        return "diff"

    lower = item.relative_path.lower()
    suffix = Path(lower).suffix
    mapping = {
        ".php": "php",
        ".phtml": "php",
        ".inc": "php",
        ".ts": "ts",
        ".tsx": "tsx",
        ".js": "js",
        ".mjs": "js",
        ".cjs": "js",
        ".jsx": "jsx",
        ".sql": "sql",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".ini": "ini",
        ".md": "markdown",
    }
    return mapping.get(suffix, "")


def safe_fence(content: str) -> str:
    longest = max(
        (len(match.group(0)) for match in _BACKTICK_RUN.finditer(content)),
        default=0,
    )
    return "`" * max(3, longest + 1)


def render_bundle_item(item: BundleItem) -> RenderedItem:
    if not isinstance(item, BundleItem):
        raise OutputAdapterError(
            "item must be a BundleItem value"
        )

    fence = safe_fence(item.content)
    language = get_fence_language(item)
    opening_fence = fence + language
    content = item.content

    if content and not content.endswith("\n"):
        content += "\n"

    lines = [
        "--- BEGIN BUNDLE ITEM ---",
        f"Path: {item.relative_path}",
        f"ContentKind: {item.content_kind.value}",
        f"Origin: {item.origin.value}",
        "GitChange: "
        + (item.git_change.value if item.git_change is not None else "(none)"),
        f"PreviousPath: {item.previous_path or '(none)'}",
        f"Encoding: {item.encoding}",
        f"SourceBytes: {item.source_bytes}",
        f"SourceSHA256: {item.source_sha256}",
        "--- CONTENT ---",
        opening_fence,
    ]
    block = "\n".join(lines) + "\n" + content
    block += fence + "\n--- END BUNDLE ITEM ---\n"
    return RenderedItem(
        item=item,
        group=get_group(item.relative_path),
        block=block,
    )


def content_items(bundle: BundleModel) -> tuple[BundleItem, ...]:
    reserved = {path.casefold() for path in START_DOCUMENT_PATHS}
    selected: list[BundleItem] = []

    for item in bundle.items:
        if (
            bundle.command is BundleCommand.START
            and item.origin is BundleOrigin.GENERATED
            and item.relative_path.casefold() in reserved
        ):
            continue

        selected.append(item)

    return tuple(selected)


def rendered_content_items(bundle: BundleModel) -> tuple[RenderedItem, ...]:
    rendered = tuple(render_bundle_item(item) for item in content_items(bundle))
    return tuple(sorted(rendered, key=_rendered_item_sort_key))


def build_output_documents(bundle: BundleModel) -> OutputDocuments:
    start_documents: tuple[tuple[str, str], ...] = ()

    if bundle.command is BundleCommand.START:
        start_documents = _extract_start_documents(bundle)
        skipped = dict(start_documents)["SKIPPED.md"]
        diff_index = None
    elif bundle.command is BundleCommand.REVIEW:
        skipped = render_review_skipped(bundle)
        diff_index = render_diff_index(bundle)
    else:
        raise OutputAdapterError(
            f"unsupported bundle command: {bundle.command.value}"
        )

    return OutputDocuments(
        start_documents=start_documents,
        skipped=skipped,
        manifest=render_manifest_csv(bundle),
        diff_index=diff_index,
    )


def render_index(
    bundle: BundleModel,
    context: OutputContext,
    *,
    output_files: Iterable[str],
    document_files: Iterable[str],
    part_files: Iterable[str],
) -> str:
    outputs = tuple(output_files)
    documents = tuple(document_files)
    parts = tuple(part_files)
    lines = [
        "# INDEX",
        "",
        "## Meta",
        "",
        f"- DocSet: `{context.docset}`",
        f"- GeneratedAt(JST): `{context.generated_at_jst}`",
        f"- Command: `{bundle.command.value}`",
        f"- Target: `{context.target.value}`",
        f"- Profile: `{bundle.profile_name}`",
        f"- BundleLabel: `{context.bundle_label(bundle)}`",
        f"- RepoRoot: `{context.repo_root}`",
        "",
        "## Stats",
        "",
        f"- Included items: {bundle.included_count}",
        f"- Skipped items: {bundle.skipped_count}",
        f"- Target paths: {len(bundle.target_paths)}",
        f"- Part files: {len(parts)}",
        "",
        "## Output Files",
        "",
    ]
    lines.extend(_render_path_list(outputs))
    lines.extend(["", "## Bundle Documents", ""])
    lines.extend(_render_path_list(documents))
    lines.extend(["", "## Part Files", ""])
    lines.extend(_render_path_list(parts))

    if bundle.target_paths:
        lines.extend(["", "## Review Target Paths", ""])
        lines.extend(_render_path_list(bundle.target_paths))

    return "\n".join(lines) + "\n"


def render_review_skipped(bundle: BundleModel) -> str:
    if bundle.command is not BundleCommand.REVIEW:
        raise OutputAdapterError(
            "review skipped document requires command=review"
        )

    skipped = tuple(sorted(bundle.skipped_items, key=_skipped_sort_key))
    lines = [
        "# SKIPPED",
        "",
        f"- Profile: `{bundle.profile_name}`",
        f"- Count: {len(skipped)}",
        "",
    ]

    if not skipped:
        lines.append("(none)")
        return "\n".join(lines) + "\n"

    for index, item in enumerate(skipped, start=1):
        lines.extend(
            [
                f"{index}. Status: `{item.status.value}`",
                f"   - Origin: `{item.origin.value}`",
                f"   - Requested: `{item.requested_path}`",
            ]
        )

        if item.relative_path is not None:
            lines.append(
                f"   - Relative path: `{item.relative_path}`"
            )

        lines.append(f"   - Reason: {_inline_text(item.reason)}")

    return "\n".join(lines) + "\n"


def render_diff_index(bundle: BundleModel) -> str:
    if bundle.command is not BundleCommand.REVIEW:
        raise OutputAdapterError(
            "diff index requires command=review"
        )

    items = tuple(sorted(bundle.items, key=_bundle_item_output_key))
    counts = {
        origin: sum(1 for item in items if item.origin is origin)
        for origin in (
            BundleOrigin.STAGED,
            BundleOrigin.UNSTAGED,
            BundleOrigin.UNTRACKED,
        )
    }
    lines = [
        "# DIFF_INDEX",
        "",
        f"- Profile: `{bundle.profile_name}`",
        f"- Target paths: {len(bundle.target_paths)}",
        f"- Staged: {counts[BundleOrigin.STAGED]}",
        f"- Unstaged: {counts[BundleOrigin.UNSTAGED]}",
        f"- Untracked: {counts[BundleOrigin.UNTRACKED]}",
        "",
        "## Items",
        "",
    ]

    if not items:
        lines.append("(none)")
        return "\n".join(lines) + "\n"

    for index, item in enumerate(items, start=1):
        change = item.git_change.value if item.git_change else "(none)"
        lines.append(
            f"{index}. `{item.relative_path}` "
            f"(`{item.origin.value}`, `{change}`)"
        )

        if item.previous_path is not None:
            lines.append(f"   - Previous: `{item.previous_path}`")

    return "\n".join(lines) + "\n"


def render_markdown_csv(title: str, content: str) -> str:
    fence = safe_fence(content)
    body = content

    if body and not body.endswith("\n"):
        body += "\n"

    return f"# {title}\n\n{fence}csv\n{body}{fence}\n"


def validate_no_placeholders(texts: Iterable[str]) -> None:
    for text in texts:
        for marker in _PLACEHOLDER_MARKERS:
            if marker in text:
                raise OutputAdapterError(
                    f"unresolved placeholder remains: {marker}"
                )


@contextmanager
def atomic_bundle_directory(
    context: OutputContext,
    bundle: BundleModel,
) -> Iterator[tuple[Path, Path, str]]:
    label = context.bundle_label(bundle)
    context.output_root.mkdir(parents=True, exist_ok=True)
    final_directory = context.output_root / label

    if final_directory.exists() or final_directory.is_symlink():
        raise OutputAdapterError(
            f"output already exists: {final_directory}"
        )

    temp_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{label}.tmp-",
            dir=context.output_root,
        )
    )

    try:
        yield temp_directory, final_directory, label
        temp_directory.rename(final_directory)
    except Exception:
        shutil.rmtree(temp_directory, ignore_errors=True)
        raise


def exceeds_part_limit(
    content: str,
    *,
    max_chars: int,
    max_bytes: int | None,
) -> bool:
    if len(content) > max_chars:
        return True

    return (
        max_bytes is not None
        and len(content.encode("utf-8")) > max_bytes
    )


def _extract_start_documents(
    bundle: BundleModel,
) -> tuple[tuple[str, str], ...]:
    expected = {path.casefold(): path for path in START_DOCUMENT_PATHS}
    found: dict[str, BundleItem] = {}

    for item in bundle.items:
        folded = item.relative_path.casefold()

        if folded not in expected:
            continue

        if item.origin is not BundleOrigin.GENERATED:
            raise OutputAdapterError(
                "start document path is not generated: "
                f"{item.relative_path}"
            )

        if item.content_kind is not ContentKind.TEXT:
            raise OutputAdapterError(
                "start documents must contain text content"
            )

        if folded in found:
            raise OutputAdapterError(
                f"duplicate start document: {item.relative_path}"
            )

        found[folded] = item

    missing = [
        path
        for path in START_DOCUMENT_PATHS
        if path.casefold() not in found
    ]

    if missing:
        raise OutputAdapterError(
            "start bundle is missing generated documents: "
            + ", ".join(missing)
        )

    return tuple(
        (path, found[path.casefold()].content)
        for path in START_DOCUMENT_PATHS
    )


def _rendered_item_sort_key(
    rendered: RenderedItem,
) -> tuple[int, str, str, int, str, str]:
    item = rendered.item
    return (
        _GROUP_ORDER[rendered.group],
        item.relative_path.casefold(),
        item.relative_path,
        _ORIGIN_ORDER[item.origin],
        (item.previous_path or "").casefold(),
        item.previous_path or "",
    )


def _bundle_item_output_key(
    item: BundleItem,
) -> tuple[str, str, int, str, str]:
    return (
        item.relative_path.casefold(),
        item.relative_path,
        _ORIGIN_ORDER[item.origin],
        (item.previous_path or "").casefold(),
        item.previous_path or "",
    )


def _skipped_sort_key(
    item: SkippedItem,
) -> tuple[str, str, int, str, str, str]:
    return (
        item.requested_path.casefold(),
        item.requested_path,
        _ORIGIN_ORDER[item.origin],
        item.status.value,
        (item.relative_path or "").casefold(),
        item.relative_path or "",
    )


def _render_path_list(paths: Iterable[str]) -> list[str]:
    values = tuple(paths)

    if not values:
        return ["- (none)"]

    return [f"- `{path}`" for path in values]


def _inline_text(value: str) -> str:
    return " ".join(value.splitlines())
