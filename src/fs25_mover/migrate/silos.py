"""Migrate stored grain / silo contents.

Two distinct storage shapes:

1. Bunker silo (silage): <placeable><bunkerSilo state fillLevel fermentingTime .../></placeable>
   - Content type is implicit (silage). state determines fermenting/finished.
   - Strategy: add source fillLevel to target bunkerSilo, preserve target state
     unless target is empty (state=0) — in which case adopt source state +
     fermentingTime so the silage doesn't reset its fermenting clock.

2. Storage silo (loose grain): <placeable>...<fillUnit><unit fillType="WHEAT" fillLevel=.../></fillUnit></placeable>
   - Content type explicit, multiple unit entries possible.
   - Strategy: for each source unit, find a matching unit in the target placeable
     (by fillType) and add to its fillLevel; if none exists, append a new unit.

Mapping is uniqueId -> uniqueId per silo pair. Caller decides which source maps
to which target.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from ..parsers.savegame import Savegame


@dataclass
class SiloMigrationResult:
    bunker_moves: list[tuple[str, str, float]] = field(default_factory=list)  # (src_uid, tgt_uid, level)
    fillunit_moves: list[tuple[str, str, str, float]] = field(default_factory=list)  # (src, tgt, fillType, level)
    skipped: list[str] = field(default_factory=list)
    # Bunkers we deliberately did NOT migrate, with how much silage was abandoned per source placeable.
    bunkers_abandoned: list[tuple[str, float]] = field(default_factory=list)


def migrate_silos(
    src: Savegame,
    tgt: Savegame,
    silo_mapping: dict[str, str],
) -> SiloMigrationResult:
    """Migrate grain storage. Bunker silos (silage) are NOT migrated — the
    visual silage mound is runtime physics state that XML alone can't recreate,
    and source/target bunker dimensions differ. Source bunker silage is
    reported as abandoned so the user can be warned to consume it pre-migration.

    Only `<fillUnit><unit fillType=.../></fillUnit>` grain storage is migrated.
    """
    result = SiloMigrationResult()

    src_by_uid = {p.get("uniqueId"): p for p in src.placeables()}
    tgt_by_uid = {p.get("uniqueId"): p for p in tgt.placeables()}

    # Report abandoned bunker silage across the whole source (not just mapped ones).
    for sp in src.placeables():
        for bs in sp.findall(".//bunkerSilo"):
            lvl = float(bs.get("fillLevel") or 0)
            if lvl > 0:
                result.bunkers_abandoned.append((sp.get("uniqueId") or "", lvl))

    for src_uid, tgt_uid in silo_mapping.items():
        src_p = src_by_uid.get(src_uid)
        tgt_p = tgt_by_uid.get(tgt_uid)
        if src_p is None or tgt_p is None:
            result.skipped.append(src_uid)
            continue

        # --- <fillUnit><unit/></fillUnit> grain storage (older shape) ---
        src_fu = src_p.find(".//fillUnit")
        tgt_fu = tgt_p.find(".//fillUnit")
        if src_fu is not None:
            if tgt_fu is None:
                tgt_fu = etree.SubElement(tgt_p, "fillUnit")
            for src_unit in src_fu.findall("unit"):
                ft = src_unit.get("fillType")
                src_level = float(src_unit.get("fillLevel") or 0)
                if not ft or src_level <= 0:
                    continue
                tgt_unit = next(
                    (u for u in tgt_fu.findall("unit") if u.get("fillType") == ft),
                    None,
                )
                if tgt_unit is None:
                    tgt_unit = etree.SubElement(tgt_fu, "unit")
                    tgt_unit.set("fillType", ft)
                    if src_unit.get("index") is not None:
                        tgt_unit.set("index", src_unit.get("index"))
                    tgt_unit.set("fillLevel", f"{src_level:.6f}")
                else:
                    cur = float(tgt_unit.get("fillLevel") or 0)
                    tgt_unit.set("fillLevel", f"{cur + src_level:.6f}")
                result.fillunit_moves.append((src_uid, tgt_uid, ft, src_level))

        # --- <silo><storage><node/></storage></silo> grain storage (FS25 shape) ---
        # Skip husbandries — their storage holds slurry/feed and is migrated by
        # the animal-pen path.
        for src_storage in _silo_storages(src_p):
            tgt_storage = _ensure_silo_storage_match(tgt_p, src_storage)
            if tgt_storage is None:
                continue
            tgt_nodes_by_ft = {n.get("fillType"): n for n in tgt_storage.findall("node")}
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
                    tgt_node = etree.SubElement(tgt_storage, "node",
                                                fillType=ft, fillLevel="0")
                    tgt_nodes_by_ft[ft] = tgt_node
                try:
                    cur = float(tgt_node.get("fillLevel") or 0)
                except ValueError:
                    cur = 0.0
                tgt_node.set("fillLevel", f"{cur + src_level:.6f}")
                result.fillunit_moves.append((src_uid, tgt_uid, ft, src_level))

    return result


def _silo_storages(placeable: etree._Element):
    """Yield every `<storage>` element under a placeable that represents a silo
    bin (i.e. NOT inside a husbandry). Each yielded element contains <node>
    fillType / fillLevel children."""
    for storage in placeable.findall(".//storage"):
        # Walk up parents to confirm it's not under <husbandry>.
        ancestor = storage.getparent()
        in_husbandry = False
        while ancestor is not None and ancestor is not placeable:
            if ancestor.tag == "husbandry":
                in_husbandry = True
                break
            ancestor = ancestor.getparent()
        if in_husbandry:
            continue
        yield storage


def _ensure_silo_storage_match(target: etree._Element, src_storage: etree._Element):
    """Find a target <storage> with the same `index` as src (or first if no
    index attr), or create one alongside the source's parent shape. Returns
    None when we can't safely create a matching target (no <silo> parent)."""
    src_index = src_storage.get("index")
    candidates = list(_silo_storages(target))
    if src_index is not None:
        for c in candidates:
            if c.get("index") == src_index:
                return c
    elif candidates:
        return candidates[0]
    # Nothing to merge into — only create when target has a <silo> parent to
    # host the new storage block, otherwise the file shape would be invalid.
    silo_parent = target.find("silo")
    if silo_parent is None:
        return None
    new_storage = etree.SubElement(silo_parent, "storage")
    if src_index is not None:
        new_storage.set("index", src_index)
    if src_storage.get("farmId") is not None:
        new_storage.set("farmId", src_storage.get("farmId"))
    return new_storage
