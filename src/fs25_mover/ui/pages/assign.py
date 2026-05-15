"""Assignment page: PDA on the left, source -> target dropdowns on the right.

Right-click on the PDA sets the vehicle drop zone. Each source silo / pen
appears as a row with a combo box listing all candidate target placeables.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from ...model.poi import CATEGORY_COLOR
from ...parsers.dds import dds_to_qimage
from ...parsers.map_zip import MapSource
from ..pda_view import Marker, PdaView


class AssignPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Assign destinations")
        self.setSubTitle(
            "Right-click the PDA to choose where vehicles & bales should land. "
            "Pick destination silo and pen for each source one."
        )
        self._initialised = False

        # Filled in on initializePage() once we know map + savegame.
        self.view: PdaView | None = None
        self.drop_label = QLabel("Vehicle drop zone: <not set — right-click the map>")
        self.silo_combos: dict[str, QComboBox] = {}
        self.pen_combos: dict[str, QComboBox] = {}

        # Heading picker.
        self.yaw_combo = QComboBox()
        # Yaw degrees → label. Values match FS25 convention (Y-axis rotation).
        for label, deg in (
            ("North (facing -Z)", 0.0),
            ("East (facing +X)", 90.0),
            ("South (facing +Z)", 180.0),
            ("West (facing -X)", -90.0),
        ):
            self.yaw_combo.addItem(label, deg)
        self.yaw_combo.currentIndexChanged.connect(self._yaw_changed)

        yaw_row = QHBoxLayout()
        yaw_row.addWidget(QLabel("All vehicles face:"))
        yaw_row.addWidget(self.yaw_combo, 1)

        # Spacing controls.
        self.col_spin = QDoubleSpinBox()
        self.col_spin.setRange(2.0, 30.0)
        self.col_spin.setSingleStep(0.5)
        self.col_spin.setSuffix(" m")
        self.col_spin.setValue(10.0)
        self.col_spin.valueChanged.connect(self._spacing_changed)

        self.row_spin = QDoubleSpinBox()
        self.row_spin.setRange(2.0, 50.0)
        self.row_spin.setSingleStep(0.5)
        self.row_spin.setSuffix(" m")
        self.row_spin.setValue(10.0)
        self.row_spin.valueChanged.connect(self._spacing_changed)

        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 30)
        self.cols_spin.setValue(10)
        self.cols_spin.valueChanged.connect(self._spacing_changed)

        spacing_row = QHBoxLayout()
        spacing_row.addWidget(QLabel("Side gap:"))
        spacing_row.addWidget(self.col_spin)
        spacing_row.addSpacing(12)
        spacing_row.addWidget(QLabel("Front-back gap:"))
        spacing_row.addWidget(self.row_spin)
        spacing_row.addSpacing(12)
        spacing_row.addWidget(QLabel("Per row:"))
        spacing_row.addWidget(self.cols_spin)
        spacing_row.addStretch(1)

        # Layout shell.
        self._left = QVBoxLayout()
        self._left.addWidget(self.drop_label)
        self._left.addLayout(yaw_row)
        self._left.addLayout(spacing_row)
        self._right = QVBoxLayout()

        outer = QHBoxLayout()
        outer.addLayout(self._left, 3)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_panel = QWidget()
        right_panel.setLayout(self._right)
        right_scroll.setWidget(right_panel)
        outer.addWidget(right_scroll, 2)
        self.setLayout(outer)

    def initializePage(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        state = self._wizard.state
        assert state.source_sg and state.target_sg and state.map_path

        # --- Build the PDA view ---
        with MapSource(str(state.map_path)) as src:
            dds = src.overview_bytes()
            playable_px = src.playable_image_size()
            world_size = src.world_size() or 2048.0
        img = dds_to_qimage(dds)
        self.view = PdaView(img, world_size=world_size, playable_px=playable_px)
        self.view.add_origin_crosshair()
        # Only render the placeables the user is actually choosing between on
        # this page (silos + pens). Sheds, productions, sellpoints, etc. are
        # noise here and will be added later behind category toggles.
        relevant = {"silo", "pen"}
        for poi in state.target_pois:
            if poi.category not in relevant:
                continue
            self.view.add_marker(
                Marker(
                    label=poi.label,
                    world_x=poi.world_x,
                    world_z=poi.world_z,
                    color=QColor(CATEGORY_COLOR.get(poi.category, "#cccccc")),
                    radius_px=7.0,
                )
            )
        self.view.clicked_world.connect(self._on_pda_clicked)
        self._left.insertWidget(0, self.view, 1)
        # Fit after the widget has a non-zero size.
        self.view.showEvent = self._wrap_first_show(self.view.showEvent)

        # --- Right side: dropdowns for silos and pens ---
        self._build_silo_section(state)
        self._build_pen_section(state)
        self._right.addStretch(1)

    def _wrap_first_show(self, original):
        view = self.view
        called = {"v": False}
        def wrapped(event):
            original(event)
            if not called["v"]:
                called["v"] = True
                view.fit_image()
        return wrapped

    def _yaw_changed(self) -> None:
        self._wizard.state.vehicle_yaw_deg = float(self.yaw_combo.currentData() or 0.0)

    def _spacing_changed(self) -> None:
        st = self._wizard.state
        st.vehicle_col_pitch = float(self.col_spin.value())
        st.vehicle_row_pitch = float(self.row_spin.value())
        st.vehicle_cols_per_row = int(self.cols_spin.value())

    def _on_pda_clicked(self, wx: float, wz: float) -> None:
        # Sample terrain Y at the click so vehicles spawn on the ground, not
        # falling from 100m. +0.3m headroom keeps them just above terrain.
        state = self._wizard.state
        ground_y = None
        if state.map_path is not None:
            with MapSource(str(state.map_path)) as src:
                ground_y = src.sample_height(wx, wz)
        y = (ground_y + 0.3) if ground_y is not None else 100.0
        state.drop_xyz = (wx, y, wz)
        note = f"ground y={ground_y:.2f}" if ground_y is not None else "fallback y=100 (no height sample)"
        self.drop_label.setText(f"Vehicle drop zone: ({wx:.1f}, {wz:.1f})  — {note}")
        self.completeChanged.emit()

    def _build_silo_section(self, state) -> None:
        # Source silos with content; only <fillUnit> grain (bunker silage is skipped).
        src_grain = []
        for placeable in state.source_sg.placeables():
            units = placeable.findall(".//fillUnit/unit")
            grain = sum(float(u.get("fillLevel") or 0) for u in units)
            if grain > 0:
                src_grain.append((placeable, grain))

        target_silos = [
            p for p in state.target_pois
            if p.category == "silo" and (p.farm_id == 1 or p.farm_id == 0)
        ]

        box = QGroupBox("Storage silos (grain — bunker silage is NOT migrated)")
        form = QFormLayout()
        if not src_grain:
            form.addRow(QLabel("(No loose grain in source silos to migrate.)"))
        else:
            for placeable, total in src_grain:
                uid = placeable.get("uniqueId") or ""
                src_label = f"{placeable.get('filename', '?').rsplit('/', 1)[-1]}  ({total:,.0f} kg)"
                combo = QComboBox()
                combo.addItem("(skip)", "")
                for t in target_silos:
                    combo.addItem(f"{t.label}  ({t.world_x:.0f}, {t.world_z:.0f})", t.uid)
                combo.currentIndexChanged.connect(self._silo_changed)
                self.silo_combos[uid] = combo
                form.addRow(QLabel(src_label), combo)
        box.setLayout(form)
        self._right.addWidget(box)

    def _build_pen_section(self, state) -> None:
        # Source pens with animals.
        src_pens = []
        for placeable in state.source_sg.placeables():
            animals = placeable.findall(".//husbandryAnimals/clusters/animal")
            if animals:
                src_pens.append((placeable, animals))

        target_pens = [p for p in state.target_pois if p.category == "pen"]

        box = QGroupBox("Animal pens")
        form = QFormLayout()
        if not src_pens:
            form.addRow(QLabel("(No populated pens in source save.)"))
        else:
            for placeable, animals in src_pens:
                uid = placeable.get("uniqueId") or ""
                from collections import Counter
                cnt = Counter()
                for a in animals:
                    cnt[a.get("subType") or "?"] += int(a.get("numAnimals") or 1)
                src_label = f"{placeable.get('filename', '?').rsplit('/', 1)[-1]}  "
                src_label += "  ".join(f"{n}× {t}" for t, n in cnt.most_common())
                combo = QComboBox()
                combo.addItem("(skip)", "")
                for t in target_pens:
                    combo.addItem(f"{t.label}  ({t.world_x:.0f}, {t.world_z:.0f})", t.uid)
                combo.currentIndexChanged.connect(self._pen_changed)
                self.pen_combos[uid] = combo
                form.addRow(QLabel(src_label), combo)
        box.setLayout(form)
        self._right.addWidget(box)

    def _silo_changed(self) -> None:
        self._wizard.state.silo_mapping = {
            src_uid: c.currentData()
            for src_uid, c in self.silo_combos.items()
            if c.currentData()
        }
        self.completeChanged.emit()

    def _pen_changed(self) -> None:
        self._wizard.state.pen_mapping = {
            src_uid: c.currentData()
            for src_uid, c in self.pen_combos.items()
            if c.currentData()
        }
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        # Don't gate on dropdowns — user may legitimately skip all silos/pens.
        # Just require a drop zone so vehicles aren't dumped at (0,0,0).
        return self._wizard.state.drop_xyz is not None
