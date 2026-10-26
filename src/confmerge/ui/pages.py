"""Schermate 1–3 del wizard: selezione, analisi, revisione."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QProgressBar, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from .. import paths, pipeline, proxy
from ..ffmpeg_wrapper import FFmpegError
from ..media_scan import (_natural_key, AUDIO_EXT, SLIDE_EXT, VIDEO_EXT, MediaInfo, find_gaps, media_info, order_clips,
                          pick_external_audio, scan_folder)
from ..sync import analyze_sync
from ..worker import Worker
from .player import PlayerWidget, fmt
from .waveform import WaveformWidget
from .widgets import Segmented

AUDIO_FILTER = "Audio (*.mp3 *.wav *.ogg *.m4a *.flac)"
VIDEO_FILTER = "Video (*.mp4 *.mov *.m4v)"
SLIDE_FILTER = "Slide (*.pdf *.png *.jpg *.jpeg)"


class SelectPage(QWidget):
    ready = Signal(bool)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setAcceptDrops(True)
        self.videos: list[Path] = []
        self.audio: Path | None = None
        self.slides: list[Path] = []
        self.infos: list[MediaInfo] = []
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<h2>1. Seleziona i file</h2>"
                             "Scegli una cartella (modalità automatica) oppure aggiungi i file a mano. "
                             "Puoi anche trascinarli qui."))
        row = QHBoxLayout()
        b = QPushButton("📁 Scegli cartella…")
        b.clicked.connect(self.pick_folder)
        row.addWidget(b)
        for text, fn in (("Aggiungi video…", self.add_videos), ("Scegli audio esterno…", self.pick_audio),
                         ("Aggiungi slide…", self.add_slides)):
            bb = QPushButton(text)
            bb.clicked.connect(fn)
            row.addWidget(bb)
        row.addStretch(1)
        lay.addLayout(row)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Ordine di montaggio:"))
        self.order_mode = "date"
        self.order_seg = Segmented([("Per data di registrazione", "date"), ("Per nome file", "name"), ("Manuale", "manual")])
        self.order_seg.changed.connect(self._order_changed)
        orow.addWidget(self.order_seg)
        orow.addStretch(1)
        lay.addLayout(orow)
        box = QGroupBox("Video: il PRIMO in alto è il primo del montaggio")
        bl = QHBoxLayout(box)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        bl.addWidget(self.list, 1)
        col = QVBoxLayout()
        for text, d in (("▲ Su", -1), ("▼ Giù", 1)):
            bb = QPushButton(text)
            bb.clicked.connect(lambda _=False, dd=d: self.move(dd))
            col.addWidget(bb)
        rm = QPushButton("Rimuovi")
        rm.clicked.connect(self.remove)
        col.addWidget(rm)
        col.addStretch(1)
        bl.addLayout(col)
        lay.addWidget(box, 1)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        self.refresh()

    # --- input
    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella della conferenza", self.state.settings.data.get("last_folder", ""))
        if d:
            self.load_folder(Path(d))

    def load_folder(self, folder: Path):
        try:
            scan = scan_folder(folder)
        except FFmpegError as e:
            QMessageBox.warning(self, "ConfMerge", str(e))
            return
        self.state.settings.data["last_folder"] = str(folder)
        self.state.settings.save()
        self.videos = list(scan.videos)
        self.audio = pick_external_audio(scan.audios)
        self.slides = list(scan.slides)
        self.refresh(reorder=True)

    def add_videos(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Video", self.state.settings.data.get("last_folder", ""), VIDEO_FILTER)
        self.videos += [Path(f) for f in fs if Path(f) not in self.videos]
        self.refresh(reorder=True)

    def pick_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "Audio esterno", self.state.settings.data.get("last_folder", ""), AUDIO_FILTER)
        if f:
            self.audio = Path(f)
            self.refresh()

    def add_slides(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Slide (PDF o immagini)", self.state.settings.data.get("last_folder", ""), SLIDE_FILTER)
        self.slides += [Path(f) for f in fs]
        self.refresh()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = Path(u.toLocalFile())
            if p.is_dir():
                self.load_folder(p)
                return
            ext = p.suffix.lower()
            if ext in VIDEO_EXT and p not in self.videos:
                self.videos.append(p)
            elif ext in AUDIO_EXT:
                self.audio = p
            elif ext in SLIDE_EXT:
                self.slides.append(p)
        self.refresh(reorder=True)

    def move(self, d: int):
        i = self.list.currentRow()
        j = i + d
        if 0 <= i < len(self.videos) and 0 <= j < len(self.videos):
            self.videos[i], self.videos[j] = self.videos[j], self.videos[i]
            self.infos[i], self.infos[j] = self.infos[j], self.infos[i]
            self.order_mode = "manual"
            self.order_seg.setValue("manual")
            self.refresh()
            self.list.setCurrentRow(j)

    def remove(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.videos):
            del self.videos[i]
            self.refresh(reorder=True)

    # --- riepilogo
    def _order_changed(self, mode: str):
        self.order_mode = mode
        if mode != "manual":
            self.refresh(reorder=True)

    def _sorted(self, infos: list[MediaInfo]) -> tuple[list[MediaInfo], str]:
        """Applica il criterio scelto; restituisce (clip, avviso sul criterio effettivo)."""
        by_name = sorted(infos, key=lambda c: _natural_key(c.path))
        by_date, how = order_clips(infos)
        note = ""
        if self.order_mode == "manual":
            known = {c.path: c for c in infos}
            kept = [known[v] for v in self.videos if v in known]
            return kept + [c for c in by_name if c.path not in {k.path for k in kept}], note
        if self.order_mode == "name":
            return by_name, note
        if how != "creation_time":
            note = "Le date di registrazione mancano o sono uguali: ho usato l'ordine dei nomi."
        elif [c.path for c in by_date] != [c.path for c in by_name]:
            note = ("L'ordine per data è diverso da quello per nome file: controlla che il primo dell'elenco sia "
                    "davvero l'inizio (puoi cambiare criterio qui sopra).")
        return by_date, note

    def refresh(self, reorder: bool = False):
        warn: list[str] = []
        if reorder or len(self.infos) != len(self.videos):
            infos = []
            for v in self.videos:
                try:
                    infos.append(media_info(v))
                except FFmpegError as e:
                    warn.append(str(e))
            self.infos, note = self._sorted(infos) if infos else ([], "")
            if note:
                warn.append(note)
            self.videos = [c.path for c in self.infos]
        self.list.clear()
        for n, c in enumerate(self.infos, 1):
            when = c.creation_time.astimezone().strftime("%d/%m/%Y %H:%M:%S") if c.creation_time else "data sconosciuta"
            self.list.addItem(f"{n}.  {c.name}  —  registrato il {when}  —  durata {fmt(c.duration)}  —  "
                              f"{c.width}×{c.height} @ {c.fps:.0f} fps" + (f" (ruotato {c.rotation}°)" if c.rotation else ""))
        warn += [g.message() for g in find_gaps(self.infos)]
        parts = [f"<b>{len(self.videos)}</b> video"]
        parts.append(f"audio esterno: <b>{self.audio.name}</b>" if self.audio else "<span style='color:#c33'>audio esterno mancante</span>")
        if self.slides:
            parts.append(f"<b>{len(self.slides)}</b> file di slide")
        txt = "Riepilogo: " + " · ".join(parts)
        if self.infos:
            txt += "<br>Il montaggio segue l'elenco dall'alto in basso. Cambia criterio o usa ▲▼ per riordinare."
        if warn:
            txt += "<br><span style='color:#d08000'>⚠ " + "<br>⚠ ".join(warn) + "</span>"
        self.summary.setText(txt)
        self.ready.emit(bool(self.videos and self.audio))


class AnalysisPage(QWidget):
    done = Signal()
    failed = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker: Worker | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<h2>2. Analisi</h2>Unione logica, audio della camera, sincronizzazione, "
                             "suggerimento dei tagli e anteprima. Puoi annullare in qualsiasi momento."))
        self.msg = QLabel("…")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.cancel_btn = QPushButton("Annulla")
        self.cancel_btn.clicked.connect(self.cancel)
        lay.addWidget(self.msg)
        lay.addWidget(self.bar)
        lay.addWidget(self.cancel_btn, 0, Qt.AlignLeft)
        lay.addStretch(1)

    def start(self, videos: list[Path], audio: Path, slides: list[Path]):
        paths.temp_dir()

        def job(cancel, report):
            rep = pipeline.analyze(videos, audio, lambda m, f: report(f * 0.5, m), cancel, keep_order=True)
            out = paths.temp_dir() / "proxy.mp4"
            a, b = proxy.initial_window(rep.project)
            msg = "Preparo l'anteprima (10 minuti da quando inizia l'audio)…"
            report(0.5, msg)
            proxy.build_window(rep.project, rep.clips, a, b, out, lambda f, s: report(0.5 + f * 0.5, msg), cancel)
            return rep, out, (a, b)

        self.worker = Worker(job)
        self.worker.progress.connect(lambda f, m: (self.bar.setValue(int(f * 1000)), m and self.msg.setText(m)))
        self.worker.finished_ok.connect(lambda r: self._ok(r, slides))
        self.worker.failed.connect(self._fail)
        self.worker.cancelled.connect(lambda: (self.msg.setText("Analisi annullata."), self.failed.emit()))
        self.cancel_btn.setEnabled(True)
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)

    def _fail(self, msg: str):
        QMessageBox.critical(self, "Analisi non riuscita", msg + f"\n\nLog: {paths.data_dir() / 'confmerge.log'}")
        self.failed.emit()

    def _ok(self, res, slides: list[Path]):
        rep, out, rng = res
        st = self.state
        st.project, st.clips, st.cam, st.ext = rep.project, rep.clips, rep.cam, rep.ext
        st.proxy, st.proxy_stale, st.warnings, st.proxy_range = out, False, rep.warnings, rng
        if slides:
            st.spec.slides.files = [str(s) for s in slides]
            st.spec.slides.enabled = True
        st.spec.image.kb_t1 = min(st.spec.image.kb_t1, rep.project.total_duration)
        st.project_changed.emit()
        self.done.emit()




from .review_page import ReviewPage  # noqa: E402,F401  (schermata 3, in un file a parte)
