from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.config import (
    DEFAULT_INVENTORY_EXCLUDE_PATHS,
    ConfigError,
    load_config,
    load_project_profiles,
    parse_config,
    parse_project_profiles,
)


class ConfigTest(unittest.TestCase):
    def test_parse_valid_config(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "filters": {
                    "excludePaths": [".git", "vendor/"],
                    "binaryExtensions": [".psd"],
                    "maxTextBytes": 12345,
                },
                "inventory": {
                    "excludePaths": ["private/generated/"],
                },
            }
        )

        self.assertEqual(config.schema_version, 1)
        self.assertEqual(
            config.filters.exclude_paths,
            (".git", "vendor/"),
        )
        self.assertEqual(
            config.filters.binary_extensions,
            (".psd",),
        )
        self.assertEqual(config.filters.max_text_bytes, 12345)
        self.assertEqual(
            config.inventory.exclude_paths[: len(DEFAULT_INVENTORY_EXCLUDE_PATHS)],
            DEFAULT_INVENTORY_EXCLUDE_PATHS,
        )
        self.assertEqual(
            config.inventory.exclude_paths[-1],
            "private/generated/",
        )


    def test_parses_include_sets_and_preserves_path_order(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "filters": {},
                "includeSets": {
                    "common_rules": [
                        "project/rules.md",
                        "project/local.md",
                        "project/rules.md",
                    ],
                    "review": ["project/status.md"],
                },
            }
        )

        self.assertEqual(
            tuple(item.name for item in config.include_sets),
            ("common_rules", "review"),
        )
        self.assertEqual(
            config.get_include_set("COMMON_RULES").paths,
            (
                "project/rules.md",
                "project/local.md",
                "project/rules.md",
            ),
        )

    def test_rejects_invalid_include_sets(self) -> None:
        invalid_values = (
            [],
            {"": ["project/a.md"]},
            {" common": ["project/a.md"]},
            {"common": []},
            {"common": "project/a.md"},
            {"common": ["project/"]},
            {"common": ["../project/a.md"]},
            {"common": ["project\\a.md"]},
            {
                "Common": ["project/a.md"],
                "common": ["project/b.md"],
            },
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ConfigError):
                    parse_config(
                        {
                            "schemaVersion": 1,
                            "filters": {},
                            "includeSets": value,
                        }
                    )

    def test_unknown_include_set_lists_available_names(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "filters": {},
                "includeSets": {
                    "common_rules": ["project/rules.md"],
                },
            }
        )

        with self.assertRaisesRegex(
            ConfigError,
            "available: common_rules",
        ):
            config.get_include_set("missing")

    def test_output_defaults_are_applied_without_section(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "filters": {},
            }
        )

        self.assertEqual(
            config.outputs.chatgpt.out_root,
            "ai-consult-tools/chatgpt/consult_case",
        )
        self.assertEqual(
            config.outputs.chatgpt.max_bytes_per_part,
            536_870_912,
        )
        self.assertEqual(
            config.outputs.chatgpt.max_chars_per_part,
            300_000,
        )
        self.assertEqual(
            config.outputs.claude.out_root,
            "ai-consult-tools/claude/consult_case",
        )
        self.assertEqual(
            config.outputs.claude.max_chars_per_part,
            300_000,
        )

    def test_parses_model_output_settings(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "outputs": {
                    "chatgpt": {
                        "outRoot": "build/chatgpt",
                        "maxBytesPerPart": 1234,
                        "maxCharsPerPart": 567,
                    },
                    "claude": {
                        "outRoot": "build/claude",
                        "maxCharsPerPart": 890,
                    },
                },
            }
        )

        self.assertEqual(config.outputs.chatgpt.out_root, "build/chatgpt")
        self.assertEqual(config.outputs.chatgpt.max_bytes_per_part, 1234)
        self.assertEqual(config.outputs.chatgpt.max_chars_per_part, 567)
        self.assertEqual(config.outputs.claude.out_root, "build/claude")
        self.assertEqual(config.outputs.claude.max_chars_per_part, 890)
        self.assertEqual(
            config.output_roots,
            ("build/chatgpt", "build/claude"),
        )

    def test_output_roots_are_deduplicated_without_glob_conversion(
        self,
    ) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "outputs": {
                    "chatgpt": {
                        "outRoot": "project/generated/[chat]",
                    },
                    "claude": {
                        "outRoot": "PROJECT/GENERATED/[CHAT]",
                    },
                },
            }
        )

        self.assertEqual(
            config.output_roots,
            ("project/generated/[chat]",),
        )

    def test_rejects_invalid_output_settings(self) -> None:
        invalid_payloads = (
            {"outputs": []},
            {"outputs": {"unexpected": {}}},
            {"outputs": {"chatgpt": []}},
            {"outputs": {"claude": []}},
            {"outputs": {"chatgpt": {"unexpected": 1}}},
            {"outputs": {"claude": {"unexpected": 1}}},
            {"outputs": {"chatgpt": {"outRoot": "/outside"}}},
            {"outputs": {"chatgpt": {"outRoot": ".."}}},
            {"outputs": {"claude": {"outRoot": "bad\\path"}}},
            {"outputs": {"chatgpt": {"maxBytesPerPart": 0}}},
            {"outputs": {"chatgpt": {"maxCharsPerPart": True}}},
            {"outputs": {"claude": {"maxCharsPerPart": -1}}},
        )

        for extra in invalid_payloads:
            with self.subTest(extra=extra):
                payload = {"schemaVersion": 1}
                payload.update(extra)

                with self.assertRaises(ConfigError):
                    parse_config(payload)

    def test_inventory_defaults_are_applied_without_section(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "filters": {},
            }
        )

        self.assertEqual(
            config.inventory.exclude_paths,
            DEFAULT_INVENTORY_EXCLUDE_PATHS,
        )

    def test_inventory_duplicate_default_is_not_added_twice(self) -> None:
        config = parse_config(
            {
                "schemaVersion": 1,
                "filters": {},
                "inventory": {
                    "excludePaths": [".GIT"],
                },
            }
        )

        self.assertEqual(
            sum(
                1
                for value in config.inventory.exclude_paths
                if value.casefold() == ".git"
            ),
            1,
        )

    def test_rejects_unsupported_schema(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config({"schemaVersion": 99})

    def test_rejects_unknown_key(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "schemaVersion": 1,
                    "unexpected": True,
                }
            )

    def test_rejects_unknown_inventory_key(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "schemaVersion": 1,
                    "inventory": {
                        "unexpected": True,
                    },
                }
            )

    def test_rejects_invalid_string_list(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "schemaVersion": 1,
                    "filters": {
                        "excludePaths": "vendor/",
                    },
                }
            )


    def test_loads_common_config_example_with_include_sets(self) -> None:
        config = load_config(
            TOOL_ROOT / "config" / "consult.config.example.json"
        )

        self.assertEqual(
            config.get_include_set("common_rules").paths,
            (
                "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
                "ai-consult-tools/shared/02_consult_template.md",
                "ai-consult-tools/local/consult.local.md",
            ),
        )
        self.assertEqual(
            config.get_include_set("ai_consult_maintenance").paths,
            (
                "ai-consult-tools/README.md",
                "ai-consult-tools/docs/01_current_spec.md",
                "ai-consult-tools/shared/01_ai_consult_procedures.md",
                "ai-consult-tools/shared/SECURITY.md",
                "ai-consult-tools/shared/consult.local.example.md",
            ),
        )
        self.assertEqual(
            config.get_include_set("repository_structure").paths,
            ("docs/REPOSITORY_STRUCTURE.md",),
        )
        self.assertNotIn(
            "ai-consult-tools/local/",
            config.filters.exclude_paths,
        )
        self.assertEqual(
            config.outputs.chatgpt.out_root,
            "ai-consult-tools/chatgpt/consult_case",
        )
        self.assertEqual(
            config.outputs.claude.out_root,
            "ai-consult-tools/claude/consult_case",
        )

    def test_loads_utf8_bom_json(self) -> None:
        payload = {
            "schemaVersion": 1,
            "filters": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps(payload),
                encoding="utf-8-sig",
            )

            config = load_config(path)

        self.assertEqual(config.schema_version, 1)


