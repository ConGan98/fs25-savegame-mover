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
