"""Migrate items.xml entries (bales, pallets, standalone world items)."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from lxml import etree

from ..parsers.savegame import Savegame
from .ids import collect_ids, remap_collisions


@dataclass
class ItemMigrationResult:
    moved: int
    remap: dict[str, str]


def migrate_items(
    src: Savegame,
    tgt: Savegame,
    drop_xyz: tuple[float, float, float] | None,
    farm_id: int = 1,
) -> ItemMigrationResult:
    """Append every source item to target items.xml.

    If drop_xyz is provided, all moved items are repositioned around it (small
    grid offset). If None, items keep their original world coordinates (only
    sensible when source and target maps share a coordinate convention — rare).
    """
    src_root = src.root("items.xml")
    if src_root is None:
        return ItemMigrationResult(moved=0, remap={})

    tgt_tree = tgt.tree("items.xml")
    if tgt_tree is None:
        tgt_root = etree.Element("items")
        tgt._trees["items.xml"] = etree.ElementTree(tgt_root)
    else:
        tgt_root = tgt_tree.getroot()

    src_items = list(src_root.findall("item"))
    taken = collect_ids(tgt_root)
    remap = remap_collisions(src_items, taken)

    pitch = 1.5
    moved = 0
    for i, it in enumerate(src_items):
        clone = copy.deepcopy(it)
        old_uid = clone.get("uniqueId")
        if old_uid and old_uid in remap:
            clone.set("uniqueId", remap[old_uid])
        if clone.get("farmId") is not None:
            clone.set("farmId", str(farm_id))

        if drop_xyz is not None:
            row, col = divmod(i, 10)
            new_pos = (
                drop_xyz[0] + (col - 5) * pitch,
                drop_xyz[1],
                drop_xyz[2] + row * pitch,
            )
            clone.set("position", f"{new_pos[0]:.3f} {new_pos[1]:.3f} {new_pos[2]:.3f}")

        tgt_root.append(clone)
        moved += 1

    return ItemMigrationResult(moved=moved, remap=remap)
