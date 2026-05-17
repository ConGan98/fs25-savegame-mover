"""Target page: pick which save to migrate INTO, auto-resolve its map mod."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWizardPage,
)

from ...model.farm import FarmSnapshot
from ...model.poi import resolve_pois
from ...parsers.fs25_root import resolve_map_mod_for
from ...parsers.i3d import positions_for_savegame
from ...parsers.map_zip import MapSource
from ...parsers.savegame import Savegame


class TargetPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Target savegame + map")
        self.setSubTitle(
            "A fresh save on the NEW map (start one in-game first). "
            "We'll auto-find the map mod zip; override with Browse if needed."
        )

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_save_change)

        self.map_edit = QLineEdit()
        self.map_edit.setPlaceholderText("(auto-resolved when you pick the save)")
        map_browse = QPushButton("Browse…")
        map_browse.clicked.connect(self._browse_map)

        self.summary = QTextBrowser()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(300)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Target save:"))
        save_row.addWidget(self.combo, 1)

        map_row = QHBoxLayout()
        map_row.addWidget(QLabel("Map mod:"))
        map_row.addWidget(self.map_edit, 1)
        map_row.addWidget(map_browse)

        layout = QVBoxLayout()
        layout.addLayout(save_row)
        layout.addLayout(map_row)
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary, 1)
        self.setLayout(layout)

        self._tgt_loaded = False
        self._map_loaded = False

    def initializePage(self) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("(pick a fresh target save…)", None)
        info = getattr(self._wizard.state, "fs25_root_info", None)
        if info is not None:
            # Highlight fresh saves first.
            for save in sorted(
                info.saves, key=lambda s: (not s.is_fresh, s.map_title or "", s.slot)
            ):
                if self._wizard.state.source_sg is not None and Path(
                    self._wizard.state.source_sg.path
                ) == save.folder:
                    continue  # don't allow same save as source
                self.combo.addItem(save.display, save)
        self.combo.blockSignals(False)
        self._tgt_loaded = False
        self._map_loaded = False
        self.completeChanged.emit()

    def _on_save_change(self) -> None:
        save = self.combo.currentData()
        if save is None:
            self._tgt_loaded = False
            self._map_loaded = False
            self.summary.clear()
            self.completeChanged.emit()
            return
        try:
            sg = Savegame.load(save.folder)
        except Exception as exc:
            self.summary.setPlainText(f"Failed to load target save:\n{exc}")
            self._tgt_loaded = False
            self.completeChanged.emit()
            return
        self._wizard.state.target_sg = sg
        self._tgt_loaded = True

        # Auto-resolve map mod path (third-party mod, base game, or DLC).
        info = self._wizard.state.fs25_root_info
        resolution = (
            resolve_map_mod_for(info.mods_dir, save.map_id, install_dir=info.install_dir)
            if info else None
        )
        if resolution is not None and resolution.path is not None and not resolution.is_dlc:
            self.map_edit.setText(str(resolution.path))
            self._load_map(str(resolution.path))
        else:
            self.map_edit.clear()
            if resolution is not None and resolution.is_dlc:
                msg = resolution.error or "DLC map — encrypted, unsupported as target"
            elif resolution is not None and resolution.error:
                msg = resolution.error
            else:
                msg = f"(couldn't auto-find {save.map_id} — click Browse to point at the .zip)"
            self.map_edit.setPlaceholderText(msg[:140])
            self._map_loaded = False
        self._refresh_summary()

    def _browse_map(self) -> None:
        info = getattr(self._wizard.state, "fs25_root_info", None)
        start = self.map_edit.text() or (str(info.mods_dir) if info and info.mods_dir else str(Path.home()))
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select map mod .zip", start, "Map mod (*.zip);;All files (*.*)"
        )
        if chosen:
            self.map_edit.setText(chosen)
            self._load_map(chosen)
            self._refresh_summary()

    def _load_map(self, path: str) -> None:
        try:
            with MapSource(path) as src:
                src.overview_bytes()  # cheap sanity check
            self._wizard.state.map_path = Path(path)
            self._map_loaded = True
        except Exception as exc:
            self._map_loaded = False
            self.summary.append(f"<p><b>Map load failed:</b> {exc}</p>")

    def _refresh_summary(self) -> None:
        state = self._wizard.state
        lines = []
        if state.target_sg is not None:
            snap = FarmSnapshot.from_savegame(state.target_sg)
            lines.append(f"<h3>Target save: {snap.map_title or '(unknown)'}</h3>")
            lines.append(
                f"<p>Map ID: {snap.map_id}<br>"
                f"Vehicles already in target: {snap.vehicle_count}<br>"
                f"Animal pens (any): {len(snap.husbandries)}<br>"
                f"Bunker silos (any): {len(snap.silos)}<br>"
                "Farm money: "
                + ", ".join(f"farm {fid} = ${m:,.0f}" for fid, m in snap.farm_money.items())
                + "</p>"
            )

        if state.target_sg is not None and state.map_path is not None:
            info = getattr(state, "fs25_root_info", None)
            mods_dir = info.mods_dir if info else None
            install_dir = info.install_dir if info else None
            with MapSource(str(state.map_path)) as src:
                i3d_positions = positions_for_savegame(src)
                pois = resolve_pois(
                    state.target_sg, src,
                    i3d_positions=i3d_positions,
                    mods_dir=mods_dir, install_dir=install_dir,
                )
            state.target_pois = pois
            cats = Counter(p.category for p in pois)
            silos = [p for p in pois if p.category == "silo" and p.farm_id in (0, 1)]
            pens = [p for p in pois if p.category == "pen"]
            lines.append("<p><b>POIs resolved on target map:</b><br>")
            for cat, n in cats.most_common():
                lines.append(f"&nbsp;&nbsp;{cat}: {n}<br>")
            lines.append("</p>")
            lines.append(
                f"<p>Silos available as migration targets: {len(silos)}<br>"
                f"Animal pens available: {len(pens)}</p>"
            )

        self.summary.setHtml("".join(lines) or "<i>Pick the target save above.</i>")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._tgt_loaded and self._map_loaded
