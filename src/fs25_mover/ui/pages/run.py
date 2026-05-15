"""Run page: pick output folder, click Migrate, show results."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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

from ...migrate.engine import apply as apply_migration


class RunPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Run migration")
        self.setSubTitle("Choose where the migrated save folder should be written, then click Migrate.")
        self._done = False

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Output folder (will be created — never overwrites in place)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)

        self.run_btn = QPushButton("Migrate")
        self.run_btn.clicked.connect(self._run)

        self.log = QTextBrowser()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(360)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(browse)

        layout = QVBoxLayout()
        layout.addLayout(out_row)
        layout.addWidget(self.run_btn)
        layout.addWidget(self.log, 1)
        self.setLayout(layout)

    def initializePage(self) -> None:
        # Default: <source-save>_migrated next to the target save.
        state = self._wizard.state
        if not self.out_edit.text() and state.target_sg is not None:
            default = state.target_sg.path.parent / f"{state.target_sg.path.name}_migrated"
            self.out_edit.setText(str(default))

    def _browse(self) -> None:
        start = self.out_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if chosen:
            self.out_edit.setText(chosen)

    def _run(self) -> None:
        state = self._wizard.state
        out = self.out_edit.text().strip()
        if not out:
            self.log.append("Pick an output folder first.")
            return
        state.output_path = Path(out)
        try:
            plan = state.to_plan()
        except AssertionError:
            self.log.append("Missing source/target/output — go back and complete earlier pages.")
            return

        self.run_btn.setEnabled(False)
        self.log.append(f"Migrating to: {out}\n")

        try:
            report = apply_migration(plan)
        except Exception as exc:
            self.log.append(f"<span style='color:red;'>FAILED:</span> {exc!r}")
            self.run_btn.setEnabled(True)
            return

        lines = [f"Done — wrote {report.output_path}"]
        if report.vehicles:
            lines.append(f"  vehicles moved: {report.vehicles.moved} (uid remaps: {len(report.vehicles.remap)})")
        if report.items:
            lines.append(f"  items moved:    {report.items.moved}")
        if report.silos:
            lines.append(f"  storage moves:  {len(report.silos.fillunit_moves)} grain transfers")
            if report.silos.bunkers_abandoned:
                total = sum(lvl for _, lvl in report.silos.bunkers_abandoned)
                lines.append(f"  bunker silage NOT migrated: {len(report.silos.bunkers_abandoned)} silo(s), {total:,.0f} kg")
        if report.animals:
            lines.append(f"  animals moved:  {report.animals.total_moved} into {len(report.animals.moved_by_pen)} pens")
        if report.money and report.money.applied:
            lines.append(f"  money:          ${report.money.money:,.2f}")
        lines.append("\nTo load this save in FS25, copy the folder contents into an empty savegameN slot under")
        lines.append("   Documents\\My Games\\FarmingSimulator2025\\savegameN\\")
        self.log.append("\n".join(lines))
        self._done = True
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done
