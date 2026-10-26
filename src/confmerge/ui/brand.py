"""Logo e icona dell'applicazione (file nelle risorse del pacchetto)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

from .theme import RESOURCES

ICON_FILE = RESOURCES / "app" / "icon.png"


def app_icon() -> QIcon:
    return QIcon(str(ICON_FILE))


def logo_pixmap(size: int, dpr: float = 2.0) -> QPixmap:
    px = QPixmap(str(ICON_FILE)).scaled(int(size * dpr), int(size * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    px.setDevicePixelRatio(dpr)
    return px
