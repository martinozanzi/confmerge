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
from ..media_scan import (AUDIO_EXT, SLIDE_EXT, VIDEO_EXT, MediaInfo, find_gaps, media_info, order_clips,
                          pick_external_audio, scan_folder)
from ..sync import analyze_sync
from ..worker import Worker
from .player import PlayerWidget, fmt
from .waveform import WaveformWidget

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
        box = QGroupBox("Video (ordine di montaggio)")
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
            self.refresh()
            self.list.setCurrentRow(j)

    def remove(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.videos):
            del self.videos[i]
            self.refresh(reorder=True)

    # --- riepilogo
    def refresh(self, reorder: bool = False):
        warn: list[str] = []
        if reorder or len(self.infos) != len(self.videos):
            infos = []
            for v in self.videos:
                try:
                    infos.append(media_info(v))
                except FFmpegError as e:
                    warn.append(str(e))
            self.infos, self.order_method = (order_clips(infos) if infos else ([], "nome"))
            self.videos = [c.path for c in self.infos]
        self.list.clear()
        for c in self.infos:
            self.list.addItem(f"{c.name} — {fmt(c.duration)} — {c.width}×{c.height} @ {c.fps:.0f} fps"
                              + (f" (ruotato {c.rotation}°)" if c.rotation else ""))
        warn += [g.message() for g in find_gaps(self.infos)]
        parts = [f"<b>{len(self.videos)}</b> video"]
        parts.append(f"audio esterno: <b>{self.audio.name}</b>" if self.audio else "<span style='color:#c33'>audio esterno mancante</span>")
        if self.slides:
            parts.append(f"<b>{len(self.slides)}</b> file di slide")
        txt = "Riepilogo: " + " · ".join(parts)
        if self.infos:
            txt += f"<br>Ordinati per {getattr(self, 'order_method', 'nome')}. Riordinali con ▲▼ se necessario."
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
            report(0.5, "Creazione dell'anteprima 480p con audio allineato…")
            proxy.build_proxy(rep.project, rep.clips, out, lambda f, s: report(0.5 + f * 0.5, "Creazione dell'anteprima 480p con audio allineato…"), cancel)
            return rep, out

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
        rep, out = res
        st = self.state
        st.project, st.clips, st.cam, st.ext = rep.project, rep.clips, rep.cam, rep.ext
        st.proxy, st.proxy_stale, st.warnings = out, False, rep.warnings
        if slides:
            st.spec.slides.files = [str(s) for s in slides]
            st.spec.slides.enabled = True
        st.spec.image.kb_t1 = min(st.spec.image.kb_t1, rep.project.total_duration)
        st.project_changed.emit()
        self.done.emit()


class ReviewPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker: Worker | None = None
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.player = PlayerWidget(state)
        ll.addWidget(self.player, 1)
        self.wave = WaveformWidget()
        ll.addWidget(self.wave)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        split.addWidget(right)
        split.setStretchFactor(0, 4)
        main = QVBoxLayout(self)
        main.addWidget(QLabel("<h2>3. Revisione</h2>"))
        main.addWidget(split, 1)

        g = QGroupBox("Sincronizzazione")
        f = QFormLayout(g)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-36000000, 36000000)
        self.offset.setDecimals(0)
        self.offset.setSuffix(" ms")
        self.offset.setSingleStep(10)
        self.offset.valueChanged.connect(self._offset_changed)
        f.addRow("Offset", self.offset)
        self.conf = QLabel()
        f.addRow("Confidenza", self.conf)
        self.drift = QCheckBox("Correggi la deriva dei clock (atempo)")
        self.drift.toggled.connect(self._drift_toggled)
        f.addRow(self.drift)
        self.drift_lbl = QLabel()
        self.drift_lbl.setWordWrap(True)
        f.addRow(self.drift_lbl)
        b1 = QPushButton("Applica all'anteprima")
        b1.setToolTip("Rigenera l'audio dell'anteprima con l'offset corrente (rapido)")
        b1.clicked.connect(self.apply_offset)
        b2 = QPushButton("🎧 Riascolta sincronia (10 s)")
        b2.setToolTip("Sovrappone audio camera ed esterno intorno alla posizione corrente: se non coincidono si sente l'eco")
        b2.clicked.connect(self.listen_sync)
        f.addRow(b1)
        f.addRow(b2)
        rl.addWidget(g)

        t = QGroupBox("Tagli (mai applicati senza conferma)")
        tf = QFormLayout(t)
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for e in (self.start_edit, self.end_edit):
            e.setPlaceholderText("h:mm:ss.cc")
            e.editingFinished.connect(self._edit_markers)
        hb = QHBoxLayout()
        hb.addWidget(self.start_edit)
        bs = QPushButton("Qui")
        bs.setToolTip("Imposta l'inizio sulla posizione corrente (I)")
        bs.clicked.connect(self.set_start_here)
        gs = QPushButton("Vai")
        gs.clicked.connect(lambda: self._goto(self.wave.start))
        hb.addWidget(bs)
        hb.addWidget(gs)
        tf.addRow("Inizio", hb)
        hb = QHBoxLayout()
        hb.addWidget(self.end_edit)
        be = QPushButton("Qui")
        be.setToolTip("Imposta la fine sulla posizione corrente (O)")
        be.clicked.connect(self.set_end_here)
        ge = QPushButton("Vai")
        ge.clicked.connect(lambda: self._goto(self.wave.end))
        hb.addWidget(be)
        hb.addWidget(ge)
        tf.addRow("Fine", hb)
        self.sugg = QLabel()
        self.sugg.setWordWrap(True)
        tf.addRow(self.sugg)
        ab = QPushButton("Applica il taglio suggerito")
        ab.clicked.connect(self.apply_suggestion)
        tf.addRow(ab)
        rl.addWidget(t)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet("color:#d08000")
        rl.addWidget(self.warn)
        self.status = QLabel()
        rl.addWidget(self.status)
        rl.addStretch(1)

        self.player.positionChanged.connect(self._pos)
        self.wave.seek.connect(self.player.set_position)
        self.wave.markersChanged.connect(self._markers_from_wave)
        state.project_changed.connect(self.load)
        state.spec_changed.connect(self._slide_marks)

    # --- caricamento
    def load(self):
        st = self.state
        pr = st.project
        if not pr:
            return
        self.player.load(st.proxy, pr.total_duration)
        self.wave.set_data(st.cam, st.ext, pr.total_duration)
        self.wave.offset = pr.effective_offset
        self.wave.start, self.wave.end = pr.trim_start, pr.trim_end
        if pr.suggested_start is not None:
            self.wave.suggest = (pr.suggested_start, pr.suggested_end)
            self.sugg.setText(f"Suggerito: {fmt(pr.suggested_start)} → {fmt(pr.suggested_end)}")
        else:
            self.wave.suggest = None
            self.sugg.setText("Nessun taglio suggerito.")
        self.offset.blockSignals(True)
        self.offset.setValue(round(pr.effective_offset * 1000))
        self.offset.blockSignals(False)
        low = pr.sync_confidence < 7
        self.conf.setText(f"{pr.sync_confidence:.1f}" + ("  ⚠ bassa: controlla a orecchio" if low else "  ✓"))
        self.conf.setStyleSheet("color:#c33" if low else "color:#2a8")
        has_drift = pr.offset_corrected_s is not None and pr.drift_s is not None and abs(pr.drift_s) > 0.05
        self.drift.setVisible(has_drift)
        self.drift_lbl.setText(f"Deriva misurata: {pr.drift_s * 1000:+.0f} ms (atempo {pr.atempo:.6f})" if has_drift else "")
        self.warn.setText("\n".join("⚠ " + w for w in st.warnings))
        self._sync_edits()
        self._slide_marks()

    def _slide_marks(self):
        st = self.state
        self.wave.marks = [st.from_out(c.t) for c in st.spec.slides.changes] if st.spec.slides.enabled else []
        self.wave.update()

    def _pos(self, t: float):
        self.wave.pos = t
        self.wave.update()

    def _goto(self, t):
        if t is not None:
            self.player.set_position(t)

    # --- offset / deriva
    def _offset_changed(self, ms: float):
        pr = self.state.project
        if not pr:
            return
        v = ms / 1000
        if pr.use_drift_correction:
            pr.offset_corrected_s = v
        else:
            pr.offset_s = v
        self.wave.offset = v
        self.wave.update()
        self.state.proxy_stale = True
        self.status.setText("Offset modificato: premi «Applica all'anteprima» per riascoltarlo.")

    def _drift_toggled(self, on: bool):
        pr = self.state.project
        pr.use_drift_correction = on
        self.offset.blockSignals(True)
        self.offset.setValue(round(pr.effective_offset * 1000))
        self.offset.blockSignals(False)
        self.wave.offset = pr.effective_offset
        self.wave.update()
        self.state.proxy_stale = True

    def apply_offset(self):
        st = self.state
        if not st.proxy:
            return
        out = paths.temp_dir() / f"proxy_{int(self.offset.value())}.mp4"
        pos = self.player.position()
        self.status.setText("Rigenerazione dell'audio dell'anteprima…")
        self.worker = Worker(lambda c, r: proxy.rebuild_audio(st.project, st.proxy, out, c))
        self.worker.finished_ok.connect(lambda p: (setattr(st, "proxy", p), setattr(st, "proxy_stale", False),
                                                  self.player.load(p, st.project.total_duration),
                                                  self.player.set_position(pos), self.status.setText("Anteprima aggiornata.")))
        self.worker.failed.connect(lambda m: self.status.setText(m))
        self.worker.start()

    def listen_sync(self):
        st = self.state
        out = paths.temp_dir() / "sync_listen.wav"
        self.status.setText("Preparazione dell'ascolto…")
        center = self.player.position()
        self.worker = Worker(lambda c, r: proxy.sync_preview(st.project, st.clips, center, out))
        self.worker.finished_ok.connect(self._play_wav)
        self.worker.failed.connect(lambda m: self.status.setText(m))
        self.worker.start()

    def _play_wav(self, path):
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        self.player.player.pause()
        self._wav = QMediaPlayer(self)
        self._wav_out = QAudioOutput(self)
        self._wav.setAudioOutput(self._wav_out)
        self._wav.setSource(QUrl.fromLocalFile(str(path)))
        self._wav.play()
        self.status.setText("Riproduzione: audio camera + esterno sovrapposti.")

    # --- tagli
    def _sync_edits(self):
        self.start_edit.setText(fmt(self.wave.start) if self.wave.start is not None else "")
        self.end_edit.setText(fmt(self.wave.end) if self.wave.end is not None else "")

    @staticmethod
    def _parse(text: str) -> float | None:
        try:
            t = 0.0
            for x in text.strip().split(":"):
                t = t * 60 + float(x)
            return t
        except ValueError:
            return None

    def _edit_markers(self):
        s, e = self._parse(self.start_edit.text()), self._parse(self.end_edit.text())
        self.wave.start, self.wave.end = s, e
        self._markers_from_wave(from_edit=True)

    def _markers_from_wave(self, from_edit: bool = False):
        pr = self.state.project
        pr.trim_start, pr.trim_end = self.wave.start, self.wave.end
        if not from_edit:
            self._sync_edits()
        self.wave.update()
        self.state.spec_changed.emit()

    def set_start_here(self):
        self.wave.start = self.player.position()
        self._markers_from_wave()

    def set_end_here(self):
        self.wave.end = self.player.position()
        self._markers_from_wave()

    def apply_suggestion(self):
        pr = self.state.project
        if pr and pr.suggested_start is not None:
            self.wave.start, self.wave.end = pr.suggested_start, pr.suggested_end
            self._markers_from_wave()

    # --- tastiera
    def keyPressEvent(self, e):
        k, mod = e.key(), e.modifiers()
        if k == Qt.Key_Space:
            self.player.toggle()
        elif k == Qt.Key_Left:
            self.player.step(-1.0 if mod & Qt.ShiftModifier else -0.04)
        elif k == Qt.Key_Right:
            self.player.step(1.0 if mod & Qt.ShiftModifier else 0.04)
        elif k == Qt.Key_I:
            self.set_start_here()
        elif k == Qt.Key_O:
            self.set_end_here()
        elif k == Qt.Key_N:
            self.mark_slide()
        else:
            super().keyPressEvent(e)

    def mark_slide(self):
        """Tasto N: segna un cambio slide al tempo corrente (avanza all'indice successivo)."""
        from ..spec import SlideChange
        st = self.state
        sls = st.spec.slides
        if not sls.enabled:
            return
        t = max(0.0, st.to_out(self.player.position()))
        nxt = (max((c.index for c in sls.changes), default=-1) + 1)
        sls.changes.append(SlideChange(round(t, 2), nxt))
        sls.changes.sort(key=lambda c: c.t)
        st.spec_changed.emit()
        self.status.setText(f"Cambio slide {nxt + 1} segnato a {fmt(t)}")
