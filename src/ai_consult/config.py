from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_PROJECT_PROFILES_SCHEMA_VERSION = 1
DEFAULT_MAX_TEXT_BYTES = 2_000_000
DEFAULT_CHATGPT_OUT_ROOT = "ai-consult-tools/chatgpt/consult_case"
DEFAULT_CLAUDE_OUT_ROOT = "ai-consult-tools/claude/consult_case"
DEFAULT_CHATGPT_MAX_BYTES_PER_PART = 536_870_912
DEFAULT_CHATGPT_MAX_CHARS_PER_PART = 300_000
DEFAULT_CLAUDE_MAX_CHARS_PER_PART = 300_000
DEFAULT_INVENTORY_EXCLUDE_PATHS = (
    ".git",
    "node_modules",
    "vendor",
    ".gradle",
    ".vscode",
    ".backups",
    "__pycache__",
    "*.py[cod]",
    "build",
    "dist",
    "out",
    "release",
    ".consult/consult_case/",
    ".consult/consult_project/",
    "consult_case",
    "consult_project",
    "ai-consult-tools/chatgpt/consult_case/",
    "ai-consult-tools/chatgpt/consult_project/",
    "ai-consult-tools/claude/consult_case/",
    "ai-consult-tools/claude/consult_project/",
    "ai-consult-tools/local/",
    "ai-consult-tools/archive/",
    ".env",
    ".env.*",
    "*.env*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*credential*",
    "*secret*",
    "google-services.json",
    "GoogleService-Info.plist",
    "id_rsa*",
    "key.properties",
    "local.properties",
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class FilterConfig:
    exclude_paths: tuple[str, ...] = ()
    binary_extensions: tuple[str, ...] = ()
    max_text_bytes: int = DEFAULT_MAX_TEXT_BYTES


@dataclass(frozen=True)
class InventoryConfig:
    exclude_paths: tuple[str, ...] = DEFAULT_INVENTORY_EXCLUDE_PATHS


@dataclass(frozen=True)
class ChatGPTOutputConfig:
    out_root: str = DEFAULT_CHATGPT_OUT_ROOT
    max_bytes_per_part: int = DEFAULT_CHATGPT_MAX_BYTES_PER_PART
    max_chars_per_part: int = DEFAULT_CHATGPT_MAX_CHARS_PER_PART

    def __post_init__(self) -> None:
        _validate_repo_relative_path(
            self.out_root,
            "outputs.chatgpt.outRoot",
            allow_trailing_slash=False,
        )
        _validate_positive_integer(
            self.max_bytes_per_part,
            "outputs.chatgpt.maxBytesPerPart",
        )
        _validate_positive_integer(
            self.max_chars_per_part,
            "outputs.chatgpt.maxCharsPerPart",
        )


@dataclass(frozen=True)
class ClaudeOutputConfig:
    out_root: str = DEFAULT_CLAUDE_OUT_ROOT
    max_chars_per_part: int = DEFAULT_CLAUDE_MAX_CHARS_PER_PART

    def __post_init__(self) -> None:
        _validate_repo_relative_path(
            self.out_root,
            "outputs.claude.outRoot",
            allow_trailing_slash=False,
        )
        _validate_positive_integer(
            self.max_chars_per_part,
            "outputs.claude.maxCharsPerPart",
        )


@dataclass(frozen=True)
class OutputsConfig:
    chatgpt: ChatGPTOutputConfig = field(
        default_factory=ChatGPTOutputConfig
    )
    claude: ClaudeOutputConfig = field(
        default_factory=ClaudeOutputConfig
    )


@dataclass(frozen=True)
class IncludeSetConfig:
    name: str
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name
            or self.name != self.name.strip()
        ):
            raise ConfigError(
                "include set name must be a non-empty trimmed string"
            )

        paths = tuple(self.paths)
        object.__setattr__(self, "paths", paths)

        if not paths:
            raise ConfigError(
                f"includeSets.{self.name} must contain at least one path"
            )

        for index, path in enumerate(paths):
            if not isinstance(path, str):
                raise ConfigError(
                    f"includeSets.{self.name}[{index}] must be a string"
                )

            _validate_repo_relative_path(
                path,
                f"includeSets.{self.name}[{index}]",
                allow_trailing_slash=False,
            )


