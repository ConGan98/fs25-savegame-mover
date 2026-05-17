"""Standalone PDA preview window — Phase 3 demo.

Loads a map mod (.zip or folder), decodes overview.dds, renders it with pan/zoom
and a marker layer pre-populated with placeableHotspots from map.xml. Right-click
on the map prints the world coords (and shows them in the status bar).
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..model.poi import CATEGORY_COLOR, resolve_pois
from ..parsers.dds import dds_to_qimage
from ..parsers.i3d import positions_for_savegame
from ..parsers.map_zip import MapSource
from ..parsers.savegame import Savegame
from .pda_view import Marker, PdaView


_HOTSPOT_COLORS = {
    "SHOP_VEHICLE": QColor("#ffcc00"),
    "SHOP_ANIMAL": QColor("#66ddff"),
    "SHOP_STORE": QColor("#ffaa55"),
}


class PdaWindow(QMainWindow):
    def __init__(self, map_path: str, world_size: float | None = None, savegame_path: str | None = None):
        super().__init__()
        self.setWindowTitle(f"FS25 PDA — {map_path}")
        self.resize(1100, 1100)

        with MapSource(map_path) as src:
            dds = src.overview_bytes()
            hotspots = src.hotspots()
            detected = src.world_size()
            playable_px = src.playable_image_size()
            i3d_positions = positions_for_savegame(src) if savegame_path else {}

        pois = []
        if savegame_path:
            sg = Savegame.load(savegame_path)
            # Reload MapSource for the resolve call — it closed above.
            with MapSource(map_path) as src2:
                pois = resolve_pois(sg, src2, i3d_positions=i3d_positions)

        # CLI override wins; otherwise auto-detected; otherwise 2048 default.
        if world_size is None:
            world_size = detected if detected is not None else 2048.0
        detect_note = (
            f"detected from heightmap ({detected:g}m)"
            if detected is not None
            else "default — could not auto-detect from map.i3d"
        )

        img = dds_to_qimage(dds)
        # If the image is larger than the playable region, only the centred
        # playable subrect maps to world coords (the rest is overhang border).
        if playable_px is not None and (playable_px[0] != img.width() or playable_px[1] != img.height()):
            inset_note = f", playable inset {playable_px[0]}x{playable_px[1]} px in {img.width()}x{img.height()} image"
        else:
            inset_note = ""
        self.view = PdaView(img, world_size=world_size, playable_px=playable_px)
        self.view.add_origin_crosshair()

        # Hotspots from map.xml.
        for h in hotspots:
            color = _HOTSPOT_COLORS.get(h.type, QColor("#cccccc"))
            self.view.add_marker(
                Marker(label=h.label, world_x=h.world_x, world_z=h.world_z, color=color)
            )

        # Savegame POIs (silos, animal pens, sellpoints, ...).
        for poi in pois:
            self.view.add_marker(
                Marker(
                    label=poi.label,
                    world_x=poi.world_x,
                    world_z=poi.world_z,
                    color=QColor(CATEGORY_COLOR.get(poi.category, "#cccccc")),
                    radius_px=6.0,
                )
            )

        legend = QLabel(
            "  Drag = pan   Wheel = zoom   Right-click = read world coords  "
            f"  |   World: {world_size:g}m × {world_size:g}m ({detect_note}){inset_note}"
        )
        legend.setStyleSheet("color: #ddd; background: #1f241f; padding: 6px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(legend)
        layout.addWidget(self.view, 1)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        bar = QStatusBar()
        self.setStatusBar(bar)
        self._hotspot_count = len(hotspots)
        msg = f"Loaded — {self._hotspot_count} hotspots from map.xml"
        if pois:
            from collections import Counter
            cats = Counter(p.category for p in pois)
            cat_summary = ", ".join(f"{n} {c}" for c, n in cats.most_common())
            msg += f"  |  {len(pois)} POIs from savegame ({cat_summary})"
        bar.showMessage(msg)

        self.view.clicked_world.connect(self._on_clicked)

        # Fit to view after layout settles.
        self.view.fit_image()

    def _on_clicked(self, wx: float, wz: float) -> None:
        msg = f"Clicked world position: x = {wx:.2f}, z = {wz:.2f}"
        print(msg)
        self.statusBar().showMessage(msg)
