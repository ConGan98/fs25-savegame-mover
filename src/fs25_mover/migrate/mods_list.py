"""Merge `<mod>` entries from source's careerSavegame.xml into target's.

FS25 records every mod a save depends on as a `<mod modName=... title=...
version=... required=... fileHash=.../>` child of `<careerSavegame>`. When
the game loads a save, it uses this list to prompt the player to activate
missing mods. A fresh target save only lists the map mod, so without this
merge the migrated save loads silently and vehicles/placeables from
source-only mods get dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..parsers.savegame import Savegame


@dataclass
class ModListMergeResult:
    added: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)


def merge_mod_list(src: Savegame, tgt: Savegame) -> ModListMergeResult:
    result = ModListMergeResult()
    src_root = src.root("careerSavegame.xml")
    tgt_root = tgt.root("careerSavegame.xml")
    if src_root is None or tgt_root is None:
        return result

    existing = {
        m.get("modName")
        for m in tgt_root.findall("mod")
        if m.get("modName")
    }

    # Append after the last existing <mod>, or after <foliageTypes> if no mods
    # exist yet — that's where Giants puts them.
    insert_after = None
    for child in tgt_root:
        if child.tag == "mod":
            insert_after = child
    if insert_after is not None:
        anchor_idx = list(tgt_root).index(insert_after) + 1
    else:
        anchor_idx = len(list(tgt_root))

    for src_mod in src_root.findall("mod"):
        name = src_mod.get("modName")
        if not name:
            continue
        if name in existing:
            result.already_present.append(name)
            continue
        from copy import deepcopy
        clone = deepcopy(src_mod)
        tgt_root.insert(anchor_idx, clone)
        anchor_idx += 1
        existing.add(name)
        result.added.append(name)

    return result
