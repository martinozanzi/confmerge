"""Mini-timeline sotto l'anteprima: durata di titolo, lower third e overlay sul video principale."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..render.model import Element, resolve_text, substitute
from .layer_list import element_title
from .player import fmt_simple
from .theme import theme

ROW_H = 18
LABEL_W = 96
MAX_ROWS = 6


class MiniTimeline(QWidget):
    timeSelected = Signal(float)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.t = 0.0
        self.total = 1.0
        self.scene = None            # Scene (titolo/finale) oppure None = video principale
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(ROW_H + 8)
        state.spec_changed.connect(self._refresh)

    def set_scene(self, scene, total: float) -> None:
        self.scene, self.total = scene, max(total, 0.1)
        self._refresh()

    def set_time(self, t: float) -> None:
        self.t = t
        self.update()

    def rows(self) -> list[tuple[str, float, float, str]]:
        """(nome, inizio, fine, tipo)"""
        st = self.state
        gr = st.spec.graphics
        out: list[tuple[str, float, float, str]] = []
        total = self.total
        if self.scene is not None:
            for e in self.scene.elements:
                if e.visible:
                    out.append((element_title(substitute([e], st.spec.variables)[0]), e.start,
                                total if e.end is None else min(e.end, total), "el"))
            return out
        if gr.title.enabled and gr.title.over_video:
            out.append(("Titolo", 0.0, min(gr.title.duration, total), "title"))
        for lt in gr.lower_thirds:
            out.append((resolve_text(lt.name, st.spec.variables) or "Lower third", lt.start, min(lt.start + lt.duration, total), "lt"))
        for e in gr.elements:
            if "main" in e.targets and e.visible:
                out.append((element_title(substitute([e], st.spec.variables)[0]), e.start,
                            total if e.end is None else min(e.end, total), "el"))
        return out

    def _refresh(self) -> None:
        if self.scene is None:
            pr = self.state.project
            self.total = max(1.0, self.state.trim_end - self.state.trim_start) if pr else 30.0
        n = min(len(self.rows()), MAX_ROWS)
        self.setFixedHeight(max(1, n) * ROW_H + 10)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(300, max(1, min(len(self.rows()), MAX_ROWS)) * ROW_H + 10)

    def _x(self, t: float) -> float:
        w = self.width() - LABEL_W - 6
        return LABEL_W + t / max(self.total, 1e-6) * w

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rows = self.rows()
        if not rows:
            p.setPen(QColor(t.text2))
            p.drawText(self.rect().adjusted(6, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       "Nessun elemento sul video: aggiungine uno e comparirà qui.")
            return
        fm = QFontMetrics(self.font())
        for i, (name, a, b, kind) in enumerate(rows[:MAX_ROWS]):
            y = 4 + i * ROW_H
            p.setPen(QColor(t.text2))
            p.drawText(QRectF(4, y, LABEL_W - 8, ROW_H), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(name, Qt.ElideRight, LABEL_W - 10))
            col = QColor(t.accent2 if kind == "lt" else t.accent if kind == "title" else t.success)
            col.setAlphaF(0.75)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.border))
            p.drawRoundedRect(QRectF(LABEL_W, y + 4, self.width() - LABEL_W - 6, ROW_H - 8), 3, 3)
            p.setBrush(col)
            x0, x1 = self._x(a), max(self._x(b), self._x(a) + 4)
            p.drawRoundedRect(QRectF(x0, y + 3, x1 - x0, ROW_H - 6), 3, 3)
        if len(rows) > MAX_ROWS:
            p.setPen(QColor(t.text2))
            p.drawText(QRectF(LABEL_W, 4 + MAX_ROWS * ROW_H - 2, 200, 12), Qt.AlignLeft, f"+{len(rows) - MAX_ROWS} altri")
        x = self._x(min(self.t, self.total))
        p.setPen(QColor(t.text))
        p.drawLine(int(x), 2, int(x), self.height() - 2)

    def mousePressEvent(self, e):
        w = self.width() - LABEL_W - 6
        if e.position().x() >= LABEL_W and w > 0:
            self.timeSelected.emit(min(max(0.0, (e.position().x() - LABEL_W) / w * self.total), self.total))
