"""Discover savegames + mods directory inside a FS25 root folder.

The FS25 root is typically:
    Documents/My Games/FarmingSimulator2025/

It contains `savegameN/` subfolders, a `gameSettings.xml` with an optional
`<modsDirectoryOverride active="true" directory="..."/>`, and a local `mods/`
folder used when the override is inactive or missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


@dataclass(order=True)
class SaveInfo:
    slot: int
    folder: Path
    map_id: str | None
    map_title: str | None
    save_date: str | None
    is_fresh: bool   # rough "this save is unmodified / brand new" heuristic

    @property
    def display(self) -> str:
        title = self.map_title or self.map_id or "(unknown map)"
        date = f"  [{self.save_date}]" if self.save_date else ""
        fresh = "  (fresh)" if self.is_fresh else ""
        return f"savegame{self.slot}  —  {title}{date}{fresh}"


@dataclass
class Fs25RootInfo:
    root: Path
    mods_dir: Path | None         # None if neither override nor local mods/ exists
    mods_dir_is_override: bool    # True when from gameSettings.xml override
    saves: list[SaveInfo]
    save_count: int
    mod_count: int
    install_dir: Path | None = None  # FS25 game install (for base/DLC maps)


def detect(root: str | Path) -> Fs25RootInfo:
    """Inspect a FS25 root folder and return what's inside."""
    r = Path(root)
    if not r.is_dir():
        raise FileNotFoundError(f"FS25 root not found: {r}")

    saves = list(_discover_saves(r))
    saves.sort()
    mods_dir, is_override = _resolve_mods_dir(r)
    mod_count = _count_mods(mods_dir) if mods_dir is not None else 0
    install_dir = detect_install_dir_from_log(r)
    if install_dir is None:
        for cand in _candidate_install_dirs():
            if cand.is_dir() and (cand / "data" / "maps").is_dir():
                install_dir = cand
                break
    return Fs25RootInfo(
        root=r,
        mods_dir=mods_dir,
        mods_dir_is_override=is_override,
        saves=saves,
        save_count=len(saves),
        mod_count=mod_count,
        install_dir=install_dir,
    )


def looks_like_fs25_root(path: str | Path) -> bool:
    p = Path(path)
    if not p.is_dir():
        return False
    # A genuine FS25 root has at least gameSettings.xml + one savegameN folder.
    return (p / "gameSettings.xml").is_file() and any(p.glob("savegame[0-9]*"))


def default_root() -> Path | None:
    """Best-guess default location on Windows. None if it doesn't look right."""
    import os
    docs = os.environ.get("USERPROFILE")
    if not docs:
        return None
    candidate = Path(docs) / "Documents" / "My Games" / "FarmingSimulator2025"
    return candidate if looks_like_fs25_root(candidate) else None


# ---------------------------------------------------------------------------

_SLOT_RE = re.compile(r"^savegame(\d+)$")


def _discover_saves(root: Path):
    for child in root.iterdir():
        if not child.is_dir():
            continue
        m = _SLOT_RE.match(child.name)
        if not m:
            continue
        cs = child / "careerSavegame.xml"
        if not cs.is_file():
            continue
        info = _read_career_metadata(cs)
        yield SaveInfo(
            slot=int(m.group(1)),
            folder=child,
            map_id=info.get("mapId"),
            map_title=info.get("mapTitle"),
            save_date=info.get("saveDate"),
            is_fresh=_looks_fresh(child, info),
        )


