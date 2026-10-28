"""Studio Social: un secondo video nello stesso reel, uno sopra e uno sotto."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QSlider, QVBoxLayout

from ..media_scan import VIDEO_EXT
from ..render.masks import MASKS
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
        cols = QBoxLayout(QBoxLayout.LeftToRight)                 # due colonne (una sola se lo spazio è poco)
        self._cols = cols
        cols.setSpacing(18)
        left, right = QVBoxLayout(), QVBoxLayout()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        self.body.lay.addLayout(cols)
        row = QHBoxLayout()
        self.pick = SecondaryButton("Scegli il secondo video…", "film")
        self.pick.clicked.connect(self._pick)
        self.pick.setToolTip("Se il secondo video è più corto, si ripete. L'anteprima mostra un solo fotogramma.")
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
        left.addWidget(label("Forma del riquadro", ""))
        self.shape = QComboBox()
        for k, v in MASKS.items():
            self.shape.addItem(v, k)
        self.shape.currentIndexChanged.connect(self._shape)
        left.addWidget(self.shape)
        left.addStretch(1)
        self.zoom_lbl = label("", "caption", True)
        right.addWidget(self.zoom_lbl)
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(100, 300)                              # ingrandimento del secondo video: 100 % … 300 %
        self.zoom.valueChanged.connect(self._zoom)
        right.addWidget(self.zoom)
        tip = "Inquadratura del secondo video: prima sinistra/destra, poi alto/basso (si usa da 101 % di ingrandimento)"
        self.second_x = QSlider(Qt.Horizontal)
        self.second_x.setRange(0, 100)
        self.second_x.setToolTip(tip)
        self.second_x.valueChanged.connect(self._second_x)
        right.addWidget(self.second_x)
        self.second_y = QSlider(Qt.Horizontal)
        self.second_y.setRange(0, 100)
        self.second_y.setToolTip(tip)
        self.second_y.valueChanged.connect(self._second_y)
        right.addWidget(self.second_y)
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
        right.addStretch(1)
        state.profile_changed.connect(self.sync)
        self.sync()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        want = QBoxLayout.TopToBottom if self.width() < 600 else QBoxLayout.LeftToRight
        if self._cols.direction() != want:
            self._cols.setDirection(want)
            self.updateGeometry()

    def sp(self):
        return self.state.spec.split

    def sync(self):
        s = self.sp()
        for w, v in ((self.on, s.enabled), (self.audio, s.second_audio)):
            w.blockSignals(True)
            w.setChecked(v)
            w.blockSignals(False)
        for sl, v in ((self.ratio, round(s.ratio * 100)), (self.second_x, round(s.second_x * 100)),
                       (self.second_y, round(s.second_y * 100)), (self.zoom, round(s.second_scale * 100)),
                       (self.db, round(s.second_db))):
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
        self.zoom_lbl.setText(f"Ingrandimento del secondo video: {s.second_scale * 100:.0f} %")
        self.shape.blockSignals(True)
        self.shape.setCurrentIndex(max(0, self.shape.findData(s.mask)))
        self.shape.blockSignals(False)
        for w in (self.second_y, self.second_x):
            w.setEnabled(s.second_scale > 1.001 or w is self.second_x)
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

    def _zoom(self, v: int):
        self.sp().second_scale = v / 100
        self._touch()

    def _second_y(self, v: int):
        self.sp().second_y = v / 100
        self.state.touch()

    def _shape(self, _=0):
        self.sp().mask = self.shape.currentData()
        self.state.touch()

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
