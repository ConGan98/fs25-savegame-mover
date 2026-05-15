"""Read/write FS25 savegame XML files.

A Savegame wraps a savegameN/ folder. Files are parsed on first access and
cached. The same Savegame can be written back to a different output folder
without mutating the source path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from lxml import etree


SAVEGAME_FILES = (
    "careerSavegame.xml",
    "vehicles.xml",
    "items.xml",
    "placeables.xml",
    "farms.xml",
    "economy.xml",
    "environment.xml",
    "farmland.xml",
)


@dataclass
class Savegame:
    path: Path
    _trees: dict[str, etree._ElementTree] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Savegame":
        p = Path(path)
        if not p.is_dir():
            raise FileNotFoundError(f"Savegame folder not found: {p}")
        if not (p / "careerSavegame.xml").is_file():
            raise ValueError(f"Not an FS25 savegame folder (no careerSavegame.xml): {p}")
        return cls(path=p)

    def tree(self, name: str) -> etree._ElementTree | None:
        """Return parsed tree for an XML file in the savegame folder, or None if missing."""
        if name in self._trees:
            return self._trees[name]
        f = self.path / name
        if not f.is_file():
            return None
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(f), parser)
        self._trees[name] = tree
        return tree

    def root(self, name: str):
        t = self.tree(name)
        return t.getroot() if t is not None else None

    # ---- convenience queries ----

    @property
    def map_id(self) -> str | None:
        r = self.root("careerSavegame.xml")
        if r is None:
            return None
        el = r.find("settings/mapId")
        return el.text if el is not None else None

    @property
    def map_title(self) -> str | None:
        r = self.root("careerSavegame.xml")
        if r is None:
            return None
        el = r.find("settings/mapTitle")
        return el.text if el is not None else None

    def vehicles(self) -> list[etree._Element]:
        r = self.root("vehicles.xml")
        return list(r.findall("vehicle")) if r is not None else []

    def items(self) -> list[etree._Element]:
        r = self.root("items.xml")
        return list(r.findall("item")) if r is not None else []

    def placeables(self) -> list[etree._Element]:
        r = self.root("placeables.xml")
        return list(r.findall("placeable")) if r is not None else []

    def farms(self) -> list[etree._Element]:
        r = self.root("farms.xml")
        return list(r.findall("farm")) if r is not None else []

    def bunker_silos(self) -> Iterator[tuple[etree._Element, etree._Element]]:
        """Yield (placeable, bunkerSilo) pairs from placeables.xml."""
        for p in self.placeables():
            for bs in p.findall(".//bunkerSilo"):
                yield p, bs

    def husbandries(self) -> Iterator[tuple[etree._Element, etree._Element]]:
        """Yield (placeable, husbandryAnimals) pairs from placeables.xml."""
        for p in self.placeables():
            ha = p.find(".//husbandryAnimals")
            if ha is not None:
                yield p, ha

    def write_to(self, out_dir: str | Path) -> Path:
        """Write all loaded XML trees plus any unloaded files (copied) to out_dir."""
        import shutil

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        # Copy everything from source first (preserves non-XML cache files, etc.)
        for child in self.path.iterdir():
            if child.is_file():
                shutil.copy2(child, out / child.name)
            elif child.is_dir():
                dest = out / child.name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(child, dest)
        # Overwrite the XML files we have edited trees for.
        for name, tree in self._trees.items():
            tree.write(
                str(out / name),
                xml_declaration=True,
                encoding="utf-8",
                standalone=False,
            )
        return out
