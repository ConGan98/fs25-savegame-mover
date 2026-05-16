"""Source page: pick which save to migrate FROM, from the detected list."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWizardPage,
)

from ...model.farm import FarmSnapshot
from ...parsers.savegame import Savegame


class SourcePage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Source savegame")
        self.setSubTitle("The save you want to migrate FROM (vehicles, animals, money, etc.).")

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_change)

        self.summary = QTextBrowser()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(360)

        row = QHBoxLayout()
        row.addWidget(QLabel("Save:"))
        row.addWidget(self.combo, 1)

        layout = QVBoxLayout()
        layout.addLayout(row)
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary, 1)
        self.setLayout(layout)

        self._loaded = False

    def initializePage(self) -> None:
        # Repopulate every time (in case user backed up and changed root).
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("(pick a save…)", None)
        info = getattr(self._wizard.state, "fs25_root_info", None)
        if info is not None:
            # Sort by map title for friendlier browsing.
            for save in sorted(
                info.saves, key=lambda s: (s.map_title or "", s.slot)
            ):
                self.combo.addItem(save.display, save)
        self.combo.blockSignals(False)
        self._loaded = False
        self.summary.clear()
        self.completeChanged.emit()

    def _on_change(self) -> None:
        save = self.combo.currentData()
        if save is None:
            self._loaded = False
            self.summary.clear()
            self.completeChanged.emit()
            return
        try:
            sg = Savegame.load(save.folder)
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
        lines.append(
            f"<p><b>Vehicles:</b> {snap.vehicle_count}<br>"
            f"<b>Items (bales/pallets):</b> {snap.item_count}<br>"
            f"<b>Animal pens populated:</b> "
            f"{sum(1 for h in snap.husbandries if h.total_animals)}"
            f" ({sum(h.total_animals for h in snap.husbandries)} animals)<br>"
            f"<b>Bunker silos with silage:</b> "
            f"{sum(1 for s in snap.silos if s.fill_level > 0)} "
            f"({sum(s.fill_level for s in snap.silos if s.fill_level > 0):,.0f} kg — WILL BE LOST)<br>"
            "<b>Farm money:</b> "
            + ", ".join(f"farm {fid} = ${m:,.0f}" for fid, m in snap.farm_money.items())
            + "</p>"
        )
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
