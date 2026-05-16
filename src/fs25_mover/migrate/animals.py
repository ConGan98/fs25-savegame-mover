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
    # Per-pen production-state transfer: tgt_uid -> {fillType -> level moved}.
    storage_moved: dict[str, dict[str, float]] = field(default_factory=dict)


def migrate_animals(
    src: Savegame,
    tgt: Savegame,
    pen_mapping: dict[str, str],
    farm_id: int = 1,
    include_husbandry_storage: bool = True,
) -> AnimalMigrationResult:
    """Move animals and (optionally) production state between mapped pens.

    `include_husbandry_storage` controls whether the source husbandry's
    `<storage>` children (slurry / straw / manure / milk fill levels) are
    merged into the target husbandry. When False, only animals move; the
    target keeps its existing (usually zero) production state.
    """
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

        # --- Husbandry production state (slurry / straw / manure / milk) ---
        if include_husbandry_storage:
            src_husb = src_pen.find(".//husbandry")
            tgt_husb = tgt_pen.find(".//husbandry")
            if src_husb is not None and tgt_husb is not None:
                moved_levels = _merge_husbandry_storage(src_husb, tgt_husb, farm_id)
                if moved_levels:
                    result.storage_moved[tgt_uid] = moved_levels

    return result


def _merge_husbandry_storage(
    src_husb: etree._Element,
    tgt_husb: etree._Element,
    farm_id: int,
) -> dict[str, float]:
    """Merge `<storage><node fillType=... fillLevel=.../></storage>` levels from
    source into target. Returns {fillType -> level merged}.
    """
    src_storage = src_husb.find("storage")
    if src_storage is None:
        return {}

    tgt_storage = tgt_husb.find("storage")
    if tgt_storage is None:
        tgt_storage = etree.SubElement(tgt_husb, "storage", farmId=str(farm_id))
    else:
        tgt_storage.set("farmId", str(farm_id))

    moved: dict[str, float] = {}
    # Index target nodes by fillType so we can merge fillLevels per type.
    tgt_nodes_by_ft = {
        n.get("fillType"): n for n in tgt_storage.findall("node")
    }
    for src_node in src_storage.findall("node"):
        ft = src_node.get("fillType")
        try:
            src_level = float(src_node.get("fillLevel") or 0)
        except ValueError:
            continue
        if not ft or src_level <= 0:
            continue
        tgt_node = tgt_nodes_by_ft.get(ft)
        if tgt_node is None:
            tgt_node = etree.SubElement(tgt_storage, "node", fillType=ft, fillLevel="0")
            tgt_nodes_by_ft[ft] = tgt_node
        try:
            cur = float(tgt_node.get("fillLevel") or 0)
        except ValueError:
            cur = 0.0
        tgt_node.set("fillLevel", f"{cur + src_level:.6f}")
        moved[ft] = moved.get(ft, 0.0) + src_level
    return moved
