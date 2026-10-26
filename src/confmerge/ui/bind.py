"""Piccoli costruttori di widget collegati direttamente agli attributi di un oggetto (dataclass)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QLineEdit, QPushButton, QSpinBox)


def _set(obj, attr, v, cb):
    setattr(obj, attr, v)
    cb()


def spin(obj, attr, lo, hi, step=0.1, decimals=2, suffix="", scale=1.0, cb: Callable = lambda: None) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(decimals)
    if suffix:
        w.setSuffix(suffix)
    v = getattr(obj, attr)
    w.setValue((v if v is not None else 0.0) * scale)
    w.valueChanged.connect(lambda x: _set(obj, attr, x / scale, cb))
    return w


def ispin(obj, attr, lo, hi, cb: Callable = lambda: None, suffix="") -> QSpinBox:
    w = QSpinBox()
    w.setRange(lo, hi)
    if suffix:
        w.setSuffix(suffix)
    w.setValue(int(getattr(obj, attr)))
    w.valueChanged.connect(lambda x: _set(obj, attr, x, cb))
    return w


def check(obj, attr, text, cb: Callable = lambda: None):
    from .widgets.toggle import Toggle
    w = Toggle(text)
    w.setChecked(bool(getattr(obj, attr)))
    w.toggled.connect(lambda x: _set(obj, attr, x, cb))
    return w


def combo(obj, attr, items, cb: Callable = lambda: None) -> QComboBox:
    """items: lista di valori oppure di (etichetta, valore)."""
    w = QComboBox()
    for it in items:
        label, val = it if isinstance(it, tuple) else (str(it), it)
        w.addItem(label, val)
    cur = getattr(obj, attr)
    i = w.findData(cur)
    w.setCurrentIndex(max(0, i))
    w.currentIndexChanged.connect(lambda _: _set(obj, attr, w.currentData(), cb))
    return w


def line(obj, attr, cb: Callable = lambda: None) -> QLineEdit:
    w = QLineEdit(str(getattr(obj, attr) or ""))
    w.textEdited.connect(lambda x: _set(obj, attr, x, cb))
    return w


def color(obj, attr, cb: Callable = lambda: None) -> QPushButton:
    w = QPushButton()
    w.setMinimumWidth(64)

    def paint():
        c = getattr(obj, attr)
        w.setStyleSheet(f"background:{c}; border:1px solid #666;")
        w.setText("")

    def pick():
        c = QColorDialog.getColor(QColor(getattr(obj, attr)), w, "Colore")
        if c.isValid():
            setattr(obj, attr, c.name())
            paint()
            cb()

    paint()
    w.clicked.connect(pick)
    return w
