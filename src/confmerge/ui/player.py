"""Player con anteprima WYSIWYG: QMediaPlayer → QVideoSink → Canvas."""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from .canvas import Canvas

FRAME = 0.04


def fmt(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


class PlayerWidget(QWidget):
    positionChanged = Signal(float)      # secondi della timeline del video unito

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
        self.duration = 0.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(lambda v: self.set_position(v / 1000 * self.duration))
        lay.addWidget(self.slider)
        row = QHBoxLayout()
        self.btn_play = QPushButton("▶ Riproduci")
        self.btn_play.setToolTip("Spazio")
        self.btn_play.clicked.connect(self.toggle)
        row.addWidget(self.btn_play)
        for text, delta, tip in (("⏮ -1 s", -1.0, "Maiusc+Sinistra"), ("◀ fotogramma", -FRAME, "Sinistra"),
                                 ("fotogramma ▶", FRAME, "Destra"), ("+1 s ⏭", 1.0, "Maiusc+Destra")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, d=delta: self.step(d))
            row.addWidget(b)
        self.lbl = QLabel("0:00:00.00 / 0:00:00.00")
        row.addStretch(1)
        row.addWidget(self.lbl)
        lay.addLayout(row)
        self._last_pos = 0.0

    def load(self, path, duration: float) -> None:
        self.duration = duration
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.pause()

    def position(self) -> float:
        return self.player.position() / 1000.0

    def set_position(self, t: float) -> None:
        t = min(max(0.0, t), self.duration)
        self.player.setPosition(int(t * 1000))
        self._update(t)

    def step(self, d: float) -> None:
        self.player.pause()
        self.set_position(self.position() + d)

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play_range(self, a: float) -> None:
        self.set_position(a)
        self.player.play()

    def _on_state(self, st) -> None:
        self.btn_play.setText("⏸ Pausa" if st == QMediaPlayer.PlayingState else "▶ Riproduci")

    def _on_pos(self, ms: int) -> None:
        self._update(ms / 1000.0)

    def _update(self, t: float) -> None:
        self._last_pos = t
        self.lbl.setText(f"{fmt(t)} / {fmt(self.duration)}")
        if self.duration:
            self.slider.blockSignals(True)
            self.slider.setValue(int(t / self.duration * 1000))
            self.slider.blockSignals(False)
        self.canvas.set_time(self.state.to_out(t))
        self.positionChanged.emit(t)

    def _on_frame(self, frame) -> None:
        img = frame.toImage()
        if not img.isNull():
            self.state.last_frame = img
            self.canvas.set_frame(img)
