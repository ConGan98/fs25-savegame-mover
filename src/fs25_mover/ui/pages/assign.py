"""Assignment page: PDA on the left, source -> target dropdowns on the right.

Right-click on the PDA sets the vehicle drop zone. Each source silo / pen
appears as a row with a combo box listing all candidate target placeables.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
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
        self.storage_combos: dict[str, QComboBox] = {}

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
        # Render every POI into its category sub-group so the toggle row can
        # show/hide them independently. Defaults set after creation.
        for poi in state.target_pois:
            self.view.add_marker(
                Marker(
                    label=poi.label,
                    world_x=poi.world_x,
                    world_z=poi.world_z,
                    color=QColor(CATEGORY_COLOR.get(poi.category, "#cccccc")),
                    radius_px=7.0,
                ),
                category=poi.category,
            )

        # Toggle row above the PDA: silo/pen/storage on by default; the rest off.
        self._default_visible = {"silo", "pen", "storage"}
        self._category_checks: dict[str, QCheckBox] = {}
        toggle_row = self._build_category_toggle_row(state.target_pois)
        self.view.clicked_world.connect(self._on_pda_clicked)
        self._left.insertLayout(0, toggle_row)
        self._left.insertWidget(1, self.view, 1)
        # Fit after the widget has a non-zero size.
        self.view.showEvent = self._wrap_first_show(self.view.showEvent)

        # --- Right side: dropdowns for silos, pens, and bale/pallet storage ---
        self._build_silo_section(state)
        self._build_pen_section(state)
        self._build_storage_section(state)
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

    def _build_category_toggle_row(self, pois):
        """Row of checkboxes — one per POI category that has at least one marker.
        Defaults: silo/pen/storage = on, everything else = off."""
        from collections import Counter
        from PySide6.QtCore import Qt

        counts: Counter = Counter(p.category for p in pois)
        # Stable, ordered list of categories that exist on this map.
        order = ["silo", "pen", "storage", "sell", "production", "shop", "shed", "other"]
        row = QHBoxLayout()
        row.addWidget(QLabel("Show on map:"))
        for cat in order:
            n = counts.get(cat, 0)
            if n == 0:
                continue
            color = CATEGORY_COLOR.get(cat, "#cccccc")
            cb = QCheckBox(f"{cat} ({n})")
            cb.setChecked(cat in self._default_visible)
            # Tint the checkbox text in the category colour so it's obvious.
            cb.setStyleSheet(f"QCheckBox {{ color: {color}; font-weight: bold; }}")
            cb.toggled.connect(lambda checked, c=cat: self._on_category_toggled(c, checked))
            self._category_checks[cat] = cb
            row.addWidget(cb)
            # Apply default visibility right away.
            self.view.set_category_visible(cat, cat in self._default_visible)
        row.addStretch(1)
        return row

    def _on_category_toggled(self, category: str, checked: bool) -> None:
        self.view.set_category_visible(category, checked)

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
        # Source silos with stored grain / diesel / fertiliser etc. FS25 uses
        # two shapes:
        #   - <fillUnit><unit fillType="WHEAT" fillLevel="..."/></fillUnit>
        #   - <silo><storage><node fillType="WHEAT" fillLevel="..."/></storage></silo>
        # We accept either. <storage> entries inside <husbandry> are ignored
        # (those are pen-internal stores).
        from collections import Counter
        src_grain = []
        for placeable in state.source_sg.placeables():
            per_ft: Counter = Counter()
            for u in placeable.findall(".//fillUnit/unit"):
                ft = u.get("fillType") or "?"
                try:
                    fl = float(u.get("fillLevel") or 0)
                except ValueError:
                    fl = 0.0
                if fl > 0:
                    per_ft[ft] += fl
            for storage in placeable.findall(".//storage"):
                # Skip husbandry-internal storage.
                anc = storage.getparent()
                under_husbandry = False
                while anc is not None and anc is not placeable:
                    if anc.tag == "husbandry":
                        under_husbandry = True
                        break
                    anc = anc.getparent()
                if under_husbandry:
                    continue
                for node in storage.findall("node"):
                    ft = node.get("fillType") or "?"
                    try:
                        fl = float(node.get("fillLevel") or 0)
                    except ValueError:
                        fl = 0.0
                    if fl > 0:
                        per_ft[ft] += fl
            if per_ft:
                src_grain.append((placeable, per_ft))

        target_silos = [
            p for p in state.target_pois
            if p.category == "silo" and (p.farm_id == 1 or p.farm_id == 0)
        ]

        box = QGroupBox("Storage silos (grain — bunker silage is NOT migrated)")
        form = QFormLayout()
        if not src_grain:
            form.addRow(QLabel("(No loose grain in source silos to migrate.)"))
        else:
            for placeable, per_ft in src_grain:
                uid = placeable.get("uniqueId") or ""
                summary = ", ".join(f"{int(v):,} {ft}" for ft, v in per_ft.most_common())
                fn = (placeable.get("filename", "?") or "?").rsplit("/", 1)[-1]
                src_label = f"{fn}  ({summary})"
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

        # Toggle: also move everything in the husbandry's <storage> — food
        # (hay / grass / silage / TMR / grain / forage), bedding (straw),
        # water, and produced outputs (slurry / manure / milk).
        self.husb_storage_check = QCheckBox(
            "Also move food, water, bedding and produced slurry/milk stored in the pen"
        )
        self.husb_storage_check.setChecked(state.include_husbandry_storage)
        self.husb_storage_check.toggled.connect(self._husb_storage_toggled)
        form.addRow(self.husb_storage_check)

        # Optional silage cash-out — preview the value live.
        from ...migrate.silage_sale import (
            silage_avg_price_per_litre,
            total_bunker_silage,
        )
        litres, n_bunkers = total_bunker_silage(state.source_sg)
        price = silage_avg_price_per_litre(state.source_sg) if litres > 0 else 0.0
        proceeds = litres * price
        if litres > 0:
            label_txt = (
                f"Sell bunker silage instead of losing it  "
                f"({litres:,.0f} L × ${price:.4f}/L = ${proceeds:,.0f} added to farm money)"
            )
        else:
            label_txt = "Sell bunker silage instead of losing it  (no silage to sell)"
        self.sell_silage_check = QCheckBox(label_txt)
        self.sell_silage_check.setChecked(state.sell_bunker_silage)
        self.sell_silage_check.setEnabled(litres > 0)
        self.sell_silage_check.toggled.connect(self._sell_silage_toggled)
        form.addRow(self.sell_silage_check)

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

    def _husb_storage_toggled(self, checked: bool) -> None:
        self._wizard.state.include_husbandry_storage = checked

    def _sell_silage_toggled(self, checked: bool) -> None:
        self._wizard.state.sell_bunker_silage = checked

    def _build_storage_section(self, state) -> None:
        # Source placeables with <objectStorage> that has content.
        from collections import Counter
        src_storage = []
        for p in state.source_sg.placeables():
            objs = p.findall(".//objectStorage/object")
            if objs:
                src_storage.append((p, objs))

        # Target candidates: any placeable that has an <objectStorage> element
        # (even empty). This catches placeables whose primary category is
        # "pen" or "silo" but which ALSO act as auto-storage (e.g. multi-purpose
        # mod sheds). We synthesize a tiny POI-like row for the dropdown.
        from ...model.poi import PoiMarker
        target_storage = []
        # Match each target placeable to a known POI marker (for position) when
        # possible — otherwise use a (0,0) placeholder for the label.
        poi_by_uid = {p.uid: p for p in state.target_pois}
        for tp in state.target_sg.placeables():
            if tp.find(".//objectStorage") is None:
                continue
            uid = tp.get("uniqueId") or ""
            farm_id = tp.get("farmId")
            # Only show targets owned by farm 1 or 0 (player-accessible).
            if farm_id not in ("1", "0"):
                continue
            existing = poi_by_uid.get(uid)
            if existing is not None:
                target_storage.append(existing)
            else:
                label = (tp.get("filename") or "?").rsplit("/", 1)[-1].rsplit(".", 1)[0]
                target_storage.append(PoiMarker(
                    uid=uid, label=label, category="storage",
                    world_x=0.0, world_z=0.0, farm_id=int(farm_id) if farm_id else None,
                ))

        box = QGroupBox("Bale / pallet storage sheds (auto-storage)")
        form = QFormLayout()
        if not src_storage:
            form.addRow(QLabel("(No source placeables with stored bales/pallets.)"))
        else:
            for placeable, objs in src_storage:
                uid = placeable.get("uniqueId") or ""
                # Count by className + fillType so the user knows what's inside.
                cnt: Counter = Counter()
                for o in objs:
                    kind = "Bale" if o.get("className") == "Bale" else "Pallet"
                    ft = o.get("fillType") or "?"
                    cnt[(kind, ft)] += 1
                summary = "  ".join(
                    f"{n}× {kind} {ft}" for (kind, ft), n in cnt.most_common()
                )
                src_label = f"{placeable.get('filename', '?').rsplit('/', 1)[-1]}  {summary}"
                combo = QComboBox()
                combo.addItem("(skip)", "")
                for t in target_storage:
                    combo.addItem(f"{t.label}  ({t.world_x:.0f}, {t.world_z:.0f})", t.uid)
                combo.currentIndexChanged.connect(self._storage_changed)
                self.storage_combos[uid] = combo
                form.addRow(QLabel(src_label), combo)
            if not target_storage:
                form.addRow(QLabel(
                    "<i>No auto-storage sheds on the target map. Place one in-game first, "
                    "then re-run the wizard if you want to migrate these.</i>"
                ))
        box.setLayout(form)
        self._right.addWidget(box)

    def _storage_changed(self) -> None:
        self._wizard.state.storage_mapping = {
            src_uid: c.currentData()
            for src_uid, c in self.storage_combos.items()
            if c.currentData()
        }
        self.completeChanged.emit()

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