class ProjectProfilesConfigTest(unittest.TestCase):
    def test_parse_profiles_and_match_scope_roots(self) -> None:
        config = parse_project_profiles(
            {
                "schemaVersion": 1,
                "profiles": {
                    "tax_ledger": {
                        "scopeRoots": ["apps/tax-ledger"],
                    },
                    "ai_consult_tools": {
                        "scopeRoots": ["ai-consult-tools"],
                    },
                },
            }
        )

        self.assertEqual(
            tuple(profile.name for profile in config.profiles),
            ("ai_consult_tools", "tax_ledger"),
        )
        self.assertTrue(
            config.get("TAX_LEDGER").contains(
                "apps/tax-ledger/docs/00_project_status.md"
            )
        )
        self.assertFalse(
            config.get("tax_ledger").contains("apps/other/file.txt")
        )
        self.assertEqual(
            config.matching_profile_names(
                "ai-consult-tools/src/ai_consult/config.py"
            ),
            ("ai_consult_tools",),
        )

    def test_rejects_invalid_project_profile_schema(self) -> None:
        invalid_payloads = (
            {"schemaVersion": 99, "profiles": {}},
            {
                "schemaVersion": 1,
                "profiles": {},
                "unexpected": True,
            },
            {
                "schemaVersion": 1,
                "profiles": {
                    "sample": {
                        "scopeRoots": ["apps/sample"],
                        "unexpected": True,
                    }
                },
            },
            {
                "schemaVersion": 1,
                "profiles": {
                    "sample": {"scopeRoots": "apps/sample"}
                },
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ConfigError):
                    parse_project_profiles(payload)

    def test_rejects_invalid_or_duplicate_scope_roots(self) -> None:
        invalid_roots = (
            "",
            " apps/sample",
            "apps/sample ",
            "/apps/sample",
            "C:/apps/sample",
            "apps\\sample",
            "apps/sample/",
            ".",
            "..",
            "apps/../sample",
            "apps//sample",
        )

        for root in invalid_roots:
            with self.subTest(root=root):
                with self.assertRaises(ConfigError):
                    parse_project_profiles(
                        {
                            "schemaVersion": 1,
                            "profiles": {
                                "sample": {"scopeRoots": [root]}
                            },
                        }
                    )

        with self.assertRaises(ConfigError):
            parse_project_profiles(
                {
                    "schemaVersion": 1,
                    "profiles": {
                        "sample": {
                            "scopeRoots": [
                                "apps/sample",
                                "APPS/SAMPLE",
                            ]
                        }
                    },
                }
            )

    def test_loads_project_profiles_example(self) -> None:
        path = TOOL_ROOT / "config" / "project_profiles.example.json"
        config = load_project_profiles(path)

        self.assertEqual(config.schema_version, 1)
        self.assertEqual(
            tuple(profile.name for profile in config.profiles),
            (
                "ai_consult_tools",
                "arcane_eriya",
                "pavilion_ellese",
                "tax_ledger",
            ),
        )
        self.assertEqual(
            config.get("arcane_eriya").scope_roots,
            (
                "apps/games/arcane_warmaiden_eriya",
                "apps/games/arcane_warmaiden_eriya_trial",
                "docs/arcane_eriya",
            ),
        )
        self.assertIn(
            "docs/pavilion-ellese",
            config.get("pavilion_ellese").scope_roots,
        )


if __name__ == "__main__":
    unittest.main()
