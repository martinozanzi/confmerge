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
    g.setColorAt(0, QColor("#2563EB"))
    g.setColorAt(1, QColor("#22D3EE"))
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
s.fill(QColor("#0E1014"))
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


def write_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """ICO con più dimensioni (PNG incorporati): Windows sceglie la più adatta (Esplora file, barra, Alt+Tab)."""
    import struct
    from PySide6.QtCore import QBuffer, QIODevice
    blobs = []
    for sz in sizes:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        logo(512).scaled(sz, sz, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(buf, "PNG")
        blobs.append((sz, bytes(buf.data())))
    head = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, data = b"", b""
    for sz, b in blobs:
        entries += struct.pack("<BBBBHHII", 0 if sz >= 256 else sz, 0 if sz >= 256 else sz, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
        data += b
    path.write_bytes(head + entries + data)


write_ico(out / "icon.ico")
logo(256).save(str(out / "icon.png"))
res = Path(__file__).resolve().parents[1] / "src" / "confmerge" / "resources" / "app"
res.mkdir(parents=True, exist_ok=True)
logo(256).save(str(res / "icon.png"))
print("asset generati in", out, "e", res)
