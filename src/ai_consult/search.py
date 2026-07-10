from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ai_consult.config import ProjectProfile
from ai_consult.inventory import InventoryEntry, InventoryEntryType


class StructureSearchError(ValueError):
    pass


class StructureMatchRank(IntEnum):
    EXACT_PATH = 0
    EXACT_NAME = 1
    PARTIAL_NAME = 2
    PARTIAL_PATH = 3


@dataclass(frozen=True)
class StructureSearchMatch:
    entry: InventoryEntry
    rank: StructureMatchRank


def normalize_structure_query(value: str) -> str:
    normalized = value.strip().replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    normalized = normalized.rstrip("/")

    if not normalized:
        raise StructureSearchError("find query must not be empty")

    return normalized


def _match_rank(
    entry: InventoryEntry,
    folded_query: str,
) -> StructureMatchRank | None:
    folded_path = entry.relative_path.casefold()
    folded_name = entry.name.casefold()

    if folded_path == folded_query:
        return StructureMatchRank.EXACT_PATH

    if folded_name == folded_query:
        return StructureMatchRank.EXACT_NAME

    if folded_query in folded_name:
        return StructureMatchRank.PARTIAL_NAME

    if folded_query in folded_path:
        return StructureMatchRank.PARTIAL_PATH

    return None


def find_structure_entries(
    entries: tuple[InventoryEntry, ...],
    query: str,
    *,
    profile: ProjectProfile | None = None,
) -> tuple[StructureSearchMatch, ...]:
    normalized_query = normalize_structure_query(query)
    folded_query = normalized_query.casefold()
    matches: list[StructureSearchMatch] = []

    for entry in entries:
        if entry.entry_type is not InventoryEntryType.FILE:
            continue

        if profile is not None and not profile.contains(
            entry.relative_path
        ):
            continue

        rank = _match_rank(entry, folded_query)

        if rank is None:
            continue

        matches.append(StructureSearchMatch(entry=entry, rank=rank))

    matches.sort(
        key=lambda match: (
            int(match.rank),
            match.entry.relative_path.casefold(),
            match.entry.relative_path,
        )
    )
    return tuple(matches)
