"""Scelta delle transizioni: anteprime animate al passaggio del mouse, disegnate con QPainter (come Canva)."""
from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QDialog, QDialogButtonBox, QGridLayout, QVBoxLayout, QWidget)

from .. import transitions as TR
from .theme import theme
from .widgets import label

PW, PH = 150, 84


def _scene_a(p: QPainter, r: QRectF) -> None:
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#2563EB"))
    g.setColorAt(1, QColor("#22D3EE"))
    p.fillRect(r, g)
    _glyph(p, r, "A")


def _scene_b(p: QPainter, r: QRectF) -> None:
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#F97316"))
    g.setColorAt(1, QColor("#EC4899"))
    p.fillRect(r, g)
    _glyph(p, r, "B")


def _glyph(p: QPainter, r: QRectF, ch: str) -> None:
    f = QFont()
    f.setPixelSize(int(r.height() * 0.55))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 235))
    p.drawText(r, Qt.AlignCenter, ch)


def paint_transition(p: QPainter, r: QRectF, tid: str, k: float) -> None:
    """Disegna lo stato della transizione a progresso k (0 = solo A, 1 = solo B)."""
    w, h = r.width(), r.height()
    p.save()
    p.setClipRect(r)
    p.translate(r.topLeft())
    r0 = QRectF(0, 0, w, h)
    if tid == "cut":
        (_scene_a if k < 0.5 else _scene_b)(p, r0)
    elif tid in ("fade", "hblur"):
        _scene_a(p, r0)
        p.setOpacity(k)
        _scene_b(p, r0)
        if tid == "hblur":
            amp = math.sin(k * math.pi)
            for i in range(1, 5):
                p.setOpacity(0.18 * amp)
                p.save()
                p.translate(i * 5 * amp, 0)
                _scene_b(p, r0)
                p.restore()
                p.save()
                p.translate(-i * 5 * amp, 0)
                _scene_a(p, r0)
                p.restore()
    elif tid in ("fadeblack", "fadewhite"):
        col = QColor("#000000" if tid == "fadeblack" else "#FFFFFF")
        (_scene_a if k < 0.5 else _scene_b)(p, r0)
        col.setAlphaF(1 - abs(k - 0.5) * 2)
        p.fillRect(r0, col)
    elif tid in ("slideleft", "slideup"):
        dx, dy = (w, 0) if tid == "slideleft" else (0, h)
        p.save()
        p.translate(-dx * k, -dy * k)
        _scene_a(p, r0)
        p.restore()
        p.save()
        p.translate(dx * (1 - k), dy * (1 - k))
        _scene_b(p, r0)
        p.restore()
    elif tid == "wipeleft":
        _scene_a(p, r0)
        p.setClipRect(QRectF(w * (1 - k), 0, w * k, h))
        _scene_b(p, r0)
    elif tid == "circleopen":
        _scene_a(p, r0)
        path = QPainterPath()
        rad = k * math.hypot(w, h) / 2
        path.addEllipse(QPointF(w / 2, h / 2), rad, rad)
        p.setClipPath(path)
        _scene_b(p, r0)
    elif tid == "zoomin":
        p.save()
        s = 1 + k * 1.6
        p.translate(w / 2, h / 2)
        p.scale(s, s)
        p.translate(-w / 2, -h / 2)
        _scene_a(p, r0)
        p.restore()
        p.setOpacity(k * k)
        _scene_b(p, r0)
    elif tid == "pixelize":
        cols, rows = 15, 9
        cw, ch = w / cols, h / rows
        for i in range(cols):
            for j in range(rows):
                hsh = ((i * 73856093) ^ (j * 19349663)) % 100 / 100.0
                cell = QRectF(i * cw, j * ch, cw + 0.5, ch + 0.5)
                p.save()
                p.setClipRect(cell)
                (_scene_b if hsh < k else _scene_a)(p, r0)
                p.restore()
    elif tid == "radial":
        _scene_a(p, r0)
        path = QPainterPath()
        c = QPointF(w / 2, h / 2)
        path.moveTo(c)
        path.arcTo(QRectF(c.x() - w, c.y() - w, 2 * w, 2 * w), 90, -360 * k)
        path.closeSubpath()
        p.setClipPath(path)
        _scene_b(p, r0)
    else:
        _scene_a(p, r0)
        p.setOpacity(k)
        _scene_b(p, r0)
    p.restore()


