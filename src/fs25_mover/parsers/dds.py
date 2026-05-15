"""DDS -> QImage decode via Pillow.

Pillow handles the BC1/BC3 compression used by FS25's PDA overview.dds natively.
"""
from __future__ import annotations

import io

from PIL import Image
from PySide6.QtGui import QImage


def dds_to_qimage(data: bytes) -> QImage:
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    buf = im.tobytes("raw", "RGBA")
    qimg = QImage(buf, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888)
    # Detach from Pillow's buffer so the QImage owns its pixels.
    return qimg.copy()
