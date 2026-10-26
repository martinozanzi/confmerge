"""Genera splash.png e icon.ico con QPainter (nessun file binario da mantenere a mano)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter

app = QGuiApplication([])
out = Path(__file__).resolve().parents[1] / "assets"
out.mkdir(exist_ok=True)


def logo(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#00C2FF"))
    g.setColorAt(1, QColor("#7B2FF7"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    p.setBrush(QColor("white"))
    w = size * 0.5
    h = size * 0.36
    p.drawRoundedRect(QRectF(size * 0.14, size * 0.32, w, h), size * 0.06, size * 0.06)
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF
    p.drawPolygon(QPolygonF([QPointF(size * 0.68, size * 0.5), QPointF(size * 0.86, size * 0.36), QPointF(size * 0.86, size * 0.64)]))
    p.end()
    return img


s = QImage(560, 260, QImage.Format_RGB32)
s.fill(QColor("#10151c"))
p = QPainter(s)
p.setRenderHint(QPainter.Antialiasing)
p.drawImage(32, 62, logo(120))
f = QFont("Segoe UI")
f.setPixelSize(54)
f.setBold(True)
p.setFont(f)
p.setPen(QColor("white"))
p.drawText(170, 120, "ConfMerge")
f.setPixelSize(18)
f.setBold(False)
p.setFont(f)
p.setPen(QColor("#9fb0c3"))
p.drawText(172, 156, "Video di conferenze pronti per YouTube")
p.drawText(172, 228, "Caricamento…")
p.end()
s.save(str(out / "splash.png"))
logo(256).save(str(out / "icon.ico"))
logo(256).save(str(out / "icon.png"))
print("asset generati in", out)
