from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ..theme import S1, theme


class Badge(QWidget):
    """Pillola di stato: kind = ok | warn | err | info | neutral."""

    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(parent)
        self._text, self._kind = text, kind

    def set(self, text: str, kind: str) -> None:
        self._text, self._kind = text, kind
        self.updateGeometry()
        self.update()

    def _color(self) -> QColor:
        t = theme.t
        return QColor({"ok": t.success, "warn": t.warning, "err": t.error, "info": t.accent}.get(self._kind, t.text2))

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self._text) + S1 * 3 + 12, fm.height() + 8)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _):
        c = self._color()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(c)
        bg.setAlphaF(0.16)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), self.height() / 2, self.height() / 2)
        p.setBrush(c)
        p.drawEllipse(QRectF(S1 + 2, self.height() / 2 - 3, 6, 6))
        p.setPen(c)
        p.drawText(QRectF(S1 * 2 + 10, 0, self.width(), self.height()), Qt.AlignVCenter | Qt.AlignLeft, self._text)
