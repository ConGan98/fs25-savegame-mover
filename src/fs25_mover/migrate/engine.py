"""Top-level migration orchestrator."""
from __future__ import annotations

from dataclasses import dataclass

from ..model.migration_plan import MigrationPlan
from ..parsers.savegame import Savegame
from .animals import AnimalMigrationResult, migrate_animals
from .items import ItemMigrationResult, migrate_items
from .mod_files import ModFileMigrationResult, copy_mod_files
from .mods_list import ModListMergeResult, merge_mod_list
from .money import (
    FarmStatsMigrationResult,
    MoneyMigrationResult,
    migrate_farm_statistics,
    migrate_money,
)
from .object_storage import ObjectStorageMigrationResult, migrate_object_storage
from .placeables import PlaceableCopyResult, copy_player_placeables
from .silage_sale import SilageSaleResult, sell_silage_to_money
from .silos import SiloMigrationResult, migrate_silos
from .vehicles import VehicleMigrationResult, migrate_vehicles


@dataclass
class MigrationReport:
    vehicles: VehicleMigrationResult | None
    items: ItemMigrationResult | None
    silos: SiloMigrationResult | None
    animals: AnimalMigrationResult | None
    money: MoneyMigrationResult | None
    farm_stats: FarmStatsMigrationResult | None
    object_storage: ObjectStorageMigrationResult | None
    silage_sale: SilageSaleResult | None
    mod_files: ModFileMigrationResult | None
    player_placeables: PlaceableCopyResult | None
    mods_list: ModListMergeResult | None
    output_path: str


def apply(plan: MigrationPlan) -> MigrationReport:
    src = Savegame.load(plan.source_path)
    tgt = Savegame.load(plan.target_path)

    # Force-load every XML we may touch so write_to() sees an in-memory tree
    # (otherwise it just copies the on-disk file unchanged).
    for f in ("vehicles.xml", "items.xml", "placeables.xml", "farms.xml",
              "careerSavegame.xml"):
        tgt.tree(f)

    # Merge source's <mod> dependency list into target's careerSavegame.xml so
    # FS25 prompts the user to activate the source's mods on first load.
    mods_list = merge_mod_list(src, tgt)

    # SAME-MAP UPGRADE: copy the player's player-placed placeables FIRST so
    # subsequent silo/animal/storage merges see them in the target tree.
    # Identity mappings (src uid == tgt uid) are skipped by those merges to
    # avoid doubling content.
    placeables_copy = (
        copy_player_placeables(src, tgt, plan.src_farm_id, plan.tgt_farm_id)
        if plan.copy_player_placeables
        else None
    )

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
            preserve_positions=plan.preserve_vehicle_positions,
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
        migrate_animals(
            src,
            tgt,
            plan.pen_mapping,
            farm_id=plan.tgt_farm_id,
            include_husbandry_storage=plan.include_husbandry_storage,
        )
        if plan.move_animals
        else None
    )
    mon = (
        migrate_money(src, tgt, plan.src_farm_id, plan.tgt_farm_id)
        if plan.move_money
        else None
    )
    stats = (
        migrate_farm_statistics(src, tgt, plan.src_farm_id, plan.tgt_farm_id)
        if plan.move_farm_statistics
        else None
    )
    obj = (
        migrate_object_storage(src, tgt, plan.storage_mapping, farm_id=plan.tgt_farm_id)
        if plan.move_object_storage
        else None
    )
    silage = (
        sell_silage_to_money(src, tgt, plan.tgt_farm_id)
        if plan.sell_bunker_silage
        else None
    )

    out = tgt.write_to(plan.output_path)

    # AFTER write_to so source files overwrite anything the target had.
    mod_files = (
        copy_mod_files(plan.source_path, out, plan.mod_file_includes)
        if plan.mod_file_includes else None
    )

    return MigrationReport(
        vehicles=veh,
        items=itm,
        silos=silo,
        animals=ani,
        money=mon,
        farm_stats=stats,
        object_storage=obj,
        silage_sale=silage,
        mod_files=mod_files,
        player_placeables=placeables_copy,
        mods_list=mods_list,
        output_path=str(out),
    )
