#!/usr/bin/env python3
"""
consult_bundle_chatgpt.py
- ChatGPT相談用スナップショット/差分バンドル生成（仕様 v1.6.2 準拠）
- Python port of make_consult_bundle.ps1 (ChatGPT版)
- Updated: 2026-06-07

Description:
  This script generates a consultation bundle for ChatGPT based on a local Git repository.
  It supports four modes: lightweight map, full repository snapshot, partial snapshot (include), and diff.
  The output is organized into parts with size limits, and includes an INDEX.md, TREE.md,
  MANIFEST.csv, and part files under a _bundle/ work directory, then compressed into a ZIP file.
  Output layout: <outRoot>/<BundleLabel>/<BundleLabel>.zip

Usage examples:

  # Mode D: map（本文なし軽量地図）
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode map --repo-root /path/to/repo

  # Mode C: repo（全体横断スナップショット）
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode repo --repo-root /path/to/repo

  # 設定ファイルを明示する例（未指定時は ai-consult-tools/local/chatgpt/consult.config_chatgpt.json →
  #   .consult/consult.config.json の順に自動探索）
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode repo --repo-root /path/to/repo \\
      --config-path .consult/consult.config.json

  # Mode A: include（範囲指定スナップショット）
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode include --repo-root /path/to/repo \\
      --include-paths common admin db/schema

  # ファイル名のみ指定
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode include --repo-root /path/to/repo \\
      --include-paths Navigation.php Loader.php

  # Mode B: diff（差分バンドル）
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode diff --repo-root /path/to/repo

  # staged 差分
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode diff --repo-root /path/to/repo --staged

  # ref 間差分
  python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode diff --repo-root /path/to/repo \\
      --diff-base HEAD~1 --diff-target HEAD
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
JST = timezone(timedelta(hours=9))

DEFAULT_CONFIG_REL_CANDIDATES = [
    "ai-consult-tools/local/chatgpt/consult.config_chatgpt.json",
    ".consult/consult.config.json",
]

GROUP_MAP: dict[str, list[str]] = {
    "php":    [".php", ".phtml", ".inc"],
    "ts":     [".ts", ".tsx"],
    "js":     [".js", ".mjs", ".cjs"],
    "sql":    [".sql"],
    "styles": [".css", ".scss", ".sass", ".less"],
    "docs":   [".md", ".txt"],
    "config": [".json", ".yml", ".yaml", ".ini", ".conf", ".htaccess"],
}

DOCSET_FOLDER_RE = re.compile(
    r"^\d{14}(_repo|_include|_diff|_map)?(_[A-Za-z0-9._-]+)?$"
)

MAP_SUPPORTED_EXTS = {".md", ".ps1", ".php", ".ts", ".tsx", ".js", ".jsx", ".scss", ".css"}

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def get_jst_now() -> datetime:
    return datetime.now(tz=JST)

def fmt_jst(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")

def file_mtime_jst(path: Path) -> str:
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone(JST)
    return fmt_jst(dt)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_full(path: str | Path) -> Path:
    return Path(os.path.realpath(path))

def to_relative(base: Path, target: Path) -> str:
    """Return relative path from base to target using forward slashes."""
    try:
        rel = target.relative_to(base)
        return str(rel).replace("\\", "/")
    except ValueError:
        return str(os.path.relpath(target, base)).replace("\\", "/")

def normalize_sep(p: str) -> str:
    return p.replace("\\", "/")

# ---------------------------------------------------------------------------
# SHA256
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def get_group(rel_path: str) -> str:
    lower = rel_path.lower()
    name = os.path.basename(lower)
    if name == ".htaccess":
        return "config"
    ext = os.path.splitext(lower)[1]
    for group, exts in GROUP_MAP.items():
        if ext in exts:
            return group
    return "misc"

def get_code_fence_lang(rel_path: str, group: str) -> str:
    lower = rel_path.lower()
    mapping = {
        "php": "php", "ts": "ts", "js": "js",
        "sql": "sql", "styles": "css",
    }
    if group in mapping:
        return mapping[group]
    if group == "config":
        if lower.endswith(".json"):
            return "json"
        if lower.endswith((".yml", ".yaml")):
            return "yaml"
        if lower.endswith(".ini"):
            return "ini"
    return ""

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

class ConsultConfig:
    def __init__(self):
        self.out_root_rel: str = ""
        self.rule_file_rel: str = ""
        self.excluded_folders: list[str] = []
        self.excluded_extensions: list[str] = []
        self.excluded_name_patterns: list[str] = []
        self.secret_name_patterns: list[str] = []
        self.allowed_tool_include_files: list[str] = []
        self.config_path_full: str = ""
        self.applied: bool = False


def _to_str_list(value, setting_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    raise ValueError(f"Invalid config value: {setting_name} must be a string or array of strings.")


def _normalize_path_list(items: list[str]) -> list[str]:
    return [normalize_sep(s.strip()) for s in items if s.strip()]


def _normalize_ext_list(items: list[str]) -> list[str]:
    result = []
    for s in items:
        s = s.strip().lower()
        if not s:
            continue
        if not s.startswith("."):
            s = "." + s
        result.append(s)
    return result


def _unique_strings(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for item in lst:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def _resolve_repo_relative_config_path(repo_full: Path, path_value: str, setting_name: str) -> str:
    if not path_value or not path_value.strip():
        raise ValueError(f"Invalid config value: {setting_name} must not be empty.")
    candidate = path_value.strip()
    if os.path.isabs(candidate):
        full = resolve_full(candidate)
    else:
        full = resolve_full(repo_full / candidate)

    repo_norm = str(repo_full).rstrip("/\\") + os.sep
    full_norm = str(full).rstrip("/\\") + os.sep
    if not full_norm.lower().startswith(repo_norm.lower()):
        raise ValueError(f"Invalid config value: {setting_name} must resolve under RepoRoot. Value: {path_value}")
    return to_relative(repo_full, full)


def resolve_consult_config_path(repo_full: Path, config_path: str) -> Path:
    if config_path and config_path.strip():
        candidate = config_path.strip()
        if os.path.isabs(candidate):
            full = Path(candidate)
        else:
            full = resolve_full(repo_full / candidate)
        if not full.is_file():
            raise FileNotFoundError(f"ConfigPath not found: {full}")
        return full

    for rel in DEFAULT_CONFIG_REL_CANDIDATES:
        candidate = resolve_full(repo_full / rel)
        if candidate.is_file():
            return candidate

    candidates_text = ", ".join(DEFAULT_CONFIG_REL_CANDIDATES)
    print("", file=sys.stderr)
    print("エラー: consult.config.json が見つかりません。", file=sys.stderr)
    print("", file=sys.stderr)
    print("以下のいずれかを実行してください：", file=sys.stderr)
    print("  1. consult.config.example.json をコピーして consult.config.json を作成する", file=sys.stderr)
    print("     例: cp ai-consult-tools/chatgpt/consult.config.example_chatgpt.json ai-consult-tools/local/chatgpt/consult.config_chatgpt.json", file=sys.stderr)
    print("  2. --config-path オプションで設定ファイルのパスを明示する", file=sys.stderr)
    print(f"     例: --config-path \"ai-consult-tools/local/chatgpt/consult.config_chatgpt.json\"", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"探索したパス: {candidates_text}", file=sys.stderr)
    print("", file=sys.stderr)
    raise FileNotFoundError(f"consult config not found. Specify --config-path or create one of: {candidates_text}.")


def apply_consult_config(repo_full: Path, config_path: str) -> ConsultConfig:
    cfg = ConsultConfig()
    full = resolve_consult_config_path(repo_full, config_path)
    with open(full, encoding="utf-8") as f:
        data = json.load(f)

    required = ["outRoot", "ruleFile", "excludeFolders", "excludeExtensions",
                "excludeNamePatterns", "secretNamePatterns", "allowedToolIncludeFiles"]
    for key in required:
        if key not in data:
            raise ValueError(f"Invalid consult config: required property is missing: {key}")

    cfg.out_root_rel = _resolve_repo_relative_config_path(repo_full, str(data["outRoot"]), "outRoot")
    cfg.rule_file_rel = _resolve_repo_relative_config_path(repo_full, str(data["ruleFile"]), "ruleFile")
    cfg.excluded_folders = _normalize_path_list(_to_str_list(data["excludeFolders"], "excludeFolders"))
    cfg.excluded_extensions = _normalize_ext_list(_to_str_list(data["excludeExtensions"], "excludeExtensions"))
    cfg.excluded_name_patterns = _to_str_list(data["excludeNamePatterns"], "excludeNamePatterns")
    cfg.secret_name_patterns = _to_str_list(data["secretNamePatterns"], "secretNamePatterns")
    allowed = _normalize_path_list(_to_str_list(data["allowedToolIncludeFiles"], "allowedToolIncludeFiles"))

    cfg.allowed_tool_include_files = _unique_strings(allowed, [cfg.rule_file_rel])
    cfg.excluded_folders = _unique_strings(cfg.excluded_folders, [cfg.out_root_rel])
    cfg.config_path_full = str(full)
    cfg.applied = True
    return cfg

# ---------------------------------------------------------------------------
# Exclusion filters
# ---------------------------------------------------------------------------

class Filters:
    def __init__(self, cfg: ConsultConfig, repo_full: Path):
        self.cfg = cfg
        self.repo_full = repo_full

    def is_allowed_tool_include_file(self, file_full: Path) -> bool:
        rel = normalize_sep(to_relative(self.repo_full, file_full))
        return any(rel.lower() == f.lower() for f in self.cfg.allowed_tool_include_files)

    def is_excluded_by_folder(self, file_full: Path) -> bool:
        rel = normalize_sep(to_relative(self.repo_full, file_full))
        segments = [s for s in rel.split("/") if s]

        # hardcoded: shared フォルダ除外
        if segments and segments[0].lower() == "shared":
            return True
        if rel.lower() == "shared" or rel.lower().startswith("shared/"):
            return True

        for rule in self.cfg.excluded_folders:
            rule = normalize_sep(rule).rstrip("/")
            if not rule:
                continue
            if "/" not in rule:
                # フォルダ名のみ: セグメントに含まれるか
                if rule.lower() in [s.lower() for s in segments]:
                    return True
            else:
                if rel.lower() == rule.lower():
                    return True
                if rel.lower().startswith(rule.lower() + "/"):
                    return True
        return False

    def is_excluded_by_extension(self, file_full: Path) -> bool:
        ext = file_full.suffix.lower()
        if not ext:
            return False
        return ext in self.cfg.excluded_extensions

    def is_excluded_by_secret_pattern(self, file_full: Path) -> bool:
        name = file_full.name
        return any(_fnmatch(name, pat) for pat in self.cfg.secret_name_patterns)

    def is_excluded_by_name_pattern(self, file_full: Path) -> bool:
        name = file_full.name
        return any(_fnmatch(name, pat) for pat in self.cfg.excluded_name_patterns)

    def is_includable(self, file_full: Path) -> bool:
        if not file_full.is_file():
            return False
        allowed_tool = self.is_allowed_tool_include_file(file_full)
        if not allowed_tool and self.is_excluded_by_folder(file_full):
            return False
        if self.is_excluded_by_extension(file_full):
            return False
        if self.is_excluded_by_secret_pattern(file_full):
            return False
        if self.is_excluded_by_name_pattern(file_full):
            return False
        return True


def _fnmatch(name: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(name.lower(), pattern.lower())

# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def read_text_file_safe(path: Path) -> str:
    data = path.read_bytes()
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")

# ---------------------------------------------------------------------------
# DocSet folder check
# ---------------------------------------------------------------------------

def contains_docset_folder(repo_full: Path, file_full: Path) -> bool:
    rel = to_relative(repo_full, file_full)
    for seg in rel.replace("\\", "/").split("/"):
        if DOCSET_FOLDER_RE.match(seg):
            return True
    return False

# ---------------------------------------------------------------------------
# File block builder (snapshot)
# ---------------------------------------------------------------------------

def build_file_block(
    repo_full: Path,
    file_full: Path,
    group: str,
    max_chars_per_file: int,
) -> dict:
    rel = to_relative(repo_full, file_full)
    stat = file_full.stat()
    bytes_size = stat.st_size
    lwt_jst = file_mtime_jst(file_full)
    file_hash = sha256_file(file_full)

    content = read_text_file_safe(file_full)
    is_truncated = False
    trunc_note = ""

    if len(content) > max_chars_per_file:
        is_truncated = True
        head_len = int(max_chars_per_file * 0.6)
        tail_len = max_chars_per_file - head_len
        head = content[:head_len]
        tail = content[len(content) - tail_len:]
        trunc_note = f"\n[TRUNCATED] OriginalChars={len(content)} KeptChars={max_chars_per_file}\n"
        content = head + "\n... (snip) ...\n" + tail

    lang = get_code_fence_lang(rel, group)
    fence = "```"

    lines = [
        "--- BEGIN FILE ---",
        f"Path: {rel}",
        f"Bytes: {bytes_size}",
        f"LastWriteTime(JST): {lwt_jst}",
        f"SHA256: {file_hash}",
        f"Group: {group}",
        "--- CONTENT ---",
        fence + lang,
    ]
    if is_truncated and trunc_note:
        lines.append(trunc_note.strip())
    lines.append(content.rstrip("\r\n"))
    lines.append(fence)
    lines.append("--- END FILE ---")
    lines.append("")

    return {
        "relative_path": rel,
        "bytes": bytes_size,
        "last_write_time_jst": lwt_jst,
        "sha256": file_hash,
        "group": group,
        "block_text": "\n".join(lines) + "\n",
        "is_truncated": is_truncated,
    }

# ---------------------------------------------------------------------------
# Map block builder
# ---------------------------------------------------------------------------

def _limit_map_lines(lines: list[str], max_count: int = 80) -> list[str]:
    items = [l for l in lines if l.strip()]
    if len(items) <= max_count:
        return items
    return items[:max_count] + [f"- ... (truncated: {len(items) - max_count} more)"]


def get_map_text_lines(file_full: Path) -> list[str]:
    ext = file_full.suffix.lower()
    if ext not in MAP_SUPPORTED_EXTS:
        return []
    try:
        content = read_text_file_safe(file_full)
    except Exception as e:
        return [f"- [read-skip] {e}"]

    if not content:
        return []

    lines: list[str] = []

    if ext == ".md":
        for m in re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", content):
            level = len(m.group(1))
            title = m.group(2).strip()
            lines.append(f"- H{level}: {title}")

    elif ext == ".ps1":
        for m in re.finditer(r"(?m)^\s*(?:\[[^\]]+\]\s*)?\$([A-Za-z_][A-Za-z0-9_]*)\b", content):
            lines.append(f"- param: {m.group(1)}")
        for m in re.finditer(r"(?m)^\s*function\s+([A-Za-z_][A-Za-z0-9_-]*)\b", content):
            lines.append(f"- function: {m.group(1)}")

    elif ext == ".php":
        for m in re.finditer(r"(?m)^\s*(?:final\s+|abstract\s+)?(class|interface|trait)\s+([A-Za-z_][A-Za-z0-9_]*)\b", content):
            lines.append(f"- {m.group(1)}: {m.group(2)}")
        for m in re.finditer(r"(?m)^\s*(?:(?:public|protected|private)\s+)?(?:static\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\b", content):
            lines.append(f"- function: {m.group(1)}")

    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        for m in re.finditer(r"""(?m)^\s*import\s+.*?\s+from\s+['"]([^'"]+)['"]""", content):
            lines.append(f"- import from: {m.group(1)}")
        for m in re.finditer(r"(?m)^\s*export\s+(?:default\s+)?(?:abstract\s+)?(class|function|const|let|var|interface|type|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b", content):
            lines.append(f"- export {m.group(1)}: {m.group(2)}")

    elif ext in {".scss", ".css"}:
        for m in re.finditer(r"(?m)^\s*([^\r\n{};@/$][^\r\n{};]*?)\s*\{\s*$", content):
            selector = m.group(1).strip()
            if selector:
                lines.append(f"- selector: {selector}")

    return _limit_map_lines(lines)


def build_map_file_block(repo_full: Path, file_full: Path, group: str) -> dict:
    rel = to_relative(repo_full, file_full)
    stat = file_full.stat()
    bytes_size = stat.st_size
    lwt_jst = file_mtime_jst(file_full)
    file_hash = sha256_file(file_full)
    map_lines = get_map_text_lines(file_full)
    if not map_lines:
        map_lines = ["- (no supported headings/symbols detected)"]

    lines = [
        "--- BEGIN MAP FILE ---",
        f"Path: {rel}",
        f"Bytes: {bytes_size}",
        f"LastWriteTime(JST): {lwt_jst}",
        f"SHA256: {file_hash}",
        f"Group: {group}",
        f"IncludePathsCandidate: {rel}",
        "--- MAP ---",
        "※ mapは本文なしの軽量地図です。具体diff作成の一次根拠にはしないでください。",
        "",
    ] + map_lines + [
        "--- END MAP FILE ---",
        "",
    ]

    return {
        "relative_path": rel,
        "bytes": bytes_size,
        "last_write_time_jst": lwt_jst,
        "sha256": file_hash,
        "group": group,
        "block_text": "\n".join(lines) + "\n",
    }

# ---------------------------------------------------------------------------
# Tree builder
# ---------------------------------------------------------------------------

def build_included_tree_lines(relative_paths: list[str]) -> list[str]:
    root: dict = {}

    for rp in relative_paths:
        parts = [p for p in rp.replace("\\", "/").split("/") if p]
        node = root
        for i, name in enumerate(parts):
            if i == len(parts) - 1:
                node.setdefault("__files__", []).append(name)
            else:
                node = node.setdefault(name, {})

    result: list[str] = []

    def walk(node: dict, prefix: str):
        dir_keys = sorted(k for k in node if k != "__files__")
        for dk in dir_keys:
            result.append(f"{prefix}- {dk}/")
            walk(node[dk], prefix + "  ")
        for fname in sorted(node.get("__files__", [])):
            result.append(f"{prefix}- {fname}")

    walk(root, "")
    return result

# ---------------------------------------------------------------------------
# CSV field helper
# ---------------------------------------------------------------------------

def csv_field(s: str | None) -> str:
    if s is None:
        return ""
    if any(c in s for c in ['"', ",", "\n", "\r"]):
        return '"' + s.replace('"', '""') + '"'
    return s

# ---------------------------------------------------------------------------
# Part state (per-group part file writer)
# ---------------------------------------------------------------------------

class PartState:
    def __init__(self, parts_dir: Path, prefix: str, group: str, part_no: int):
        name = f"{prefix}_{group}_part_{part_no:03d}.md"
        self.path = parts_dir / name
        self.name = name
        self.part_no = part_no
        self._file = open(self.path, "w", encoding="utf-8", newline="")
        self.bytes_written = 0
        self.chars_written = 0
        self.items = 0

    def write(self, text: str):
        self._file.write(text)
        self.chars_written += len(text)
        self.bytes_written += len(text.encode("utf-8"))

    def close(self):
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None

# ---------------------------------------------------------------------------
# INDEX.md builder
# ---------------------------------------------------------------------------

def write_index_md(
    index_path: Path,
    stats: dict,
    part_files_out: list[str],
    extra_section: str,
    *,
    docset: str,
    bundle_label: str,
    generated_at: str,
    repo_root_full: Path,
    out_root_full: Path,
    rule_file_full: Path,
    cfg: ConsultConfig,
    mode: str,
    case_name: str,
    max_bytes_per_part: int,
    max_chars_per_part: int,
    max_chars_per_file: int,
    cmd_line: str,
):
    ex_folders = ", ".join(sorted(cfg.excluded_folders))
    ex_exts = ", ".join(sorted(cfg.excluded_extensions))
    sec_pats = ", ".join(sorted(cfg.secret_name_patterns))
    ex_names = ", ".join(sorted(cfg.excluded_name_patterns))

    groups_lines = []
    for k in sorted(GROUP_MAP):
        groups_lines.append(f"- {k}: {' '.join(sorted(GROUP_MAP[k]))}")
    groups_lines.append("- misc: (other)")

    parts_lines = "\n".join(f"- {f}" for f in sorted(part_files_out))

    case_meta = f"- CaseName: {case_name}\n" if case_name.strip() else ""

    if cfg.applied:
        config_meta = f"- ConfigPath: {cfg.config_path_full}\n- ConfigApplied: true\n"
    else:
        config_meta = "- ConfigPath: (default)\n- ConfigApplied: false\n"

    stats_groups_block = ""
    if stats.get("groups_text"):
        stats_groups_block = "\n".join(f"  {l}" for l in stats["groups_text"].split("\n"))

    content = f"""## 参照確定（唯一の正）

