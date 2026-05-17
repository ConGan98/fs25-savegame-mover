"""Assignment page: PDA on the left, source -> target dropdowns on the right.

Right-click on the PDA sets the vehicle drop zone. Each source silo / pen
appears as a row with a combo box listing all candidate target placeables.
"""
from __future__ import annotations

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


def _farm_id_tag(farm_id: int | None) -> str:
    """Short suffix annotating who owns a target placeable.

    farmId 1 = your farm (no tag). 0 = unowned/buyable. Other = AI/NPC farm.
    """
    if farm_id == 1 or farm_id is None:
        return ""
    if farm_id == 0:
        return "  [unowned — buy in-game first]"
    return f"  [farm {farm_id} — NPC-owned, buy before use]"


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

        # --- Shared lookups for the dropdown builders ---
        # Open the map zip once, harvest preplaced xmlFilenames from the i3d.
        # All three section builders below reuse these caches.
        from ...parsers.i3d import filenames_for_savegame
        from ...parsers.fs25_root import read_placeable_xml_bytes
        info = getattr(state, "fs25_root_info", None)
        self._mods_dir = info.mods_dir if info else None
        self._install_dir = info.install_dir if info else None
        self._i3d_filenames: dict[str, str] = {}
        try:
            with MapSource(str(state.map_path)) as _ms:
                self._i3d_filenames = filenames_for_savegame(_ms)
        except (FileNotFoundError, OSError):
            pass
        self._tp_by_uid = {
            (x.get("uniqueId") or ""): x for x in state.target_sg.placeables()
        }
        self._xml_cache: dict[str, bytes | None] = {}

        def _read_xml(fn: str | None) -> bytes | None:
            if not fn:
                return None
            if fn in self._xml_cache:
                return self._xml_cache[fn]
            data = read_placeable_xml_bytes(
                fn, self._mods_dir, self._install_dir, state.map_path,
            )
            self._xml_cache[fn] = data
            return data
        self._read_placeable_xml = _read_xml

        def _filename_for(tp) -> str | None:
            if tp is None:
                return None
            fn = tp.get("filename")
            if fn:
                return fn
            return self._i3d_filenames.get(tp.get("uniqueId") or "")
        self._filename_for = _filename_for

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

        # Build target silo list, with friendly name + accepted-fillType cache.
        # A target appears in the dropdown if it's classified as silo OR its
        # type XML declares silo capability. We annotate each option with
        # ownership and the fillTypes it can accept.
        from ...model.poi import PoiMarker
        from ...parsers.fs25_root import (
            placeable_accepted_fill_types,
            placeable_declares_silo,
            placeable_friendly_name,
        )

        _xml = self._read_placeable_xml
        _filename_for = self._filename_for
        tp_by_uid = self._tp_by_uid
        poi_by_uid = {p.uid: p for p in state.target_pois}
        candidates: list = []  # tuples (uid, fn, farm_id, label, x, z)
        seen_uids: set[str] = set()
        for p in state.target_pois:
            if p.category == "silo" and p.uid not in seen_uids:
                seen_uids.add(p.uid)
                tp = tp_by_uid.get(p.uid)
                fn = _filename_for(tp) if tp is not None else None
                candidates.append((p.uid, fn, p.farm_id, p.label, p.world_x, p.world_z))
        for tp in state.target_sg.placeables():
            uid = tp.get("uniqueId") or ""
            if uid in seen_uids:
                continue
            fn = _filename_for(tp)
            if not placeable_declares_silo(_xml(fn)):
                continue
            farm_id_raw = tp.get("farmId")
            try:
                farm_id = int(farm_id_raw) if farm_id_raw is not None else None
            except ValueError:
                farm_id = None
            candidates.append((uid, fn, farm_id, (fn or "?").rsplit("/", 1)[-1].rsplit(".", 1)[0], 0.0, 0.0))
            seen_uids.add(uid)

        # Resolve friendly name + accepts for each candidate.
        target_silos: list[tuple[PoiMarker, set[str] | None]] = []
        for uid, fn, farm_id, fallback_label, wx, wz in candidates:
            data = _xml(fn)
            tp = tp_by_uid.get(uid)
            name = placeable_friendly_name(data, tp) or fallback_label
            accepts = placeable_accepted_fill_types(data)
            marker = PoiMarker(
                uid=uid, label=name, category="silo",
                world_x=wx, world_z=wz, farm_id=farm_id,
            )
            target_silos.append((marker, accepts))
        target_silos.sort(key=lambda t: (t[0].farm_id != 1, t[0].farm_id != 0, t[0].label))

        box = QGroupBox("Storage silos (grain — bunker silage is NOT migrated)")
        form = QFormLayout()
        if not src_grain:
            form.addRow(QLabel("(No loose grain in source silos to migrate.)"))
        else:
            for placeable, per_ft in src_grain:
                uid = placeable.get("uniqueId") or ""
                summary = ", ".join(f"{int(v):,} {ft}" for ft, v in per_ft.most_common())
                src_fn = (placeable.get("filename", "?") or "?").rsplit("/", 1)[-1]
                src_pretty = (
                    placeable_friendly_name(_xml(placeable.get("filename")), placeable)
                    or src_fn.rsplit(".", 1)[0]
                )
                src_label = f"{src_pretty}  ({summary})"
                # Source's stored fillTypes — used to filter targets.
                src_fts = set(per_ft.keys())
                combo = QComboBox()
                combo.addItem("(skip)", "")
                # Order: compatible matches first (everything the source needs
                # is acceptable), then partial matches, then incompatible.
                def _compat(t_accepts, src_set):
                    if t_accepts is None:
                        return 1   # unknown — middling priority, no warning
                    if src_set <= t_accepts:
                        return 0   # all source types accepted
                    if src_set & t_accepts:
                        return 2   # partial overlap
                    return 3       # nothing accepted
                ordered = sorted(
                    target_silos,
                    key=lambda t: (_compat(t[1], src_fts), t[0].farm_id != 1,
                                   t[0].farm_id != 0, t[0].label),
                )
                for marker, accepts in ordered:
                    tag = _farm_id_tag(marker.farm_id)
                    pos_part = (
                        f"  ({marker.world_x:.0f}, {marker.world_z:.0f})"
                        if (marker.world_x or marker.world_z) else ""
                    )
                    if accepts is None:
                        fit = "  [accepts ?]"
                    elif src_fts <= accepts:
                        fit = ""
                    elif src_fts & accepts:
                        missing = ", ".join(sorted(src_fts - accepts))[:40]
                        fit = f"  [partial — won't take {missing}]"
                    else:
                        fit = "  [WRONG TYPE]"
                    combo.addItem(f"{marker.label}{pos_part}{tag}{fit}", marker.uid)
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

        # All pens, regardless of farmId — annotated in the dropdown so the
        # user sees who currently owns each one. Use the placeable type's
        # storeData name when available for friendlier labels. Filename lookup
        # falls back to the map's i3d for preplaced placeables.
        from ...parsers.fs25_root import (
            placeable_animal_type,
            placeable_friendly_name,
        )
        from ...model.poi import PoiMarker

        _xml = self._read_placeable_xml
        _filename_for = self._filename_for
        tp_by_uid = self._tp_by_uid

        target_pens_raw = [p for p in state.target_pois if p.category == "pen"]
        # Build (marker, species) pairs so we can filter against source pen animal type.
        target_pens: list[tuple[PoiMarker, str | None]] = []
        for p in target_pens_raw:
            tp = tp_by_uid.get(p.uid)
            fn = _filename_for(tp)
            data = _xml(fn)
            pretty = placeable_friendly_name(data, tp) or p.label
            species = placeable_animal_type(data)
            target_pens.append((
                PoiMarker(
                    uid=p.uid, label=pretty, category="pen",
                    world_x=p.world_x, world_z=p.world_z, farm_id=p.farm_id,
                ),
                species,
            ))
        target_pens.sort(key=lambda t: (t[0].farm_id != 1, t[0].farm_id != 0, t[0].label))

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

        from ...parsers.fs25_root import animal_subtype_species
        if not src_pens:
            form.addRow(QLabel("(No populated pens in source save.)"))
        else:
            for placeable, animals in src_pens:
                uid = placeable.get("uniqueId") or ""
                from collections import Counter
                cnt = Counter()
                species_cnt: Counter = Counter()
                for a in animals:
                    sub = a.get("subType") or "?"
                    n = int(a.get("numAnimals") or 1)
                    cnt[sub] += n
                    sp = animal_subtype_species(sub)
                    if sp:
                        species_cnt[sp] += n
                # Source pen's dominant species (e.g. cow pen w/ 1 stray sheep -> COW)
                src_species = species_cnt.most_common(1)[0][0] if species_cnt else None

                src_fn = (placeable.get('filename', '?').rsplit('/', 1)[-1])
                src_pretty = placeable_friendly_name(
                    _xml(placeable.get("filename")),
                    placeable,
                ) or src_fn.rsplit(".", 1)[0]
                src_label = f"{src_pretty}  ({sum(cnt.values())} {src_species or 'animals'}: "
                src_label += ", ".join(f"{n}× {t}" for t, n in cnt.most_common()) + ")"

                # Sort targets: compatible-species first, then unknown, then wrong.
                def _compat(target_species):
                    if target_species is None:
                        return 1            # unknown — middle priority
                    if src_species is None:
                        return 1            # source unknown — let user pick
                    return 0 if target_species == src_species else 2
                ordered = sorted(
                    target_pens,
                    key=lambda t: (_compat(t[1]), t[0].farm_id != 1, t[0].farm_id != 0, t[0].label),
                )

                combo = QComboBox()
                combo.addItem("(skip)", "")
                for marker, target_species in ordered:
                    tag = _farm_id_tag(marker.farm_id)
                    if target_species is None or src_species is None:
                        fit = "  [accepts ?]" if target_species is None else ""
                    elif target_species == src_species:
                        fit = ""
                    else:
                        fit = f"  [WRONG ANIMAL — accepts {target_species}]"
                    combo.addItem(
                        f"{marker.label}  ({marker.world_x:.0f}, {marker.world_z:.0f}){tag}{fit}",
                        marker.uid,
                    )
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

        # Target candidates. FS25 only writes <objectStorage> into the savegame
        # once something is stored, so empty sheds are invisible by element
        # alone. We also consult the placeable's source XML (from the mod zip
        # or game install) and accept any whose type declares <objectStorage>.
        # Result: empty player-placed sheds appear in the dropdown.
        from ...model.poi import PoiMarker
        from ...parsers.fs25_root import (
            placeable_declares_object_storage,
            placeable_friendly_name,
        )

        _xml = self._read_placeable_xml
        i3d_filenames = self._i3d_filenames

        target_storage = []
        poi_by_uid = {p.uid: p for p in state.target_pois}
        for tp in state.target_sg.placeables():
            uid = tp.get("uniqueId") or ""
            fn = tp.get("filename") or i3d_filenames.get(uid)
            has_element = tp.find(".//objectStorage") is not None
            if not has_element and not placeable_declares_object_storage(_xml(fn)):
                continue
            farm_id_raw = tp.get("farmId")
            try:
                farm_id = int(farm_id_raw) if farm_id_raw is not None else None
            except ValueError:
                farm_id = None
            existing = poi_by_uid.get(uid)
            pretty = placeable_friendly_name(_xml(fn), tp)
            if existing is not None:
                target_storage.append(PoiMarker(
                    uid=existing.uid, label=pretty or existing.label, category="storage",
                    world_x=existing.world_x, world_z=existing.world_z,
                    farm_id=existing.farm_id,
                ))
            else:
                label = pretty or (fn or "?").rsplit("/", 1)[-1].rsplit(".", 1)[0]
                target_storage.append(PoiMarker(
                    uid=uid, label=label, category="storage",
                    world_x=0.0, world_z=0.0, farm_id=farm_id,
                ))
        target_storage.sort(key=lambda p: (p.farm_id != 1, p.farm_id != 0, p.label))

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
                    tag = _farm_id_tag(t.farm_id)
                    pos_part = (
                        f"  ({t.world_x:.0f}, {t.world_z:.0f})"
                        if (t.world_x or t.world_z) else ""
                    )
                    combo.addItem(f"{t.label}{pos_part}{tag}", t.uid)
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
