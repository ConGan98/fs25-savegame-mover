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
from ...parsers.savegame import Savegame
from ...util.paths import default_savegames_dir


class SourcePage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Source savegame")
        self.setSubTitle("The save you want to migrate FROM (vehicles, animals, money, etc.).")

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Browse to a savegame folder (e.g. savegame1)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)

        self.summary = QTextBrowser()
        self.summary.setReadOnly(True)
        self.summary.setOpenExternalLinks(False)
        self.summary.setMinimumHeight(360)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Folder:"))
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        layout = QVBoxLayout()
        layout.addLayout(path_row)
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary, 1)
        self.setLayout(layout)

        self._loaded = False

    def _browse(self) -> None:
        start = self.path_edit.text() or str(default_savegames_dir() or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select source savegame folder", start)
        if not chosen:
            return
        self.path_edit.setText(chosen)
        self._load(chosen)

    def _load(self, path: str) -> None:
        try:
            sg = Savegame.load(path)
        except Exception as exc:
            self.summary.setPlainText(f"Failed to load:\n{exc}")
            self._loaded = False
            self.completeChanged.emit()
            return
        snap = FarmSnapshot.from_savegame(sg)
        self._wizard.state.source_sg = sg
        self._loaded = True
        self._render_summary(snap)
        self.completeChanged.emit()

    def _render_summary(self, snap: FarmSnapshot) -> None:
        lines = []
        lines.append(f"<h3>{snap.map_title or '(unknown map)'}</h3>")
        lines.append(f"<p><b>Map ID:</b> {snap.map_id}</p>")
        lines.append(f"<p><b>Vehicles:</b> {snap.vehicle_count}<br>")
        lines.append(f"<b>Items (bales/pallets):</b> {snap.item_count}<br>")
        lines.append(f"<b>Animal pens:</b> {sum(1 for h in snap.husbandries if h.total_animals)}"
                     f" populated  ({sum(h.total_animals for h in snap.husbandries)} animals)<br>")
        lines.append(f"<b>Bunker silos with silage:</b> "
                     f"{sum(1 for s in snap.silos if s.fill_level > 0)} "
                     f"({sum(s.fill_level for s in snap.silos if s.fill_level > 0):,.0f} kg — WILL BE LOST)<br>")
        lines.append("<b>Farm money:</b> "
                     + ", ".join(f"farm {fid} = ${m:,.0f}" for fid, m in snap.farm_money.items())
                     + "</p>")
        if snap.husbandries:
            lines.append("<p><b>Populated pens:</b><br>")
            for h in snap.husbandries:
                if h.total_animals == 0:
                    continue
                subs = ", ".join(f"{n}x{t}" for t, n in h.sub_types.most_common())
                lines.append(f"&nbsp;&nbsp;{h.placeable_uid[:14]}…  ({subs})<br>")
            lines.append("</p>")
        self.summary.setHtml("".join(lines))

    def isComplete(self) -> bool:
        return self._loaded
