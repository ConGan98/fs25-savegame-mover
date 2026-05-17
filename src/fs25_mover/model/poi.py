"""Resolve a savegame's placeables to map-space markers.

Strategy:
- Preplaced placeables (uniqueId starting with `preplaced_`) have position (0,0,0)
  in the savegame; their real position comes from the map's i3d.
- Player-placed placeables carry their own `position` attribute in the savegame.

Each placeable is classified into one of a small set of POI categories so the
UI can colour-code them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..parsers.map_zip import MapSource
from ..parsers.savegame import Savegame


PEN_KEYWORDS = ("cowbarn", "cowbarnparlour", "sheepbarn", "pigbarn", "chickenbarn",
                "horsebarn", "rabbit", "goatbarn", "buffalobarn", "husbandry")
SHOP_KEYWORDS = ("shop", "store", "dealer", "marketplace", "farmersmarket")
SELL_KEYWORDS = ("sellingstation", "grainelevator", "weighingstation", "sell")
PRODUCTION_KEYWORDS = ("production", "bakery", "dairy", "sawmill", "carpenter",
                       "mill", "factory", "bga250kw", "biogas")


CATEGORY_COLOR = {
    "silo":       "#ffd34d",   # yellow
    "pen":        "#66ddff",   # cyan
    "storage":    "#ff7fbf",   # pink — bale/pallet object-storage sheds
    "shop":       "#ff9966",   # orange
    "sell":       "#aaff88",   # green
    "production": "#cc99ff",   # purple
    "shed":       "#cccccc",   # gray
    "other":      "#999999",
}


@dataclass
class PoiMarker:
    uid: str
    label: str
    category: str
    world_x: float
    world_z: float
    farm_id: int | None


def _has_non_husbandry_storage_node(placeable) -> bool:
    """True when the placeable has a <storage><node/></storage> NOT inside a
    <husbandry> block (i.e. a grain/diesel/fertiliser silo bin)."""
    for storage in placeable.findall(".//storage"):
        if storage.find("node") is None:
            continue
        anc = storage.getparent()
        while anc is not None and anc is not placeable:
            if anc.tag == "husbandry":
                break
            anc = anc.getparent()
        else:
            return True
        if anc is not None and anc.tag == "husbandry":
            continue
    return False


def _classify(placeable, uid: str, filename: str | None) -> tuple[str, str]:
    """Return (category, short_label) for a placeable.

    Classification priority:
      1. Inspect the placeable's children — `<husbandryAnimals>` → pen,
         `<bunkerSilo>` or `<fillUnit>` → silo, `<sellingStation>` → sell,
         `<productionPoint>` → production. This catches non-English names.
      2. Fall back to keyword matching against uniqueId / filename for
         categories that don't have a tell-tale child element (shops, sheds).
    """
    # --- Step 1: structural classification ---
    if placeable.find(".//husbandryAnimals") is not None or placeable.find("husbandry") is not None:
        cat = "pen"
    elif placeable.find(".//objectStorage") is not None:
        # Bale / pallet auto-storage sheds. Classify by element presence
        # (an empty shed on a fresh save still has the element).
        cat = "storage"
    elif (
        placeable.find(".//bunkerSilo") is not None
        or placeable.find(".//fillUnit/unit") is not None
        or placeable.find("silo") is not None
        or _has_non_husbandry_storage_node(placeable)
    ):
        cat = "silo"
    elif placeable.find(".//sellingStation") is not None:
        cat = "sell"
    elif placeable.find(".//productionPoint") is not None:
        cat = "production"
    else:
        # --- Step 2: keyword fallback ---
        # NOTE: silo / clamp keywords are deliberately NOT used here because
        # they produce false positives — many decorative mod placeables ship
        # under names like `bunkerSiloPack/deko1.xml`, `placeableSiloDeco/...`,
        # `manureClamp01.xml` etc. and have no actual storage. Real silos are
        # already caught structurally above, or via the placeable-type XML
        # declaration check in parsers/fs25_root.py.
        haystack = f"{uid} {filename or ''}".lower()

        def has(words):
            return any(w in haystack for w in words)

        if has(PEN_KEYWORDS):
            cat = "pen"
        elif has(SELL_KEYWORDS):
            cat = "sell"
        elif has(PRODUCTION_KEYWORDS):
            cat = "production"
        elif has(SHOP_KEYWORDS):
            cat = "shop"
        elif "shed" in haystack or "garage" in haystack:
            cat = "shed"
        else:
            cat = "other"

    # Build a short label.
    if uid.startswith("preplaced_"):
        rest = uid[len("preplaced_"):]
        if len(rest) > 33 and rest[-33] == "_":
            rest = rest[:-33]
        label = rest
    elif filename:
        tail = filename.rsplit("/", 1)[-1]
        label = tail.rsplit(".", 1)[0]
    else:
        label = uid[:16]
    return cat, label


def resolve_pois(
    sg: Savegame,
    map_src: MapSource,
    i3d_positions: dict[str, tuple[float, float, float]] | None = None,
    include_categories: Iterable[str] | None = None,
    mods_dir=None,
    install_dir=None,
    pretty_names: bool = True,
) -> list[PoiMarker]:
    """Walk the savegame's placeables and produce a list of map-space markers.

    When `pretty_names=True` and `mods_dir`/`install_dir` are provided, the
    label for each silo / pen / storage POI is replaced with the placeable
    type's storeData name (variant-aware via `<baseConfiguration>`). This is
    the friendly name the user sees in-game.
    """
    if i3d_positions is None:
        from ..parsers.i3d import positions_for_savegame
        i3d_positions = positions_for_savegame(map_src)
    # Also pull preplaced positions from the map's config/placeables.xml — some
    # maps (e.g. Mechet) declare positions there but not in the i3d.
    config_positions = map_src.preplaced_positions()
    # i3d xmlFilename per uniqueId (preplaced placeables don't have a filename
    # attribute on the savegame entry — the i3d has it).
    i3d_filenames: dict[str, str] = {}
    if pretty_names:
        from ..parsers.i3d import filenames_for_savegame
        try:
            i3d_filenames = filenames_for_savegame(map_src)
        except Exception:
            i3d_filenames = {}

    wanted = set(include_categories) if include_categories else None

    # Cache type-XML reads per filename so a map with hundreds of placeables
    # doesn't reread the same zip entry over and over.
    from ..parsers.fs25_root import (
        placeable_friendly_name as _friendly,
        read_placeable_xml_bytes as _read_xml,
    )
    xml_cache: dict[str, bytes | None] = {}
    map_path = getattr(map_src, "path", None)

    def _pretty_label(p, uid: str, filename: str | None, default_label: str) -> str:
        if not pretty_names:
            return default_label
        fn = filename or i3d_filenames.get(uid)
        if not fn:
            return default_label
        if fn in xml_cache:
            data = xml_cache[fn]
        else:
            data = _read_xml(fn, mods_dir, install_dir, map_path)
            xml_cache[fn] = data
        return _friendly(data, p) or default_label

    out: list[PoiMarker] = []
    for p in sg.placeables():
        uid = p.get("uniqueId") or ""
        filename = p.get("filename")
        try:
            farm_id = int(p.get("farmId")) if p.get("farmId") else None
        except ValueError:
            farm_id = None

        # Resolve position from three sources, in order of trust:
        # 1. i3d TransformGroup (most authoritative — actual scene position)
        # 2. map's config/placeables.xml (declared preplaced positions)
        # 3. the placeable's own `position` attribute (player-placed)
        pos = i3d_positions.get(uid) or config_positions.get(uid)
        if pos is None:
            attr = p.get("position")
            if attr:
                parts = attr.split()
                if len(parts) == 3:
                    try:
                        x, y, z = (float(parts[0]), float(parts[1]), float(parts[2]))
                        if (x, y, z) != (0.0, 0.0, 0.0):
                            pos = (x, y, z)
                    except ValueError:
                        pass
        if pos is None:
            continue

        cat, label = _classify(p, uid, filename)
        if wanted is not None and cat not in wanted:
            continue
        # Only resolve friendly names for categories whose markers carry
        # labels worth dressing up (silo / pen / storage / shop). Sheds and
        # "other" stay as raw filename basenames — cheaper, and they're
        # hidden behind the category-toggle row anyway.
        if cat in {"silo", "pen", "storage", "shop", "sell", "production"}:
            label = _pretty_label(p, uid, filename, label)
        out.append(
            PoiMarker(
                uid=uid,
                label=label,
                category=cat,
                world_x=pos[0],
                world_z=pos[2],
                farm_id=farm_id,
            )
        )
    return out
