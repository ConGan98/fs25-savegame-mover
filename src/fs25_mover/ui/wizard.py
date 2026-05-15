"""Main migration wizard.

Pages share state via `WizardState` attached to the wizard instance — easier to
work with than QWizard's field() machinery for the structured data we move
around (Savegame, MapSource, MigrationPlan, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWizard

from ..model.migration_plan import MigrationPlan
from ..model.poi import PoiMarker
from ..parsers.savegame import Savegame


@dataclass
class WizardState:
    source_sg: Savegame | None = None
    target_sg: Savegame | None = None
    map_path: Path | None = None
    target_pois: list[PoiMarker] = field(default_factory=list)
    drop_xyz: tuple[float, float, float] | None = None
    vehicle_yaw_deg: float = 0.0
    vehicle_col_pitch: float = 10.0
    vehicle_row_pitch: float = 10.0
    vehicle_cols_per_row: int = 10
    silo_mapping: dict[str, str] = field(default_factory=dict)
    pen_mapping: dict[str, str] = field(default_factory=dict)
    output_path: Path | None = None

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
            silo_mapping=dict(self.silo_mapping),
            pen_mapping=dict(self.pen_mapping),
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
        from .pages.welcome import WelcomePage
        from .pages.source import SourcePage
        from .pages.target import TargetPage
        from .pages.assign import AssignPage
        from .pages.review import ReviewPage
        from .pages.run import RunPage

        self.addPage(WelcomePage(self))
        self.addPage(SourcePage(self))
        self.addPage(TargetPage(self))
        self.addPage(AssignPage(self))
        self.addPage(ReviewPage(self))
        self.addPage(RunPage(self))