@dataclass(frozen=True)
class ConsultConfig:
    schema_version: int
    filters: FilterConfig
    inventory: InventoryConfig = field(default_factory=InventoryConfig)
    include_sets: tuple[IncludeSetConfig, ...] = ()
    outputs: OutputsConfig = field(default_factory=OutputsConfig)

    def __post_init__(self) -> None:
        include_sets = tuple(self.include_sets)
        object.__setattr__(self, "include_sets", include_sets)

        if not isinstance(self.outputs, OutputsConfig):
            raise ConfigError(
                "outputs must be an OutputsConfig value"
            )

        if not all(
            isinstance(item, IncludeSetConfig)
            for item in include_sets
        ):
            raise ConfigError(
                "include_sets must contain only IncludeSetConfig values"
            )

        folded_names = tuple(
            item.name.casefold() for item in include_sets
        )

        if len(folded_names) != len(set(folded_names)):
            raise ConfigError(
                "include_sets contains duplicate names"
            )

    def get_include_set(self, name: str) -> IncludeSetConfig:
        if not isinstance(name, str) or not name or name != name.strip():
            raise ConfigError(
                "include set name must be a non-empty trimmed string"
            )

        folded_name = name.casefold()

        for include_set in self.include_sets:
            if include_set.name.casefold() == folded_name:
                return include_set

        known = ", ".join(
            sorted(
                (item.name for item in self.include_sets),
                key=lambda value: (value.casefold(), value),
            )
        ) or "(none)"
        raise ConfigError(
            f"unknown include set: {name}; available: {known}"
        )


@dataclass(frozen=True)
class ProjectProfile:
    name: str
    scope_roots: tuple[str, ...]

    def contains(self, relative_path: str) -> bool:
        _validate_repo_relative_path(
            relative_path,
            "relativePath",
            allow_trailing_slash=False,
        )
        folded_path = relative_path.casefold()

        return any(
            folded_path == root.casefold()
            or folded_path.startswith(root.casefold() + "/")
            for root in self.scope_roots
        )


@dataclass(frozen=True)
class ProjectProfilesConfig:
    schema_version: int
    profiles: tuple[ProjectProfile, ...]

    def get(self, name: str) -> ProjectProfile:
        folded_name = name.casefold()

        for profile in self.profiles:
            if profile.name.casefold() == folded_name:
                return profile

        raise ConfigError(f"unknown project profile: {name}")

    def matching_profile_names(
        self,
        relative_path: str,
    ) -> tuple[str, ...]:
        return tuple(
            profile.name
            for profile in self.profiles
            if profile.contains(relative_path)
        )


