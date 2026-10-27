"""Schermata iniziale: che cosa vuoi fare? Studio Social oppure Merge Conferenze (si ricorda l'ultima scelta)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QVBoxLayout, QWidget

from .theme import RADIUS_CARD, theme
from .widgets import label

CHOICES = [
    ("social", "scissors", "Studio Social",
     "Taglia pause ed errori, aggiungi sottotitoli e musica, ed esporta pronto per YouTube, Shorts, Reel, TikTok, X e Threads."),
    ("merge", "film", "Merge Conferenze",
     "Unisci le riprese di più telecamere, sincronizza l'audio registrato a parte e prepara il video completo con titoli e grafica."),
]


class _Card(QAbstractButton):
    def __init__(self, key: str, icon: str, title: str, text: str, parent=None):
        super().__init__(parent)
        self.key, self.icon_name, self.title, self.text_ = key, icon, title, text
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(340, 250)
        self.setAccessibleName(title)
        self.setToolTip(text)

    def paintEvent(self, _):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        hot = self.underMouse() or self.hasFocus()
        p.setBrush(QColor(t.surface2 if hot else t.surface))
        p.setPen(QPen(QColor(t.accent if hot else t.border), 2 if hot else 1))
        p.drawRoundedRect(r, RADIUS_CARD, RADIUS_CARD)
        theme.icon(self.icon_name, t.accent, 40).paint(p, 28, 28, 40, 40)
        f = self.font()
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(t.text))
        p.drawText(QRectF(28, 86, self.width() - 56, 34), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f.setPixelSize(14)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(t.text2))
        p.drawText(QRectF(28, 128, self.width() - 56, self.height() - 150), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                   self.text_)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class HomePage(QWidget):
    chosen = Signal(str)             # "social" | "merge"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(18)
        t = label("Che cosa vuoi fare?", "title")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        s = label("Scegli lo strumento: la prossima volta si apre direttamente quello. Puoi cambiare quando vuoi dall'alto.",
                  "muted", True)
        s.setAlignment(Qt.AlignCenter)
        s.setMinimumWidth(560)
        s.setMinimumHeight(40)
        s.setMaximumWidth(680)
        lay.addWidget(s, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        row.setSpacing(24)
        row.setAlignment(Qt.AlignCenter)
        self.cards: dict[str, _Card] = {}
        for key, icon, title, text in CHOICES:
            c = _Card(key, icon, title, text)
            c.clicked.connect(lambda _=False, k=key: self.chosen.emit(k))
            row.addWidget(c)
            self.cards[key] = c
        lay.addLayout(row)
