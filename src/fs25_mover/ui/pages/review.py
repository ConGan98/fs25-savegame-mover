"""Review page: dry-run summary + mod dependency report."""
from __future__ import annotations

from collections import Counter

from PySide6.QtWidgets import (
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWizardPage,
)

from ...model.farm import FarmSnapshot


class ReviewPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Review")
        self.setSubTitle("What will move, and which mods you need installed on the target system.")

        self.body = QTextBrowser()
        self.body.setReadOnly(True)
        self.body.setMinimumHeight(500)
        layout = QVBoxLayout()
        layout.addWidget(self.body, 1)
        self.setLayout(layout)

    def initializePage(self) -> None:
        state = self._wizard.state
        assert state.source_sg and state.target_sg

        src_snap = FarmSnapshot.from_savegame(state.source_sg)

        # Aggregated mod usage across vehicles + items + placeables.
        mods: Counter = Counter()
        for v in state.source_sg.vehicles():
            mn = v.get("modName")
            if mn:
                mods[mn] += 1
        for it in state.source_sg.items():
            mn = it.get("modName")
            if mn:
                mods[mn] += 1
        for p in state.source_sg.placeables():
            mn = p.get("modName")
            if mn:
                mods[mn] += 1

        lines = []
        lines.append("<h3>Migration plan</h3>")
        lines.append("<ul>")
        lines.append(f"<li><b>Vehicles:</b> {src_snap.vehicle_count} (dropped at "
                     f"{state.drop_xyz[0]:.0f}, {state.drop_xyz[2]:.0f})</li>")
        lines.append(f"<li><b>Bales/items:</b> {src_snap.item_count}</li>")
        lines.append(f"<li><b>Silo grain mappings:</b> {len(state.silo_mapping)} "
                     f"(loose-grain storage only; bunker silage is skipped)</li>")
        lines.append(f"<li><b>Animal pen mappings:</b> {len(state.pen_mapping)} "
                     f"(animals merged into target pens)</li>")
        money = sum(src_snap.farm_money.values())
        lines.append(f"<li><b>Money:</b> ${money:,.0f}</li>")
        lines.append("</ul>")

        # Bunker silage warning.
        silage_lost = sum(s.fill_level for s in src_snap.silos if s.fill_level > 0)
        if silage_lost > 0:
            lines.append(
                "<p style='color:#cc6600;'><b>Warning:</b> "
                f"{silage_lost:,.0f} kg of bunker silage will NOT be migrated. "
                "Sell or consume it on the source map before migrating, or it is lost.</p>"
            )

        # Unmapped source pens.
        src_pens_with_animals = [
            p for p in state.source_sg.placeables()
            if p.findall(".//husbandryAnimals/clusters/animal")
        ]
        unmapped = [p for p in src_pens_with_animals if p.get("uniqueId") not in state.pen_mapping]
        if unmapped:
            lines.append(f"<p style='color:#cc6600;'><b>{len(unmapped)} populated pen(s) "
                         f"have no destination — their animals will not be migrated.</b></p>")

        # Mod dependency table.
        if mods:
            lines.append("<h3>Mods required on target system</h3>")
            lines.append("<p>Every item below must be installed on the machine that will "
                         "load the migrated save. If a mod is missing, that vehicle / item / "
                         "placeable will silently fail to load.</p>")
            lines.append("<table border='1' cellpadding='4' cellspacing='0' width='100%'>")
            lines.append("<tr><th align='left'>Mod</th><th align='right'>References</th></tr>")
            for mod, n in mods.most_common():
                lines.append(f"<tr><td>{mod}</td><td align='right'>{n}</td></tr>")
            lines.append("</table>")

        self.body.setHtml("".join(lines))
