"""Migrate animals from source husbandries to target husbandries.

Mapping is by uniqueId: caller supplies {src_placeable_uid -> tgt_placeable_uid}.
For each pair, we copy every <animal> from source <husbandryAnimals><clusters>
into the target's. Animal `farmId` is rewritten to the target farm.

We do NOT touch the husbandry's storage / pregnancy meters — those live on the
target placeable and stay as-is.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from lxml import etree

from ..parsers.savegame import Savegame


@dataclass
class AnimalMigrationResult:
    moved_by_pen: dict[str, int] = field(default_factory=dict)
    unmatched_src_pens: list[str] = field(default_factory=list)
    total_moved: int = 0


def migrate_animals(
    src: Savegame,
    tgt: Savegame,
    pen_mapping: dict[str, str],
    farm_id: int = 1,
) -> AnimalMigrationResult:
    result = AnimalMigrationResult()

    src_pens = {
        p.get("uniqueId"): p
        for p in src.placeables()
        if p.find(".//husbandryAnimals") is not None
    }
    tgt_pens = {
        p.get("uniqueId"): p
        for p in tgt.placeables()
        if p.find(".//husbandryAnimals") is not None
    }

    for src_uid, tgt_uid in pen_mapping.items():
        src_pen = src_pens.get(src_uid)
        tgt_pen = tgt_pens.get(tgt_uid)
        if src_pen is None or tgt_pen is None:
            result.unmatched_src_pens.append(src_uid)
            continue

        src_ha = src_pen.find(".//husbandryAnimals")
        tgt_ha = tgt_pen.find(".//husbandryAnimals")
        if src_ha is None or tgt_ha is None:
            result.unmatched_src_pens.append(src_uid)
            continue

        tgt_clusters = tgt_ha.find("clusters")
        if tgt_clusters is None:
            tgt_clusters = etree.SubElement(tgt_ha, "clusters")

        moved = 0
        for animal in src_ha.findall(".//animal"):
            clone = copy.deepcopy(animal)
            clone.set("farmId", str(farm_id))
            tgt_clusters.append(clone)
            moved += int(clone.get("numAnimals") or 1)

        result.moved_by_pen[tgt_uid] = moved
        result.total_moved += moved

    return result
