from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
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
from ...parsers.i3d import positions_for_savegame
from ...parsers.map_zip import MapSource
from ...parsers.savegame import Savegame
from ...util.paths import default_savegames_dir


class TargetPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Target savegame + map")
        self.setSubTitle(
            "A fresh save on the NEW map (start one in-game first), plus the map mod .zip "
            "so we can read its PDA image and preplaced silo/pen positions."
        )

        self.tgt_edit = QLineEdit()
        self.tgt_edit.setPlaceholderText("Browse to the fresh target savegame folder")
        tgt_browse = QPushButton("Browse…")
        tgt_browse.clicked.connect(self._browse_tgt)

        self.map_edit = QLineEdit()
        self.map_edit.setPlaceholderText("Path to the new map's mod .zip (or unpacked folder)")
        map_browse = QPushButton("Browse…")
        map_browse.clicked.connect(self._browse_map)

        self.summary = QTextBrowser()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(300)

        tgt_row = QHBoxLayout()
        tgt_row.addWidget(QLabel("Target save folder:"))
        tgt_row.addWidget(self.tgt_edit, 1)
        tgt_row.addWidget(tgt_browse)

        map_row = QHBoxLayout()
        map_row.addWidget(QLabel("Target map .zip:"))
        map_row.addWidget(self.map_edit, 1)
        map_row.addWidget(map_browse)

        layout = QVBoxLayout()
        layout.addLayout(tgt_row)
        layout.addLayout(map_row)
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary, 1)
        self.setLayout(layout)

        self._tgt_loaded = False
        self._map_loaded = False

    def _browse_tgt(self) -> None:
        start = self.tgt_edit.text() or str(default_savegames_dir() or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select fresh target savegame folder", start)
        if chosen:
            self.tgt_edit.setText(chosen)
            self._load_target(chosen)

    def _browse_map(self) -> None:
        start = self.map_edit.text() or str(Path.home())
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select map mod .zip", start, "Map mod (*.zip);;All files (*.*)"
        )
        if chosen:
            self.map_edit.setText(chosen)
            self._load_map(chosen)

    def _load_target(self, path: str) -> None:
        try:
            sg = Savegame.load(path)
        except Exception as exc:
            self.summary.setPlainText(f"Failed to load target save:\n{exc}")
            self._tgt_loaded = False
            self.completeChanged.emit()
            return
        self._wizard.state.target_sg = sg
        self._tgt_loaded = True
        self._refresh_summary()

    def _load_map(self, path: str) -> None:
        try:
            with MapSource(path) as src:
                # Cheap sanity check — must contain an overview.
                src.overview_bytes()
            self._wizard.state.map_path = Path(path)
            self._map_loaded = True
        except Exception as exc:
            self.summary.append(f"\n<b>Map load failed:</b> {exc}")
            self._map_loaded = False
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        state = self._wizard.state
        lines = []
        if state.target_sg is not None:
            snap = FarmSnapshot.from_savegame(state.target_sg)
            lines.append(f"<h3>Target save: {snap.map_title or '(unknown)'}</h3>")
            lines.append(f"<p>Map ID: {snap.map_id}<br>"
                         f"Vehicles already in target: {snap.vehicle_count}<br>"
                         f"Animal pens (any): {len(snap.husbandries)}<br>"
                         f"Bunker silos (any): {len(snap.silos)}<br>"
                         "Farm money: "
                         + ", ".join(f"farm {fid} = ${m:,.0f}" for fid, m in snap.farm_money.items())
                         + "</p>")

        if state.target_sg is not None and state.map_path is not None:
            with MapSource(str(state.map_path)) as src:
                i3d_positions = positions_for_savegame(src)
                pois = resolve_pois(state.target_sg, src, i3d_positions=i3d_positions)
            state.target_pois = pois
            from collections import Counter
            cats = Counter(p.category for p in pois)
            silos = [p for p in pois if p.category == "silo" and (p.farm_id == 1 or p.farm_id == 0)]
            pens = [p for p in pois if p.category == "pen"]
            lines.append("<p><b>POIs resolved on target map:</b><br>")
            for cat, n in cats.most_common():
                lines.append(f"&nbsp;&nbsp;{cat}: {n}<br>")
            lines.append("</p>")
            lines.append(f"<p>Silos available as migration targets (farmId 0 or 1): {len(silos)}<br>"
                         f"Animal pens available: {len(pens)}</p>")

        self.summary.setHtml("".join(lines) or "<i>Pick the target save and map zip above.</i>")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._tgt_loaded and self._map_loaded
