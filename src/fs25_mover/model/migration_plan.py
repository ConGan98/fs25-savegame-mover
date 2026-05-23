"""MigrationPlan: the user's choices for one source -> target migration.

Built by the GUI (Phase 4) or hand-authored as a JSON file for CLI testing.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MigrationPlan:
    source_path: str
    target_path: str
    output_path: str

    # Migration toggles
    move_vehicles: bool = True
    move_items: bool = True
    move_silos: bool = True
    move_animals: bool = True
    move_money: bool = True
    move_farm_statistics: bool = True
    move_object_storage: bool = True

    # Vehicle / item drop zone on the new map (world coords). drop_xyz.y should
    # be terrain height + small headroom (e.g. +0.3m) so vehicles spawn on the
    # ground without falling.
    drop_xyz: tuple[float, float, float] = (0.0, 100.0, 0.0)
    # Heading (degrees) every vehicle is rotated to face. 0 = facing -Z (north).
    vehicle_yaw_deg: float = 0.0
    # Same-map-upgrade mode: keep every vehicle exactly where the player left it
    # in the source save. Skips the grid layout AND the attached-implement detach
    # step (hitches still valid because the world hasn't changed).
    preserve_vehicle_positions: bool = False
    # Same-map-upgrade mode: also copy the player's player-placed <placeable>
    # entries (silos, sheds, pens they bought) into the target. Subsequent
    # silo/animal/storage merges treat source-uid==target-uid as a no-op so
    # content isn't doubled. Unsafe in cross-map mode — leave default False.
    copy_player_placeables: bool = False
    # Spacing (metres) between vehicles in the placement grid.
    # col_pitch = side-to-side gap. row_pitch = front-to-back gap. Defaults are
    # generous (5m / 8m) to accommodate combines and trailered implements.
    vehicle_col_pitch: float = 10.0
    vehicle_row_pitch: float = 10.0
    vehicle_cols_per_row: int = 10
    # If true, repositions bales/pallets to drop_xyz; otherwise keeps source coords.
    reposition_items: bool = True

    # When migrating animals, also copy the source husbandry's <storage>
    # (slurry / straw / manure / milk fill levels) onto the target pen.
    include_husbandry_storage: bool = True

    # If true, sell every bunker silo's silage at the source map's economy
    # price and add the proceeds to the target farm's money (instead of just
    # losing the silage on migration).
    sell_bunker_silage: bool = False

    # Per-placeable mappings, source uniqueId -> target uniqueId.
    silo_mapping: dict[str, str] = field(default_factory=dict)
    pen_mapping: dict[str, str] = field(default_factory=dict)
    # Auto-storage sheds (bales / pallets stored inside <objectStorage>).
    storage_mapping: dict[str, str] = field(default_factory=dict)

    # Mod-specific savegame files to copy from source to the migrated output
    # (e.g. RedTape.xml, rm_RlAnimalSystem.xml). User picks per file in the
    # wizard's Mod files page. Source wins over any target equivalent.
    mod_file_includes: list[str] = field(default_factory=list)

    # Farm ids
    src_farm_id: int = 1
    tgt_farm_id: int = 1

    @classmethod
    def from_json(cls, path: str | Path) -> "MigrationPlan":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if "drop_xyz" in data and isinstance(data["drop_xyz"], list):
            data["drop_xyz"] = tuple(data["drop_xyz"])
        return cls(**data)

    def to_json(self, path: str | Path) -> None:
        d = asdict(self)
        d["drop_xyz"] = list(d["drop_xyz"])
        Path(path).write_text(json.dumps(d, indent=2), encoding="utf-8")
