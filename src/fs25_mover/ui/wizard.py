"""Main migration wizard.

Pages share state via `WizardState` attached to the wizard instance — easier to
work with than QWizard's field() machinery for the structured data we move
around (Savegame, MapSource, MigrationPlan, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import QWizard

from ..model.migration_plan import MigrationPlan
from ..model.poi import PoiMarker
from ..parsers.fs25_root import Fs25RootInfo
from ..parsers.savegame import Savegame


@dataclass
class WizardState:
    fs25_root_info: Fs25RootInfo | None = None
    source_sg: Savegame | None = None
    target_sg: Savegame | None = None
    map_path: Path | None = None
    target_pois: list[PoiMarker] = field(default_factory=list)
    drop_xyz: tuple[float, float, float] | None = None
    vehicle_yaw_deg: float = 0.0
    vehicle_col_pitch: float = 10.0
    vehicle_row_pitch: float = 10.0
    vehicle_cols_per_row: int = 10
    include_husbandry_storage: bool = True
    sell_bunker_silage: bool = False
    move_farm_statistics: bool = True
    preserve_vehicle_positions: bool = False
    copy_player_placeables: bool = False
    silo_mapping: dict[str, str] = field(default_factory=dict)
    pen_mapping: dict[str, str] = field(default_factory=dict)
    storage_mapping: dict[str, str] = field(default_factory=dict)
    mod_file_includes: list[str] = field(default_factory=list)
    output_path: Path | None = None

    @property
    def is_same_map_upgrade(self) -> bool:
        """True when source and target reference the same map mod by mapId.
        In this mode the wizard pre-fills mappings, keeps vehicle positions,
        and defaults terrain-bound mod files to ON."""
        if self.source_sg is None or self.target_sg is None:
            return False
        src_id = self.source_sg.map_id
        tgt_id = self.target_sg.map_id
        return bool(src_id and tgt_id and src_id == tgt_id)

    def to_plan(self) -> MigrationPlan:
        assert self.source_sg and self.target_sg and self.output_path
        drop = self.drop_xyz or (0.0, 100.0, 0.0)
        return MigrationPlan(
            source_path=str(self.source_sg.path),
            target_path=str(self.target_sg.path),
            output_path=str(self.output_path),
            drop_xyz=drop,
            vehicle_yaw_deg=self.vehicle_yaw_deg,
            vehicle_col_pitch=self.vehicle_col_pitch,
            vehicle_row_pitch=self.vehicle_row_pitch,
            vehicle_cols_per_row=self.vehicle_cols_per_row,
            include_husbandry_storage=self.include_husbandry_storage,
            sell_bunker_silage=self.sell_bunker_silage,
            move_farm_statistics=self.move_farm_statistics,
            preserve_vehicle_positions=self.preserve_vehicle_positions,
            copy_player_placeables=self.copy_player_placeables,
            silo_mapping=dict(self.silo_mapping),
            pen_mapping=dict(self.pen_mapping),
            storage_mapping=dict(self.storage_mapping),
            mod_file_includes=list(self.mod_file_includes),
        )


class MigrationWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FS25 Savegame Mover")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.IndependentPages, False)
        self.resize(1280, 900)

        self.state = WizardState()

        # Import pages lazily to keep import-time small.
        from .pages.setup import SetupPage
        from .pages.source import SourcePage
        from .pages.target import TargetPage
        from .pages.assign import AssignPage
        from .pages.review import ReviewPage
        from .pages.modfiles import ModFilesPage
        from .pages.run import RunPage

        self.addPage(SetupPage(self))
        self.addPage(SourcePage(self))
        self.addPage(TargetPage(self))
        self.addPage(AssignPage(self))
        self.addPage(ReviewPage(self))
        self.addPage(ModFilesPage(self))
        self.addPage(RunPage(self))
