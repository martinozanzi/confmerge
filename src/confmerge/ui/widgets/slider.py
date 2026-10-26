from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from ..theme import S1, S2


class ValueSlider(QWidget):
    """Slider con valore numerico visibile (formato configurabile)."""
    valueChanged = Signal(float)

    def __init__(self, lo: float, hi: float, value: float, step: float = 1.0, fmt: str = "{:.0f}", parent=None):
        super().__init__(parent)
        self._lo, self._step, self._fmt = lo, step, fmt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(S2)
        self.s = QSlider(Qt.Horizontal)
        self.s.setRange(0, max(1, round((hi - lo) / step)))
        self.s.setValue(round((value - lo) / step))
        self.lbl = QLabel(fmt.format(value))
        self.lbl.setMinimumWidth(48)
        self.lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.s, 1)
        lay.addWidget(self.lbl)
        self.s.valueChanged.connect(self._ch)

    def _ch(self, i: int):
        v = self._lo + i * self._step
        self.lbl.setText(self._fmt.format(v))
        self.valueChanged.emit(v)

    def value(self) -> float:
        return self._lo + self.s.value() * self._step

    def setValue(self, v: float):
        self.s.setValue(round((v - self._lo) / self._step))