class _Card(QAbstractButton):
    def __init__(self, tr: TR.Transition, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFixedSize(PW + 12, PH + 40)
        self.setToolTip(tr.description)
        self.setAccessibleName(f"Transizione {tr.label}")
        self._k = 0.5
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def sizeHint(self):
        return QSize(PW + 12, PH + 40)

    def _tick(self):
        ms = self._clock.elapsed() % 1700
        self._k = min(1.0, ms / 1200)         # 1,2 s di movimento, poi una breve pausa sul risultato
        self.update()

    def enterEvent(self, e):
        self._clock.start()
        self._timer.start()

    def leaveEvent(self, e):
        self._timer.stop()
        self._k = 0.5
        self.update()

    def paintEvent(self, e):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(QColor(t.surface2 if self.underMouse() else t.surface))
        p.setPen(QPen(QColor(t.accent if self.isChecked() else t.border), 2 if self.isChecked() else 1))
        p.drawRoundedRect(r, 10, 10)
        pr = QRectF(6, 6, PW, PH)
        clip = QPainterPath()
        clip.addRoundedRect(pr, 6, 6)
        p.save()
        p.setClipPath(clip)
        paint_transition(p, pr, self.tr.id, self._k)
        p.restore()
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(self.isChecked())
        p.setFont(f)
        p.setPen(QColor(t.text))
        p.drawText(QRectF(8, PH + 10, PW - 4, 24), Qt.AlignVCenter | Qt.AlignLeft,
                   self.fontMetrics().elidedText(self.tr.label, Qt.ElideRight, PW - 4))
        p.end()


class TransitionGallery(QWidget):
    """Griglia di transizioni. `join_only` limita agli effetti usabili tra due clip."""
    picked = Signal(str)

    def __init__(self, current: str = "fade", join_only: bool = False, parent=None):
        super().__init__(parent)
        self.current = current
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        items = TR.join_options() if join_only else TR.TRANSITIONS
        self._cards = []
        for tr in items:
            c = _Card(tr)
            c.clicked.connect(lambda _=False, i=tr.id: self._pick(i))
            self._cards.append(c)
        self._cols = 0
        self._layout_cards()

    def set_current(self, tid: str):
        self.current = tid
        for c in self._cards:
            c.setChecked(c.tr.id == tid)

    def _pick(self, tid: str):
        self.set_current(tid)
        self.picked.emit(tid)

    def _layout_cards(self):
        cols = max(1, (max(self.width(), PW + 12) + 10) // (PW + 22))
        if cols == self._cols:
            return
        self._cols = cols
        while self.grid.count():
            self.grid.takeAt(0)
        for n, c in enumerate(self._cards):
            self.grid.addWidget(c, n // cols, n % cols)
        self.set_current(self.current)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_cards()


class TransitionDialog(QDialog):
    """«Scegli la transizione» per la modalità Semplice: un solo stile per titolo, clip e finale."""

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transizioni")
        self.chosen = ""
        lay = QVBoxLayout(self)
        lay.addWidget(label("Come cambia la scena", "h2"))
        lay.addWidget(label("Passa il mouse su un effetto per vederlo in movimento. Vale per il titolo, per il passaggio "
                            "tra le clip e per la schermata finale.", "muted", True))
        from .graphics_page import scrolled
        self.gal = TransitionGallery(current)
        self.gal.picked.connect(self._picked)
        lay.addWidget(scrolled(self.gal), 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(740, 560)

    def _picked(self, tid: str):
        self.chosen = tid
        self.accept()
