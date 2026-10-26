"""Player con anteprima WYSIWYG: QMediaPlayer → QVideoSink → Canvas.

Le posizioni sono SEMPRE sulla linea temporale del video unito. Il file di anteprima ne copre solo una parte
(`origin`…`origin+length`): se si chiede un punto fuori, viene emesso `windowNeeded` e la schermata ne prepara un'altra.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .canvas import Canvas
from .widgets import IconButton

log = logging.getLogger(__name__)
FRAME = 0.04


def fmt(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def fmt_simple(t: float) -> str:
    """Minuti e secondi, per persone: 12:05 oppure 1:02:05."""
    t = int(max(0.0, t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


class PlayerWidget(QWidget):
    positionChanged = Signal(float)      # secondi della timeline del video unito
    windowNeeded = Signal(float)         # si è chiesto un punto non coperto dall'anteprima attuale

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.canvas = Canvas(state)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self.player.positionChanged.connect(self._on_pos)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(lambda e, msg: log.error("Errore del player: %s %s", e, msg))
        self.duration = 0.0              # durata totale della timeline
        self.origin = 0.0                # istante della timeline a cui corrisponde l'inizio del file di anteprima
        self.length = 0.0
        self._pending_seek: float | None = None
        self._stop_at: float | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas, 1)
        self.msg = QLabel("")
        self.msg.setProperty("role", "warn")
        self.msg.setWordWrap(True)
        self.msg.setVisible(False)
        lay.addWidget(self.msg)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(lambda v: self.set_position(v / 1000 * self.duration))
        lay.addWidget(self.slider)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_play = IconButton("play", "Riproduci / pausa (Spazio)")
        self.btn_play.clicked.connect(self.toggle)
        row.addWidget(self.btn_play)
        for icon, delta, tip in (("skip-back", -1.0, "Indietro di 1 secondo (Maiusc+Sinistra)"),
                                 ("chevron-left", -FRAME, "Fotogramma precedente (Sinistra)"),
                                 ("chevron-right", FRAME, "Fotogramma successivo (Destra)"),
                                 ("skip-forward", 1.0, "Avanti di 1 secondo (Maiusc+Destra)")):
            b = IconButton(icon, tip)
            b.clicked.connect(lambda _=False, d=delta: self.step(d))
            row.addWidget(b)
        self.lbl = QLabel("0:00 / 0:00")
        self.lbl.setProperty("role", "muted")
        row.addStretch(1)
        row.addWidget(self.lbl)
        lay.addLayout(row)
        # i click ravvicinati sulla timeline vengono uniti: si esegue solo l'ultima richiesta
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(60)
        self._seek_timer.timeout.connect(self._apply_seek)
        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self.player.pause)

    # --- caricamento
    def load(self, path, origin: float, length: float, total: float) -> None:
        self.origin, self.length, self.duration = origin, length, total
        self.set_message("")
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.pause()

    def set_message(self, text: str) -> None:
        self.msg.setText(text)
        self.msg.setVisible(bool(text))

    def covers(self, t: float) -> bool:
        return self.origin - 0.01 <= t <= self.origin + self.length + 0.01

    # --- posizione
    def position(self) -> float:
        return self.origin + self.player.position() / 1000.0

    def set_position(self, t: float) -> None:
        t = min(max(0.0, t), self.duration or t)
        self._update(t)
        if not self.covers(t):
            self._pending_seek = None
            self.player.pause()
            self.windowNeeded.emit(t)
            return
        self._pending_seek = t
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _apply_seek(self) -> None:
        t, self._pending_seek = self._pending_seek, None
        if t is None:
            return
        try:
            self.player.setPosition(int(min(max(0.0, t - self.origin), self.length) * 1000))
        except Exception:  # noqa: BLE001
            log.exception("setPosition non riuscito (t=%s)", t)

    def step(self, d: float) -> None:
        self.player.pause()
        self.set_position(self.position() + d)

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if not self.covers(self.position()):
                self.windowNeeded.emit(self.position())
                return
            self.player.play()

    def play_for(self, seconds: float) -> None:
        """Riproduce `seconds` secondi dalla posizione attuale e poi si ferma."""
        if not self.covers(self.position()):
            self.windowNeeded.emit(self.position())
            return
        self.player.play()
        self._stop_timer.start(int(seconds * 1000))

    def play_range(self, a: float) -> None:
        self.set_position(a)
        self.player.play()

    def _on_state(self, st) -> None:
        self.btn_play.set_icon("pause" if st == QMediaPlayer.PlayingState else "play")

    def _on_pos(self, ms: int) -> None:
        if self._pending_seek is None:
            self._update(self.origin + ms / 1000.0)

    def _update(self, t: float) -> None:
        self.lbl.setText(f"{fmt_simple(t)} / {fmt_simple(self.duration)}")
        if self.duration:
            self.slider.blockSignals(True)
            self.slider.setValue(int(t / self.duration * 1000))
            self.slider.blockSignals(False)
        self.canvas.set_time(self.state.to_out(t))
        self.positionChanged.emit(t)

    def _on_frame(self, frame) -> None:
        try:
            img = frame.toImage()
            if not img.isNull():
                self.state.last_frame = img
                self.canvas.set_frame(img)
        except Exception:  # noqa: BLE001
            log.exception("Fotogramma non leggibile")