- 唯一の正：{bundle_label}.zip
- DocSet: {docset}
- Mode: {mode}
- 運用ルール：00_ai_consult_operation_rules.md に従ってください

---

# INDEX (DocSet={docset})

このDocSetの生成物のみを唯一の正とし、それ以外の古いファイルは参照しないこと。
生成条件（除外/対象/モード/コマンドライン）を根拠とすること。

---

## Meta

- DocSet: {docset}
- BundleLabel: {bundle_label}
{case_meta}- GeneratedAt(JST): {generated_at}
- RepoRoot: {repo_root_full}
- OutRoot: {out_root_full}
- RuleFile: {rule_file_full}
{config_meta}- Mode: {mode}
- CommandLine: {cmd_line}

---

## Limits

- MaxBytesPerPart: {max_bytes_per_part}
- MaxCharsPerPart: {max_chars_per_part}
- MaxCharsPerFile: {max_chars_per_file}

---

## Exclusions

### Excluded Folders

- {ex_folders}

### Excluded Extensions

- {ex_exts}

### Excluded Name Patterns (minified etc.)

- {ex_names}


### Secret Patterns (excluded)

- {sec_pats}

---

## Grouping

{chr(10).join(groups_lines)}

---

## Stats

- IncludedFiles: {stats.get('included_files', 0)}
- SkippedFiles: {stats.get('skipped_files', 0)}
- IncludedBytesTotal: {stats.get('included_bytes_total', 0)}
- Groups:
{stats_groups_block}

