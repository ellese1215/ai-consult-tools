from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_PROJECT_PROFILES_SCHEMA_VERSION = 1
DEFAULT_MAX_TEXT_BYTES = 2_000_000
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
class ConsultConfig:
    schema_version: int
    filters: FilterConfig
    inventory: InventoryConfig = field(default_factory=InventoryConfig)


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
    if not value:
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


def parse_config(payload: Any) -> ConsultConfig:
    if not isinstance(payload, dict):
        raise ConfigError("configuration root must be an object")

    _reject_unknown_keys(
        payload,
        {"schemaVersion", "filters", "inventory"},
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
