"""Schermate «Sorgenti» e «Analisi» della modalità Avanzata: sono solo viste su SourcesModel e AnalysisRunner."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QListWidget, QMessageBox, QVBoxLayout, QWidget)

from .. import paths
from ..ffmpeg_wrapper import FFmpegError
from ..media_scan import _natural_key  # noqa: F401  (compatibilità con codice esistente)
from .player import fmt_simple
from .theme import S1, S2
from .widgets import (Card, DropZone, GhostButton, IconButton, PrimaryButton, ProgressBarThin, SecondaryButton, Segmented,
                      label)

AUDIO_FILTER = "Audio (*.mp3 *.wav *.ogg *.m4a *.flac)"
VIDEO_FILTER = "Video (*.mp4 *.mov *.m4v)"
SLIDE_FILTER = "Slide (*.pdf *.png *.jpg *.jpeg)"


def source_lines(model) -> list[str]:
    """Una riga per video: numero, nome, data di registrazione, durata (il primo in alto è il primo del montaggio)."""
    out = []
    for n, c in enumerate(model.infos, 1):
        when = c.creation_time.astimezone().strftime("%d/%m/%Y %H:%M:%S") if c.creation_time else "data sconosciuta"
        out.append(f"{n}.  {c.name}  —  registrato il {when}  —  durata {fmt_simple(c.duration)}  —  "
                   f"{c.width}×{c.height} @ {c.fps:.0f} fps" + (f" (ruotato {c.rotation}°)" if c.rotation else ""))
    return out


class SelectPage(QWidget):
    ready = Signal(bool)
    analyzeRequested = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.model = state.sources
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Sorgenti", "title"))
        lay.addWidget(label("Scegli la cartella della conferenza (il programma trova da solo video, audio e slide) "
                            "oppure aggiungi i file a mano. Puoi anche trascinarli qui.", "muted", True))
        row = QHBoxLayout()
        row.setSpacing(S1)
        b = PrimaryButton("Scegli la cartella…", "folder-open")
        b.clicked.connect(self.pick_folder)
        row.addWidget(b)
        for text, icon, fn in (("Aggiungi video…", "film", self.add_videos), ("Scegli l'audio…", "headphones", self.pick_audio),
                               ("Aggiungi slide…", "presentation", self.add_slides)):
            bb = SecondaryButton(text, icon)
            bb.clicked.connect(fn)
            row.addWidget(bb)
        row.addStretch(1)
        lay.addLayout(row)
        orow = QHBoxLayout()
        orow.addWidget(label("Ordine di montaggio:"))
        self.order_seg = Segmented([("Per data di registrazione", "date"), ("Per nome file", "name"), ("Manuale", "manual")])
        self.order_seg.changed.connect(self.model.set_order)
        orow.addWidget(self.order_seg)
        orow.addStretch(1)
        lay.addLayout(orow)
        card = Card()
        card.add(label("Video: il PRIMO in alto è il primo del montaggio", "caption", True))
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setMinimumHeight(140)
        body.addWidget(self.list, 1)
        col = QVBoxLayout()
        for icon, tip, fn in (("arrow-up", "Sposta su", lambda: self.model.move(self.list.currentRow(), -1)),
                              ("arrow-down", "Sposta giù", lambda: self.model.move(self.list.currentRow(), 1)),
                              ("trash-2", "Rimuovi dal montaggio", lambda: self.model.remove(self.list.currentRow()))):
            ib = IconButton(icon, tip)
            ib.clicked.connect(fn)
            col.addWidget(ib)
        col.addStretch(1)
        body.addLayout(col)
        card.lay.addLayout(body)
        lay.addWidget(card, 1)
        self.summary = label("", "", True)
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        go = QHBoxLayout()
        go.addStretch(1)
        self.go_btn = PrimaryButton("Analizza", "wand-sparkles", "Unisce i video, sincronizza l'audio e cerca inizio e fine")
        self.go_btn.clicked.connect(self.analyzeRequested)
        go.addWidget(self.go_btn)
        lay.addLayout(go)
        self.model.changed.connect(self.render)
        self.render()

    # compatibilità con test e codice esistente
    @property
    def videos(self):
        return self.model.videos

    @property
    def audio(self):
        return self.model.audio

    @property
    def slides(self):
        return self.model.slides

    @property
    def infos(self):
        return self.model.infos

    def load_folder(self, folder: Path) -> None:
        try:
            self.model.load_folder(Path(folder))
        except FFmpegError as e:
            QMessageBox.warning(self, "ConfMerge", str(e))
            return
        self.state.settings.data["last_folder"] = str(folder)
        self.state.settings.save()

    # --- input
    def _start_dir(self) -> str:
        return self.state.settings.data.get("last_folder", "")

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella della conferenza", self._start_dir())
        if d:
            self.load_folder(Path(d))

    def add_videos(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Video", self._start_dir(), VIDEO_FILTER)
        if fs:
            self.model.add_videos([Path(f) for f in fs])

    def pick_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "Audio registrato", self._start_dir(), AUDIO_FILTER)
        if f:
            self.model.set_audio(Path(f))

    def add_slides(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Slide (PDF o immagini)", self._start_dir(), SLIDE_FILTER)
        if fs:
            self.model.add_slides([Path(f) for f in fs])

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        folder = self.model.accept_paths([Path(u.toLocalFile()) for u in e.mimeData().urls()])
        if folder:
            self.state.settings.data["last_folder"] = str(folder)

    # --- vista
    def render(self):
        m = self.model
        self.order_seg.setValue(m.order_mode)
        self.list.clear()
        for line in source_lines(m):
            self.list.addItem(line)
        parts = [f"<b>{len(m.videos)}</b> video"]
        parts.append(f"audio registrato: <b>{m.audio.name}</b>" if m.audio else "<b>audio registrato mancante</b>")
        if m.slides:
            parts.append(f"<b>{len(m.slides)}</b> file di slide")
        txt = "Riepilogo: " + " · ".join(parts)
        if m.infos:
            txt += "<br>Il montaggio segue l'elenco dall'alto in basso."
        warn = m.warnings()
        if warn:
            txt += "<br>⚠ " + "<br>⚠ ".join(warn)
        self.summary.setText(txt)
        self.go_btn.setEnabled(m.ready)
        self.ready.emit(m.ready)


class AnalysisPage(QWidget):
    """Avanzamento dell'analisi (vista su AnalysisRunner)."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.runner = state.analysis
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        lay.addWidget(label("Un attimo, sto preparando tutto", "title"), 0, Qt.AlignHCenter)
        self.msg = label("…", "muted")
        lay.addWidget(self.msg, 0, Qt.AlignHCenter)
        self.bar = ProgressBarThin()
        self.bar.setMaximumWidth(520)
        self.bar.setMinimumWidth(320)
        lay.addWidget(self.bar, 0, Qt.AlignHCenter)
        self.cancel_btn = GhostButton("Annulla", "x")
        self.cancel_btn.clicked.connect(self.runner.cancel)
        lay.addWidget(self.cancel_btn, 0, Qt.AlignHCenter)
        lay.addStretch(2)
        self.runner.progress.connect(self._progress)

    def _progress(self, f: float, m: str):
        self.bar.setValue(f)
        if m:
            self.msg.setText(m)

    def start(self):
        m = self.state.sources
        self.bar.setValue(0)
        self.msg.setText("Guardo i video…")
        self.runner.start(list(m.videos), m.audio, list(m.slides))


from .review_page import ReviewPage  # noqa: E402,F401  (schermata «Controlla», in un file a parte)
