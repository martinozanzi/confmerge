from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ..theme import RADIUS_CARD, S1, S2, S3, S4, pixmap, theme
from .buttons import SecondaryButton


class DropZone(QFrame):
    """Area di rilascio con bordo tratteggiato che si illumina al passaggio del file."""
    dropped = Signal(list)
    browse = Signal()

    def __init__(self, title: str, subtitle: str = "", button: str = "Sfoglia…", icon: str = "folder-open", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._hover = False
        self._icon = icon
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S4, S4, S4)
        lay.setSpacing(S2)
        lay.setAlignment(Qt.AlignCenter)
        self.ic = QLabel()
        self.ic.setAlignment(Qt.AlignCenter)
        self.ic.setFixedHeight(56)
        self.title = QLabel(title)
        self.title.setProperty("role", "h2")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.sub = QLabel(subtitle)
        self.sub.setProperty("role", "muted")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)
        self.btn = SecondaryButton(button, "folder-open")
        self.btn.clicked.connect(self.browse)
        for w in (self.ic, self.title, self.sub):
            lay.addWidget(w)
        lay.addWidget(self.btn, 0, Qt.AlignCenter)
        theme.changed.connect(self._icon_refresh)
        self._icon_refresh()
        self.setMinimumSize(QSize(320, 220))

    def _icon_refresh(self):
        self.ic.setPixmap(pixmap(self._icon, theme.t.accent, 48))
        self.update()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hover = True
            self.update()

    def dragLeaveEvent(self, e):
        self._hover = False
        self.update()

    def dropEvent(self, e):
        self._hover = False
        self.update()
        self.dropped.emit([Path(u.toLocalFile()) for u in e.mimeData().urls()])

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        bg = QColor(t.accent)
        bg.setAlphaF(0.10 if self._hover else 0.0)
        p.setBrush(bg)
        pen = QPen(QColor(t.accent if self._hover else t.border), 2, Qt.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(r, RADIUS_CARD, RADIUS_CARD)
