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

    # Source: only pens that actually have animals to move.
    src_pens = {
        p.get("uniqueId"): p
        for p in src.placeables()
        if p.find(".//husbandryAnimals") is not None
    }
    # Target: look up by uniqueId across ALL placeables. An empty / just-placed
    # husbandry might not have <husbandryAnimals> persisted yet — we'll create
    # the element on demand, same as we do for <objectStorage>.
    tgt_all = {p.get("uniqueId"): p for p in tgt.placeables()}

    for src_uid, tgt_uid in pen_mapping.items():
        src_pen = src_pens.get(src_uid)
        tgt_pen = tgt_all.get(tgt_uid)
        if src_pen is None or tgt_pen is None:
            result.unmatched_src_pens.append(src_uid)
            continue

        src_ha = src_pen.find(".//husbandryAnimals")
        if src_ha is None:
            result.unmatched_src_pens.append(src_uid)
            continue
        tgt_ha = tgt_pen.find(".//husbandryAnimals")
        if tgt_ha is None:
            tgt_ha = etree.SubElement(tgt_pen, "husbandryAnimals")

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

        # --- Husbandry state migration ---
        # FS25 spreads husbandry content across THREE separate elements:
        #   <husbandry><storage><node>           — STRAW, MILK, MANURE, LIQUIDMANURE, WATER
        #   <husbandryFood><fillLevel>            — SILAGE, FORAGE, GRAIN, TMR (the food bars)
        #   <husbandryMeadow><fillType>           — GRASS_WINDROW pasture grass
        # plus productionFactor / globalProductionFactor on <husbandry> which
        # drive whether the husbandry actually consumes/produces.
        if include_husbandry_storage:
            moved_total: dict[str, float] = {}

            src_husb = src_pen.find(".//husbandry")
            if src_husb is not None:
                tgt_husb = tgt_pen.find(".//husbandry")
                if tgt_husb is None:
                    tgt_husb = etree.SubElement(tgt_pen, "husbandry")
                for attr in ("productionFactor", "globalProductionFactor"):
                    val = src_husb.get(attr)
                    if val is not None:
                        tgt_husb.set(attr, val)
                for ft, lvl in _merge_husbandry_storage(src_husb, tgt_husb, farm_id).items():
                    moved_total[ft] = moved_total.get(ft, 0.0) + lvl

            # <husbandryFood> — actual food levels (silage, forage, grain, ...)
            src_food = src_pen.find("husbandryFood")
            if src_food is not None:
                tgt_food = tgt_pen.find("husbandryFood")
                if tgt_food is None:
                    tgt_food = etree.SubElement(tgt_pen, "husbandryFood")
                for src_fl in src_food.findall("fillLevel"):
                    ft = src_fl.get("fillType")
                    try:
                        lvl = float(src_fl.get("fillLevel") or 0)
                    except ValueError:
                        continue
                    if not ft or lvl <= 0:
                        continue
                    tgt_fl = next(
                        (f for f in tgt_food.findall("fillLevel")
                         if f.get("fillType") == ft),
                        None,
                    )
                    if tgt_fl is None:
                        etree.SubElement(tgt_food, "fillLevel",
                                         fillType=ft, fillLevel=f"{lvl:.6f}")
                    else:
                        cur = float(tgt_fl.get("fillLevel") or 0)
                        tgt_fl.set("fillLevel", f"{cur + lvl:.6f}")
                    moved_total[ft] = moved_total.get(ft, 0.0) + lvl

            # <husbandryMeadow> — pasture grass. Target keeps its own capacity
            # (tied to the placeable's meadow area on the new map); we just
            # carry the fillLevel.
            src_meadow = src_pen.find("husbandryMeadow")
            if src_meadow is not None:
                tgt_meadow = tgt_pen.find("husbandryMeadow")
                if tgt_meadow is None:
                    tgt_meadow = etree.SubElement(tgt_pen, "husbandryMeadow")
                for src_fl in src_meadow.findall("fillType"):
                    name = src_fl.get("name")
                    try:
                        lvl = float(src_fl.get("fillLevel") or 0)
                    except ValueError:
                        continue
                    if not name or lvl <= 0:
                        continue
                    tgt_fl = next(
                        (f for f in tgt_meadow.findall("fillType")
                         if f.get("name") == name),
                        None,
                    )
                    if tgt_fl is None:
                        new = etree.SubElement(tgt_meadow, "fillType",
                                               name=name, fillLevel=f"{lvl:.6f}")
                        # Carry capacity if source had one (target may not).
                        cap = src_fl.get("capacity")
                        if cap is not None:
                            new.set("capacity", cap)
                    else:
                        cur = float(tgt_fl.get("fillLevel") or 0)
                        try:
                            cap = float(tgt_fl.get("capacity") or 0)
                        except ValueError:
                            cap = 0
                        new_lvl = cur + lvl
                        # Respect target's declared capacity if set.
                        if cap > 0:
                            new_lvl = min(new_lvl, cap)
                        tgt_fl.set("fillLevel", f"{new_lvl:.6f}")
                    moved_total[name] = moved_total.get(name, 0.0) + lvl

            if moved_total:
                result.storage_moved[tgt_uid] = moved_total

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
