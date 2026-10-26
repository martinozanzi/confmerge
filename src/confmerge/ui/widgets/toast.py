from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from ..theme import RADIUS_CTRL, S1, S2, S3, pixmap, theme
from .anim import enabled


class Toast(QWidget):
    """Notifica non bloccante in basso a destra (ok / warn / err / info)."""
    _active: list["Toast"] = []

    def __init__(self, parent: QWidget, text: str, kind: str = "info", ms: int = 3500):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._kind = kind
        t = theme.t
        col = {"ok": t.success, "warn": t.warning, "err": t.error}.get(kind, t.accent)
        icon = {"ok": "circle-check", "warn": "triangle-alert", "err": "circle-x"}.get(kind, "info")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(S2, S1 + 4, S3, S1 + 4)
        lay.setSpacing(S1 + 4)
        ic = QLabel()
        ic.setPixmap(pixmap(icon, col, 20))
        self.lbl = QLabel(text)
        self.lbl.setWordWrap(True)
        lay.addWidget(ic)
        lay.addWidget(self.lbl, 1)
        self.setStyleSheet(f"Toast {{ background: {t.surface2}; border: 1px solid {col}; border-radius: {RADIUS_CTRL}px; }}")
        self.setFixedWidth(360)
        self.adjustSize()
        self.setAutoFillBackground(False)
        Toast._active.append(self)
        self._place()
        self.show()
        self.raise_()
        if enabled():
            eff = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", self)
            a.setDuration(200)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.start()
        QTimer.singleShot(ms, self.close_)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter
        from PySide6.QtWidgets import QStyle, QStyleOption
        o = QStyleOption()
        o.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, o, p, self)

    def _place(self):
        par = self.parentWidget()
        idx = Toast._active.index(self) if self in Toast._active else 0
        y = par.height() - S3
        for t in Toast._active[:idx + 1]:
            y -= t.height() + S1
        self.move(par.width() - self.width() - S3, y)

    def close_(self):
        if self in Toast._active:
            Toast._active.remove(self)
        self.hide()
        self.deleteLater()


def toast(parent: QWidget, text: str, kind: str = "info") -> Toast:
    return Toast(parent.window(), text, kind)
