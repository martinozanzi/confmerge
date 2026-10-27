from __future__ import annotations

from PySide6.QtCore import Property, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..theme import ANIM_BASE, CONTROL_H, RADIUS_CTRL, S1, S2, theme
from .anim import animate


class Segmented(QWidget):
    """Controllo a segmenti (es. Semplice / Avanzata) con evidenziazione animata."""
    changed = Signal(object)

    def __init__(self, options: list[tuple[str, object]], parent=None, icons: list[str | None] | None = None):
        super().__init__(parent)
        self.options = options
        self.icons = icons or [None] * len(options)
        self._i = 0
        self._x = 0.0
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _seg_w(self) -> list[int]:
        fm = QFontMetrics(self.font())
        return [fm.horizontalAdvance(t) + S2 * 2 + (22 if ic else 0) for (t, _), ic in zip(self.options, self.icons)]

    def sizeHint(self) -> QSize:
        return QSize(sum(self._seg_w()) + 8, CONTROL_H)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def get_x(self) -> float:
        return self._x

    def set_x(self, v: float) -> None:
        self._x = v
        self.update()

    x_ = Property(float, get_x, set_x)

    def value(self):
        return self.options[self._i][1]

    def setValue(self, v, animated: bool = False) -> None:
        for i, (_, val) in enumerate(self.options):
            if val == v:
                self._set(i, animated)
                return

    def _set(self, i: int, animated: bool = True) -> None:
        if i == self._i and self._x == float(i):
            return
        old = self._x
        self._i = i
        if animated:
            animate(self, b"x_", old, float(i), ANIM_BASE)
        else:
            self._x = float(i)
        self.update()

    def mousePressEvent(self, e):
        x = e.position().x() - 4
        acc = 0
        for i, w in enumerate(self._seg_w()):
            if acc <= x < acc + w:
                if i != self._i:
                    self._set(i)
                    self.changed.emit(self.options[i][1])
                return
            acc += w

    def keyPressEvent(self, e):
        d = {Qt.Key_Left: -1, Qt.Key_Right: 1}.get(e.key())
        if d is None:
            return super().keyPressEvent(e)
        j = min(max(self._i + d, 0), len(self.options) - 1)
        if j != self._i:
            self._set(j)
            self.changed.emit(self.options[j][1])

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QColor(t.surface2))
        p.drawRoundedRect(r, RADIUS_CTRL, RADIUS_CTRL)
        widths = self._seg_w()
        # evidenziazione interpolata fra due segmenti
        lo = int(self._x)
        hi = min(lo + 1, len(widths) - 1)
        frac = self._x - lo
        starts = [4 + sum(widths[:k]) for k in range(len(widths))]
        hx = starts[lo] + (starts[hi] - starts[lo]) * frac
        hw = widths[lo] + (widths[hi] - widths[lo]) * frac
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.btn1))
        p.drawRoundedRect(QRectF(hx, 4, hw, self.height() - 8), RADIUS_CTRL - 2, RADIUS_CTRL - 2)
        for i, ((text, _), ic, x0, w) in enumerate(zip(self.options, self.icons, starts, widths)):
            sel = abs(i - self._x) < 0.5
            col = t.on_accent if sel else t.text2
            tx = x0 + S2
            if ic:
                theme.icon(ic, col, 14).paint(p, int(tx), (self.height() - 14) // 2, 14, 14)
                tx += 22
            p.setPen(QColor(col))
            p.drawText(QRectF(tx, 0, w, self.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), RADIUS_CTRL, RADIUS_CTRL)
