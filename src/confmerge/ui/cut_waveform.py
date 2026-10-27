"""Forma d'onda per tagliare (Studio Social): le parti tolte sono scure, si trascina per scegliere una parte."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .theme import theme

HOP_S = 0.01
RULER_H = 18


def fmt_clock(t: float) -> str:
    t = int(max(0, t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


class CutWaveform(QWidget):
    seek = Signal(float)                 # clic: porta lì il video
    selectionChanged = Signal(object)    # (inizio, fine) oppure None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.peaks = np.zeros(1, np.float32)
        self.total = 1.0
        self.removed: list[tuple[float, float]] = []
        self.pos = 0.0
        self.sel: tuple[float, float] | None = None
        self.va, self.vb = 0.0, 1.0          # parte visibile (secondi)
        self._press: QPointF | None = None
        self._press_t = 0.0
        self._dragging = False

    # --- dati
    def set_data(self, samples: np.ndarray, sr: int, total: float) -> None:
        n = max(1, int(sr * HOP_S))
        m = len(samples) // n
        self.peaks = (np.abs(samples[:m * n].reshape(m, n)).max(axis=1) if m else np.zeros(1)).astype(np.float32)
        ref = float(np.percentile(self.peaks, 99)) if len(self.peaks) else 1.0
        if ref > 1e-6:
            self.peaks = np.minimum(self.peaks / ref, 1.0)
        self.total = max(total, 1e-3)
        self.va, self.vb = 0.0, self.total
        self.sel = None
        self.update()

    def set_removed(self, removed: list[tuple[float, float]]) -> None:
        self.removed = list(removed)
        self.update()

    def set_pos(self, t: float) -> None:
        self.pos = t
        if not (self.va <= t <= self.vb) and self._following:
            span = self.vb - self.va
            self.va = min(max(0.0, t - span * 0.1), max(0.0, self.total - span))
            self.vb = self.va + span
        self.update()

    _following = True

    def zoom_all(self) -> None:
        self.va, self.vb = 0.0, self.total
        self.update()

    def selection(self) -> tuple[float, float] | None:
        return self.sel

    def clear_selection(self) -> None:
        if self.sel is not None:
            self.sel = None
            self.selectionChanged.emit(None)
            self.update()

    # --- geometria
    def _wave_rect(self) -> QRectF:
        return QRectF(0, RULER_H, self.width(), max(10, self.height() - RULER_H))

    def _t_at(self, x: float) -> float:
        r = self._wave_rect()
        return self.va + min(max(x / max(r.width(), 1), 0.0), 1.0) * (self.vb - self.va)

    def _x_at(self, t: float) -> float:
        r = self._wave_rect()
        return (t - self.va) / max(self.vb - self.va, 1e-6) * r.width()

    # --- mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position()
            self._press_t = self._t_at(e.position().x())
            self._dragging = False

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.LeftButton):
            if abs(e.position().x() - self._press.x()) > 4:
                self._dragging = True
            if self._dragging:
                t = self._t_at(e.position().x())
                self.sel = (min(self._press_t, t), max(self._press_t, t))
                self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press is None:
            return
        if self._dragging and self.sel and self.sel[1] - self.sel[0] > 0.05:
            self.selectionChanged.emit(self.sel)
        else:
            self.clear_selection()
            self.seek.emit(self._press_t)
        self._press = None
        self._dragging = False

    def wheelEvent(self, e):
        """Rotellina: ingrandisce attorno al puntatore; con Maiusc scorre."""
        d = e.angleDelta().y() or e.angleDelta().x()
        span = self.vb - self.va
        if e.modifiers() & Qt.ShiftModifier:
            shift = -span * 0.15 * (1 if d > 0 else -1)
            self.va = min(max(0.0, self.va + shift), max(0.0, self.total - span))
            self.vb = self.va + span
        else:
            t = self._t_at(e.position().x())
            f = 0.8 if d > 0 else 1.25
            new = min(max(span * f, 2.0), self.total)
            frac = (t - self.va) / max(span, 1e-6)
            self.va = min(max(0.0, t - frac * new), max(0.0, self.total - new))
            self.vb = self.va + new
        self.update()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        self.zoom_all()

    # --- disegno
    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._wave_rect()
        p.fillRect(self.rect(), QColor(t.surface))
        W = max(1, int(r.width()))
        span = max(self.vb - self.va, 1e-6)
        edges = np.linspace(self.va / HOP_S, self.vb / HOP_S, W + 1).astype(int)
        edges = np.clip(edges, 0, max(len(self.peaks) - 1, 0))
        cols = np.maximum.reduceat(self.peaks, edges[:-1]) if len(self.peaks) > 1 else np.zeros(W)
        mid = r.y() + r.height() / 2
        half = r.height() / 2 - 4
        keep = QColor(t.accent)
        gone = QColor(t.text2)
        gone.setAlphaF(0.35)
        for x in range(W):
            tt = self.va + (x + 0.5) / W * span
            is_gone = any(a <= tt < b for a, b in self.removed)
            p.setPen(QPen(gone if is_gone else keep, 1))
            h = max(1.0, float(cols[min(x, len(cols) - 1)]) * half)
            p.drawLine(QPointF(x + 0.5, mid - h), QPointF(x + 0.5, mid + h))
        # parti tolte: velo scuro con tratteggio
        for a, b in self.removed:
            x0, x1 = self._x_at(a), self._x_at(b)
            if x1 < 0 or x0 > r.width():
                continue
            zone = QRectF(max(0.0, x0), r.y(), min(r.width(), x1) - max(0.0, x0), r.height())
            p.fillRect(zone, QColor(0, 0, 0, 90))
            p.fillRect(zone, QBrush(QColor(255, 90, 90, 70), Qt.BDiagPattern))
        # selezione
        if self.sel:
            x0, x1 = self._x_at(self.sel[0]), self._x_at(self.sel[1])
            zone = QRectF(max(0.0, x0), r.y(), min(r.width(), x1) - max(0.0, x0), r.height())
            sel = QColor(t.btn1)
            sel.setAlphaF(0.30)
            p.fillRect(zone, sel)
            p.setPen(QPen(QColor(t.btn1), 2))
            p.drawLine(QPointF(x0, r.y()), QPointF(x0, r.bottom()))
            p.drawLine(QPointF(x1, r.y()), QPointF(x1, r.bottom()))
        # righello
        p.setPen(QColor(t.text2))
        step = _nice_step(span / max(1, W / 90))
        k = int(self.va // step) * step
        while k <= self.vb:
            x = self._x_at(k)
            if 0 <= x <= r.width():
                p.setPen(QColor(t.border))
                p.drawLine(QPointF(x, RULER_H - 4), QPointF(x, RULER_H))
                p.setPen(QColor(t.text2))
                p.drawText(QRectF(x + 3, 0, 70, RULER_H - 2), Qt.AlignLeft | Qt.AlignVCenter, fmt_clock(k))
            k += step
        # posizione
        x = self._x_at(self.pos)
        if 0 <= x <= r.width():
            p.setPen(QPen(QColor(t.text), 2))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))


def _nice_step(raw: float) -> float:
    for s in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600):
        if s >= raw:
            return float(s)
    return 3600.0
