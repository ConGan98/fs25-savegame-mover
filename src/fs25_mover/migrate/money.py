"""Migrate farm money + loan, plus optional career statistics, from source
farmId to target farmId. All writes target the SAME `farms.xml` `<farm>` entry.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from lxml import etree

from ..parsers.savegame import Savegame


# Fields inside `<statistics>` that must NOT be copied during a stats
# migration — these are per-save IDs that belong to the target's bookkeeping,
# not the player's portable career history.
STATS_PER_SAVE_FIELDS = frozenset({
    "farmId",     # inner farmId (the target's per-save numeric id)
    "cowId",
    "pigId",
    "sheepId",
    "horseId",
    "chickenId",
    "goatId",
    "buffaloId",
})


@dataclass
class MoneyMigrationResult:
    src_farm_id: int
    tgt_farm_id: int
    money: float
    loan: float
    applied: bool


@dataclass
class FarmStatsMigrationResult:
    src_farm_id: int
    tgt_farm_id: int
    fields_copied: int
    skipped_fields: list[str] = field(default_factory=list)
    applied: bool = False


def migrate_money(
    src: Savegame,
    tgt: Savegame,
    src_farm_id: int = 1,
    tgt_farm_id: int = 1,
) -> MoneyMigrationResult:
    src_root = src.root("farms.xml")
    tgt_root = tgt.root("farms.xml")
    if src_root is None or tgt_root is None:
        return MoneyMigrationResult(src_farm_id, tgt_farm_id, 0.0, 0.0, applied=False)

    src_farm = next(
        (f for f in src_root.findall("farm") if f.get("farmId") == str(src_farm_id)),
        None,
    )
    tgt_farm = next(
        (f for f in tgt_root.findall("farm") if f.get("farmId") == str(tgt_farm_id)),
        None,
    )
    if src_farm is None or tgt_farm is None:
        return MoneyMigrationResult(src_farm_id, tgt_farm_id, 0.0, 0.0, applied=False)

    money = float(src_farm.get("money") or 0)
    loan = float(src_farm.get("loan") or 0)
    tgt_farm.set("money", f"{money:.6f}")
    tgt_farm.set("loan", f"{loan:.6f}")
    return MoneyMigrationResult(src_farm_id, tgt_farm_id, money, loan, applied=True)


def _find_farm(root, farm_id: int):
    return next(
        (f for f in root.findall("farm") if f.get("farmId") == str(farm_id)),
        None,
    )


def migrate_farm_statistics(
    src: Savegame,
    tgt: Savegame,
    src_farm_id: int = 1,
    tgt_farm_id: int = 1,
) -> FarmStatsMigrationResult:
    """Copy the source farm's `<statistics>` block onto the target's, EXCEPT
    per-save ID fields (see STATS_PER_SAVE_FIELDS).

    Element-by-element copy — target-only fields the source doesn't know about
    are preserved (forward-compat with future FS25 patches).
    """
    src_root = src.root("farms.xml")
    tgt_root = tgt.root("farms.xml")
    if src_root is None or tgt_root is None:
        return FarmStatsMigrationResult(src_farm_id, tgt_farm_id, 0)

    src_farm = _find_farm(src_root, src_farm_id)
    tgt_farm = _find_farm(tgt_root, tgt_farm_id)
    if src_farm is None or tgt_farm is None:
        return FarmStatsMigrationResult(src_farm_id, tgt_farm_id, 0)

    src_stats = src_farm.find("statistics")
    if src_stats is None:
        return FarmStatsMigrationResult(src_farm_id, tgt_farm_id, 0)

    tgt_stats = tgt_farm.find("statistics")
    if tgt_stats is None:
        tgt_stats = etree.SubElement(tgt_farm, "statistics")

    # Index target children by tag so we can replace-in-place.
    tgt_by_tag: dict[str, etree._Element] = {}
    for child in list(tgt_stats):
        tgt_by_tag[child.tag] = child

    copied = 0
    skipped: list[str] = []
    for src_child in src_stats:
        tag = src_child.tag
        if tag in STATS_PER_SAVE_FIELDS:
            skipped.append(tag)
            continue
        new_child = copy.deepcopy(src_child)
        existing = tgt_by_tag.get(tag)
        if existing is not None:
            tgt_stats.replace(existing, new_child)
        else:
            tgt_stats.append(new_child)
        tgt_by_tag[tag] = new_child
        copied += 1

    return FarmStatsMigrationResult(
        src_farm_id=src_farm_id,
        tgt_farm_id=tgt_farm_id,
        fields_copied=copied,
        skipped_fields=skipped,
        applied=copied > 0,
    )
