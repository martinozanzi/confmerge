"""Miniatura 1280×720: fotogramma + grafica con lo stesso editor; export JPG (<2 MB) e PNG."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter

from .ffmpeg_wrapper import _CREATIONFLAGS, FFmpegError, ffmpeg_path
from .media_scan import MediaInfo
from .render import compositor
from .render.model import Element

THUMB_W, THUMB_H = 1280, 720
MAX_JPG_BYTES = 2_000_000


def grab_frame(clip: Path | str, t: float, out: Path, width: int | None = None) -> QImage:
    vf = f"scale={width}:-2" if width else "null"
    r = subprocess.run([ffmpeg_path(), "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(clip), "-frames:v", "1",
                        "-vf", vf, str(out)], capture_output=True, creationflags=_CREATIONFLAGS)
    img = QImage(str(out))
    if r.returncode != 0 or img.isNull():
        raise FFmpegError("Impossibile estrarre il fotogramma")
    return img


def locate(clips: list[MediaInfo], t: float) -> tuple[MediaInfo, float]:
    pos = 0.0
    for c in clips:
        if t < pos + c.duration or c is clips[-1]:
            return c, max(0.0, min(t - pos, c.duration - 0.05))
        pos += c.duration
    return clips[-1], 0.0


def suggest_times(t0: float, t1: float, n: int = 5) -> list[float]:
    return [t0 + (t1 - t0) * (i + 1) / (n + 1) for i in range(n)]


def compose(frame: QImage, elements: list[Element], W: int = THUMB_W, H: int = THUMB_H) -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.black)
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    s = frame.scaled(W, H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    p.drawImage((W - s.width()) // 2, (H - s.height()) // 2, s)
    p.end()
    return compositor.render_frame(elements, W, H, 0.0, 1e9, img)


def save_jpg_under_limit(img: QImage, path: Path, limit: int = MAX_JPG_BYTES) -> int:
    """Salva in JPG riducendo la qualità finché resta sotto 2 MB (limite YouTube)."""
    rgb = img.convertToFormat(QImage.Format_RGB32)
    for q in (95, 90, 85, 80, 75, 70, 60, 50):
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        rgb.save(buf, "JPG", q)
        if buf.size() < limit:
            Path(path).write_bytes(bytes(buf.data()))
            return buf.size()
    raise FFmpegError("Impossibile portare la miniatura sotto 2 MB")
