"""Top-level migration orchestrator."""
from __future__ import annotations

from dataclasses import dataclass

from ..model.migration_plan import MigrationPlan
from ..parsers.savegame import Savegame
from .animals import AnimalMigrationResult, migrate_animals
from .items import ItemMigrationResult, migrate_items
from .money import MoneyMigrationResult, migrate_money
from .silos import SiloMigrationResult, migrate_silos
from .vehicles import VehicleMigrationResult, migrate_vehicles


@dataclass
class MigrationReport:
    vehicles: VehicleMigrationResult | None
    items: ItemMigrationResult | None
    silos: SiloMigrationResult | None
    animals: AnimalMigrationResult | None
    money: MoneyMigrationResult | None
    output_path: str


def apply(plan: MigrationPlan) -> MigrationReport:
    src = Savegame.load(plan.source_path)
    tgt = Savegame.load(plan.target_path)

    # Force-load every XML we may touch so write_to() sees an in-memory tree
    # (otherwise it just copies the on-disk file unchanged).
    for f in ("vehicles.xml", "items.xml", "placeables.xml", "farms.xml"):
        tgt.tree(f)

    veh = (
        migrate_vehicles(
            src,
            tgt,
            plan.drop_xyz,
            farm_id=plan.tgt_farm_id,
            src_farm_id=plan.src_farm_id,
            target_yaw_deg=plan.vehicle_yaw_deg,
            col_pitch=plan.vehicle_col_pitch,
            row_pitch=plan.vehicle_row_pitch,
            cols_per_row=plan.vehicle_cols_per_row,
        )
        if plan.move_vehicles
        else None
    )
    itm = (
        migrate_items(
            src,
            tgt,
            plan.drop_xyz if plan.reposition_items else None,
            farm_id=plan.tgt_farm_id,
        )
        if plan.move_items
        else None
    )
    silo = (
        migrate_silos(src, tgt, plan.silo_mapping)
        if plan.move_silos
        else None
    )
    ani = (
        migrate_animals(src, tgt, plan.pen_mapping, farm_id=plan.tgt_farm_id)
        if plan.move_animals
        else None
    )
    mon = (
        migrate_money(src, tgt, plan.src_farm_id, plan.tgt_farm_id)
        if plan.move_money
        else None
    )

    out = tgt.write_to(plan.output_path)
    return MigrationReport(
        vehicles=veh, items=itm, silos=silo, animals=ani, money=mon, output_path=str(out)
    )
