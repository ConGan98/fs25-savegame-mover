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

    # Vehicle / item drop zone on the new map (world coords). drop_xyz.y should
    # be terrain height + small headroom (e.g. +0.3m) so vehicles spawn on the
    # ground without falling.
    drop_xyz: tuple[float, float, float] = (0.0, 100.0, 0.0)
    # Heading (degrees) every vehicle is rotated to face. 0 = facing -Z (north).
    vehicle_yaw_deg: float = 0.0
    # Spacing (metres) between vehicles in the placement grid.
    # col_pitch = side-to-side gap. row_pitch = front-to-back gap. Defaults are
    # generous (5m / 8m) to accommodate combines and trailered implements.
    vehicle_col_pitch: float = 10.0
    vehicle_row_pitch: float = 10.0
    vehicle_cols_per_row: int = 10
    # If true, repositions bales/pallets to drop_xyz; otherwise keeps source coords.
    reposition_items: bool = True

    # Per-placeable mappings, source uniqueId -> target uniqueId.
    silo_mapping: dict[str, str] = field(default_factory=dict)
    pen_mapping: dict[str, str] = field(default_factory=dict)

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