---

## Output Parts

{parts_lines}

{extra_section}
"""
    index_path.write_text(content, encoding="utf-8")


def write_tree_md(tree_path: Path, tree_lines: list[str], docset: str, mode: str):
    if mode == "map":
        description = "map対象ファイルのみのツリー。本文は含めず、include束候補選定用の地図として扱う。"
    else:
        description = "今回「含めたファイルのみ」のツリー。"

    content = f"""# TREE (DocSet={docset})

{description}

---

{chr(10).join(tree_lines)}
"""
    tree_path.write_text(content, encoding="utf-8")


def write_manifest_csv(manifest_path: Path, rows: list[dict]):
    lines = [
        "relative_path,bytes,last_write_time_jst,sha256,group,part_file,is_truncated,mode,docset,repo_root,is_deleted"
    ]
    for r in rows:
        if r is None:
            continue
        line = ",".join([
            csv_field(r.get("relative_path", "")),
            str(r.get("bytes", 0)),
            csv_field(r.get("last_write_time_jst", "")),
            csv_field(r.get("sha256", "")),
            csv_field(r.get("group", "")),
            csv_field(r.get("part_file", "")),
            str(r.get("is_truncated", False)).lower(),
            csv_field(r.get("mode", "")),
            csv_field(r.get("docset", "")),
            csv_field(r.get("repo_root", "")),
            str(r.get("is_deleted", False)).lower(),
        ])
        lines.append(line)
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_skipped_txt(skipped_path: Path, skipped: list[str], docset: str):
    if skipped:
        content = f"# SKIPPED (DocSet={docset})\n\n" + "\n".join(skipped)
    else:
        content = f"# SKIPPED (DocSet={docset})\n\n(none)"
    skipped_path.write_text(content, encoding="utf-8")

# ---------------------------------------------------------------------------
# ZIP creator
# ---------------------------------------------------------------------------

def create_zip(work_dir: Path, case_dir: Path, bundle_label: str) -> Path:
    """Compress work_dir contents into <bundle_label>.zip under case_dir."""
    zip_path = case_dir / f"{bundle_label}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(work_dir.rglob("*")):
            if item.is_file():
                arcname = item.relative_to(work_dir)
                zf.write(item, arcname)

    if not zip_path.is_file():
        raise RuntimeError(f"ZIP not found after compression: {zip_path}")
    if zip_path.stat().st_size < 1024:
        raise RuntimeError(f"ZIP too small (unexpected): {zip_path} (size={zip_path.stat().st_size})")

    return zip_path

# ---------------------------------------------------------------------------
# Part file writer helper
# ---------------------------------------------------------------------------

def _make_part_header(prefix: str, docset: str, mode: str, group: str, part_no: int,
                      repo_full: Path, diff_args: list[str] | None = None) -> str:
    if prefix == "diff":
        args_str = " ".join(diff_args) if diff_args else ""
        return (
            f"# DIFF PART (DocSet={docset})\n\n"
            f"- RepoRoot: {repo_full}\n"
            f"- Mode: diff\n"
            f"- DiffArgs: {args_str}\n"
            f"- Group: {group}\n"
            f"- Part: {part_no}\n\n---\n\n"
        )
    elif prefix == "map":
        return (
            f"# MAP PART (DocSet={docset})\n\n"
            f"- RepoRoot: {repo_full}\n"
            f"- Mode: map\n"
            f"- Group: {group}\n"
            f"- Part: {part_no}\n"
            f"- Notice: 本文なしの軽量地図です。具体diff作成はinclude束を一次根拠にしてください。\n\n---\n\n"
        )
    else:
        return (
            f"# SNAPSHOT PART (DocSet={docset})\n\n"
            f"- RepoRoot: {repo_full}\n"
            f"- Mode: {mode}\n"
            f"- Group: {group}\n"
            f"- Part: {part_no}\n\n---\n\n"
        )


def _process_group_parts(
    items_sorted: list[dict],
    parts_dir: Path,
    prefix: str,
    docset: str,
    mode: str,
    repo_full: Path,
    max_bytes_per_part: int,
    max_chars_per_part: int,
    build_block_fn,   # callable(item) -> dict with 'block_text', 'bytes', etc.
    skipped: list[str],
    manifest_rows: list[dict],
    manifest_row_fn,  # callable(item, block, state) -> dict
    diff_args: list[str] | None = None,
) -> list[str]:
    """
    Process a sorted list of items, splitting by group and size limits.
    Returns list of part file summary strings like "name.md (items=N, bytes=M)".
    """
    part_files_out: list[str] = []
    current_group = None
    state: PartState | None = None
    part_no = 1

    for it in items_sorted:
        if current_group != it["group"]:
            if state:
                state.close()
                part_files_out.append(f"{state.name} (items={state.items}, bytes={state.bytes_written})")
                state = None
            current_group = it["group"]
            part_no = 1
            state = PartState(parts_dir, prefix, current_group, part_no)
            header = _make_part_header(prefix, docset, mode, current_group, part_no, repo_full, diff_args)
            state.write(header)

        # Build block
        try:
            block = build_block_fn(it)
        except Exception as e:
            print(f"Warning: Skip file: {it.get('full', it.get('rel', ''))}\n  {e}", file=sys.stderr)
            skipped.append(f"{it.get('full', it.get('rel', ''))}\t{e}")
            continue

        text = block["block_text"]
        b = len(text.encode("utf-8"))
        would_bytes = state.bytes_written + b
        would_chars = state.chars_written + len(text)

        if state.items > 0 and (would_bytes > max_bytes_per_part or would_chars > max_chars_per_part):
            state.close()
            part_files_out.append(f"{state.name} (items={state.items}, bytes={state.bytes_written})")

            part_no += 1
            state = PartState(parts_dir, prefix, current_group, part_no)
            header = _make_part_header(prefix, docset, mode, current_group, part_no, repo_full, diff_args)
            state.write(header)

        state.write(text)
        state.items += 1

        row = manifest_row_fn(it, block, state)
        if row is not None:
            manifest_rows.append(row)

    if state:
        state.close()
        part_files_out.append(f"{state.name} (items={state.items}, bytes={state.bytes_written})")

    return part_files_out

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def assert_git_available():
    if not shutil.which("git"):
        raise RuntimeError("git not found in PATH. Install Git or add to PATH.")


def invoke_git(repo_full: Path, git_args: list[str]) -> str:
    cmd = ["git", "-c", "core.quotepath=false"] + git_args
    result = subprocess.run(
        cmd,
        cwd=str(repo_full),
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(git_args)} failed (exit={result.returncode})\n{result.stderr}"
        )
    return result.stdout

# ---------------------------------------------------------------------------
# Map git section
# ---------------------------------------------------------------------------

def get_map_git_section(repo_full: Path) -> str:
    try:
        assert_git_available()
        status = invoke_git(repo_full, ["status", "--short"]).strip() or "(clean)"
        log = invoke_git(repo_full, ["log", "--oneline", "-5"]).strip() or "(none)"
        return (
            f"---\n\n## Git Status\n\n```text\n{status}\n```\n\n"
            f"---\n\n## Git Log\n\n```text\n{log}\n```\n"
        )
    except Exception as e:
        return f"---\n\n## Git Info\n\n```text\n[git-info-unavailable] {e}\n```\n"

# ---------------------------------------------------------------------------
# Command line formatter
# ---------------------------------------------------------------------------

def format_command_line(args: argparse.Namespace, cfg: ConsultConfig, repo_root_full: Path) -> str:
    script = os.path.abspath(sys.argv[0])
    parts = [f'python "{script}"', f"--mode {args.mode}", f'--repo-root "{repo_root_full}"']
    if args.mode == "include" and args.include_paths:
        for ip in args.include_paths:
            parts.append(f'--include-paths "{ip}"')
    if cfg.applied:
        parts.append(f'--config-path "{cfg.config_path_full}"')
    if args.allow_docset_folders:
        parts.append("--allow-docset-folders")
    if args.keep_bundle_dir:
        parts.append("--keep-bundle-dir")
    if args.case_name:
        parts.append(f'--case-name "{args.case_name}"')
    if args.max_bytes_per_part != 536870912:
        parts.append(f"--max-bytes-per-part {args.max_bytes_per_part}")
    if args.max_chars_per_part != 300000:
        parts.append(f"--max-chars-per-part {args.max_chars_per_part}")
    if args.max_chars_per_file != 300000:
        parts.append(f"--max-chars-per-file {args.max_chars_per_file}")
    if args.mode == "diff":
        if args.staged:
            parts.append("--staged")
        if args.unstaged_only:
            parts.append("--unstaged-only")
        if args.diff_base:
            parts.append(f"--diff-base {args.diff_base}")
        if args.diff_target:
            parts.append(f"--diff-target {args.diff_target}")
    return " ".join(parts)

# ---------------------------------------------------------------------------
# Include path resolver
# ---------------------------------------------------------------------------

def resolve_include_targets(
    repo_full: Path,
    include_paths: list[str],
    filters: Filters,
    allow_docset_folders: bool,
) -> list[Path]:
    if not include_paths:
        raise ValueError("include_paths is required for mode=include")

    targets: list[Path] = []
    skipped: list[str] = []

    for raw in include_paths:
        spec = raw.strip()
        if not spec:
            continue

        if any(c in spec for c in ["*", "?", "["]):
            raise ValueError(f"Wildcards are not supported in v1.4.5 include specs: {spec}")

        spec_is_no_sep = not os.path.isabs(spec) and "/" not in spec and "\\" not in spec
        candidate_path = Path(spec) if os.path.isabs(spec) else repo_full / spec
        exists_as_path = candidate_path.exists()

        is_file_name_only = spec_is_no_sep and not exists_as_path

        if is_file_name_only:
            # Search by folder name
            dir_hits = [
                d for d in repo_full.rglob(spec)
                if d.is_dir()
                and (allow_docset_folders or not contains_docset_folder(repo_full, d))
            ]
            dir_filtered = []
            for d in dir_hits:
                has_any = any(
                    True for f in d.rglob("*")
                    if f.is_file()
                    and (allow_docset_folders or not contains_docset_folder(repo_full, f))
                    and filters.is_includable(f)
                )
                if has_any:
                    dir_filtered.append(d)

            if len(dir_filtered) > 1:
                rels = sorted(to_relative(repo_full, d) for d in dir_filtered)
                raise ValueError(
                    f"IncludeFolderName is ambiguous (multiple matches). Use explicit path.\n"
                    f"Name: {spec}\nMatches:\n - " + "\n - ".join(rels)
                )
            if len(dir_filtered) == 1:
                for f in dir_filtered[0].rglob("*"):
                    if not f.is_file():
                        continue
                    if not allow_docset_folders and contains_docset_folder(repo_full, f):
                        continue
                    if filters.is_includable(f):
                        targets.append(f)
                continue

            # Search by file name
            file_hits = [
                f for f in repo_full.rglob(spec)
                if f.is_file()
                and (allow_docset_folders or not contains_docset_folder(repo_full, f))
                and filters.is_includable(f)
            ]
            if not file_hits:
                print(f"Warning: IncludeFileName not found or excluded (skipped): {spec}", file=sys.stderr)
                skipped.append(spec)
                continue
            if len(file_hits) > 1:
                rels = sorted(to_relative(repo_full, f) for f in file_hits)
                raise ValueError(
                    f"IncludeFileName is ambiguous (multiple matches). Use explicit path.\n"
                    f"Name: {spec}\nMatches:\n - " + "\n - ".join(rels)
                )
            targets.append(file_hits[0])
            continue

        # Treat as explicit path
        candidate = Path(spec) if os.path.isabs(spec) else repo_full / spec
        if not candidate.exists():
            print(f"Warning: IncludePath not found (skipped): {spec}", file=sys.stderr)
            skipped.append(spec)
            continue

        full = resolve_full(candidate)
        if full.is_file():
            if not allow_docset_folders and contains_docset_folder(repo_full, full):
                print(f"Warning: IncludePath skipped (DocSet folder): {spec}", file=sys.stderr)
                skipped.append(spec)
                continue
            if not filters.is_includable(full):
                print(f"Warning: IncludePath is excluded by rules (skipped): {spec}", file=sys.stderr)
                skipped.append(spec)
                continue
            targets.append(full)
        elif full.is_dir():
            for f in full.rglob("*"):
                if not f.is_file():
                    continue
                if not allow_docset_folders and contains_docset_folder(repo_full, f):
                    continue
                targets.append(f)

    if not targets:
        raise ValueError(
            f"No valid IncludePaths remained after filtering. Requested: {', '.join(include_paths)}"
        )

    # Deduplicate
    seen: set[Path] = set()
    result: list[Path] = []
    for p in sorted(set(targets)):
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result

# ---------------------------------------------------------------------------
# Map processing
# ---------------------------------------------------------------------------

def invoke_map(
    repo_full: Path,
    filters: Filters,
    work_dir: Path,
    parts_dir: Path,
    case_dir: Path,
    bundle_label: str,
    docset: str,
    generated_at: str,
    out_root_full: Path,
    rule_file_full: Path,
    max_bytes_per_part: int,
    max_chars_per_part: int,
    index_kwargs: dict,
):
    candidate_files = [f for f in repo_full.rglob("*") if f.is_file()]
    included = []
    for f in candidate_files:
        if filters.is_includable(f):
            rel = to_relative(repo_full, f)
            group = get_group(rel)
            included.append({"full": f, "rel": rel, "group": group})

    included_sorted = sorted(included, key=lambda x: (x["group"], x["rel"]))
    manifest_rows: list[dict] = []
    skipped: list[str] = []
    included_bytes_total = 0

    def build_fn(it: dict) -> dict:
        return build_map_file_block(repo_full, it["full"], it["group"])

    def row_fn(it: dict, block: dict, state: PartState) -> dict:
        nonlocal included_bytes_total
        included_bytes_total += block["bytes"]
        return {
            "relative_path": block["relative_path"],
            "bytes": block["bytes"],
            "last_write_time_jst": block["last_write_time_jst"],
            "sha256": block["sha256"],
            "group": it["group"],
            "part_file": state.name,
            "is_truncated": False,
            "mode": "map",
            "docset": docset,
            "repo_root": str(repo_full),
            "is_deleted": False,
        }

    part_files_out = _process_group_parts(
        included_sorted, parts_dir, "map", docset, "map", repo_full,
        max_bytes_per_part, max_chars_per_part,
        build_fn, skipped, manifest_rows, row_fn,
    )

    group_counts: dict[str, int] = {}
    for it in included_sorted:
        group_counts[it["group"]] = group_counts.get(it["group"], 0) + 1
    groups_text = "\n".join(f"- {g}: {c} files" for g, c in sorted(group_counts.items()))

    stats = {
        "included_files": len(included_sorted),
        "skipped_files": len(skipped),
        "included_bytes_total": included_bytes_total,
        "groups_text": groups_text,
    }

    tree_lines = build_included_tree_lines([r["relative_path"] for r in manifest_rows])

    index_path = work_dir / "INDEX.md"
    tree_path = work_dir / "TREE.md"
    manifest_path = work_dir / "MANIFEST.csv"
    skipped_path = work_dir / "SKIPPED.txt"

    map_extra = (
        "---\n\n## Map Mode Notice\n\n"
        "- mapは本文なしの軽量地図です。\n"
        "- include束を作る対象ファイル候補の選定に使ってください。\n"
        "- map束だけを根拠に、具体的なコード差分・仕様差分を作らないでください。\n"
        "- 具体修正は必ずinclude束、反映後確認はdiff束を一次根拠にしてください。\n"
        + get_map_git_section(repo_full)
    )

    write_index_md(
        index_path, stats, part_files_out, map_extra,
        **index_kwargs,
    )
    write_tree_md(tree_path, tree_lines, docset, "map")
    write_manifest_csv(manifest_path, manifest_rows)
    write_skipped_txt(skipped_path, skipped, docset)

# ---------------------------------------------------------------------------
# Snapshot processing (repo / include)
# ---------------------------------------------------------------------------

def invoke_snapshot(
    mode: str,
    repo_full: Path,
    candidate_files: list[Path],
    filters: Filters,
    work_dir: Path,
    parts_dir: Path,
    bundle_label: str,
    docset: str,
    generated_at: str,
    max_bytes_per_part: int,
    max_chars_per_part: int,
    max_chars_per_file: int,
    index_kwargs: dict,
):
    included = []
    for f in candidate_files:
        if filters.is_includable(f):
            rel = to_relative(repo_full, f)
            group = get_group(rel)
            included.append({"full": f, "rel": rel, "group": group})

    included_sorted = sorted(included, key=lambda x: (x["group"], x["rel"]))
    manifest_rows: list[dict] = []
    skipped: list[str] = []
    included_bytes_total = 0

    def build_fn(it: dict) -> dict:
        return build_file_block(repo_full, it["full"], it["group"], max_chars_per_file)

    def row_fn(it: dict, block: dict, state: PartState) -> dict:
        nonlocal included_bytes_total
        included_bytes_total += block["bytes"]
        return {
            "relative_path": block["relative_path"],
            "bytes": block["bytes"],
            "last_write_time_jst": block["last_write_time_jst"],
            "sha256": block["sha256"],
            "group": it["group"],
            "part_file": state.name,
            "is_truncated": block["is_truncated"],
            "mode": mode,
            "docset": docset,
            "repo_root": str(repo_full),
            "is_deleted": False,
        }

    part_files_out = _process_group_parts(
        included_sorted, parts_dir, "snapshot", docset, mode, repo_full,
        max_bytes_per_part, max_chars_per_part,
        build_fn, skipped, manifest_rows, row_fn,
    )

    group_counts: dict[str, int] = {}
    for it in included_sorted:
        group_counts[it["group"]] = group_counts.get(it["group"], 0) + 1
    groups_text = "\n".join(f"- {g}: {c} files" for g, c in sorted(group_counts.items()))

    # Recompute stats from manifest (consistent with PS1)
    included_bytes_total = sum(r["bytes"] for r in manifest_rows)
    stats = {
        "included_files": len(manifest_rows),
        "skipped_files": len(skipped),
        "included_bytes_total": included_bytes_total,
        "groups_text": groups_text,
    }

    tree_lines = build_included_tree_lines([r["relative_path"] for r in manifest_rows])

    index_path = work_dir / "INDEX.md"
    tree_path = work_dir / "TREE.md"
    manifest_path = work_dir / "MANIFEST.csv"
    skipped_path = work_dir / "SKIPPED.txt"

    write_index_md(index_path, stats, part_files_out, "", **index_kwargs)
    write_tree_md(tree_path, tree_lines, docset, mode)
    write_manifest_csv(manifest_path, manifest_rows)
    write_skipped_txt(skipped_path, skipped, docset)

# ---------------------------------------------------------------------------
# Diff processing
# ---------------------------------------------------------------------------

def invoke_diff(
    repo_full: Path,
    filters: Filters,
    work_dir: Path,
    parts_dir: Path,
    case_dir: Path,
    out_root_full: Path,
    bundle_label: str,
    docset: str,
    generated_at: str,
    max_bytes_per_part: int,
    max_chars_per_part: int,
    index_kwargs: dict,
    args: argparse.Namespace,
) -> bool:
    """Returns False if diff=0 (nothing to do), True otherwise."""
    assert_git_available()

    diff_args = ["diff", "--no-color", "--no-ext-diff"]
    diff_scope = None

    if args.unstaged_only:
        if args.staged:
            raise ValueError("Invalid options: --unstaged-only cannot be used with --staged.")
        if args.diff_base or args.diff_target:
            raise ValueError("Invalid options: --unstaged-only cannot be used with --diff-base/--diff-target.")

    if args.staged:
        diff_args.append("--staged")
        diff_scope = "--staged"
    elif args.unstaged_only:
        diff_scope = "index..worktree"
    elif args.diff_base and args.diff_target:
        diff_args += [args.diff_base, args.diff_target]
        diff_scope = "base..target"
    elif args.diff_base:
        diff_args.append(args.diff_base)
        diff_scope = f"{args.diff_base}..worktree"
    else:
        diff_args.append("HEAD")
        diff_scope = "HEAD..worktree"

    name_only_out = invoke_git(repo_full, diff_args + ["--name-only"])
    changed_rel = [
        normalize_sep(line.strip().strip('"'))
        for line in name_only_out.splitlines()
        if line.strip()
    ]

    filtered: list[dict] = []
    skipped: list[str] = []

    for rp in changed_rel:
        full = repo_full / rp
        allowed_tool = filters.is_allowed_tool_include_file(full)

        segments = [s for s in rp.split("/") if s]
        is_excl_folder = any(
            f.lower() in [s.lower() for s in segments]
            for f in filters.cfg.excluded_folders
        )
        if not allowed_tool and is_excl_folder:
            skipped.append(f"[excluded-folder] {rp}")
            continue

        ext = os.path.splitext(rp)[1].lower()
        if ext and ext in filters.cfg.excluded_extensions:
            skipped.append(f"[excluded-ext] {rp}")
            continue

        name = os.path.basename(rp)
        if any(_fnmatch(name, pat) for pat in filters.cfg.excluded_name_patterns):
            skipped.append(f"[excluded-name] {rp}")
            continue
        if any(_fnmatch(name, pat) for pat in filters.cfg.secret_name_patterns):
            skipped.append(f"[secret] {rp}")
            continue

        group = get_group(rp)
        filtered.append({"rel": rp, "full": repo_full / rp, "group": group})

    # Parse deleted + renames
    name_status_out = invoke_git(repo_full, diff_args + ["-M", "--name-status"])
    deleted_files: list[str] = []
    renames: list[dict] = []

    for line in name_status_out.splitlines():
        t = line.strip()
        if not t:
            continue
        parts = t.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].strip()

        if status.startswith("R") and len(parts) >= 3:
            old = normalize_sep(parts[1].strip().strip('"'))
            new = normalize_sep(parts[2].strip().strip('"'))
            renames.append({"status": status, "old": old, "new": new})
            continue

        if status != "D":
            continue

        rp = normalize_sep(parts[1].strip().strip('"'))
        full_del = repo_full / rp

        allowed_tool = filters.is_allowed_tool_include_file(full_del)
        segments = [s for s in rp.split("/") if s]
        is_excl_folder = any(
            f.lower() in [s.lower() for s in segments]
            for f in filters.cfg.excluded_folders
        )
        if not allowed_tool and is_excl_folder:
            continue

        ext = os.path.splitext(rp)[1].lower()
        if ext and ext in filters.cfg.excluded_extensions:
            continue

        name = os.path.basename(rp)
        if any(_fnmatch(name, pat) for pat in filters.cfg.excluded_name_patterns):
            continue
        if any(_fnmatch(name, pat) for pat in filters.cfg.secret_name_patterns):
            continue

        deleted_files.append(rp)

    deleted_set = {d.lower() for d in deleted_files}
    filtered_sorted = sorted(filtered, key=lambda x: (x["group"], x["rel"]))

    # diff=0件なら生成しない
    if not filtered_sorted and not deleted_files:
        print(f"INFO: diff結果=0件（変更/削除ともに0）。生成物は作成しません。({' '.join(diff_args)})")
        # 空フォルダがあれば削除
        try:
            if work_dir.is_dir():
                shutil.rmtree(work_dir)
            if case_dir.is_dir() and not any(case_dir.iterdir()):
                case_dir.rmdir()
        except Exception:
            pass
        return False

    # diff>0件のみ出力先作成
    out_root_full.mkdir(parents=True, exist_ok=True)
    case_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    # 運用ルール文書を同梱
    rule_file_full: Path = index_kwargs["rule_file_full"]
    if rule_file_full.is_file():
        shutil.copy2(rule_file_full, work_dir / "00_ai_consult_operation_rules.md")
    else:
        raise FileNotFoundError(f"Required rule file not found: {rule_file_full}")

    manifest_rows: list[dict] = []
    manifest_path_set: set[str] = set()
    included_bytes_total = 0

    stats_lines = [
        f"- DiffMode: {' '.join(diff_args)}",
        f"- ChangedFiles: {len(filtered_sorted)}",
    ]

    def build_fn(it: dict) -> dict:
        file_diff_args = diff_args + ["--", it["rel"].replace("\\", "/")]
        diff_text = invoke_git(repo_full, file_diff_args)

        bytes_size = 0
        lwt_jst = ""
        file_hash = ""
        is_deleted = it["rel"].lower() in deleted_set

        if Path(it["full"]).is_file():
            try:
                bytes_size = Path(it["full"]).stat().st_size
                lwt_jst = file_mtime_jst(Path(it["full"]))
                file_hash = sha256_file(Path(it["full"]))
            except Exception:
                pass

        if is_deleted:
            bytes_size = 0
            lwt_jst = ""
            file_hash = ""

        fence = "```"
        block_lines = [
            "--- BEGIN DIFF FILE ---",
            f"Path: {it['rel']}",
            f"Group: {it['group']}",
            "--- DIFF ---",
            fence + "diff",
            diff_text.rstrip("\r\n"),
            fence,
            "--- END DIFF FILE ---",
            "",
        ]
        return {
            "block_text": "\n".join(block_lines) + "\n",
            "bytes": bytes_size,
            "last_write_time_jst": lwt_jst,
            "sha256": file_hash,
            "is_deleted": is_deleted,
        }

    def row_fn(it: dict, block: dict, state: PartState) -> dict:
        nonlocal included_bytes_total
        is_deleted = block["is_deleted"]
        if not is_deleted:
            included_bytes_total += block["bytes"]
        row = {
            "relative_path": it["rel"],
            "bytes": block["bytes"],
            "last_write_time_jst": block["last_write_time_jst"],
            "sha256": block["sha256"],
            "group": it["group"],
            "part_file": state.name,
            "is_truncated": False,
            "mode": "diff",
            "docset": docset,
            "repo_root": str(repo_full),
            "is_deleted": is_deleted,
        }
        manifest_path_set.add(it["rel"].lower())
        return row

    part_files_out = _process_group_parts(
        filtered_sorted, parts_dir, "diff", docset, "diff", repo_full,
        max_bytes_per_part, max_chars_per_part,
        build_fn, skipped, manifest_rows, row_fn,
        diff_args=diff_args,
    )

    # Add deleted-only entries to MANIFEST
    for del_rel in deleted_files:
        if del_rel.lower() in manifest_path_set:
            continue
        full_del = repo_full / del_rel
        if filters.is_excluded_by_folder(full_del):
            continue
        if filters.is_excluded_by_extension(full_del):
            continue
        if filters.is_excluded_by_secret_pattern(full_del):
            continue
        manifest_rows.append({
            "relative_path": del_rel,
            "bytes": 0,
            "last_write_time_jst": "",
            "sha256": "",
            "group": get_group(del_rel),
            "part_file": "",
            "is_truncated": False,
            "mode": "diff",
            "docset": docset,
            "repo_root": str(repo_full),
            "is_deleted": True,
        })
        manifest_path_set.add(del_rel.lower())

    manifest_rows.sort(key=lambda r: (r["group"], r["relative_path"]))

    group_counts: dict[str, int] = {}
    for r in manifest_rows:
        if not r["is_deleted"]:
            group_counts[r["group"]] = group_counts.get(r["group"], 0) + 1
    groups_text = "\n".join(f"- {g}: {c} files" for g, c in sorted(group_counts.items()))

    # Stats
    included_bytes_total = sum(r["bytes"] for r in manifest_rows)
    stats = {
        "included_files": len(manifest_rows),
        "skipped_files": len(skipped),
        "included_bytes_total": included_bytes_total,
        "groups_text": groups_text,
    }

    tree_lines = build_included_tree_lines([it["rel"] for it in filtered_sorted])

    # DIFF_INDEX.md
    file_list_lines = (
        "\n".join(f"- [{it['group']}] {it['rel']}" for it in filtered_sorted)
        or "- (none)"
    )
    parts_lines_str = (
        "\n".join(f"- {f}" for f in sorted(part_files_out))
        or "- (none)"
    )
    renames_lines = (
        "\n".join(f"- {r['status']} {r['old']} -> {r['new']}" for r in renames)
        or "- (none)"
    )

    diff_index_content = (
        f"# DIFF_INDEX (DocSet={docset})\n\n"
        f"- DocSet: {docset}\n"
        f"- GeneratedAt(JST): {generated_at}\n"
        f"- RepoRoot: {repo_full}\n"
        f"- Mode: diff\n"
        f"- DiffArgs: {' '.join(diff_args)}\n"
        f"- DiffScope: {diff_scope}\n"
        f"- RenameDetection: enabled (-M, heuristic)\n\n"
        f"---\n\n## Stats\n\n"
        + "\n".join(stats_lines) + "\n\n"
        f"---\n\n## Changed Files (filtered)\n\n{file_list_lines}\n\n"
        f"---\n\n## Renames (heuristic via -M)\n\n{renames_lines}\n\n"
        f"---\n\n## Output Parts\n\n{parts_lines_str}\n\n"
    )

    diff_index_path = work_dir / "DIFF_INDEX.md"
    diff_index_path.write_text(diff_index_content, encoding="utf-8")

    # INDEX.md extra section (reference to DIFF_INDEX)
    diff_extra = "\n---\n\n## Diff Index\n\n- DIFF_INDEX.md を参照（変更ファイル一覧と統計）\n\n"

    index_path = work_dir / "INDEX.md"
    tree_path = work_dir / "TREE.md"
    manifest_path = work_dir / "MANIFEST.csv"
    skipped_path = work_dir / "SKIPPED.txt"

    write_index_md(index_path, stats, part_files_out, diff_extra, **index_kwargs)
    write_tree_md(tree_path, tree_lines, docset, "diff")
    write_manifest_csv(manifest_path, manifest_rows)
    write_skipped_txt(skipped_path, skipped, docset)

    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ChatGPT相談用スナップショット/差分バンドル生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", required=True, choices=["map", "repo", "include", "diff"])
    parser.add_argument("--repo-root", required=True, help="Git repository root path")
    parser.add_argument("--case-name", default="", help="Optional case name suffix")
    parser.add_argument("--config-path", default="", help="Path to consult.config.json")
    parser.add_argument("--include-paths", nargs="+", default=[], help="Paths to include (mode=include)")
    parser.add_argument("--allow-docset-folders", action="store_true")
    parser.add_argument("--keep-bundle-dir", action="store_true", help="Keep _bundle work directory after ZIP")
    parser.add_argument("--diag", action="store_true", help="Verbose error output")
    parser.add_argument("--max-bytes-per-part", type=int, default=536870912, help="512MB default")
    parser.add_argument("--max-chars-per-part", type=int, default=300000)
    parser.add_argument("--max-chars-per-file", type=int, default=300000)
    parser.add_argument("--staged", action="store_true", help="diff: staged changes")
    parser.add_argument("--unstaged-only", action="store_true", help="diff: unstaged changes only")
    parser.add_argument("--diff-base", default="", help="diff: base ref")
    parser.add_argument("--diff-target", default="", help="diff: target ref")

    args = parser.parse_args()

    repo_root_full = resolve_full(args.repo_root)
    if not repo_root_full.is_dir():
        print(f"Error: RepoRoot not found: {repo_root_full}", file=sys.stderr)
        sys.exit(1)

    jst_now = get_jst_now()
    docset = jst_now.strftime("%Y%m%d%H%M%S")
    generated_at = fmt_jst(jst_now)

    try:
        cfg = apply_consult_config(repo_root_full, args.config_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    rule_file_full = repo_root_full / cfg.rule_file_rel
    out_root_full = repo_root_full / cfg.out_root_rel

    safe_case = ""
    if args.case_name.strip():
        safe_case = re.sub(r"\s+", "_", args.case_name.strip())
        safe_case = re.sub(r"[^0-9A-Za-z._-]", "", safe_case)

    bundle_label = f"{docset}_{args.mode}"
    if safe_case:
        bundle_label = f"{bundle_label}_{safe_case}"

    case_dir = out_root_full / bundle_label
    work_dir = case_dir / "_bundle"
    parts_dir = work_dir / "parts"

    cmd_line = format_command_line(args, cfg, repo_root_full)

    index_kwargs = dict(
        docset=docset,
        bundle_label=bundle_label,
        generated_at=generated_at,
        repo_root_full=repo_root_full,
        out_root_full=out_root_full,
        rule_file_full=rule_file_full,
        cfg=cfg,
        mode=args.mode,
        case_name=safe_case,
        max_bytes_per_part=args.max_bytes_per_part,
        max_chars_per_part=args.max_chars_per_part,
        max_chars_per_file=args.max_chars_per_file,
        cmd_line=cmd_line,
    )

    filters = Filters(cfg, repo_root_full)

    try:
        if args.mode in ("map", "repo", "include"):
            out_root_full.mkdir(parents=True, exist_ok=True)
            case_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            parts_dir.mkdir(parents=True, exist_ok=True)

            # 運用ルール文書を同梱
            if not rule_file_full.is_file():
                raise FileNotFoundError(f"Required rule file not found: {rule_file_full}")
            shutil.copy2(rule_file_full, work_dir / "00_ai_consult_operation_rules.md")

        if args.mode == "map":
            invoke_map(
                repo_root_full, filters, work_dir, parts_dir, case_dir,
                bundle_label, docset, generated_at,
                out_root_full, rule_file_full,
                args.max_bytes_per_part, args.max_chars_per_part, index_kwargs,
            )
            print(f"OK: map bundle generated at {work_dir}")

        elif args.mode == "repo":
            all_files = [f for f in repo_root_full.rglob("*") if f.is_file()]
            invoke_snapshot(
                "repo", repo_root_full, all_files, filters,
                work_dir, parts_dir, bundle_label, docset, generated_at,
                args.max_bytes_per_part, args.max_chars_per_part, args.max_chars_per_file,
                index_kwargs,
            )
            print(f"OK: repo snapshot generated at {work_dir}")

        elif args.mode == "include":
            targets = resolve_include_targets(
                repo_root_full, args.include_paths, filters, args.allow_docset_folders
            )
            invoke_snapshot(
                "include", repo_root_full, targets, filters,
                work_dir, parts_dir, bundle_label, docset, generated_at,
                args.max_bytes_per_part, args.max_chars_per_part, args.max_chars_per_file,
                index_kwargs,
            )
            print(f"OK: include snapshot generated at {work_dir}")

        elif args.mode == "diff":
            diff_ok = invoke_diff(
                repo_root_full, filters, work_dir, parts_dir, case_dir,
                out_root_full, bundle_label, docset, generated_at,
                args.max_bytes_per_part, args.max_chars_per_part,
                index_kwargs, args,
            )
            if not diff_ok:
                sys.exit(0)
            print(f"OK: diff bundle generated at {work_dir}")

    except Exception as e:
        if args.diag:
            import traceback
            traceback.print_exc()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # ZIP 自動生成
    try:
        zip_path = create_zip(work_dir, case_dir, bundle_label)
        print(f"ZIP created: {zip_path}")

        if not args.keep_bundle_dir:
            try:
                shutil.rmtree(work_dir)
                print(f"WorkDir removed (zip-only): {work_dir}")
            except Exception as e:
                print(f"Warning: WorkDir removal failed (kept): {e}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: ZIP creation failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
