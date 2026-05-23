"""Wizard page: pick which mod-specific source files to copy into the
migrated save (RedTape, Realistic Livestock, AutoDrive, etc.)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from ...parsers.mod_files import (
    ModFile,
    default_includes,
    detect_mod_files,
)


_CATEGORY_HEADINGS: dict[str, str] = {
    "safe":    "Safe mod data — known farm-state files that carry across maps",
    "unknown": "Unrecognised files — leave off unless you know what they do",
    "terrain": "Map-bound files — tied to the source map's terrain (likely won't work on a new map)",
}
_CATEGORY_ORDER: tuple[str, ...] = ("safe", "unknown", "terrain")


def _humanise_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


class ModFilesPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Mod files")
        self.setSubTitle(
            "Pick which mod-specific files from the source save should be "
            "carried over. Defaults are sensible — terrain-bound files are "
            "off because they'd break on a new map."
        )
        self._initialised = False
        self._checkboxes: dict[str, QCheckBox] = {}

        self._inner_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setLayout(self._inner_layout)
        scroll.setWidget(inner)

        outer = QVBoxLayout()
        outer.addWidget(scroll, 1)
        self.setLayout(outer)

    def initializePage(self) -> None:
        if self._initialised:
            return
        self._initialised = True

        state = self._wizard.state
        if state.source_sg is None:
            self._inner_layout.addWidget(QLabel("(No source save loaded.)"))
            return

        detected = detect_mod_files(state.source_sg.path)
        # Seed the wizard state with default includes the first time we land here.
        # In same-map upgrade mode, terrain-bound files default to ON because
        # the world hasn't changed (Courseplay courses still valid, etc.).
        same_map = state.is_same_map_upgrade
        if not state.mod_file_includes:
            state.mod_file_includes = default_includes(
                detected, include_terrain=same_map,
            )

        # Group displayable files (skip binary_map).
        by_cat: dict[str, list[ModFile]] = {c: [] for c in _CATEGORY_ORDER}
        binary_count = 0
        for m in detected:
            if m.category == "binary_map":
                binary_count += 1
                continue
            by_cat.setdefault(m.category, []).append(m)

        any_shown = False
        for cat in _CATEGORY_ORDER:
            files = by_cat.get(cat, [])
            if not files:
                continue
            any_shown = True
            heading = QLabel(f"<b>{_CATEGORY_HEADINGS[cat]}</b>")
            heading.setStyleSheet("margin-top: 10px;")
            self._inner_layout.addWidget(heading)
            for m in files:
                cb = QCheckBox(
                    f"{m.name}  ({_humanise_size(m.size_bytes)})  —  {m.note}"
                )
                cb.setChecked(m.name in state.mod_file_includes)
                cb.toggled.connect(
                    lambda checked, name=m.name: self._on_toggled(name, checked)
                )
                self._checkboxes[m.name] = cb
                self._inner_layout.addWidget(cb)

        if not any_shown:
            self._inner_layout.addWidget(QLabel(
                "<i>No mod-specific files detected in the source save. Nothing to migrate here.</i>"
            ))

        if binary_count:
            note = QLabel(
                f"<i>({binary_count} binary terrain map file(s) skipped — these "
                "are bound to the source map and can't be migrated.)</i>"
            )
            note.setStyleSheet("color: #888; margin-top: 8px;")
            self._inner_layout.addWidget(note)

        self._inner_layout.addStretch(1)

    def _on_toggled(self, name: str, checked: bool) -> None:
        includes = list(self._wizard.state.mod_file_includes)
        if checked and name not in includes:
            includes.append(name)
        elif not checked and name in includes:
            includes.remove(name)
        self._wizard.state.mod_file_includes = includes
