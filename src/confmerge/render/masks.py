"""Maschere (forme di ritaglio): rettangolo, angoli arrotondati, cerchio. Una sola definizione per anteprima ed export."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from ..view import mask_radius_px

MASKS = {"": "Rettangolo", "rounded": "Arrotondato", "circle": "Cerchio"}


def shape_path(rect: QRectF, mask: str, radius: float) -> QPainterPath:
    """Contorno della forma dentro `rect` (vuoto = rettangolo pieno)."""
    path = QPainterPath()
    r = mask_radius_px(mask, radius, rect.width(), rect.height()) if mask else 0.0
    if r > 0.5:
        path.addRoundedRect(rect, r, r)
    else:
        path.addRect(rect)
    return path


def mask_image(w: int, h: int, mask: str, radius: float) -> QImage:
    """PNG in scala di grigi (bianco = si vede) grande w×h: serve ad `alphamerge` nel filtergraph."""
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("black"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    p.drawPath(shape_path(QRectF(0, 0, w, h), mask, radius))
    p.end()
    return img


def geq_alpha(w: int, h: int, mask: str, radius: float) -> str:
    """Espressione per `geq` (alfa) di una forma w×h: per i clip piccoli che hanno già un loro canale alfa da conservare."""
    r = mask_radius_px(mask, radius, w, h)
    cx, cy = w / 2, h / 2
    ax, ay = max(0.0, cx - r), max(0.0, cy - r)
    # fuori dall'angolo arrotondato l'alfa scende a 0 (con un bordo di mezzo pixel per non avere scalini)
    return f"alpha(X,Y)*clip({r:.2f}+0.5-hypot(max(abs(X-{cx:.2f})-{ax:.2f},0),max(abs(Y-{cy:.2f})-{ay:.2f},0)),0,1)"
