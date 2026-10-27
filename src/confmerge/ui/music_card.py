"""Scheda «Musica di sottofondo»: un brano scelto dall'utente, con volume e abbassamento automatico quando si parla."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout

from . import bind
from .widgets import Card, Segmented, SecondaryButton, Toggle, label

LEVELS = [("Bassa", -16.0), ("Media", -12.0), ("Alta", -8.0)]
AUDIO_FILTER = "Musica (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)"


class MusicCard(Card):
    def __init__(self, state, detailed: bool = False, parent=None):
        super().__init__(parent)
        self.state, self.detailed = state, detailed
        self.add(label("Musica di sottofondo", "h2", True))
        self.add(label("Un brano a tua scelta sotto la voce. Si sente di più nelle pause e si abbassa da solo quando "
                       "qualcuno parla. Parte con il video e finisce con la dissolvenza.", "caption", True))
        row = QHBoxLayout()
        self.name = label("", "", True)
        row.addWidget(self.name, 1)
        self.pick_btn = SecondaryButton("Scegli un brano…", "music")
        self.pick_btn.clicked.connect(self.pick)
        self.clear_btn = SecondaryButton("Togli", "x")
        self.clear_btn.clicked.connect(self.clear)
        row.addWidget(self.pick_btn)
        row.addWidget(self.clear_btn)
        self.lay.addLayout(row)
        self.vol = Segmented([(t, v) for t, v in LEVELS])
        self.vol.changed.connect(self._vol)
        vr = QHBoxLayout()
        vr.addWidget(label("Volume della musica:"))
        vr.addWidget(self.vol)
        vr.addStretch(1)
        self.lay.addLayout(vr)
        self.duck = Toggle("Abbassa la musica quando qualcuno parla")
        self.duck.toggled.connect(lambda on: self._set("music_duck", on))
        self.add(self.duck)
        self.extra = None
        if detailed:
            from PySide6.QtWidgets import QFormLayout
            self.extra = QFormLayout()
            self.lay.addLayout(self.extra)
        self.sync()
        state.profile_changed.connect(self.sync)

    def a(self):
        return self.state.spec.audio

    def _set(self, attr, v):
        setattr(self.a(), attr, v)
        self.state.touch()

    def sync(self):
        a = self.a()
        on = bool(a.music_path)
        self.name.setText(Path(a.music_path).name if on else "Nessuna musica.")
        self.clear_btn.setVisible(on)
        self.pick_btn.setText("Cambia brano…" if on else "Scegli un brano…")
        nearest = min(LEVELS, key=lambda lv: abs(lv[1] - a.music_db))[1]
        self.vol.setValue(nearest)
        self.duck.blockSignals(True)
        self.duck.setChecked(a.music_duck)
        self.duck.blockSignals(False)
        for w in (self.vol, self.duck):
            w.setEnabled(on)
        if self.extra is not None:
            while self.extra.rowCount():
                self.extra.removeRow(0)
            cb = self.state.touch
            self.extra.addRow("Livello nelle pause (dB)", bind.spin(a, "music_db", -40, 0, 1, 0, "", 1, cb))
            self.extra.addRow("Si abbassa ancora di (dB)", bind.spin(a, "music_duck_db", -30, 0, 1, 0, "", 1, cb))
            self.extra.addRow("Dissolvenza (s)", bind.spin(a, "music_fade", 0, 10, 0.5, 1, "", 1, cb))

    def pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Musica di sottofondo", "", AUDIO_FILTER)
        if p:
            self._set("music_path", p)
            self.sync()

    def clear(self):
        self._set("music_path", "")
        self.sync()

    def _vol(self, v):
        if v is not None and self.a().music_path:
            self._set("music_db", float(v))
