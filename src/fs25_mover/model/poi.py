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


SILO_KEYWORDS = ("bunkersilo", "siloband", "silo", "grainsilo", "clamp")
PEN_KEYWORDS = ("cowbarn", "cowbarnparlour", "sheepbarn", "pigbarn", "chickenbarn",
                "horsebarn", "rabbit", "goatbarn", "buffalobarn", "husbandry")
SHOP_KEYWORDS = ("shop", "store", "dealer", "marketplace", "farmersmarket")
SELL_KEYWORDS = ("sellingstation", "grainelevator", "weighingstation", "sell")
PRODUCTION_KEYWORDS = ("production", "bakery", "dairy", "sawmill", "carpenter",
                       "mill", "factory", "bga250kw", "biogas")


CATEGORY_COLOR = {
    "silo":       "#ffd34d",   # yellow
    "pen":        "#66ddff",   # cyan
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
    elif placeable.find(".//bunkerSilo") is not None or placeable.find(".//fillUnit/unit") is not None:
        cat = "silo"
    elif placeable.find(".//sellingStation") is not None:
        cat = "sell"
    elif placeable.find(".//productionPoint") is not None:
        cat = "production"
    else:
        # --- Step 2: keyword fallback ---
        haystack = f"{uid} {filename or ''}".lower()

        def has(words):
            return any(w in haystack for w in words)

        if has(PEN_KEYWORDS):
            cat = "pen"
        elif has(SILO_KEYWORDS):
            cat = "silo"
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
) -> list[PoiMarker]:
    """Walk the savegame's placeables and produce a list of map-space markers."""
    if i3d_positions is None:
        from ..parsers.i3d import positions_for_savegame
        i3d_positions = positions_for_savegame(map_src)
    # Also pull preplaced positions from the map's config/placeables.xml — some
    # maps (e.g. Mechet) declare positions there but not in the i3d.
    config_positions = map_src.preplaced_positions()

    wanted = set(include_categories) if include_categories else None

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
