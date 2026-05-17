"""Summary view over a Savegame — derived data, no XML mutation here."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from ..parsers.savegame import Savegame


@dataclass
class SiloEntry:
    placeable_uid: str
    fill_type: str            # may be None on bunker silos (state-driven content)
    fill_level: float
    state: str | None
    position: tuple[float, float, float]


@dataclass
class HusbandryEntry:
    placeable_uid: str
    sub_types: Counter        # COW_HOLSTEIN -> count, etc.
    total_animals: int
    position: tuple[float, float, float]


@dataclass
class FarmSnapshot:
    map_id: str | None
    map_title: str | None
    vehicle_count: int
    vehicles_by_mod: Counter           # modName -> count (None key = base game)
    item_count: int
    items_by_mod: Counter
    silos: list[SiloEntry]
    grain_totals: dict[str, float]     # fillType -> total fillLevel (best-effort)
    husbandries: list[HusbandryEntry]
    farm_money: dict[int, float]       # farmId -> money
    farm_loans: dict[int, float]

    @classmethod
    def from_savegame(cls, sg: Savegame) -> "FarmSnapshot":
        vehicles_by_mod: Counter = Counter()
        for v in sg.vehicles():
            vehicles_by_mod[v.get("modName")] += 1

        items_by_mod: Counter = Counter()
        for it in sg.items():
            items_by_mod[it.get("modName")] += 1

        silos: list[SiloEntry] = []
        grain_totals: dict[str, float] = defaultdict(float)
        for placeable, bs in sg.bunker_silos():
            pos = _parse_xyz(placeable.get("position"))
            fill_type = bs.get("fillType")  # often absent on bunkers (state-driven)
            fill_level = float(bs.get("fillLevel") or 0.0)
            silos.append(
                SiloEntry(
                    placeable_uid=placeable.get("uniqueId") or "",
                    fill_type=fill_type,
                    fill_level=fill_level,
                    state=bs.get("state"),
                    position=pos,
                )
            )
            if fill_type:
                grain_totals[fill_type] += fill_level

        # Also pick up <fillUnit><unit fillType=... fillLevel=...> entries
        # under placeables (silo storage placeables typically use this form).
        for placeable in sg.placeables():
            for unit in placeable.findall(".//fillUnit/unit"):
                ft = unit.get("fillType")
                fl = float(unit.get("fillLevel") or 0.0)
                if ft and fl > 0:
                    grain_totals[ft] += fl

        husbandries: list[HusbandryEntry] = []
        for placeable, ha in sg.husbandries():
            pos = _parse_xyz(placeable.get("position"))
            subs: Counter = Counter()
            for a in ha.findall(".//animal"):
                st = a.get("subType") or "UNKNOWN"
                n = int(a.get("numAnimals") or 1)
                subs[st] += n
            husbandries.append(
                HusbandryEntry(
                    placeable_uid=placeable.get("uniqueId") or "",
                    sub_types=subs,
                    total_animals=sum(subs.values()),
                    position=pos,
                )
            )

        farm_money: dict[int, float] = {}
        farm_loans: dict[int, float] = {}
        for f in sg.farms():
            try:
                fid = int(f.get("farmId"))
            except (TypeError, ValueError):
                continue
            farm_money[fid] = float(f.get("money") or 0.0)
            farm_loans[fid] = float(f.get("loan") or 0.0)

        return cls(
            map_id=sg.map_id,
            map_title=sg.map_title,
            vehicle_count=len(sg.vehicles()),
            vehicles_by_mod=vehicles_by_mod,
            item_count=len(sg.items()),
            items_by_mod=items_by_mod,
            silos=silos,
            grain_totals=dict(grain_totals),
            husbandries=husbandries,
            farm_money=farm_money,
            farm_loans=farm_loans,
        )


def _parse_xyz(s: str | None) -> tuple[float, float, float]:
    if not s:
        return (0.0, 0.0, 0.0)
    parts = s.split()
    if len(parts) != 3:
        return (0.0, 0.0, 0.0)
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return (0.0, 0.0, 0.0)
