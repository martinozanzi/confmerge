"""Studio Social: un secondo video nello stesso reel, uno sopra e uno sotto."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFileDialog, QHBoxLayout, QSlider, QVBoxLayout

from ..media_scan import VIDEO_EXT
from .widgets import Card, SecondaryButton, Segmented, Toggle, label


class SplitCard(Card):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.add(label("Due video nello stesso reel", "h2", True))
        self.add(label("Metti un secondo video sopra o sotto il tuo (per esempio quello a cui rispondi).", "caption", True))
        self.on = Toggle("Usa un secondo video")
        self.on.toggled.connect(self._toggled)
        self.add(self.on)
        self.body = Card(flat=True, padding=0)
        self.add(self.body)
        cols = QHBoxLayout()                                      # due colonne: la pagina non deve scorrere
        cols.setSpacing(18)
        left, right = QVBoxLayout(), QVBoxLayout()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        self.body.lay.addLayout(cols)
        row = QHBoxLayout()
        self.pick = SecondaryButton("Scegli il secondo video…", "film")
        self.pick.clicked.connect(self._pick)
        row.addWidget(self.pick)
        row.addStretch(1)
        left.addLayout(row)
        self.name = label("", "caption", True)
        left.addWidget(self.name)
        left.addWidget(label("Il tuo video sta…", ""))
        self.where = Segmented([("In alto", True), ("In basso", False)])
        self.where.changed.connect(self._where)
        left.addWidget(self.where)
        self.ratio_lbl = label("", "", True)
        left.addWidget(self.ratio_lbl)
        self.ratio = QSlider(Qt.Horizontal)
        self.ratio.setRange(25, 75)                               # % dell'altezza per il riquadro in alto
        self.ratio.valueChanged.connect(self._ratio)
        left.addWidget(self.ratio)
        left.addStretch(1)
        self.x_lbl = label("Inquadratura del secondo video: a sinistra o a destra", "caption", True)
        right.addWidget(self.x_lbl)
        self.second_x = QSlider(Qt.Horizontal)
        self.second_x.setRange(0, 100)
        self.second_x.valueChanged.connect(self._second_x)
        right.addWidget(self.second_x)
        srow = QHBoxLayout()
        srow.addWidget(label("Parte dal secondo", "caption"))
        self.start = QDoubleSpinBox()
        self.start.setRange(0, 36000)
        self.start.setDecimals(1)
        self.start.setSingleStep(0.5)
        self.start.valueChanged.connect(self._start)
        srow.addWidget(self.start)
        srow.addStretch(1)
        right.addLayout(srow)
        self.audio = Toggle("Si sente anche l'audio del secondo")
        self.audio.toggled.connect(self._audio)
        right.addWidget(self.audio)
        self.db_lbl = label("", "caption", True)
        right.addWidget(self.db_lbl)
        self.db = QSlider(Qt.Horizontal)
        self.db.setRange(-30, 0)
        self.db.valueChanged.connect(self._db)
        right.addWidget(self.db)
        right.addWidget(label("Se il secondo video è più corto, si ripete. L'anteprima mostra un solo fotogramma.", "caption", True))
        right.addStretch(1)
        state.profile_changed.connect(self.sync)
        self.sync()

    def sp(self):
        return self.state.spec.split

    def sync(self):
        s = self.sp()
        for w, v in ((self.on, s.enabled), (self.audio, s.second_audio)):
            w.blockSignals(True)
            w.setChecked(v)
            w.blockSignals(False)
        for sl, v in ((self.ratio, round(s.ratio * 100)), (self.second_x, round(s.second_x * 100)), (self.db, round(s.second_db))):
            sl.blockSignals(True)
            sl.setValue(v)
            sl.blockSignals(False)
        self.start.blockSignals(True)
        self.start.setValue(s.second_start)
        self.start.blockSignals(False)
        self.where.setValue(s.main_on_top)
        self.name.setText(Path(s.path).name if s.path else "Nessun video scelto.")
        self.ratio_lbl.setText(f"Altezza del riquadro in alto: {s.ratio * 100:.0f} %")
        self.db_lbl.setText(f"Volume del secondo video: {s.second_db:.0f} dB rispetto al tuo")
        self.db.setEnabled(s.second_audio)
        self.body.setVisible(s.enabled)

    def _touch(self):
        self.state.touch()
        self.sync()

    def _toggled(self, on: bool):
        s = self.sp()
        s.enabled = on
        if on and not s.path:
            self._pick()
            if not s.path:                                        # nessun file scelto: resta spento
                s.enabled = False
        self._touch()

    def _pick(self):
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXT))
        f, _ = QFileDialog.getOpenFileName(self, "Scegli il secondo video", "", f"Video ({exts})")
        if f:
            self.sp().path = f
            self.sp().enabled = True
            self._touch()

    def _where(self, v):
        self.sp().main_on_top = bool(v)
        self._touch()

    def _ratio(self, v: int):
        self.sp().ratio = v / 100
        self._touch()

    def _second_x(self, v: int):
        self.sp().second_x = v / 100
        self.state.touch()

    def _start(self, v: float):
        self.sp().second_start = v
        self.state.touch()

    def _audio(self, on: bool):
        self.sp().second_audio = on
        self._touch()

    def _db(self, v: int):
        self.sp().second_db = float(v)
        self._touch()
