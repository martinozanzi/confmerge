"""Selettore colore a comparsa (al posto della finestra Qt di sistema): leggibile in entrambi i temi, in italiano."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from .theme import RADIUS_CARD, S1, S2, shadow, theme

SUGGESTED = ["#FFFFFF", "#F3F4F6", "#9CA3AF", "#4B5563", "#1F2937", "#000000",
             "#EF4444", "#F97316", "#F59E0B", "#FACC15", "#84CC16", "#22C55E",
             "#14B8A6", "#06B6D4", "#38BDF8", "#3B82F6", "#6366F1", "#EC4899",
             "#FDE68A", "#FCA5A5", "#A7F3D0", "#BAE6FD", "#C7D2FE", "#FBCFE8"]
# Palette già pronte (sei colori ciascuna): si scelgono da un menu, poi un clic sul colore.
PALETTES: dict[str, list[str]] = {
    "Giornalistica": ["#FFFFFF", "#111827", "#E11D48", "#FACC15", "#2563EB", "#9CA3AF"],
    "Istituzionale": ["#FFFFFF", "#0F2A4A", "#1D4ED8", "#38BDF8", "#C9A227", "#E5E7EB"],
    "Social vivace": ["#FFFFFF", "#000000", "#FF3B6B", "#FFD60A", "#7C3AED", "#06D6A0"],
    "Pastello": ["#FFFFFF", "#334155", "#FBCFE8", "#BAE6FD", "#FDE68A", "#BBF7D0"],
    "Notte": ["#F8FAFC", "#020617", "#1E293B", "#6366F1", "#22D3EE", "#F472B6"],
    "Terra": ["#FFF7ED", "#292524", "#9A3412", "#CA8A04", "#4D7C0F", "#78716C"],
    "Alto contrasto": ["#FFFFFF", "#000000", "#FFE600", "#00E5FF", "#FF2D2D", "#00D26A"],
}
MAX_RECENT = 10


class _SV(QWidget):
    changed = Signal(float, float)       # saturazione, luminosità (0..1)

    def __init__(self):
        super().__init__()
        self.setFixedSize(236, 150)
        self.setCursor(Qt.CrossCursor)
        self.h, self.s, self.v = 0.0, 1.0, 1.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        base = QColor.fromHsvF(self.h, 1.0, 1.0)
        g = QLinearGradient(0, 0, r.width(), 0)
        g.setColorAt(0, QColor("white"))
        g.setColorAt(1, base)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 8, 8)
        g2 = QLinearGradient(0, 0, 0, r.height())
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor("black"))
        p.setBrush(g2)
        p.drawRoundedRect(r, 8, 8)
        x, y = self.s * r.width(), (1 - self.v) * r.height()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("black"), 3))
        p.drawEllipse(QPoint(int(x), int(y)), 7, 7)
        p.setPen(QPen(QColor("white"), 2))
        p.drawEllipse(QPoint(int(x), int(y)), 7, 7)

    def _set(self, pos):
        self.s = min(max(pos.x() / self.width(), 0.0), 1.0)
        self.v = 1.0 - min(max(pos.y() / self.height(), 0.0), 1.0)
        self.changed.emit(self.s, self.v)
        self.update()

    def mousePressEvent(self, e):
        self._set(e.position())

    def mouseMoveEvent(self, e):
        self._set(e.position())


class _Hue(QWidget):
    changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.setFixedSize(236, 18)
        self.setCursor(Qt.PointingHandCursor)
        self.h = 0.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF(min(i / 6, 0.999), 1, 1))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 4, self.width(), 10), 5, 5)
        x = self.h * self.width()
        p.setBrush(QColor.fromHsvF(min(self.h, 0.999), 1, 1))
        p.setPen(QPen(QColor("white"), 2.5))
        p.drawEllipse(QPoint(int(x), 9), 7, 7)

    def _set(self, pos):
        self.h = min(max(pos.x() / self.width(), 0.0), 0.999)
        self.changed.emit(self.h)
        self.update()

    def mousePressEvent(self, e):
        self._set(e.position())

    def mouseMoveEvent(self, e):
        self._set(e.position())


class _Swatch(QPushButton):
    def __init__(self, color: str):
        super().__init__()
        self.color = color
        self.setFixedSize(26, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(color)
        self.setAccessibleName(f"Colore {color}")
        t = theme.t
        self.setStyleSheet(f"QPushButton {{ background:{color}; border:1px solid {t.border}; border-radius:6px; min-height:0; padding:0; }}"
                           f"QPushButton:hover {{ border:2px solid {t.text}; }}")


class ColorPicker(QFrame):
    """Si apre sotto un pulsante; il colore cambia in tempo reale; si chiude cliccando fuori."""
    colorChanged = Signal(str)
    closed = Signal(str)

    def __init__(self, initial: str, parent: QWidget | None = None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_DeleteOnClose)
        c = QColor(initial)
        if not c.isValid():
            c = QColor("#FFFFFF")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S2, S2, S2, S2)
        lay.setSpacing(S1 + 2)
        top = QLabel("Scegli un colore")
        top.setProperty("role", "h2")
        lay.addWidget(top)
        self.sv = _SV()
        self.hue = _Hue()
        lay.addWidget(self.sv)
        lay.addWidget(self.hue)
        row = QHBoxLayout()
        self.chip = QLabel()
        self.chip.setFixedSize(34, 34)
        row.addWidget(self.chip)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setPlaceholderText("#RRGGBB")
        self.hex.setToolTip("Codice del colore, per esempio #FFCC00")
        self.hex.editingFinished.connect(self._from_hex)
        row.addWidget(self.hex, 1)
        lay.addLayout(row)
        lay.addWidget(self._cap("Palette pronte"))
        self.pal = QComboBox()
        for n in PALETTES:
            self.pal.addItem(n)
        self.pal.setToolTip("Scegli una palette: poi clicca uno dei suoi colori")
        lay.addWidget(self.pal)
        self.pal_box = QVBoxLayout()
        lay.addLayout(self.pal_box)
        self.pal.currentTextChanged.connect(self._palette)
        self._palette(self.pal.currentText())
        lay.addWidget(self._cap("Colori suggeriti"))
        lay.addLayout(self._grid(SUGGESTED, 6))
        recent = list(theme.prefs.get("recent_colors", []))[:MAX_RECENT]
        self.recent_cap = self._cap("Usati di recente")
        self.recent_cap.setVisible(bool(recent))
        lay.addWidget(self.recent_cap)
        lay.addLayout(self._grid(recent, 6))
        shadow(self, 28, 6)
        self._set_color(c, emit=False)
        self.sv.changed.connect(lambda s, v: self._hsv_changed(self.hue.h, s, v))
        self.hue.changed.connect(lambda h: self._hsv_changed(h, self.sv.s, self.sv.v))
        self.color = c.name().upper()

    def _cap(self, text: str) -> QLabel:
        lb = QLabel(text)
        lb.setProperty("role", "caption")
        return lb

    def _palette(self, name: str) -> None:
        while self.pal_box.count():
            it = self.pal_box.takeAt(0)
            if it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self.pal_box.addLayout(self._grid(PALETTES.get(name, []), 6))

    def _grid(self, colors: list[str], cols: int) -> QGridLayout:
        g = QGridLayout()
        g.setSpacing(6)
        g.setColumnStretch(cols, 1)          # i campioni restano a sinistra, non si allargano
        for i, col in enumerate(colors):
            b = _Swatch(col)
            b.clicked.connect(lambda _=False, cc=col: self._set_color(QColor(cc)))
            g.addWidget(b, i // cols, i % cols)
        return g

    def _hsv_changed(self, h: float, s: float, v: float) -> None:
        self._set_color(QColor.fromHsvF(min(h, 0.999), s, v), update_pickers=False)

    def _from_hex(self) -> None:
        t = self.hex.text().strip()
        if not t.startswith("#"):
            t = "#" + t
        c = QColor(t)
        if c.isValid():
            self._set_color(c)
        else:
            self.hex.setText(self.color)

    def _set_color(self, c: QColor, emit: bool = True, update_pickers: bool = True) -> None:
        self.color = c.name().upper()
        if update_pickers:
            h, s, v, _ = c.getHsvF()
            self.hue.h = max(0.0, h) if h >= 0 else self.hue.h
            self.sv.h, self.sv.s, self.sv.v = self.hue.h, s, v
            self.hue.update()
        self.sv.h = self.hue.h
        self.sv.update()
        self.chip.setStyleSheet(f"background:{self.color}; border:1px solid {theme.t.border}; border-radius:8px;")
        if not self.hex.hasFocus():
            self.hex.setText(self.color)
        if emit:
            self.colorChanged.emit(self.color)

    def closeEvent(self, e):
        recent = [c for c in theme.prefs.get("recent_colors", []) if c != self.color]
        theme.prefs.set("recent_colors", ([self.color] + recent)[:MAX_RECENT])
        self.closed.emit(self.color)
        super().closeEvent(e)

    def show_below(self, anchor: QWidget) -> None:
        self.adjustSize()
        pt = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        scr = QApplication.screenAt(pt) or QApplication.primaryScreen()
        g = scr.availableGeometry()
        x = min(max(g.left(), pt.x()), g.right() - self.width())
        y = pt.y() if pt.y() + self.height() <= g.bottom() else anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() - 6
        self.move(x, max(g.top(), y))
        self.show()
