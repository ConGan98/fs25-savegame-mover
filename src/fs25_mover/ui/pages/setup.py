"""Setup page: pick the FS25 folder once, remember it across launches."""
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

from ...parsers.fs25_root import (
    Fs25RootInfo,
    default_root,
    detect,
    looks_like_fs25_root,
)
from ...util.config import AppConfig


class SetupPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("FS25 folder")
        self.setSubTitle(
            "Where are your Farming Simulator 25 savegames? "
            "We'll remember this for next time."
        )

        # Load remembered config; auto-detect if absent.
        self._config = AppConfig.load()
        initial = self._config.fs25_root or (
            str(default_root() or "")
        )

        self.path_edit = QLineEdit(initial)
        self.path_edit.setPlaceholderText(
            r"Browse to e.g. C:\Users\<you>\Documents\My Games\FarmingSimulator2025"
        )
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)

        self.info = QTextBrowser()
        self.info.setReadOnly(True)
        self.info.setMinimumHeight(360)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("FS25 folder:"))
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        intro = QLabel(
            "<p>This wizard moves a farm — vehicles, animals, bales, money, stored "
            "grain — from one map savegame to another. Your original saves are "
            "never touched; a new save folder is written.</p>"
            "<p><b>Tip:</b> start a fresh save on the target map in-game first "
            "(we use it to discover where silos and pens sit on the new map).</p>"
        )
        intro.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(intro)
        layout.addLayout(path_row)
        layout.addWidget(QLabel("What we found:"))
        layout.addWidget(self.info, 1)
        self.setLayout(layout)

        # Try to detect immediately if we have a candidate path.
        self._info: Fs25RootInfo | None = None
        if initial:
            self._refresh(initial)

    def _browse(self) -> None:
        start = self.path_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select FS25 folder", start)
        if chosen:
            self.path_edit.setText(chosen)
            self._refresh(chosen)

    def _refresh(self, path: str) -> None:
        if not looks_like_fs25_root(path):
            self.info.setHtml(
                "<p><i>That folder doesn't look like a Farming Simulator 25 root. "
                "It should contain <code>gameSettings.xml</code> and one or more "
                "<code>savegameN</code> folders.</i></p>"
            )
            self._info = None
            self.completeChanged.emit()
            return
        try:
            self._info = detect(path)
        except FileNotFoundError as exc:
            self.info.setHtml(f"<p>{exc}</p>")
            self._info = None
            self.completeChanged.emit()
            return

        info = self._info
        lines = [
            f"<h3>{info.root}</h3>",
            f"<p><b>Savegames found:</b> {info.save_count}<br>",
            f"<b>Mods folder:</b> {info.mods_dir or '<i>(none — neither override nor local mods/)</i>'}",
        ]
        if info.mods_dir_is_override:
            lines.append(" <i>(from gameSettings.xml override)</i>")
        lines.append(f"<br><b>Mods installed:</b> {info.mod_count}<br>")
        lines.append(
            f"<b>Game install:</b> "
            + (str(info.install_dir) if info.install_dir
               else "<i>not auto-detected (base / DLC maps may not resolve — Browse override still works)</i>")
            + "</p>"
        )
        if info.saves:
            lines.append("<p><b>Detected saves:</b></p><ul>")
            for s in info.saves:
                lines.append(f"<li>{s.display}</li>")
            lines.append("</ul>")
        else:
            lines.append("<p><i>No savegames detected in this folder.</i></p>")
        self.info.setHtml("".join(lines))

        # Stash detection on the wizard so later pages can read it.
        self._wizard.state.fs25_root_info = info
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._info is not None and self._info.save_count >= 1

    def validatePage(self) -> bool:
        if self._info is None:
            return False
        # Persist on Next.
        self._config.fs25_root = str(self._info.root)
        try:
            self._config.save()
        except OSError:
            pass
        return True