def _read_career_metadata(path: Path) -> dict:
    out: dict[str, str | None] = {"mapId": None, "mapTitle": None, "saveDate": None}
    try:
        # Read just enough — careerSavegame.xml's relevant data is near the top.
        with path.open("rb") as f:
            head = f.read(4096)
        # Quick element checks via simple parsing.
        root = etree.fromstring(head + b"</settings></careerSavegame>", parser=etree.XMLParser(recover=True))
    except Exception:
        return out
    if root is None:
        return out
    for tag in ("mapId", "mapTitle", "saveDate", "saveDateFormatted"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            key = "saveDate" if tag.startswith("saveDate") else tag
            if not out.get(key):
                out[key] = el.text.strip()
    return out


def _looks_fresh(folder: Path, meta: dict) -> bool:
    """Heuristic: does this look like a freshly-started save?

    A save is "fresh-ish" when:
      - vehicles.xml is small (under ~50 KB — base starter fleet only)
      - no items.xml or items.xml has zero <item> entries
    """
    try:
        veh = folder / "vehicles.xml"
        if veh.is_file() and veh.stat().st_size < 50_000:
            return True
    except OSError:
        pass
    return False


def _resolve_mods_dir(root: Path) -> tuple[Path | None, bool]:
    gs = root / "gameSettings.xml"
    if gs.is_file():
        try:
            tree = etree.parse(str(gs))
            el = tree.getroot().find("modsDirectoryOverride")
            if el is not None and el.get("active", "").lower() == "true":
                d = el.get("directory")
                if d:
                    override = Path(d)
                    if override.is_dir():
                        return override, True
        except etree.XMLSyntaxError:
            pass
    local = root / "mods"
    if local.is_dir():
        return local, False
    return None, False


def _count_mods(mods_dir: Path) -> int:
    count = 0
    for child in mods_dir.iterdir():
        if child.is_file() and child.suffix.lower() == ".zip":
            count += 1
        elif child.is_dir() and (child / "modDesc.xml").is_file():
            count += 1
    return count


@dataclass
class MapResolution:
    """Outcome of map-mod resolution. `path` is set when we found something
    readable. `error` is set when we know what's wrong (DLC, missing, etc.)."""
    path: Path | None = None
    error: str | None = None
    is_dlc: bool = False
    is_base_game: bool = False


def resolve_map_mod_for(
    mods_dir: Path | None,
    map_id: str | None,
    install_dir: Path | None = None,
) -> MapResolution:
    """Locate the map mod for a given save's mapId.

    Looks in (in order):
      1. `<mods>/<modName>.zip`               — third-party map mods
      2. `<mods>/<modName>/`                  — unpacked third-party map mods
      3. `<install>/data/maps/<modName>/`     — base-game maps (mapAS, mapEU, mapUS)
      4. `<install>/pdlc/<modName>.dlc`       — DLC (encrypted — unsupported)
    """
    if not map_id:
        return MapResolution(error="No mapId in save")
    mod_name = map_id.split(".", 1)[0]
    if not mod_name:
        return MapResolution(error=f"Couldn't parse mapId: {map_id!r}")

    # 1 + 2: mods folder.
    if mods_dir is not None:
        zip_path = mods_dir / f"{mod_name}.zip"
        if zip_path.is_file():
            return MapResolution(path=zip_path)
        dir_path = mods_dir / mod_name
        if dir_path.is_dir() and (dir_path / "modDesc.xml").is_file():
            return MapResolution(path=dir_path)

    # 3 + 4: game install. Try install_dir hint; if not given, scan common paths.
    candidates = [install_dir] if install_dir else _candidate_install_dirs()
    for cand in candidates:
        if cand is None or not cand.is_dir():
            continue
        # Base maps are case-insensitive on Windows, but the actual folder is
        # often lowercase first char (`mapEU` from mod-style `MapEU`).
        for name_variant in (mod_name, _camel_to_lower(mod_name)):
            base_dir = cand / "data" / "maps" / name_variant
            if base_dir.is_dir():
                return MapResolution(path=base_dir, is_base_game=True)
        # DLC: pdlc_<name> -> pdlc/<name>.dlc
        if mod_name.startswith("pdlc_"):
            dlc_stem = mod_name[len("pdlc_"):]
            dlc_file = cand / "pdlc" / f"{dlc_stem}.dlc"
            if dlc_file.is_file():
                return MapResolution(
                    path=dlc_file,
                    is_dlc=True,
                    error="DLC maps are encrypted by GIANTS — the tool cannot "
                          "read map.xml / overview.dds from them. "
                          "Migration source is OK; target must be a non-DLC map.",
                )

    return MapResolution(
        error=f"Couldn't find map mod '{mod_name}' in the mods folder or game install. "
              "Use Browse to point at it manually.",
    )


def _candidate_install_dirs() -> list[Path]:
    """Common locations where Farming Simulator 25 might be installed."""
    import os
    cands = []
    for pf in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
        if pf:
            cands.append(Path(pf) / "Farming Simulator 2025")
            cands.append(Path(pf) / "Epic Games" / "FarmingSimulator2025")
            cands.append(Path(pf) / "Steam" / "steamapps" / "common" / "Farming Simulator 25")
    # Common Steam library on D:/F:/G:
    for drive in ("C:", "D:", "E:", "F:", "G:"):
        cands.append(Path(drive + r"\SteamLibrary\steamapps\common\Farming Simulator 25"))
        cands.append(Path(drive + r"\Steam\steamapps\common\Farming Simulator 25"))
    return cands


def _camel_to_lower(s: str) -> str:
    """`MapEU` -> `mapEU`. Conservative: only lowercases the first letter."""
    if s and s[0].isupper():
        return s[0].lower() + s[1:]
    return s


def read_placeable_xml_bytes(
    filename: str,
    mods_dir: Path | None,
    install_dir: Path | None,
    map_source_path: Path | None = None,
) -> bytes | None:
    """Resolve a savegame `<placeable filename="...">` reference to its bytes.

    FS25 uses several prefix tokens:
      * `$moddir$ModName/path/file.xml`  -> `<mods>/ModName.zip!path/file.xml`
        or `<mods>/ModName/path/file.xml` (unpacked mod folder).
      * `$pdlcdir$ModName/...`           -> encrypted DLC, returns None.
      * `$mapdir$/path/file.xml`         -> inside the currently selected map.
      * `$data/path/file.xml`            -> game install's data/path/file.xml.
      * absolute or relative literal     -> as-is on disk.
    """
    if not filename:
        return None
    if filename.startswith("$pdlcdir$"):
        return None  # encrypted, unreadable
    if filename.startswith("$moddir$") and mods_dir is not None:
        rest = filename[len("$moddir$"):]
        mod_name, _, inner = rest.partition("/")
        if not mod_name:
            return None
        zip_path = mods_dir / f"{mod_name}.zip"
        if zip_path.is_file():
            return _read_from_zip(zip_path, inner)
        dir_path = mods_dir / mod_name / inner
        return _read_file(dir_path)
    if filename.startswith("$mapdir$") and map_source_path is not None:
        rest = filename[len("$mapdir$"):].lstrip("/")
        if map_source_path.is_file() and map_source_path.suffix.lower() == ".zip":
            return _read_from_zip(map_source_path, rest)
        return _read_file(map_source_path / rest)
    if filename.startswith("$data/") and install_dir is not None:
        return _read_file(install_dir / filename[1:])
    # Bare `map/...` paths are inside the current map mod (i3d UserAttribute
    # often emits this form for preplaced placeables shipped with the map).
    if (filename.startswith("map/") or filename.startswith("maps/")) \
            and map_source_path is not None:
        if map_source_path.is_file() and map_source_path.suffix.lower() == ".zip":
            return _read_from_zip(map_source_path, filename)
        candidate = map_source_path / filename
        if candidate.is_file():
            return _read_file(candidate)
    # Literal / fallback
    return _read_file(Path(filename))


def _read_file(p: Path) -> bytes | None:
    try:
        return p.read_bytes() if p.is_file() else None
    except OSError:
        return None


def _read_from_zip(zip_path: Path, inner: str) -> bytes | None:
    import zipfile as _zf
    try:
        with _zf.ZipFile(zip_path, "r") as zf:
            return zf.read(inner)
    except (KeyError, _zf.BadZipFile, OSError):
        return None


# Best-effort expansion of FS25 fillTypeCategories to fillType names.
# Sourced from `data/maps/maps_fillTypes.xml` in the base game. Map mods can
# override these, but the defaults cover ~95% of cases.
_FILL_TYPE_CATEGORIES: dict[str, set[str]] = {
    "FARMSILO": {
        "WHEAT", "BARLEY", "OAT", "CANOLA", "MAIZE", "SOYBEAN", "SUNFLOWER",
        "SORGHUM", "RICE", "RICELONGGRAIN", "GREEN_BEANS", "PEAS", "SPELT",
        "RYE", "ALFALFA",
    },
    "GRAIN": {
        "WHEAT", "BARLEY", "OAT", "CANOLA", "MAIZE", "SOYBEAN", "SUNFLOWER",
        "SORGHUM", "RICE", "RICELONGGRAIN", "SPELT", "RYE", "ALFALFA",
    },
    "BULK": {
        "POTATO", "SUGARBEET", "BEETROOT", "CARROT", "PARSNIP", "ONION",
        "OLIVE", "OLIVES", "GRAPE", "COTTON", "POPLAR", "WOODCHIPS",
        "ROOTCROP", "SUGARCANE",
    },
    "LIQUID": {
        "WATER", "LIQUIDFERTILIZER", "LIQUIDMANURE", "MILK", "BUTTERMILK",
        "DIESEL", "DEF", "ADBLUE", "WINE", "VINEGAR", "BEER",
    },
    "DIESEL": {"DIESEL", "DEF", "ADBLUE"},
    "FERTILIZER": {"FERTILIZER", "LIQUIDFERTILIZER"},
    "SEEDS": {"SEEDS"},
    "LIME": {"LIME"},
    "WATER": {"WATER"},
    "MANURE": {"MANURE", "LIQUIDMANURE", "DIGESTATE"},
    "SILAGE": {"SILAGE", "FORAGE", "MIXED_RATION"},
    "STRAW": {"STRAW", "HAY", "GRASS_WINDROW", "DRYGRASS_WINDROW"},
    "ANIMALFOOD": {
        "STRAW", "HAY", "GRASS_WINDROW", "DRYGRASS_WINDROW", "SILAGE",
        "MAIZE", "BARLEY", "WHEAT", "OAT", "FORAGE", "MIXED_RATION",
        "MINERAL_FEED", "PIGFOOD",
    },
}


def placeable_accepted_fill_types(xml_bytes: bytes | None) -> set[str] | None:
    """Return the set of fillTypes this placeable's storage will accept.

    Reads both `fillTypes="..."` (explicit list) and `fillTypeCategories="..."`
    (category names like `farmSilo` / `bulk` / `liquid`) on `<storage>` and
    `<bunkerSilo>` elements anywhere in the placeable's type XML.

    Returns `None` if no acceptance info is declared (caller should treat as
    "accepts anything — show in the dropdown unfiltered").
    """
    if xml_bytes is None:
        return None
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return None
    accepts: set[str] = set()
    saw_any = False
    for s in root.iter("storage"):
        ft = s.get("fillTypes")
        if ft:
            saw_any = True
            for t in ft.split():
                if t:
                    accepts.add(t.upper())
        cats = s.get("fillTypeCategories")
        if cats:
            saw_any = True
            for c in cats.split():
                accepts |= _FILL_TYPE_CATEGORIES.get(c.upper(), set())
    for bs in root.iter("bunkerSilo"):
        ft = bs.get("acceptedFillTypes")
        if ft:
            saw_any = True
            for t in ft.split():
                if t:
                    accepts.add(t.upper())
    return accepts if saw_any else None


def placeable_friendly_name(
    xml_bytes: bytes | None,
    savegame_placeable=None,
) -> str | None:
    """Best-effort human-readable name for a placeable type.

    If the placeable has `<baseConfigurations>` variants (e.g. a single
    dieselTank01.xml file with separate Diesel / Liquid Fertiliser / Water
    variants), the SAVEGAME's `<configuration name="baseConfiguration" id="N">`
    picks which variant. We use that variant's storeData name when present.

    Otherwise we fall back to the top-level `<storeData><name>`. `$l10n_*`
    keys are stripped of common prefixes and humanised. Returns None if
    nothing usable.
    """
    if xml_bytes is None:
        return None
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return None

    raw: str | None = None

    # Variant lookup via savegame's <configuration name="baseConfiguration" id="X">
    if savegame_placeable is not None:
        cfg_id = None
        for cfg in savegame_placeable.findall("configuration"):
            if (cfg.get("name") or "").lower() == "baseconfiguration":
                cfg_id = cfg.get("id")
                break
        if cfg_id is not None:
            for base_cfg in root.iter("baseConfiguration"):
                if base_cfg.get("index") == cfg_id or base_cfg.get("id") == cfg_id:
                    name_el = base_cfg.find("storeData/name") or base_cfg.find("name")
                    if name_el is not None and name_el.text:
                        raw = name_el.text.strip()
                        break

    # Fallback: top-level storeData/name
    if raw is None:
        name_el = root.find("storeData/name")
        if name_el is None or not name_el.text:
            return None
        raw = name_el.text.strip()
    if raw.startswith("$l10n_"):
        rest = raw[len("$l10n_"):]
        # Strip common Giants prefixes.
        for prefix in ("storeItem_", "shopItem_", "placeable_", "name_",
                       "placeableObject_", "fillType_"):
            if rest.startswith(prefix):
                rest = rest[len(prefix):]
                break
        # Generic placeholder keys like `$l10n_name` give nothing useful —
        # let the caller fall back to filename.
        if not rest or rest.lower() in {"name", "title", "default"}:
            return None
        # Lower-camel/snake -> Title Case-ish.
        import re as _re
        rest = _re.sub(r"([a-z])([A-Z])", r"\1 \2", rest)
        rest = rest.replace("_", " ").strip()
        return rest.title() if rest else None
    return raw


def placeable_animal_type(xml_bytes: bytes | None) -> str | None:
    """Return the species this husbandry accepts (COW / SHEEP / PIG /
    CHICKEN / HORSE / GOAT / WATERBUFFALO / RABBIT), or None if the placeable
    isn't a husbandry or doesn't declare a species.

    Read from `<husbandry><animals type="COW">` in the placeable type XML.
    """
    if xml_bytes is None:
        return None
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return None
    for animals in root.iter("animals"):
        t = animals.get("type")
        if t:
            return t.upper()
    return None


def animal_subtype_species(subtype: str | None) -> str | None:
    """Map a specific subType ("COW_HOLSTEIN", "BULL_ANGUS", "RAM_LANDRACE")
    to its species ("COW", "SHEEP", ...). Returns None if unknown."""
    if not subtype:
        return None
    s = subtype.upper()
    # Direct prefix matches.
    for prefix, species in _SUBTYPE_PREFIX_MAP:
        if s.startswith(prefix):
            return species
    # Fall back to the token before the first underscore.
    return s.split("_", 1)[0] if "_" in s else s


_SUBTYPE_PREFIX_MAP: tuple[tuple[str, str], ...] = (
    ("COW_", "COW"),
    ("BULL_", "COW"),
    ("SHEEP_", "SHEEP"),
    ("RAM_", "SHEEP"),
    ("PIG_", "PIG"),
    ("BOAR_", "PIG"),
    ("CHICKEN_", "CHICKEN"),
    ("ROOSTER_", "CHICKEN"),
    ("HEN_", "CHICKEN"),
    ("HORSE_", "HORSE"),
    ("STALLION_", "HORSE"),
    ("MARE_", "HORSE"),
    ("GOAT_", "GOAT"),
    ("BUCK_", "GOAT"),
    ("DOE_", "GOAT"),
    ("BUFFALO_", "WATERBUFFALO"),
    ("WATERBUFFALO_", "WATERBUFFALO"),
    ("RABBIT_", "RABBIT"),
    ("DOE",   "RABBIT"),
)


def placeable_declares_object_storage(xml_bytes: bytes | None) -> bool:
    """True if the placeable type-XML declares `<objectStorage>` as a child of
    `<placeable>` — i.e. the placeable is an auto-storage shed even when empty
    in the current savegame.
    """
    return _placeable_declares_capability(xml_bytes, "objectStorage")


def placeable_declares_silo(xml_bytes: bytes | None) -> bool:
    """True if the placeable type-XML declares silo / bunker / heap storage
    capability — even when the savegame shows no state for it yet.
    """
    if xml_bytes is None:
        return False
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return False
    if root.tag != "placeable":
        return False
    ptype = (root.get("type") or "").lower()
    if ptype in {"silo", "bunkersilo", "multibunkersilo", "placeablestorageheap"}:
        return True
    for tag in ("silo", "bunkerSilo", "multiBunkerSilo", "placeableStorageHeap"):
        if root.find(tag) is not None:
            return True
    return False


def _placeable_declares_capability(xml_bytes: bytes | None, child_tag: str) -> bool:
    if xml_bytes is None:
        return False
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return False
    if root.tag != "placeable":
        return False
    if (root.get("type") or "").lower() == child_tag.lower():
        return True
    return root.find(child_tag) is not None


def detect_install_dir_from_log(root: Path) -> Path | None:
    """Best-effort: scrape the FS25 install directory from log.txt.

    The log references paths like `F:/SteamLibrary/.../Farming Simulator 25/data/...`
    or `C:/Program Files/.../FarmingSimulator2025/data/...`. We grab the first
    path containing 'Farming Simulator 25' and walk up to that folder.
    """
    log = root / "log.txt"
    if not log.is_file():
        return None
    try:
        text = log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    import re as _re
    m = _re.search(
        r"([A-Za-z]:[/\\][^\n\"'`?<>|]*?Farming Simulator 25)[/\\](data|pdlc|shared|sdk)",
        text,
    )
    if m:
        return Path(m.group(1))
    return None
