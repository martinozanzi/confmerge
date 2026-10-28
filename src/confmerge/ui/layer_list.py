"""Pannello livelli: icona per tipo, occhio (mostra/nascondi), lucchetto e trascinamento per riordinare.
La riga in alto è il livello DAVANTI (ultimo elemento della lista), come nei programmi di grafica."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QWidget

from ..render.model import Element
from .theme import ICON, theme

KIND_ICON = {"text": "type", "image": "image", "clip": "film", "shape": "shapes", "bar": "activity"}
KIND_NAME = {"text": "Testo", "image": "Immagine", "clip": "Overlay animato", "shape": "Forma", "bar": "Barra"}


def element_title(e: Element) -> str:
    if e.kind == "text":
        t = e.text.replace("\n", " ").strip()
        return t[:30] or "Testo vuoto"
    if e.kind in ("image", "clip"):
        return Path(e.path).name if e.path else "Immagine"
    return KIND_NAME.get(e.kind, e.kind)


class _Toggle(QPushButton):
    def __init__(self, on_icon: str, off_icon: str, tip: str):
        super().__init__()
        self.on_icon, self.off_icon = on_icon, off_icon
        self.setCheckable(True)
        self.setFlat(True)
        self.setProperty("variant", "icon")
        self.setFixedSize(32, 32)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(ICON - 2, ICON - 2))
        self.toggled.connect(self.paint_icon)
        theme.changed.connect(self.paint_icon)

    def paint_icon(self, *_):
        self.setIcon(theme.icon(self.on_icon if self.isChecked() else self.off_icon,
                                theme.t.text if self.isChecked() else theme.t.text2))


class _Row(QWidget):
    def __init__(self, e: Element, on_change):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 4, 0)
        lay.setSpacing(6)
        self.setFixedHeight(40)
        self.icon = QLabel()
        self.icon.setFixedWidth(20)
        self.name = QLabel(element_title(e))
        self.name.setMinimumWidth(60)
        self.eye = _Toggle("eye", "eye-off", "Mostra o nascondi questo elemento")
        self.eye.setChecked(e.visible)
        self.lock = _Toggle("lock", "lock-open", "Blocca: non si sposta più col mouse")
        self.lock.setChecked(e.locked)
        self.eye.toggled.connect(lambda on: (setattr(e, "visible", on), on_change()))
        self.lock.toggled.connect(lambda on: (setattr(e, "locked", on), on_change()))
        lay.addWidget(self.icon)
        lay.addWidget(self.name, 1)
        lay.addWidget(self.eye)
        lay.addWidget(self.lock)
        self._kind = e.kind
        theme.changed.connect(self._icon)
        self._icon()
        self.eye.paint_icon()
        self.lock.paint_icon()

    def _icon(self):
        self.icon.setPixmap(theme.icon(KIND_ICON.get(self._kind, "square"), theme.t.text2, 16).pixmap(16, 16))


class LayerList(QListWidget):
    selectedIndex = Signal(int)          # indice dell'elemento nella lista (-1 = nessuno)
    reordered = Signal(list)             # nuovo ordine, come lista di vecchi indici
    edited = Signal()                    # occhio o lucchetto cambiati

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.currentRowChanged.connect(lambda _: self.selectedIndex.emit(self.currentRow()))
        self._elements: list[Element] = []

    # indice dell'elemento, non della riga
    def currentRow(self) -> int:       # noqa: N802 (stessa API di QListWidget, ma con l'indice dell'elemento)
        it = self.currentItem()
        return -1 if it is None else int(it.data(Qt.UserRole))

    def setCurrentRow(self, i: int) -> None:   # noqa: N802
        for r in range(self.count()):
            if int(self.item(r).data(Qt.UserRole)) == i:
                super().setCurrentRow(r)
                return
        super().setCurrentRow(-1)

    def set_elements(self, elements: list[Element], current: int = -1) -> None:
        self._elements = elements
        self.blockSignals(True)
        self.clear()
        for k in reversed(range(len(elements))):
            it = QListWidgetItem()
            it.setData(Qt.UserRole, k)
            it.setSizeHint(QSize(100, 42))
            self.addItem(it)
            self.setItemWidget(it, _Row(elements[k], self.edited.emit))
        self.blockSignals(False)
        if current >= 0:
            self.setCurrentRow(current)

    def update_label(self, i: int) -> None:
        for r in range(self.count()):
            if int(self.item(r).data(Qt.UserRole)) == i and 0 <= i < len(self._elements):
                w = self.itemWidget(self.item(r))
                if w:
                    w.name.setText(element_title(self._elements[i]))
                return

    def dropEvent(self, e):
        super().dropEvent(e)
        order_rows = [int(self.item(r).data(Qt.UserRole)) for r in range(self.count())]   # davanti → dietro
        new_order = list(reversed(order_rows))                                              # dietro → davanti
        if new_order != sorted(new_order):
            QTimer.singleShot(0, lambda: self.reordered.emit(new_order))
