from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_VERSION = 1
DEFAULT_MAX_TEXT_BYTES = 2_000_000


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class FilterConfig:
    exclude_paths: tuple[str, ...] = ()
    binary_extensions: tuple[str, ...] = ()
    max_text_bytes: int = DEFAULT_MAX_TEXT_BYTES


@dataclass(frozen=True)
class ConsultConfig:
    schema_version: int
    filters: FilterConfig


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


def parse_config(payload: Any) -> ConsultConfig:
    if not isinstance(payload, dict):
        raise ConfigError("configuration root must be an object")

    _reject_unknown_keys(
        payload,
        {"schemaVersion", "filters"},
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