def _reject_unknown_keys(
    value: dict[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    unknown = sorted(set(value) - allowed)

    if unknown:
        joined = ", ".join(unknown)
        raise ConfigError(f"{context} contains unknown keys: {joined}")


def _read_string_list(
    value: dict[str, Any],
    key: str,
    context: str,
) -> tuple[str, ...]:
    raw = value.get(key, [])

    if not isinstance(raw, list):
        raise ConfigError(f"{context}.{key} must be an array")

    result: list[str] = []

    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"{context}.{key}[{index}] must be a non-empty string"
            )

        result.append(item.strip())

    return tuple(result)


def _merge_unique_strings(
    defaults: tuple[str, ...],
    additions: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for item in defaults + additions:
        key = item.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return tuple(result)


def _validate_repo_relative_path(
    value: str,
    context: str,
    *,
    allow_trailing_slash: bool,
) -> None:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{context} must be a non-empty string")

    if value != value.strip():
        raise ConfigError(
            f"{context} must not contain leading or trailing whitespace"
        )

    if "\\" in value:
        raise ConfigError(f"{context} must use / separators: {value}")

    if value.startswith("/") or (
        len(value) >= 3 and value[1:3] == ":/"
    ):
        raise ConfigError(f"{context} must be RepoRoot-relative: {value}")

    if value.endswith("/") and not allow_trailing_slash:
        raise ConfigError(f"{context} must not end with /: {value}")

    logical_value = value[:-1] if value.endswith("/") else value
    parts = logical_value.split("/")

    if any(part in {"", ".", ".."} for part in parts):
        raise ConfigError(f"{context} is not a canonical path: {value}")


def _parse_project_profile(
    name: str,
    value: Any,
) -> ProjectProfile:
    context = f"profiles.{name}"

    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be an object")

    _reject_unknown_keys(value, {"scopeRoots"}, context)
    raw_scope_roots = value.get("scopeRoots")

    if not isinstance(raw_scope_roots, list):
        raise ConfigError(f"{context}.scopeRoots must be an array")

    scope_roots: list[str] = []
    seen: set[str] = set()

    for index, item in enumerate(raw_scope_roots):
        item_context = f"{context}.scopeRoots[{index}]"

        if not isinstance(item, str):
            raise ConfigError(f"{item_context} must be a string")

        _validate_repo_relative_path(
            item,
            item_context,
            allow_trailing_slash=False,
        )
        folded = item.casefold()

        if folded in seen:
            raise ConfigError(
                f"{context}.scopeRoots contains a duplicate path: {item}"
            )

        seen.add(folded)
        scope_roots.append(item)

    return ProjectProfile(
        name=name,
        scope_roots=tuple(scope_roots),
    )


def _validate_positive_integer(value: int, context: str) -> None:
    if type(value) is not int or value <= 0:
        raise ConfigError(f"{context} must be a positive integer")


def _parse_outputs(value: Any) -> OutputsConfig:
    if value is None:
        return OutputsConfig()

    if not isinstance(value, dict):
        raise ConfigError("outputs must be an object")

    _reject_unknown_keys(value, {"chatgpt", "claude"}, "outputs")
    chatgpt_value = value.get("chatgpt", {})
    claude_value = value.get("claude", {})

    if not isinstance(chatgpt_value, dict):
        raise ConfigError("outputs.chatgpt must be an object")

    if not isinstance(claude_value, dict):
        raise ConfigError("outputs.claude must be an object")

    _reject_unknown_keys(
        chatgpt_value,
        {"outRoot", "maxBytesPerPart", "maxCharsPerPart"},
        "outputs.chatgpt",
    )
    _reject_unknown_keys(
        claude_value,
        {"outRoot", "maxCharsPerPart"},
        "outputs.claude",
    )

    return OutputsConfig(
        chatgpt=ChatGPTOutputConfig(
            out_root=chatgpt_value.get(
                "outRoot",
                DEFAULT_CHATGPT_OUT_ROOT,
            ),
            max_bytes_per_part=chatgpt_value.get(
                "maxBytesPerPart",
                DEFAULT_CHATGPT_MAX_BYTES_PER_PART,
            ),
            max_chars_per_part=chatgpt_value.get(
                "maxCharsPerPart",
                DEFAULT_CHATGPT_MAX_CHARS_PER_PART,
            ),
        ),
        claude=ClaudeOutputConfig(
            out_root=claude_value.get(
                "outRoot",
                DEFAULT_CLAUDE_OUT_ROOT,
            ),
            max_chars_per_part=claude_value.get(
                "maxCharsPerPart",
                DEFAULT_CLAUDE_MAX_CHARS_PER_PART,
            ),
        ),
    )


def _parse_include_sets(value: Any) -> tuple[IncludeSetConfig, ...]:
    if value is None:
        return ()

    if not isinstance(value, dict):
        raise ConfigError("includeSets must be an object")

    include_sets: list[IncludeSetConfig] = []
    seen_names: set[str] = set()

    for raw_name, raw_paths in value.items():
        if (
            not isinstance(raw_name, str)
            or not raw_name
            or raw_name != raw_name.strip()
        ):
            raise ConfigError(
                "includeSets names must be non-empty trimmed strings"
            )

        folded_name = raw_name.casefold()

        if folded_name in seen_names:
            raise ConfigError(
                f"includeSets contains a duplicate name: {raw_name}"
            )

        seen_names.add(folded_name)
        context = f"includeSets.{raw_name}"

        if not isinstance(raw_paths, list):
            raise ConfigError(f"{context} must be an array")

        if not raw_paths:
            raise ConfigError(f"{context} must contain at least one path")

        paths: list[str] = []

        for index, raw_path in enumerate(raw_paths):
            item_context = f"{context}[{index}]"

            if not isinstance(raw_path, str):
                raise ConfigError(f"{item_context} must be a string")

            _validate_repo_relative_path(
                raw_path,
                item_context,
                allow_trailing_slash=False,
            )
            paths.append(raw_path)

        include_sets.append(
            IncludeSetConfig(
                name=raw_name,
                paths=tuple(paths),
            )
        )

    return tuple(include_sets)


def parse_config(payload: Any) -> ConsultConfig:
    if not isinstance(payload, dict):
        raise ConfigError("configuration root must be an object")

    _reject_unknown_keys(
        payload,
        {
            "schemaVersion",
            "filters",
            "inventory",
            "includeSets",
            "outputs",
        },
        "configuration",
    )

    schema_version = payload.get("schemaVersion")

    if type(schema_version) is not int:
        raise ConfigError("schemaVersion must be an integer")

    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ConfigError(
            "unsupported schemaVersion: "
            f"{schema_version}; expected {SUPPORTED_SCHEMA_VERSION}"
        )

    filters_value = payload.get("filters", {})

    if not isinstance(filters_value, dict):
        raise ConfigError("filters must be an object")

    _reject_unknown_keys(
        filters_value,
        {
            "excludePaths",
            "binaryExtensions",
            "maxTextBytes",
        },
        "filters",
    )

    max_text_bytes = filters_value.get(
        "maxTextBytes",
        DEFAULT_MAX_TEXT_BYTES,
    )

    if type(max_text_bytes) is not int or max_text_bytes <= 0:
        raise ConfigError("filters.maxTextBytes must be a positive integer")

    inventory_value = payload.get("inventory", {})

    if not isinstance(inventory_value, dict):
        raise ConfigError("inventory must be an object")

    _reject_unknown_keys(
        inventory_value,
        {"excludePaths"},
        "inventory",
    )

    inventory_exclude_paths = _merge_unique_strings(
        DEFAULT_INVENTORY_EXCLUDE_PATHS,
        _read_string_list(
            inventory_value,
            "excludePaths",
            "inventory",
        ),
    )

    return ConsultConfig(
        schema_version=schema_version,
        filters=FilterConfig(
            exclude_paths=_read_string_list(
                filters_value,
                "excludePaths",
                "filters",
            ),
            binary_extensions=_read_string_list(
                filters_value,
                "binaryExtensions",
                "filters",
            ),
            max_text_bytes=max_text_bytes,
        ),
        inventory=InventoryConfig(
            exclude_paths=inventory_exclude_paths,
        ),
        include_sets=_parse_include_sets(payload.get("includeSets")),
        outputs=_parse_outputs(payload.get("outputs")),
    )


def parse_project_profiles(payload: Any) -> ProjectProfilesConfig:
    if not isinstance(payload, dict):
        raise ConfigError("project profiles root must be an object")

    _reject_unknown_keys(
        payload,
        {"schemaVersion", "profiles"},
        "project profiles",
    )
    schema_version = payload.get("schemaVersion")

    if type(schema_version) is not int:
        raise ConfigError(
            "project profiles schemaVersion must be an integer"
        )

    if schema_version != SUPPORTED_PROJECT_PROFILES_SCHEMA_VERSION:
        raise ConfigError(
            "unsupported project profiles schemaVersion: "
            f"{schema_version}; expected "
            f"{SUPPORTED_PROJECT_PROFILES_SCHEMA_VERSION}"
        )

    profiles_value = payload.get("profiles")

    if not isinstance(profiles_value, dict):
        raise ConfigError("project profiles.profiles must be an object")

    if not all(isinstance(name, str) for name in profiles_value):
        raise ConfigError("project profile names must be strings")

    profiles: list[ProjectProfile] = []
    seen_names: set[str] = set()

    for name in sorted(
        profiles_value,
        key=lambda item: (item.casefold(), item),
    ):
        if not name or name != name.strip():
            raise ConfigError(
                "project profile names must be non-empty and trimmed"
            )

        folded_name = name.casefold()

        if folded_name in seen_names:
            raise ConfigError(
                f"duplicate project profile name: {name}"
            )

        seen_names.add(folded_name)
        profiles.append(
            _parse_project_profile(name, profiles_value[name])
        )

    return ProjectProfilesConfig(
        schema_version=schema_version,
        profiles=tuple(profiles),
    )


def _load_json(path: Path, description: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(
            f"cannot read {description}: {path}: {exc}"
        ) from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid JSON in {description}: "
            f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc


def load_config(path: str | Path) -> ConsultConfig:
    config_path = Path(path)
    return parse_config(_load_json(config_path, "configuration"))


def load_project_profiles(
    path: str | Path,
) -> ProjectProfilesConfig:
    profiles_path = Path(path)
    return parse_project_profiles(
        _load_json(profiles_path, "project profiles")
    )
