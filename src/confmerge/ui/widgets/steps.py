from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..theme import ICON, S1, S2, S3, theme


class StepIndicator(QWidget):
    """Tre/cinque passi con numero, collegamenti e stato (completato / attivo / bloccato)."""

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self.labels = labels
        self.current = 0
        self.done_upto = -1
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(48)

    def set_state(self, current: int, done_upto: int | None = None) -> None:
        self.current = current
        self.done_upto = current - 1 if done_upto is None else done_upto
        self.update()

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.labels)
        seg = self.width() / n
        for i, lab in enumerate(self.labels):
            cx = seg * i + seg / 2
            done, active = i <= self.done_upto, i == self.current
            col = QColor(t.success if done else t.accent if active else t.border)
            if i < n - 1:
                p.setPen(QPen(QColor(t.success if done else t.border), 2))
                p.drawLine(int(cx + 16), 14, int(seg * (i + 1) + seg / 2 - 16), 14)
            p.setPen(Qt.NoPen)
            p.setBrush(col if (done or active) else QColor(t.surface2))
            p.drawEllipse(QRectF(cx - 12, 2, 24, 24))
            p.setPen(QColor(t.on_accent if (done or active) else t.text2))
            if done:
                theme.icon("check", t.on_accent, 14).paint(p, int(cx - 7), 7, 14, 14)
            else:
                p.drawText(QRectF(cx - 12, 2, 24, 24), Qt.AlignCenter, str(i + 1))
            p.setPen(QColor(t.text if active else t.text2))
            p.drawText(QRectF(seg * i, 30, seg, 18), Qt.AlignHCenter | Qt.AlignTop, lab)


class NavButton(QPushButton):
    """Voce della barra laterale: icona + nome fase + stato."""

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(text, parent)
        self._icon, self._state = icon, "idle"      # idle | done | locked
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("variant", "nav")
        self.setMinimumHeight(48)
        self.setFlat(True)
        self.setToolTip(text)
        self.setAccessibleName(text)

    def set_state(self, state: str) -> None:
        self._state = state
        self.setEnabled(state != "locked")
        self.update()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        return QSize(S3 * 2 + ICON + S1 + fm.horizontalAdvance(self.text()) + 12, 48)

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(4, 2, self.width() - 8, self.height() - 4)
        if self.isChecked():
            bg = QColor(t.accent)
            bg.setAlphaF(0.18)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, 8, 8)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRectF(0, self.height() / 2 - 10, 3, 20), 1.5, 1.5)
        elif self.underMouse() and self.isEnabled():
            h = QColor(t.text)
            h.setAlphaF(0.06)
            p.setPen(Qt.NoPen)
            p.setBrush(h)
            p.drawRoundedRect(r, 8, 8)
        col = t.accent if self.isChecked() else (t.text if self.isEnabled() else t.border)
        theme.icon(self._icon, col, ICON).paint(p, S2, (self.height() - ICON) // 2, ICON, ICON)
        p.setPen(QColor(col if self.isChecked() else (t.text2 if self.isEnabled() else t.border)))
        p.drawText(QRectF(S2 + ICON + S1 + 2, 0, self.width() - S2 - ICON - S2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if self._state == "done":
            p.setBrush(QColor(t.success))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(self.width() - S2 - 6, self.height() / 2 - 3, 6, 6))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(r, 8, 8)


class SideNav(QFrame):
    """Barra laterale compatta con le fasi."""
    selected = Signal(int)

    def __init__(self, items: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S1, S2, S1, S2)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[NavButton] = []
        for i, (icon, text) in enumerate(items):
            b = NavButton(icon, text)
            b.clicked.connect(lambda _=False, k=i: self.selected.emit(k))
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch(1)
        self.setMinimumWidth(180)

    def set_current(self, i: int) -> None:
        self.buttons[i].setChecked(True)

    def set_state(self, i: int, state: str) -> None:
        self.buttons[i].set_state(state)
