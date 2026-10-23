from __future__ import annotations

from PySide6.QtCore import Property, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..theme import ANIM_SLOW, theme
from .anim import animate


class _Animated(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._v = 0.0
        self._target = 0.0

    def get_v(self) -> float:
        return self._v

    def set_v(self, v: float) -> None:
        self._v = v
        self.update()

    v_ = Property(float, get_v, set_v)

    def setValue(self, v: float) -> None:          # 0..1, con scorrimento fluido
        v = min(max(v, 0.0), 1.0)
        animate(self, b"v_", self._v, v, ANIM_SLOW)
        self._target = v

    def value(self) -> float:
        return self._target


class ProgressBarThin(_Animated):
    """Barra sottile (6 px) con gradiente."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.border))
        p.drawRoundedRect(r, 3, 3)
        if self._v > 0:
            g = QLinearGradient(0, 0, self.width(), 0)
            g.setColorAt(0, QColor(t.accent))
            g.setColorAt(1, QColor(t.accent2))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, max(6.0, self.width() * self._v), self.height()), 3, 3)


class ProgressRing(_Animated):
    """Anello di avanzamento con percentuale al centro."""

    def __init__(self, size: int = 120, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = 8
        r = QRectF(w, w, self.width() - 2 * w, self.height() - 2 * w)
        p.setPen(QPen(QColor(t.border), w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        g = QConicalGradient(r.center(), 90)
        g.setColorAt(0, QColor(t.accent2))
        g.setColorAt(1, QColor(t.accent))
        p.setPen(QPen(g, w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 90 * 16, -int(360 * 16 * self._v))
        p.setPen(QColor(t.text))
        f = QFont(self.font())
        f.setPixelSize(max(12, self._size // 5))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, f"{self._v * 100:.0f}%")
