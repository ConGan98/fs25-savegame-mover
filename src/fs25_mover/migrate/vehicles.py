"""Migrate vehicles from source savegame into target vehicles.xml.

Each source vehicle element is deep-copied, repositioned to (drop_x, drop_y, drop_z)
plus a small per-vehicle offset (so they don't all spawn inside each other), and
appended to the target <vehicles> root. uniqueId collisions are resolved by
minting fresh ids. The vehicle's <component> children are also repositioned so
the physics components match the new origin.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from lxml import etree

from ..parsers.savegame import Savegame
from .ids import collect_ids, remap_collisions


@dataclass
class VehicleMigrationResult:
    moved: int
    skipped: int
    remap: dict[str, str]


def migrate_vehicles(
    src: Savegame,
    tgt: Savegame,
    drop_xyz: tuple[float, float, float],
    farm_id: int = 1,
    src_farm_id: int = 1,
    target_yaw_deg: float = 0.0,
    col_pitch: float = 10.0,
    row_pitch: float = 10.0,
    cols_per_row: int = 10,
) -> VehicleMigrationResult:
    """Migrate vehicles owned by `src_farm_id`. Other farms' vehicles
    (display/showcase units, AI farms, mod farms) are left behind.
    """
    src_root = src.root("vehicles.xml")
    tgt_root = tgt.root("vehicles.xml")
    if src_root is None or tgt_root is None:
        return VehicleMigrationResult(moved=0, skipped=0, remap={})

    all_src = list(src_root.findall("vehicle"))
    src_vehicles = [v for v in all_src if v.get("farmId") == str(src_farm_id)]
    skipped = len(all_src) - len(src_vehicles)
    taken = collect_ids(tgt_root)
    remap = remap_collisions(src_vehicles, taken)

    # Placement: vehicle 0 sits exactly on drop_xyz. Subsequent vehicles step
    # 3m to the LEFT of the chosen heading (perpendicular to facing direction)
    # so they line up side-by-side, not nose-to-tail. After 10 per row, start
    # a new row 5m BEHIND (opposite to facing direction).
    #
    # FS25 yaw=0 means facing -Z (north). Forward unit vector for yaw θ:
    #   forward = (sin θ, 0, -cos θ)        # rotates from -Z baseline
    # "Left" (vehicle's port side) is forward rotated +90° around +Y:
    #   left    = (-cos θ, 0, -sin θ)
    # We step `column` lengths "left" and `row` lengths "behind" (= -forward).
    yaw_rad = math.radians(target_yaw_deg)
    sin_y = math.sin(yaw_rad)
    cos_y = math.cos(yaw_rad)
    lateral = (-cos_y, -sin_y)         # left direction in (x, z)
    behind = (-sin_y, cos_y)            # behind direction in (x, z)

    moved = 0
    for i, v in enumerate(src_vehicles):
        clone = copy.deepcopy(v)

        old_uid = clone.get("uniqueId")
        if old_uid and old_uid in remap:
            clone.set("uniqueId", remap[old_uid])

        clone.set("farmId", str(farm_id))

        # Detach any implements hitched to this vehicle on the source map.
        # FS25 reattaches `<attachedImplement>` references at load time, which
        # would yank the implement out of our placement row and snap it to the
        # parent's hitch. Removing the elements makes every vehicle spawn loose.
        for ai in clone.findall(".//attacherJoints/attachedImplement"):
            ai.getparent().remove(ai)

        row, col = divmod(i, cols_per_row)
        offset_x = col * col_pitch * lateral[0] + row * row_pitch * behind[0]
        offset_z = col * col_pitch * lateral[1] + row * row_pitch * behind[1]
        new_pos = (
            drop_xyz[0] + offset_x,
            drop_xyz[1],
            drop_xyz[2] + offset_z,
        )
        _reposition_vehicle(clone, new_pos, target_yaw_deg)

        tgt_root.append(clone)
        moved += 1

    return VehicleMigrationResult(moved=moved, skipped=skipped, remap=remap)


def _reposition_vehicle(
    vehicle: etree._Element,
    new_pos: tuple[float, float, float],
    target_yaw_deg: float = 0.0,
) -> None:
    """Move the vehicle to new_pos and rotate it to face target_yaw_deg.

    All components are translated and rotated as one rigid body around the
    first component (the "pivot" — the vehicle's true world transform).
    Relative offsets between components are preserved (so multi-component
    vehicles like articulated trailers stay assembled), then the whole vehicle
    is yawed so it faces the requested heading.

    Pitch and roll are zeroed so a row of vehicles sits flat on the ground
    regardless of how they were oriented in the source save.
    """
    comps = vehicle.findall("component")
    new_pos_str = f"{new_pos[0]:.3f} {new_pos[1]:.3f} {new_pos[2]:.3f}"
    if not comps:
        vehicle.set("position", new_pos_str)
        return

    pivot_pos = _parse_xyz(comps[0].get("position"))
    pivot_rot = _parse_xyz(comps[0].get("rotation") or "0 0 0")
    old_yaw = pivot_rot[1]
    delta_yaw = target_yaw_deg - old_yaw
    rad = math.radians(delta_yaw)
    cos_d = math.cos(rad)
    sin_d = math.sin(rad)

    vehicle.set("position", new_pos_str)
    vehicle.set("rotation", f"0.000 {target_yaw_deg:.3f} 0.000")

    for comp in comps:
        cx, cy, cz = _parse_xyz(comp.get("position"))
        # Offset relative to pivot in the XZ plane.
        ox = cx - pivot_pos[0]
        oz = cz - pivot_pos[2]
        # Rotate around the Y axis by delta_yaw (FS25 uses left-handed Y-up;
        # this matches how the engine reorients child rigid bodies).
        rx = ox * cos_d - oz * sin_d
        rz = ox * sin_d + oz * cos_d
        nx = new_pos[0] + rx
        nz = new_pos[2] + rz
        ny = new_pos[1] + (cy - pivot_pos[1])
        comp.set("position", f"{nx:.3f} {ny:.3f} {nz:.3f}")
        # Flat-orient every component to the target heading.
        comp.set("rotation", f"0.000 {target_yaw_deg:.3f} 0.000")


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
