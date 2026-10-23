from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton, QWidget

from ..theme import ICON, theme


class _Btn(QPushButton):
    def __init__(self, text: str = "", icon: str | None = None, variant: str = "", tip: str = "",
                 parent: QWidget | None = None):
        super().__init__(text, parent)
        self._icon_name = icon
        self.setProperty("variant", variant)
        self.setCursor(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.PointingHandCursor)
        self.setIconSize(QSize(ICON, ICON))
        if tip:
            self.setToolTip(tip)
            self.setAccessibleName(tip)
        self._paint_icon()
        theme.changed.connect(self._paint_icon)

    def _icon_color(self) -> str:
        return theme.t.on_accent if self.property("variant") == "primary" else theme.t.text

    def _paint_icon(self) -> None:
        if self._icon_name:
            self.setIcon(theme.icon(self._icon_name, self._icon_color()))

    def set_icon(self, name: str) -> None:
        self._icon_name = name
        self._paint_icon()


class PrimaryButton(_Btn):
    def __init__(self, text="", icon=None, tip="", parent=None):
        super().__init__(text, icon, "primary", tip, parent)


class SecondaryButton(_Btn):
    def __init__(self, text="", icon=None, tip="", parent=None):
        super().__init__(text, icon, "", tip, parent)


class GhostButton(_Btn):
    def __init__(self, text="", icon=None, tip="", parent=None):
        super().__init__(text, icon, "ghost", tip, parent)


class LinkButton(_Btn):
    def __init__(self, text="", tip="", parent=None):
        super().__init__(text, None, "link", tip, parent)


class IconButton(_Btn):
    """Pulsante quadrato con sola icona (tooltip obbligatorio: è anche il nome accessibile)."""

    def __init__(self, icon: str, tip: str, parent=None, checkable: bool = False):
        super().__init__("", icon, "icon", tip, parent)
        self.setCheckable(checkable)

    def _icon_color(self) -> str:
        return theme.t.accent if self.isChecked() else theme.t.text2
