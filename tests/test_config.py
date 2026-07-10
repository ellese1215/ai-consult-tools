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

from ai_consult.config import ConfigError, load_config, parse_config


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


if __name__ == "__main__":
    unittest.main()
