from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.config import ProjectProfile
from ai_consult.inventory import InventoryEntry, InventoryEntryType
from ai_consult.search import (
    StructureMatchRank,
    StructureSearchError,
    find_structure_entries,
    normalize_structure_query,
)


class StructureSearchTest(unittest.TestCase):
    def test_normalizes_query(self) -> None:
        self.assertEqual(
            normalize_structure_query(r" .\docs\Guide.md/ "),
            "docs/Guide.md",
        )

        with self.assertRaises(StructureSearchError):
            normalize_structure_query(" ./ ")

    def test_ranks_exact_and_partial_matches_deterministically(self) -> None:
        entries = (
            InventoryEntry(
                "archive/guide/source.txt",
                InventoryEntryType.FILE,
            ),
            InventoryEntry(
                "docs/guide-notes.md",
                InventoryEntryType.FILE,
            ),
            InventoryEntry(
                "docs/guide.md",
                InventoryEntryType.FILE,
            ),
            InventoryEntry(
                "guide.md",
                InventoryEntryType.FILE,
            ),
        )

        matches = find_structure_entries(entries, "guide.md")

        self.assertEqual(
            tuple(match.entry.relative_path for match in matches),
            (
                "guide.md",
                "docs/guide.md",
            ),
        )
        self.assertEqual(
            tuple(match.rank for match in matches),
            (
                StructureMatchRank.EXACT_PATH,
                StructureMatchRank.EXACT_NAME,
            ),
        )

        partial_matches = find_structure_entries(entries, "guide")

        self.assertEqual(
            tuple(match.entry.relative_path for match in partial_matches),
            (
                "docs/guide-notes.md",
                "docs/guide.md",
                "guide.md",
                "archive/guide/source.txt",
            ),
        )
        self.assertTrue(
            all(
                match.rank is StructureMatchRank.PARTIAL_NAME
                for match in partial_matches[:3]
            )
        )
        self.assertEqual(
            partial_matches[3].rank,
            StructureMatchRank.PARTIAL_PATH,
        )

    def test_is_case_insensitive_and_normalizes_separators(self) -> None:
        entries = (
            InventoryEntry(
                "Docs/Guide.MD",
                InventoryEntryType.FILE,
            ),
        )

        matches = find_structure_entries(entries, r"docs\guide.md")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].rank, StructureMatchRank.EXACT_PATH)

    def test_filters_to_files_and_project_profile(self) -> None:
        entries = (
            InventoryEntry(
                "apps/alpha/readme.md",
                InventoryEntryType.FILE,
            ),
            InventoryEntry(
                "apps/beta/readme.md",
                InventoryEntryType.FILE,
            ),
            InventoryEntry(
                "apps/alpha/readme",
                InventoryEntryType.DIRECTORY,
            ),
        )
        profile = ProjectProfile(
            name="alpha",
            scope_roots=("apps/alpha",),
        )

        matches = find_structure_entries(
            entries,
            "readme",
            profile=profile,
        )

        self.assertEqual(
            tuple(match.entry.relative_path for match in matches),
            ("apps/alpha/readme.md",),
        )


if __name__ == "__main__":
    unittest.main()
