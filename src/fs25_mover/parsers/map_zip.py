"""Read an FS25 map mod, whether packaged as a .zip or unpacked into a folder.

Maps can ship with several different internal layouts:
  - `map/map.xml` + `map/map.i3d` + `map/textures/ui/overview.dds`
  - `maps/maps.xml` + `maps/<name>.i3d` + `maps/<name>_overview.dds`
  - Base-game maps under `map/maps/mapDE/mapDE.xml` etc.

Rather than hardcoding every variation, we locate the map XML by trying common
candidates and then derive everything else (overview, i3d, dem) from it.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


# Candidate paths for the map XML. First hit wins.
MAP_XML_CANDIDATES = (
    "map/map.xml",
    "maps/maps.xml",
    "map/maps/mapDE/mapDE.xml",
    "map/maps/mapUS/mapUS.xml",
    "map/maps/mapFR/mapFR.xml",
)


@dataclass
class Hotspot:
    label: str
    type: str
    world_x: float
    world_z: float


class MapSource:
    """Polymorphic wrapper: a .zip file OR an unpacked directory."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._zip: zipfile.ZipFile | None = None
        if self.path.is_file() and self.path.suffix.lower() == ".zip":
            self._zip = zipfile.ZipFile(self.path, "r")
        self._map_xml_cache: tuple[str, etree._Element] | None = None
        self._i3d_cache: tuple[str, etree._Element] | None = None

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def __enter__(self): return self
    def __exit__(self, *a): self.close()

    # ---- low-level read ----

    def _read(self, inner: str) -> bytes | None:
        if self._zip is not None:
            try:
                return self._zip.read(inner)
            except KeyError:
                return None
        candidate = self.path / inner
        return candidate.read_bytes() if candidate.is_file() else None

    def _iter_all_names(self):
        if self._zip is not None:
            yield from self._zip.namelist()
            return
        base = self.path
        for p in base.rglob("*"):
            if p.is_file():
                yield str(p.relative_to(base)).replace("\\", "/")

    # ---- discovery (map XML + i3d) ----

    def _map_xml(self) -> tuple[str, etree._Element] | None:
        if self._map_xml_cache is not None:
            return self._map_xml_cache
        # Try known candidates.
        for c in MAP_XML_CANDIDATES:
            data = self._read(c)
            if data is None:
                continue
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError:
                continue
            if root.tag == "map":
                self._map_xml_cache = (c, root)
                return self._map_xml_cache
        # Last-ditch: scan for any *.xml at root/maps/ level whose root is <map>.
        for name in self._iter_all_names():
            if not name.lower().endswith(".xml"):
                continue
            if name.count("/") > 2:  # too deep, skip
                continue
            data = self._read(name)
            if data is None:
                continue
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError:
                continue
            if root.tag == "map":
                self._map_xml_cache = (name, root)
                return self._map_xml_cache
        return None

    def _i3d(self) -> tuple[str, etree._Element] | None:
        if self._i3d_cache is not None:
            return self._i3d_cache
        # Prefer the path declared in <filename> inside map XML.
        candidates = []
        mx = self._map_xml()
        if mx is not None:
            fn_el = mx[1].find("filename")
            if fn_el is not None and fn_el.text:
                candidates.append(fn_el.text.strip())
        # Fallback hardcoded locations.
        candidates.extend(["map/map.i3d", "maps/map.i3d"])
        for c in candidates:
            data = self._read(c)
            if data is None:
                continue
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError:
                continue
            self._i3d_cache = (c, root)
            return self._i3d_cache
        # Last-ditch: scan for any .i3d.
        for name in self._iter_all_names():
            if name.lower().endswith(".i3d"):
                data = self._read(name)
                if data is None:
                    continue
                try:
                    root = etree.fromstring(data)
                except etree.XMLSyntaxError:
                    continue
                self._i3d_cache = (name, root)
                return self._i3d_cache
        return None

    # ---- public API ----

    def overview_bytes(self) -> bytes:
        """Return the bytes of the PDA overview .dds.

        Prefers the path declared as `imageFilename` on the map XML's `<map>`
        element (sometimes that points to a .png — we prefer the .dds sibling
        if it exists). Falls back to scanning for any `*overview*.dds`.
        """
        candidates: list[str] = []
        mx = self._map_xml()
        if mx is not None:
            img = mx[1].get("imageFilename") or ""
            if img:
                candidates.append(img)
                if img.endswith(".png"):
                    candidates.append(img[:-4] + ".dds")
                if img.endswith(".dds"):
                    candidates.append(img[:-4] + ".png")
        candidates.extend([
            "map/textures/ui/overview.dds",
            "map/data/textures/ui/overview.dds",
            "map/overview.dds",
        ])
        for c in candidates:
            data = self._read(c)
            if data is not None:
                return data
        # Last-ditch scan.
        for name in self._iter_all_names():
            n = name.lower()
            if n.endswith(".dds") and "overview" in n:
                data = self._read(name)
                if data is not None:
                    return data
        raise FileNotFoundError(f"No PDA overview image found in {self.path}")

    def hotspots(self) -> list[Hotspot]:
        mx = self._map_xml()
        if mx is None:
            return []
        out: list[Hotspot] = []
        for el in mx[1].iter("placeableHotspot"):
            pos = el.get("worldPosition") or ""
            parts = pos.split()
            if len(parts) < 2:
                continue
            try:
                wx = float(parts[0])
                wz = float(parts[-1])
            except ValueError:
                continue
            label = el.get("text") or el.get("type") or ""
            label = re.sub(r"^\$l10n_", "", label)
            out.append(Hotspot(label=label, type=el.get("type") or "", world_x=wx, world_z=wz))
        return out

    def playable_image_size(self) -> tuple[int, int] | None:
        mx = self._map_xml()
        if mx is None:
            return None
        try:
            return (int(mx[1].get("width")), int(mx[1].get("height")))
        except (TypeError, ValueError):
            return None

    def world_size(self) -> float | None:
        """Side length of the playable world in metres (from heightmap dims)."""
        i3d = self._i3d()
        if i3d is None:
            return None
        ttg = i3d[1].find(".//TerrainTransformGroup")
        if ttg is None:
            return None
        try:
            units_per_pixel = float(ttg.get("unitsPerPixel") or 1)
            heightmap_id = ttg.get("heightMapId")
        except (TypeError, ValueError):
            return None
        if heightmap_id is None:
            return None
        hm_data = self._read_heightmap(i3d, heightmap_id)
        if hm_data is None:
            return None
        if len(hm_data) < 24 or hm_data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        width = int.from_bytes(hm_data[16:20], "big")
        return (width - 1) * units_per_pixel

    def sample_height(self, world_x: float, world_z: float) -> float | None:
        i3d = self._i3d()
        if i3d is None:
            return None
        ttg = i3d[1].find(".//TerrainTransformGroup")
        if ttg is None:
            return None
        try:
            units_per_pixel = float(ttg.get("unitsPerPixel") or 1)
            height_scale = float(ttg.get("heightScale") or 255)
        except (TypeError, ValueError):
            return None
        heightmap_id = ttg.get("heightMapId")
        if heightmap_id is None:
            return None
        hm_data = self._read_heightmap(i3d, heightmap_id)
        if hm_data is None:
            return None
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(hm_data))
        except Exception:
            return None
        w, h = im.size
        ws = (w - 1) * units_per_pixel
        u = (world_x + ws / 2) / units_per_pixel
        v = (world_z + ws / 2) / units_per_pixel
        u = max(0, min(w - 1, int(round(u))))
        v = max(0, min(h - 1, int(round(v))))
        pix = im.getpixel((u, v))
        if isinstance(pix, (list, tuple)):
            pix = pix[0]
        if im.mode in ("I", "I;16", "I;16B", "I;16L"):
            denom = 65535.0
        elif im.mode == "L":
            denom = 255.0
        else:
            denom = 65535.0
        return (pix / denom) * height_scale

    def _read_heightmap(self, i3d: tuple[str, etree._Element], heightmap_id: str) -> bytes | None:
        """Resolve the heightmap PNG bytes from the i3d's File table."""
        file_el = i3d[1].find(f".//File[@fileId='{heightmap_id}']")
        if file_el is None:
            return None
        rel = file_el.get("filename")
        if not rel:
            return None
        # Try the literal path, and rooted under map/ or maps/ (FS25 i3ds use
        # data/dem.png-style relative paths).
        i3d_dir = i3d[0].rsplit("/", 1)[0] if "/" in i3d[0] else ""
        candidates = [rel]
        if i3d_dir:
            candidates.append(f"{i3d_dir}/{rel}")
        candidates.extend([f"map/{rel}", f"maps/{rel}"])
        for c in candidates:
            data = self._read(c)
            if data is not None:
                return data
        return None

    def preplaced_positions(self) -> dict[str, tuple[float, float, float]]:
        """Read the map's preplaced-placeables config and return uniqueId -> (x,y,z).

        FS25 maps drop preplaced positions in `<mapdir>/config/placeables.xml`
        (path varies: `map/config/placeables.xml` or `maps/config/placeables.xml`).
        Each `<placeable uniqueId="..." position="X Y Z" />` is one entry.

        Used by the savegame POI resolver when the i3d doesn't carry positions
        for preplaced things (some maps — e.g. Mechet — only declare them here).
        """
        out: dict[str, tuple[float, float, float]] = {}
        for c in ("map/config/placeables.xml", "maps/config/placeables.xml"):
            data = self._read(c)
            if data is None:
                continue
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError:
                continue
            for p in root.iter("placeable"):
                uid = p.get("uniqueId")
                pos = p.get("position")
                if not uid or not pos:
                    continue
                parts = pos.split()
                if len(parts) != 3:
                    continue
                try:
                    out[uid] = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    continue
            break  # first config wins
        return out

    def map_id(self) -> str | None:
        data = self._read("modDesc.xml")
        if data is None:
            return None
        try:
            root = etree.fromstring(data)
        except etree.XMLSyntaxError:
            return None
        title = root.findtext(".//title/en") or ""
        return title.strip() or None
