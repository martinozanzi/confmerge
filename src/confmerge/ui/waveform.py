"""Forma d'onda con audio camera ed esterno (allineato), marker di taglio trascinabili e playhead."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

SR = 8000


def _envelope(x: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    if len(x) == 0 or bins <= 0:
        return np.zeros(0), np.zeros(0)
    n = len(x) // bins * bins
    if n == 0:
        return x, x
    r = x[:n].reshape(bins, -1)
    return r.min(axis=1), r.max(axis=1)


class WaveformWidget(QWidget):
    seek = Signal(float)
    markersChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setMouseTracking(True)
        self.cam: np.ndarray | None = None
        self.ext: np.ndarray | None = None
        self.offset = 0.0           # secondi: ext(t) ≈ cam(t + offset)
        self.duration = 0.0
        self.pos = 0.0
        self.start: float | None = None
        self.end: float | None = None
        self.suggest: tuple[float, float] | None = None
        self.marks: list[float] = []   # cambi slide (tempo timeline)
        self._drag: str | None = None
        self._cache: tuple | None = None

    def set_data(self, cam, ext, duration: float) -> None:
        self.cam, self.ext, self.duration = cam, ext, duration
        self._cache = None
        self.update()

    def _x(self, t: float) -> float:
        return t / max(self.duration, 1e-6) * self.width()

    def _t(self, x: float) -> float:
        return min(max(0.0, x / max(self.width(), 1) * self.duration), self.duration)

    def _aligned_ext(self) -> np.ndarray | None:
        if self.ext is None or self.cam is None:
            return None
        n = len(self.cam)
        out = np.zeros(n, dtype=np.float32)
        st = int(round(self.offset * SR))
        s0, d0 = max(0, -st), max(0, st)
        m = min(len(self.ext) - s0, n - d0)
        if m > 0:
            out[d0:d0 + m] = self.ext[s0:s0 + m]
        return out

    def _envs(self):
        w = max(1, self.width())
        key = (w, round(self.offset, 4), id(self.cam), id(self.ext))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        res = None
        if self.cam is not None:
            res = (_envelope(self.cam, w), _envelope(self._aligned_ext(), w) if self.ext is not None else None)
        self._cache = (key, res)
        return res

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#14181d"))
        envs = self._envs()
        h = self.height()
        if envs:
            for i, (env, col) in enumerate(((envs[0], "#4aa3ff"), (envs[1], "#ffb347"))):
                if env is None:
                    continue
                lo, hi = env
                top, bot = i * h / 2, (i + 1) * h / 2
                mid = (top + bot) / 2
                amp = max(float(np.abs(np.concatenate([lo, hi])).max()), 1e-3)
                p.setPen(QPen(QColor(col), 1))
                for x in range(len(lo)):
                    p.drawLine(QPointF(x, mid - hi[x] / amp * (bot - top) * 0.45),
                               QPointF(x, mid - lo[x] / amp * (bot - top) * 0.45))
            p.setPen(QColor("#889"))
            p.drawText(4, 12, "camera")
            p.drawText(4, h // 2 + 12, "audio esterno (allineato)")
        if self.suggest:
            p.fillRect(QRectF(self._x(self.suggest[0]), 0, self._x(self.suggest[1]) - self._x(self.suggest[0]), h),
                       QColor(80, 200, 120, 30))
        for m in self.marks:
            p.setPen(QPen(QColor("#d070ff"), 1, Qt.DashLine))
            p.drawLine(QPointF(self._x(m), 0), QPointF(self._x(m), h))
        for t, col, lab in ((self.start, "#3ddc84", "I"), (self.end, "#ff5c5c", "O")):
            if t is None:
                continue
            x = self._x(t)
            p.setPen(QPen(QColor(col), 2))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            p.setBrush(QColor(col))
            p.drawRect(QRectF(x - 6, 0, 12, 14))
            p.setPen(Qt.black)
            p.drawText(QRectF(x - 6, 0, 12, 14), Qt.AlignCenter, lab)
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.drawLine(QPointF(self._x(self.pos), 0), QPointF(self._x(self.pos), h))

    def _hit(self, x: float) -> str | None:
        for name, t in (("start", self.start), ("end", self.end)):
            if t is not None and abs(self._x(t) - x) < 8:
                return name
        return None

    def mousePressEvent(self, e):
        self._drag = self._hit(e.position().x())
        if self._drag is None:
            self.seek.emit(self._t(e.position().x()))

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag:
            t = self._t(x)
            if self._drag == "start":
                self.start = min(t, (self.end if self.end is not None else self.duration) - 1)
            else:
                self.end = max(t, (self.start if self.start is not None else 0) + 1)
            self.markersChanged.emit()
            self.update()
        else:
            self.setCursor(Qt.SizeHorCursor if self._hit(x) else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        self._drag = None
