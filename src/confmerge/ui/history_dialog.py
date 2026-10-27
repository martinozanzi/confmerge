"""Cronologia delle modifiche: si può tornare a qualsiasi punto, avanti o indietro."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem,
                               QVBoxLayout)

from .widgets import SecondaryButton, label


def when_text(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


class HistoryDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Cronologia delle modifiche")
        self.resize(460, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Cronologia delle modifiche", "h2"))
        lay.addWidget(label("Le più recenti sono in alto. Fai doppio clic su un punto per tornarci: poi puoi anche "
                            "andare avanti. Una nuova modifica cancella i punti successivi.", "caption", True))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemDoubleClicked.connect(self._go)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.back = SecondaryButton("Indietro", "undo-2")
        self.fwd = SecondaryButton("Avanti", "redo-2")
        self.go_btn = SecondaryButton("Torna a questo punto", "rotate-ccw")
        self.back.clicked.connect(lambda: self._step(-1))
        self.fwd.clicked.connect(lambda: self._step(+1))
        self.go_btn.clicked.connect(lambda: self.list.currentItem() and self._go(self.list.currentItem()))
        for b in (self.back, self.fwd, self.go_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).setText("Chiudi")
        lay.addWidget(bb)
        state.spec_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        st = self.state
        hist, cur = st.history, st.history_index
        self.list.blockSignals(True)
        self.list.clear()
        for i in range(len(hist) - 1, -1, -1):
            e = hist[i]
            it = QListWidgetItem(f"{when_text(e.when)}   {e.label}" + ("      ← adesso" if i == cur else ""))
            it.setData(Qt.UserRole, i)
            f = it.font()
            f.setBold(i == cur)
            it.setFont(f)
            if i > cur:
                it.setForeground(self.palette().mid())          # punti «avanti» (annullati): più tenui
            self.list.addItem(it)
            if i == cur:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        self.back.setEnabled(st.can_undo)
        self.fwd.setEnabled(st.can_redo)

    def _go(self, it: QListWidgetItem):
        self.state.jump(it.data(Qt.UserRole))
        self.refresh()

    def _step(self, d: int):
        (self.state.undo if d < 0 else self.state.redo)()
        self.refresh()
