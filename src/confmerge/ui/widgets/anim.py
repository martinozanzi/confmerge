"""Micro-animazioni (150-250 ms) disattivabili con «riduci animazioni»."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from ..theme import ANIM_BASE, theme

_alive: set = set()


def enabled() -> bool:
    return not theme.reduce_motion


def animate(obj: QObject, prop: bytes, start, end, ms: int = ANIM_BASE,
            curve: QEasingCurve.Type = QEasingCurve.OutCubic, on_done=None) -> QPropertyAnimation | None:
    """Anima una proprietà; con animazioni ridotte imposta subito il valore finale."""
    if not enabled():
        obj.setProperty(prop.decode(), end)
        if on_done:
            on_done()
        return None
    a = QPropertyAnimation(obj, prop, obj)
    a.setDuration(ms)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(curve)
    if on_done:
        a.finished.connect(on_done)
    a.finished.connect(lambda: _alive.discard(a))
    _alive.add(a)
    a.start()
    return a


def fade_in(w: QWidget, ms: int = ANIM_BASE, slide: int = 0) -> None:
    """Comparsa con dissolvenza e leggero scorrimento (usata per card e transizioni fra schermate)."""
    if not enabled():
        return
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    a = QPropertyAnimation(eff, b"opacity", w)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)

    def done():
        w.setGraphicsEffect(None)
        _alive.discard(a)
    a.finished.connect(done)
    _alive.add(a)
    a.start()
    if slide:
        pos = w.pos()
        p = QPropertyAnimation(w, b"pos", w)
        p.setDuration(ms)
        p.setStartValue(QPoint(pos.x(), pos.y() + slide))
        p.setEndValue(pos)
        p.setEasingCurve(QEasingCurve.OutCubic)
        p.finished.connect(lambda: _alive.discard(p))
        _alive.add(p)
        p.start()


def stagger_cards(root: QWidget, ms: int = 200, step: int = 55, limit: int = 8) -> None:
    """Comparsa delle card una dopo l'altra (dissolvenza + leggero scorrimento)."""
    if not enabled():
        return
    from PySide6.QtCore import QTimer
    from .card import Card
    cards = [c for c in root.findChildren(Card) if c.isVisible()][:limit]
    for i, c in enumerate(cards):
        eff = QGraphicsOpacityEffect(c)
        eff.setOpacity(0.0)
        c.setGraphicsEffect(eff)
        QTimer.singleShot(i * step, lambda c=c: _reveal(c, ms))


def _reveal(w: QWidget, ms: int) -> None:
    eff = w.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        return
    a = QPropertyAnimation(eff, b"opacity", w)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)

    def done():
        w.setGraphicsEffect(None)
        _alive.discard(a)
    a.finished.connect(done)
    _alive.add(a)
    a.start()
