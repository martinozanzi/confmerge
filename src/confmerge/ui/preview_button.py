"""«Guarda 10 secondi»: prepara un pezzetto del video finito con tutti gli effetti (titoli, sottotitoli, grafica, musica) e lo
riproduce, prima di esportare. Usa gli stessi filtri dell'export, a risoluzione ridotta per fare in fretta."""
from __future__ import annotations

import copy
import logging
import time
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from .. import export_engine as ee, paths
from ..spec import RenderSpec
from ..worker import Worker
from .player import NO_PLAYER
from .widgets import SecondaryButton, label

log = logging.getLogger(__name__)
PREVIEW_SECONDS = 10.0
PREVIEW_SHORT_SIDE = 480


def show_video(parent: QWidget, path: Path, title: str = "Anteprima di 10 secondi") -> None:
    if NO_PLAYER:                                   # nei test senza schermo il lettore multimediale può bloccarsi
        return
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.resize(900, 560)
    lay = QVBoxLayout(d)
    vw = QVideoWidget()
    lay.addWidget(vw, 1)
    pl = QMediaPlayer(d)
    ao = QAudioOutput(d)
    pl.setAudioOutput(ao)
    pl.setVideoOutput(vw)
    pl.setSource(QUrl.fromLocalFile(str(path)))
    pl.play()
    d.finished.connect(pl.stop)
    d.exec()


class PreviewButton(QWidget):
    """Pulsante con messaggio di avanzamento. `pos_fn`: da dove partire (secondi del progetto); `spec_fn`: la spec da usare."""
    ready = Signal(object)                          # percorso del file pronto (anche per i test)

    def __init__(self, state, pos_fn, spec_fn=None, text: str = "Guarda 10 s", parent=None):
        super().__init__(parent)
        self.state, self.pos_fn, self.spec_fn = state, pos_fn, spec_fn
        self.worker: Worker | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.btn = SecondaryButton(text, "play", "Prepara un pezzetto del video finito, con titoli, sottotitoli, grafica e musica, "
                                   "e lo riproduce: così vedi com'è prima di esportare.")
        self.btn.clicked.connect(self.start)
        lay.addWidget(self.btn)
        self.msg = label("", "caption", True)
        self.msg.setVisible(False)
        lay.addWidget(self.msg, 1)

    @property
    def running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def start(self) -> None:
        st = self.state
        if not st.project or not st.clips or self.running:
            return
        spec = RenderSpec.from_dict((self.spec_fn() if self.spec_fn else st.spec).to_dict())
        spec.export.preset, spec.export.custom_height = "Personalizzato", PREVIEW_SHORT_SIDE      # leggero: serve a vedere, non a pubblicare
        proj = copy.deepcopy(st.project)
        clips = list(st.clips)
        start = max(0.0, float(self.pos_fn()))
        out = paths.temp_dir() / f"prova_{int(time.time() * 1000)}.mp4"
        self.btn.setEnabled(False)
        self.msg.setVisible(True)
        self.msg.setText("Preparo l'anteprima con tutti gli effetti…")
        self.worker = Worker(lambda cancel, report: (ee.render_sample(proj, clips, spec, start, PREVIEW_SECONDS, out, cancel), out)[1])
        self.worker.finished_ok.connect(self._ok)
        self.worker.failed.connect(self._failed)
        self.worker.cancelled.connect(self._reset)
        self.worker.start()

    def _reset(self) -> None:
        self.btn.setEnabled(True)
        self.msg.setVisible(False)

    def _ok(self, path) -> None:
        self._reset()
        self.ready.emit(path)
        show_video(self, Path(path))

    def _failed(self, message: str) -> None:
        self._reset()
        log.error("Anteprima di 10 secondi: %s", message)
        QMessageBox.warning(self, "ConfMerge", "Non sono riuscito a preparare l'anteprima.\n" + message[-300:])
