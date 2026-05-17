"""PDA-styled map view: a QGraphicsView with pan, wheel-zoom, and an overlay
layer for markers (POIs, vehicle drop zone, etc.).

Coordinate transform: FS25 world is (x, y, z) with y = altitude. The PDA image
is a square top-down render. Assuming the image covers a square area of
`world_size` metres centred at world origin (0, 0), the mapping is:

    u = (world_x + world_size/2) / world_size * image_width
    v = (world_size/2 - world_z) / world_size * image_height

(z flips because PDA is rendered with +Z pointing south on most FS25 maps.)
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)
from PySide6.QtGui import QFontMetricsF


@dataclass
class Marker:
    label: str
    world_x: float
    world_z: float
    color: QColor
    radius_px: float = 7.0


class PdaView(QGraphicsView):
    clicked_world = Signal(float, float)  # (world_x, world_z)

    def __init__(
        self,
        qimage: QImage,
        world_size: float = 2048.0,
        playable_px: tuple[int, int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.world_size = world_size

        scene = QGraphicsScene(self)
        pix = QPixmap.fromImage(qimage)
        self._pix_item = QGraphicsPixmapItem(pix)
        self._pix_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        scene.addItem(self._pix_item)
        self._marker_layer = QGraphicsItemGroup()
        scene.addItem(self._marker_layer)
        # Sub-groups by category — lets callers toggle whole categories on/off
        # in one call. Created lazily by `_group_for(category)`.
        self._category_groups: dict[str, QGraphicsItemGroup] = {}
        self.setScene(scene)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(20, 25, 20)))

        self._image_size = (pix.width(), pix.height())
        # Playable region (in image pixels) — defaults to the full image if no
        # overhang border. Centered within the image.
        if playable_px is not None:
            pw, ph = playable_px
        else:
            pw, ph = self._image_size
        ix, iy = self._image_size
        self._playable_rect = (
            (ix - pw) / 2.0,    # left
            (iy - ph) / 2.0,    # top
            pw,                  # width
            ph,                  # height
        )
        self._zoom_min = 0.05
        self._zoom_max = 8.0

    # ---- coordinate transforms ----

    def world_to_scene(self, wx: float, wz: float) -> QPointF:
        # FS25 convention: -Z = north (top of PDA), +Z = south (bottom of PDA).
        # +X = east (right), -X = west (left). World origin (0,0) sits at the
        # centre of the playable image region.
        px, py, pw, ph = self._playable_rect
        u = px + (wx + self.world_size / 2) / self.world_size * pw
        v = py + (wz + self.world_size / 2) / self.world_size * ph
        return QPointF(u, v)

    def scene_to_world(self, p: QPointF) -> tuple[float, float]:
        px, py, pw, ph = self._playable_rect
        wx = (p.x() - px) / pw * self.world_size - self.world_size / 2
        wz = (p.y() - py) / ph * self.world_size - self.world_size / 2
        return (wx, wz)

    # ---- markers ----

    def clear_markers(self) -> None:
        for child in list(self._marker_layer.childItems()):
            self._marker_layer.removeFromGroup(child)
            self.scene().removeItem(child)
        self._category_groups.clear()

    def _group_for(self, category: str | None) -> QGraphicsItemGroup:
        """Get-or-create the sub-group for a category."""
        key = category or ""
        g = self._category_groups.get(key)
        if g is None:
            g = QGraphicsItemGroup(parent=self._marker_layer)
            self._category_groups[key] = g
        return g

    def set_category_visible(self, category: str, visible: bool) -> None:
        """Show or hide every marker added under this category."""
        g = self._category_groups.get(category)
        if g is not None:
            g.setVisible(visible)

    def add_marker(self, m: Marker, category: str | None = None) -> None:
        group = self._group_for(category) if category else self._marker_layer
        scene_pos = self.world_to_scene(m.world_x, m.world_z)
        r = m.radius_px
        dot = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        dot.setBrush(QBrush(m.color))
        dot.setPen(QPen(QColor("black"), 1.5))
        # IgnoreTransformations: the dot keeps its pixel size as the view zooms.
        dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        dot.setPos(scene_pos)
        dot.setToolTip(f"{m.label}\n({m.world_x:.1f}, {m.world_z:.1f})")
        group.addToGroup(dot)

        if m.label:
            f = QFont()
            f.setPointSize(10)
            f.setBold(True)
            metrics = QFontMetricsF(f)
            text_h = metrics.height()
            text = QGraphicsSimpleTextItem(m.label)
            text.setFont(f)
            text.setBrush(QBrush(QColor(255, 255, 255)))
            text.setPen(QPen(Qt.PenStyle.NoPen))
            text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            text.setPos(scene_pos)
            text.setTransform(QTransform.fromTranslate(r + 4, -text_h / 2))
            group.addToGroup(text)

    def add_origin_crosshair(self) -> None:
        """Draw a crosshair at world (0, 0) so the user can visually verify orientation."""
        scene_pos = self.world_to_scene(0.0, 0.0)
        size = 18
        pen = QPen(QColor(255, 100, 100, 230), 2)
        for x1, y1, x2, y2 in [(-size, 0, size, 0), (0, -size, 0, size)]:
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            line.setPos(scene_pos)
            self._marker_layer.addToGroup(line)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        label = QGraphicsSimpleTextItem("world (0,0)")
        label.setFont(f)
        label.setBrush(QBrush(QColor(255, 220, 220)))
        label.setPen(QPen(Qt.PenStyle.NoPen))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        label.setPos(scene_pos)
        label.setTransform(QTransform.fromTranslate(size + 4, 2))
        self._marker_layer.addToGroup(label)

    # ---- interaction ----

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        cur = self.transform().m11()
        new = cur * factor
        if new < self._zoom_min or new > self._zoom_max:
            return
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            scene_pt = self.mapToScene(event.pos())
            wx, wz = self.scene_to_world(scene_pt)
            self.clicked_world.emit(wx, wz)
            return
        super().mousePressEvent(event)

    def fit_image(self) -> None:
        self.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
