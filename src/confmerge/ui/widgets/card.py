from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..theme import S2, S3, shadow, theme


def label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


class Card(QFrame):
    """Superficie con angoli 12 px, bordo sottile e ombra leggera."""

    def __init__(self, parent: QWidget | None = None, padding: int = S2, elevated: bool = False, flat: bool = False):
        super().__init__(parent)
        self.setObjectName("Card")
        if flat:
            self.setProperty("flat", True)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(S2)
        if elevated:
            shadow(self)

    def add(self, w: QWidget, stretch: int = 0) -> QWidget:
        self.lay.addWidget(w, stretch)
        return w
