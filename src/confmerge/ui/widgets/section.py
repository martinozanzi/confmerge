from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..theme import ANIM_BASE, ICON, S1, S2, theme
from .anim import enabled

QWIDGETSIZE_MAX = (1 << 24) - 1


class SectionHeader(QPushButton):
    """Intestazione cliccabile con icona e freccia."""

    def __init__(self, title: str, icon: str | None = None, parent=None):
        super().__init__(title, parent)
        self._icon = icon
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("variant", "section")
        self.toggled.connect(self._paint)
        theme.changed.connect(self._paint)
        self._paint()

    def _paint(self, *_):
        from PySide6.QtCore import QSize
        self.setIconSize(QSize(ICON, ICON))
        self.setIcon(theme.icon("chevron-down" if self.isChecked() else "chevron-right", theme.t.text2))


class Section(QFrame):
    """Sezione comprimibile con altezza animata; lo stato aperto/chiuso è ricordato in `theme.prefs`."""

    def __init__(self, title: str, key: str | None = None, opened: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.key = f"section:{key}" if key else None
        if self.key:
            opened = theme.prefs.get(self.key, opened)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(S1, S1, S1, S1)
        outer.setSpacing(0)
        self.header = SectionHeader(title)
        outer.addWidget(self.header)
        self.body = QWidget()
        self.body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(S1 + 4, S1, S1 + 4, S1 + 4)
        self.body_lay.setSpacing(S1 + 4)
        outer.addWidget(self.body)
        self._anim: QPropertyAnimation | None = None
        self.header.setChecked(opened)
        self.body.setVisible(opened)
        self.header.toggled.connect(self._toggle)

    def form(self) -> QFormLayout:
        """FormLayout ben comportato: righe a altezza deterministica, campi che si adattano alla larghezza."""
        f = QFormLayout()
        f.setContentsMargins(0, 0, 0, 0)
        f.setHorizontalSpacing(S2)
        f.setVerticalSpacing(S1 + 4)
        f.setRowWrapPolicy(QFormLayout.DontWrapRows)   # altezza deterministica (niente heightForWidth annidato)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.body_lay.addLayout(f)
        return f

    def add(self, w: QWidget) -> QWidget:
        self.body_lay.addWidget(w)
        return w

    def _target_height(self) -> int:
        lay = self.body.layout()
        w = max(self.body.width(), 200)
        return lay.totalHeightForWidth(w) if lay.hasHeightForWidth() else lay.sizeHint().height()

    def _toggle(self, on: bool) -> None:
        if self.key:
            theme.prefs.set(self.key, on)
        if self._anim:
            self._anim.stop()
        if not enabled() or not self.isVisible():
            self.body.setVisible(on)
            self.body.setMaximumHeight(QWIDGETSIZE_MAX)
            return
        h = self._target_height()
        self.body.setVisible(True)
        a = QPropertyAnimation(self.body, b"maximumHeight", self)
        a.setDuration(ANIM_BASE)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.setStartValue(0 if on else self.body.height())
        a.setEndValue(h if on else 0)

        def done():
            self.body.setMaximumHeight(QWIDGETSIZE_MAX)
            self.body.setVisible(on)
        a.finished.connect(done)
        self._anim = a
        a.start()

    def set_open(self, on: bool) -> None:
        self.header.setChecked(on)
