from __future__ import annotations

from PySide6.QtCore import Property, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy

from ..theme import ANIM_FAST, S1, S2, theme
from .anim import animate


class Toggle(QAbstractButton):
    """Interruttore al posto della checkbox: stessa API (isChecked/setChecked/toggled)."""
    TW, TH = 36, 20

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 0.0
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.toggled.connect(self._on_toggled)

    def setText(self, text: str) -> None:
        super().setText(text)
        if text and not self.toolTip():
            self.setToolTip(text)

    def get_pos(self) -> float:
        return self._pos

    def set_pos(self, v: float) -> None:
        self._pos = v
        self.update()

    pos_ = Property(float, get_pos, set_pos)

    def setChecked(self, on: bool) -> None:           # senza animazione quando impostato da codice
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def _on_toggled(self, on: bool) -> None:
        animate(self, b"pos_", self._pos, 1.0 if on else 0.0, ANIM_FAST)

    M = 4                                   # margine: l'anello di focus non viene più tagliato

    def _text_w(self, w: int) -> int:
        return max(40, w - self.M * 2 - self.TW - S1 - 2)

    def _text_h(self, w: int) -> int:
        if not self.text():
            return 0
        fm = QFontMetrics(self.font())
        return fm.boundingRect(0, 0, self._text_w(w), 10000, Qt.TextWordWrap, self.text()).height()

    def hasHeightForWidth(self) -> bool:
        return bool(self.text())

    def heightForWidth(self, w: int) -> int:
        return max(self.TH, self._text_h(w)) + 2 * self.M + 2

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        w = self.M * 2 + self.TW + (S1 + 2 + fm.horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self) -> QSize:
        w = self.M * 2 + self.TW + (S1 + 2 + 90 if self.text() else 0)
        return QSize(w, max(self.TH, QFontMetrics(self.font()).height()) + 2 * self.M + 2)

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2
        track = QRectF(self.M, cy - self.TH / 2, self.TW, self.TH)
        off, on = QColor(t.border), QColor(t.accent)
        mix = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * mix), int(off.green() + (on.green() - off.green()) * mix),
                     int(off.blue() + (on.blue() - off.blue()) * mix))
        if not self.isEnabled():
            col.setAlphaF(0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(track, self.TH / 2, self.TH / 2)
        r = self.TH - 6
        x = track.left() + 3 + (self.TW - self.TH) * mix
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, cy - r / 2, r, r))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), self.TH / 2 + 2, self.TH / 2 + 2)
        if self.text():
            p.setPen(QColor(t.text if self.isEnabled() else t.text2))
            x0 = self.M + self.TW + S1 + 2
            p.drawText(QRectF(x0, 0, self.width() - x0 - self.M, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.text())
