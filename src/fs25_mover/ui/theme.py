"""FS25-inspired Qt stylesheet.

Embedded as a Python string so PyInstaller picks it up automatically — no
runtime file lookup, no manifest fiddling. Apply via `app.setStyleSheet(QSS)`.

Palette (rough match to the in-game menu/HUD):
  bg_deep      #1c1f1a   panel backgrounds
  bg_mid       #2b2e2a   widget bodies
  bg_high      #383b35   inputs/hover
  text         #e5e4dc   cream
  text_dim     #9c9d96   muted
  border       #4a4d44   subtle separation
  amber        #ff9b1c   primary accent (buttons, focus, selection)
  amber_dark   #c87600
"""
from __future__ import annotations

QSS = """
* {
    color: #e5e4dc;
    font-family: "Segoe UI", "Calibri", sans-serif;
    font-size: 10pt;
}

QMainWindow, QDialog, QWizard, QWidget {
    background-color: #2b2e2a;
}

/* --- QWizard surfaces --- */
QWizard {
    background-color: #1c1f1a;
}
QWizard QWidget#qt_wizard_titlewidget {
    background-color: #1c1f1a;
    border-bottom: 1px solid #4a4d44;
}
QWizard QLabel#qt_wizard_titlelabel {
    color: #ff9b1c;
    font-size: 16pt;
    font-weight: bold;
    padding: 8px 4px 0 12px;
}
QWizard QLabel#qt_wizard_subtitlelabel {
    color: #b8b9b0;
    font-size: 10pt;
    padding: 0 4px 8px 12px;
}
QWizardPage {
    background-color: #2b2e2a;
    padding: 8px;
}

/* --- Group boxes (silos / pens sections on the assign page) --- */
QGroupBox {
    background-color: #232622;
    border: 1px solid #4a4d44;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #ff9b1c;
    background-color: #232622;
}

/* --- Buttons --- */
QPushButton {
    background-color: #383b35;
    border: 1px solid #4a4d44;
    border-radius: 4px;
    padding: 6px 14px;
    min-height: 22px;
    color: #e5e4dc;
}
QPushButton:hover {
    background-color: #44483f;
    border-color: #ff9b1c;
}
QPushButton:pressed {
    background-color: #1c1f1a;
}
QPushButton:disabled {
    background-color: #2b2e2a;
    color: #6f7068;
    border-color: #3a3d35;
}
QPushButton:default {
    background-color: #c87600;
    border-color: #ff9b1c;
    color: #1c1f1a;
    font-weight: bold;
}
QPushButton:default:hover {
    background-color: #ff9b1c;
}

/* --- Line / text inputs --- */
QLineEdit, QTextBrowser, QTextEdit, QPlainTextEdit {
    background-color: #1c1f1a;
    border: 1px solid #4a4d44;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: #ff9b1c;
    selection-color: #1c1f1a;
}
QLineEdit:focus, QTextBrowser:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #ff9b1c;
}
QLineEdit:disabled, QTextBrowser:disabled {
    color: #6f7068;
}

/* --- Combo / spin boxes --- */
QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1c1f1a;
    border: 1px solid #4a4d44;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
    selection-background-color: #ff9b1c;
    selection-color: #1c1f1a;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #ff9b1c;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #4a4d44;
}
QComboBox QAbstractItemView {
    background-color: #1c1f1a;
    border: 1px solid #4a4d44;
    selection-background-color: #ff9b1c;
    selection-color: #1c1f1a;
    color: #e5e4dc;
}

/* --- Tables --- */
QTableView, QTableWidget, QListView, QTreeView {
    background-color: #1c1f1a;
    alternate-background-color: #232622;
    gridline-color: #3a3d35;
    border: 1px solid #4a4d44;
    selection-background-color: #ff9b1c;
    selection-color: #1c1f1a;
}
QHeaderView::section {
    background-color: #383b35;
    border: 0;
    border-right: 1px solid #4a4d44;
    border-bottom: 1px solid #4a4d44;
    padding: 4px 8px;
    color: #ff9b1c;
    font-weight: bold;
}

/* --- Scroll bars --- */
QScrollBar:vertical, QScrollBar:horizontal {
    background-color: #1c1f1a;
    border: 0;
}
QScrollBar:vertical { width: 12px; }
QScrollBar:horizontal { height: 12px; }
QScrollBar::handle {
    background-color: #4a4d44;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background-color: #ff9b1c;
}
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* --- Tooltips --- */
QToolTip {
    background-color: #1c1f1a;
    color: #e5e4dc;
    border: 1px solid #ff9b1c;
    padding: 4px 8px;
}

/* --- Labels --- */
QLabel { background: transparent; }

/* --- Status bar --- */
QStatusBar { background-color: #1c1f1a; color: #b8b9b0; border-top: 1px solid #4a4d44; }
"""
