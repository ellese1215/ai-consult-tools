from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_VERSION = 1
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


def load_config(path: str | Path) -> ConsultConfig:
    config_path = Path(path)

    try:
        text = config_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(
            f"cannot read configuration: {config_path}: {exc}"
        ) from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid JSON in configuration: "
            f"{config_path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc

    return parse_config(payload)
