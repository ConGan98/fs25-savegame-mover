"""Detect mod-specific savegame files and classify them by safety to migrate.

When the user moves a farm between maps, mod-added XML files in the source
save (e.g. RedTape policies, Realistic Livestock animal genetics) aren't part
of the standard FS25 schema. Some are pure farm-state and follow the farm
naturally; others are tied to the source map's terrain and would break on a
new map. This module enumerates what's in a savegame folder and tags each
file with a safety category so the wizard can show a sensible default per file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Category = Literal["safe", "terrain", "unknown", "binary_map"]


@dataclass
class ModFile:
    name: str
    category: Category
    note: str
    default_include: bool
    size_bytes: int = 0


# Files written by the FS25 base game / DLC. Anything else is mod- or
# user-data and is a candidate for the mod-file migration pass. Standard
# XMLs are migrated through the in-memory tree path in `parsers/savegame.py`
# so we skip them here.
FS25_STANDARD_FILES: set[str] = {
    "careerSavegame.xml",
    "vehicles.xml",
    "items.xml",
    "placeables.xml",
    "farms.xml",
    "economy.xml",
    "environment.xml",
    "farmland.xml",
    "fields.xml",
    "handTools.xml",
    "missions.xml",
    "navigationSystem.xml",
    "onCreateObjects.xml",
    "players.xml",
    "sales.xml",
    "densityMapHeight.xml",
    "densityMap_fruits_growthState.xml",
    "snow_state.xml",
    "stone_growthState.xml",
    "weed_growthState.xml",
    "guidedTour.xml",
}

# Per-filename registry: filename -> (category, user-facing note, default_include).
KNOWN_MOD_FILES: dict[str, tuple[Category, str, bool]] = {
    # --- Farm-state mod XMLs — safe to carry across maps ---
    "RedTape.xml": (
        "safe", "RedTape — policies, schemes, tax history", True,
    ),
    "rm_RlAnimalSystem.xml": (
        "safe", "Realistic Livestock — animal genetics keyed by uniqueId", True,
    ),
    "rm_RlSettings.xml": (
        "safe", "Realistic Livestock — mod settings", True,
    ),
    "FS25_UnloadBalesEarly.xml": (
        "safe", "Unload Bales Early — mod settings", True,
    ),
    "easyDevControls.xml": (
        "safe", "Easy Dev Controls — debug settings", True,
    ),

    # --- Tied to source map terrain — break on a new map ---
    "Courseplay.xml": (
        "terrain", "Courseplay courses (world-coord waypoints — break on new map)", False,
    ),
    "CpAssignedCourses.xml": (
        "terrain", "Courseplay assigned courses", False,
    ),
    "AutoDrive_config.xml": (
        "terrain", "AutoDrive config", False,
    ),
    "AutoDriveUsersData.xml": (
        "terrain", "AutoDrive routes (world-coord waypoints — break on new map)", False,
    ),
    "precisionFarming.xml": (
        "terrain", "Precision Farming field state (fieldIds differ between maps)", False,
    ),
    "mapObjectsHider.xml": (
        "terrain", "Hidden map decorations (tied to source map geometry)", False,
    ),
    "treePlant.xml": (
        "terrain", "Planted tree positions (world coords)", False,
    ),
    "treeMarker.xml": (
        "terrain", "Tree markers (world coords)", False,
    ),
    "cropRotationPlanner.xml": (
        "terrain", "Crop rotation per fieldId (fieldIds differ)", False,
    ),
    "npc.xml": (
        "terrain", "NPC schedules / state", False,
    ),
}

# Filename-prefix / suffix patterns for binary terrain-bound maps and
# auto-generated game caches that should never be offered for migration.
_BINARY_MAP_SUFFIXES: tuple[str, ...] = (
    ".grle", ".gdm", ".dgm",
    ".cache",      # terrain.lod.type.cache / terrain.nmap.cache / terrain.occluders.cache
    ".gmss",       # split-shapes binary
)
_BINARY_MAP_PREFIXES: tuple[str, ...] = (
    "densityMap_",
    "infoLayer_",
    "precisionFarming_",
    "fallowStateMap",
    "historyStateMap",
    "catchCropMap",
    "terrain.",         # terrain.heightmap.png / terrain.*.cache
    "vehicleNavigationCostmap",
)
# Specific filenames to always hide (not terrain-bound by name pattern).
_BINARY_MAP_EXACT: set[str] = {
    "steam_autocloud.vdf",  # Steam cloud sync metadata
}


def detect_mod_files(savegame_dir: Path | str) -> list[ModFile]:
    """Walk a savegame folder and return one `ModFile` entry per file that
    isn't a base-game standard. Binary terrain maps are included with
    category `binary_map` so callers can summarise; they should NOT be
    offered for migration."""
    root = Path(savegame_dir)
    if not root.is_dir():
        return []
    out: list[ModFile] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_file():
            continue
        name = child.name
        if name in FS25_STANDARD_FILES:
            continue
        size = 0
        try:
            size = child.stat().st_size
        except OSError:
            pass
        # Binary terrain maps / auto-generated caches — never migrate.
        lower = name.lower()
        if (
            name in _BINARY_MAP_EXACT
            or any(lower.endswith(suf) for suf in _BINARY_MAP_SUFFIXES)
            or any(name.startswith(pre) for pre in _BINARY_MAP_PREFIXES)
        ):
            out.append(ModFile(
                name=name, category="binary_map",
                note="binary terrain map / cache — tied to source map, can't migrate",
                default_include=False, size_bytes=size,
            ))
            continue
        # Registered mod file?
        known = KNOWN_MOD_FILES.get(name)
        if known is not None:
            cat, note, default_inc = known
            out.append(ModFile(
                name=name, category=cat, note=note,
                default_include=default_inc, size_bytes=size,
            ))
            continue
        # Unknown — show but default off.
        out.append(ModFile(
            name=name, category="unknown",
            note="unrecognised mod file — leave off unless you know what it does",
            default_include=False, size_bytes=size,
        ))
    return out


def default_includes(detected: list[ModFile], include_terrain: bool = False) -> list[str]:
    """Filenames whose `default_include` is True. Useful for seeding the
    wizard's initial mod_file_includes list when the page first opens.

    When `include_terrain=True` (same-map version upgrade), terrain-bound
    files (Courseplay courses, AutoDrive routes, precisionFarming etc.) are
    also included — they survive a same-map upgrade because the world hasn't
    changed."""
    out: list[str] = []
    for m in detected:
        if m.category == "binary_map":
            continue
        if m.default_include or (include_terrain and m.category == "terrain"):
            out.append(m.name)
    return out
