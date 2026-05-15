from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWizardPage


class WelcomePage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("FS25 Savegame Mover")
        self.setSubTitle("Move a farm — vehicles, animals, bales, money — from one map to another.")
        body = QLabel(
            "This wizard will guide you through:\n\n"
            "  1. Pick your existing savegame to migrate FROM.\n"
            "  2. Pick a fresh savegame on the new map to migrate INTO.\n"
            "  3. Point at the new map's mod .zip so we can show its PDA.\n"
            "  4. Click where vehicles should land, and pick destination silos / animal pens.\n"
            "  5. Review what will move (and any missing mods).\n"
            "  6. Run the migration — a new savegame folder is written; your originals are not touched.\n\n"
            "Bunker silo silage cannot be migrated — sell or consume it on the source map first."
        )
        body.setWordWrap(True)
        layout = QVBoxLayout()
        layout.addWidget(body)
        layout.addStretch(1)
        self.setLayout(layout)
