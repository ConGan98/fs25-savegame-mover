"""Copy player-placed `<placeable>` entries from source into target.

Only safe in **same-map** mode, because source coordinates are valid only if
the target uses the same world geometry. Cross-map calls should not enable
this — placeables would land at source-map coords on different terrain.

The whole `<placeable>` subtree is copied verbatim (animals, husbandry food,
silo content, objectStorage bales — all already inside). Subsequent
silo/animal/storage merges in the engine detect the resulting
"source-uid == target-uid" identity mapping and skip merging so content
isn't doubled.
"""
from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, field

from lxml import etree

from ..parsers.savegame import Savegame
from .ids import collect_ids


@dataclass
class PlaceableCopyResult:
    copied_uids: set[str] = field(default_factory=set)
    skipped_already_present: int = 0
    skipped_wrong_farm: int = 0
    skipped_preplaced: int = 0


def copy_player_placeables(
    src: Savegame,
    tgt: Savegame,
    src_farm_id: int = 1,
    tgt_farm_id: int = 1,
) -> PlaceableCopyResult:
    """Append source's player-placed placeables to the target's placeables.xml.

    Filters:
      - Skip preplaced placeables (uid prefix `preplaced_` or
        `isPreplaced="true"`) — those are map-provided and already exist in
        the target by definition.
      - Only copy entries with `farmId == src_farm_id`.
      - Skip any uid that already exists in target (defensive — shouldn't
        happen for player-placed in same-map, but cheap to check).
    """
    result = PlaceableCopyResult()
    src_root = src.root("placeables.xml")
    tgt_root = tgt.root("placeables.xml")
    if src_root is None or tgt_root is None:
        return result

    taken: set[str] = collect_ids(tgt_root)
    src_farm_str = str(src_farm_id)
    tgt_farm_str = str(tgt_farm_id)

    for p in src_root.findall("placeable"):
        uid = p.get("uniqueId") or ""
        if uid.startswith("preplaced_") or p.get("isPreplaced") == "true":
            result.skipped_preplaced += 1
            continue
        if p.get("farmId") != src_farm_str:
            result.skipped_wrong_farm += 1
            continue
        if uid and uid in taken:
            result.skipped_already_present += 1
            continue
        clone = _copy.deepcopy(p)
        # Re-stamp farmId in case source farm-id differs from target's.
        clone.set("farmId", tgt_farm_str)
        # Re-stamp farmId attribute on every nested element that carries one
        # (storage farmId, husbandry storage farmId, animal farmId, etc.).
        for el in clone.iter():
            if el.get("farmId") == src_farm_str:
                el.set("farmId", tgt_farm_str)
        tgt_root.append(clone)
        if uid:
            taken.add(uid)
            result.copied_uids.add(uid)

    return result
