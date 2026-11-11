"""Schermata di avvio piccola, sullo schermo dove si trova il mouse (non sempre sul principale), e posizionamento della finestra."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QSplashScreen, QWidget

SPLASH_W, SPLASH_H = 320, 120               # piccola: non deve coprire lo schermo


def cursor_screen() -> QScreen:
    """Lo schermo dove sta il mouse (dove l'utente ha appena cliccato per aprire l'app); in mancanza, il principale."""
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


def center_on_screen(w: QWidget, screen: QScreen | None = None, max_fraction: float = 0.92) -> None:
    """Mette la finestra al centro dello schermo indicato, rimpicciolendola se non ci sta (barre e dock esclusi)."""
    screen = screen or cursor_screen()
    avail: QRect = screen.availableGeometry()
    w.resize(min(w.width(), int(avail.width() * max_fraction)), min(w.height(), int(avail.height() * max_fraction)))
    geo = w.frameGeometry()
    geo.moveCenter(avail.center())
    w.move(max(avail.left(), geo.left()), max(avail.top(), geo.top()))


def make_splash(version: str = "") -> QSplashScreen:
    from .brand import logo_pixmap
    dpr = 2.0
    px = QPixmap(int(SPLASH_W * dpr), int(SPLASH_H * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(QColor("#0F141C"))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#243040"), 1))
    p.drawRect(0, 0, SPLASH_W - 1, SPLASH_H - 1)
    p.drawPixmap(QPoint(22, 26), logo_pixmap(56, dpr))
    f = QFont("Segoe UI")
    f.setPixelSize(26)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(92, 62, "ConfMerge")
    f.setPixelSize(12)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#9fb0c3"))
    p.drawText(93, 84, ("versione " + version) if version else "Video pronti per la pubblicazione")
    p.setPen(QColor("#6b7a8d"))
    p.drawText(22, SPLASH_H - 14, "Avvio…")
    p.end()
    sp = QSplashScreen(px, Qt.FramelessWindowHint | Qt.SplashScreen)     # non «sempre in primo piano»: altre app possono stare sopra
    scr = cursor_screen()
    geo = sp.frameGeometry()
    geo.moveCenter(scr.geometry().center())
    sp.move(geo.topLeft())
    return sp
