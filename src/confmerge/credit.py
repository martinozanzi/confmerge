"""Credito finale «Created with ConfMerge» (testo in inglese, indipendente dalla lingua dell'interfaccia)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from . import REPO_URL
from .render.model import Background, Element, Fill, Scene

CREDIT_TEXT = "Created with ConfMerge"
FADE = 0.6


def qr_png(path: Path, text: str = REPO_URL, size: int = 512) -> Path:
    """QR code disegnato con QPainter (la libreria `qrcode` calcola solo la matrice)."""
    import qrcode
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#000000"))
    cell = size / n
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                p.drawRect(QRectF(x * cell, y * cell, cell + 0.6, cell + 0.6))
    p.end()
    img.save(str(path), "PNG")
    return path


def credit_scene(duration: float = 3.0, qr_path: Path | None = None, font: str = "Segoe UI") -> Scene:
    els = [
        Element(id="credit_t", kind="text", text=CREDIT_TEXT, font=font, size=0.065, bold=True,
                x=0.5, y=0.44 if qr_path is None else 0.34, targets=["outro"]),
        Element(id="credit_u", kind="text", text=REPO_URL, font=font, size=0.034,
                fill=Fill(color="#B8C2CC"), x=0.5, y=0.55 if qr_path is None else 0.45, targets=["outro"]),
    ]
    if qr_path is not None:
        els.append(Element(id="credit_qr", kind="image", path=str(qr_path), x=0.5, y=0.75, width=0.13,
                           targets=["outro"]))
    return Scene(enabled=True, duration=duration, background=Background("black"), elements=els, fade=FADE)
