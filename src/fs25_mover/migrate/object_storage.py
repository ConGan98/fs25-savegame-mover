"""Migrate `<objectStorage>` contents between bale / pallet auto-storage sheds.

Source placeables that have an `<objectStorage>` block can contain:
  * <object className="Bale" ...>   — straw, hay, silage, dryGrass bales etc.
  * <object className="Vehicle" filename="...fillablePallet.xml" ...> — pallets,
    big bags, crop boxes. Carry their own fillType/fillLevel and config children.

Mapping is by uniqueId: caller supplies {src_placeable_uid -> tgt_placeable_uid}.
For each pair, we deep-copy every `<object>` from the source storage into the
target storage, rewriting `farmId` to the target farm. The target's existing
objects are preserved (additive merge).
"""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass, field

from lxml import etree

from ..parsers.savegame import Savegame


@dataclass
class ObjectStorageMigrationResult:
    moved_by_target: dict[str, int] = field(default_factory=dict)
    # Per-target tally of fillType -> count moved (bales/pallets combined).
    fill_types_by_target: dict[str, dict[str, int]] = field(default_factory=dict)
    unmatched_src: list[str] = field(default_factory=list)
    total_moved: int = 0


def migrate_object_storage(
    src: Savegame,
    tgt: Savegame,
    storage_mapping: dict[str, str],
    farm_id: int = 1,
) -> ObjectStorageMigrationResult:
    result = ObjectStorageMigrationResult()

    src_storage = {
        p.get("uniqueId"): p
        for p in src.placeables()
        if p.find(".//objectStorage") is not None
    }
    tgt_storage = {
        p.get("uniqueId"): p
        for p in tgt.placeables()
        if p.find(".//objectStorage") is not None
    }

    for src_uid, tgt_uid in storage_mapping.items():
        sp = src_storage.get(src_uid)
        tp = tgt_storage.get(tgt_uid)
        if sp is None or tp is None:
            result.unmatched_src.append(src_uid)
            continue

        src_os = sp.find(".//objectStorage")
        tgt_os = tp.find(".//objectStorage")
        if src_os is None:
            continue
        if tgt_os is None:
            tgt_os = etree.SubElement(tp, "objectStorage")

        moved = 0
        ft_counter: Counter = Counter()
        for obj in src_os.findall("object"):
            clone = copy.deepcopy(obj)
            if clone.get("farmId") is not None:
                clone.set("farmId", str(farm_id))
            tgt_os.append(clone)
            moved += 1
            ft = clone.get("fillType") or "?"
            ft_counter[ft] += 1
        if moved:
            result.moved_by_target[tgt_uid] = moved
            result.fill_types_by_target[tgt_uid] = dict(ft_counter)
            result.total_moved += moved

    return result
