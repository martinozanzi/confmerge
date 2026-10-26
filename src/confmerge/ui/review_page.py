"""Schermata «Controlla il video»: sincronia e tagli, in parole semplici."""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from .. import paths, proxy
from ..worker import Worker
from .player import PlayerWidget, fmt, fmt_simple
from .theme import S1, S2
from .waveform import WaveformWidget
from .widgets import Badge, Card, GhostButton, PrimaryButton, SecondaryButton, Section, Toggle, label

log = logging.getLogger(__name__)
STEP_S = 0.1
BIG_STEP_S = 0.5


def sync_quality(confidence: float) -> tuple[str, str, str]:
    """(parola, tipo di badge, spiegazione): il numero grezzo non si mostra, solo nel tooltip."""
    if confidence >= 15:
        return "Ottima", "ok", "Il programma è molto sicuro che voce e video coincidano."
    if confidence >= 7:
        return "Buona", "info", "Probabilmente è a posto: controlla guardando le labbra."
    return "Da controllare", "warn", "Il programma non è sicuro: guarda e ascolta con attenzione e correggi a mano."


def seconds_text(v: float) -> str:
    return f"{abs(v):.1f}".replace(".", ",") + (" secondi" if abs(v) != 1.0 else " secondo")


class ReviewPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker: Worker | None = None
        self._queued: tuple | None = None
        self._auto = 0.0
        self._n = 0
        self._wav = None
        main = QVBoxLayout(self)
        main.addWidget(label("Controlla il video", "title"))
        main.addWidget(label("Due controlli veloci: la voce deve coincidere con le labbra e bisogna scegliere dove "
                             "inizia e finisce la conferenza. Poi premi «Avanti».", "muted", True))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.player = PlayerWidget(state)
        ll.addWidget(self.player, 1)
        self.wave = WaveformWidget()
        ll.addWidget(self.wave)
        cap = label("Le due righe mostrano il suono della telecamera (blu) e quello della registrazione (arancione). "
                    "Se sono uguali una sopra l'altra, l'audio è sincronizzato. Clicca per spostarti; "
                    "trascina le barre verde (inizio) e rossa (fine).", "caption", True)
        ll.addWidget(cap)
        split.addWidget(left)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sa.setMinimumWidth(445)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(S2)
        sa.setWidget(right)
        split.addWidget(sa)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        split.setSizes([700, 440])
        main.addWidget(split, 1)

        # ---- 1. sincronia
        c1 = Card()
        c1.add(label("1. La voce coincide con le labbra?", "h2", True))
        row = QHBoxLayout()
        row.addWidget(label("Sincronizzazione:"))
        self.badge = Badge("—", "neutral")
        row.addWidget(self.badge)
        row.addStretch(1)
        c1.lay.addLayout(row)
        self.badge_txt = label("", "muted", True)
        c1.add(self.badge_txt)
        self.btn_watch = PrimaryButton("Guarda e ascolta 10 secondi", "play",
                                       "Riproduce 10 secondi dal punto attuale, con l'audio della registrazione")
        self.btn_watch.clicked.connect(lambda: self.player.play_for(10))
        c1.add(self.btn_watch)
        c1.add(label("Guarda chi parla: la voce deve coincidere con il movimento delle labbra.", "caption", True))
        c1.add(label("Se non coincide:", ""))
        r = QHBoxLayout()
        self.b_early = SecondaryButton("Anticipa la voce", "chevron-left",
                                       "Un clic = un decimo di secondo. Tieni premuto Maiusc per mezzo secondo.")
        self.b_late = SecondaryButton("Ritarda la voce", "chevron-right",
                                      "Un clic = un decimo di secondo. Tieni premuto Maiusc per mezzo secondo.")
        self.b_early.clicked.connect(lambda: self._nudge(-1))
        self.b_late.clicked.connect(lambda: self._nudge(+1))
        r.addWidget(self.b_early)
        r.addWidget(self.b_late)
        c1.lay.addLayout(r)
        c1.add(label("«Anticipa» se la voce arriva dopo le labbra; «Ritarda» se arriva prima.", "caption", True))
        self.shift_lbl = label("", "", True)
        c1.add(self.shift_lbl)
        rb = GhostButton("Ripristina il valore automatico", "rotate-ccw")
        rb.clicked.connect(self._reset_offset)
        c1.add(rb)
        self.sync_status = label("", "caption", True)
        c1.add(self.sync_status)
        sec = Section("Altre opzioni di sincronia", "review-sync-adv", opened=False)
        self.drift = Toggle("Correggi anche lo sfasamento che cresce col tempo")
        self.drift.toggled.connect(self._drift_toggled)
        sec.add(self.drift)
        self.drift_lbl = label("", "caption", True)
        sec.add(self.drift_lbl)
        f = sec.form()
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-36000, 36000)
        self.offset.setDecimals(3)
        self.offset.setSingleStep(0.05)
        self.offset.setSuffix(" s")
        self.offset.valueChanged.connect(self._offset_edited)
        f.addRow("Spostamento preciso", self.offset)
        b2 = SecondaryButton("Prova l'eco (10 secondi)", "headphones",
                             "Sovrappone l'audio della telecamera e quello registrato: se non sono allineati si sente l'eco")
        b2.clicked.connect(self.listen_sync)
        sec.add(b2)
        c1.add(sec)
        rl.addWidget(c1)

        # ---- 2. tagli
        c2 = Card()
        c2.add(label("2. Dove inizia e finisce la conferenza?", "h2", True))
        self.sugg = label("", "muted", True)
        c2.add(self.sugg)
        self.btn_use = PrimaryButton("Usa inizio e fine suggeriti", "check")
        self.btn_use.clicked.connect(self.apply_suggestion)
        c2.add(self.btn_use)
        self.btn_all = SecondaryButton("Non tagliare: tengo tutto", "film")
        self.btn_all.clicked.connect(self.keep_all)
        c2.add(self.btn_all)
        self.start_lbl, self.end_lbl = label("", ""), label("", "")
        for lab, name, goto, here in ((self.start_lbl, "Inizio", self._goto_start, self.set_start_here),
                                      (self.end_lbl, "Fine", self._goto_end, self.set_end_here)):
            c2.add(lab)
            rr = QHBoxLayout()
            g = SecondaryButton(f"Vai all'{name.lower()}" if name == "Inizio" else "Vai alla fine", None)
            g.clicked.connect(goto)
            h = SecondaryButton(f"{name} qui", "scissors", f"Imposta {'l’inizio' if name == 'Inizio' else 'la fine'} nel punto in cui si trova il video")
            h.clicked.connect(here)
            rr.addWidget(g)
            rr.addWidget(h)
            c2.lay.addLayout(rr)
        self.trim_status = label("", "", True)
        c2.add(self.trim_status)
        sec2 = Section("Scrivi i tempi a mano", "review-trim-adv", opened=False)
        f2 = sec2.form()
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for e in (self.start_edit, self.end_edit):
            e.setPlaceholderText("minuti:secondi, es. 12:30")
            e.editingFinished.connect(self._edit_markers)
        f2.addRow("Inizio", self.start_edit)
        f2.addRow("Fine", self.end_edit)
        c2.add(sec2)
        rl.addWidget(c2)

        self.warn = label("", "warn", True)
        rl.addWidget(self.warn)
        self.status = label("", "caption", True)
        rl.addWidget(self.status)
        rl.addStretch(1)

        self.player.positionChanged.connect(self._pos)
        self.player.windowNeeded.connect(self._need_window)
        self.wave.seek.connect(self.player.set_position)
        self.wave.markersChanged.connect(self._markers_from_wave)
        state.project_changed.connect(self.load)
        state.spec_changed.connect(self._slide_marks)
        self._offset_timer = QTimer(self)
        self._offset_timer.setSingleShot(True)
        self._offset_timer.setInterval(1200)
        self._offset_timer.timeout.connect(self.apply_offset)

    # ------------------------------------------------------------------ caricamento
    def load(self):
        st = self.state
        pr = st.project
        if not pr:
            return
        a, b = st.proxy_range
        self._auto = pr.effective_offset          # valore calcolato dal programma: «Ripristina» torna qui
        self.player.load(st.proxy, a, b - a, pr.total_duration)
        self.player.set_position(a)
        self.wave.set_data(st.cam, st.ext, pr.total_duration)
        self.wave.offset = pr.effective_offset
        self.wave.start, self.wave.end = pr.trim_start, pr.trim_end
        if pr.suggested_start is not None:
            self.wave.suggest = (pr.suggested_start, pr.suggested_end)
            self.sugg.setText(f"Il programma ha cercato quando si inizia a parlare. Suggerisce: inizio a "
                              f"{fmt_simple(pr.suggested_start)}, fine a {fmt_simple(pr.suggested_end)}. Controlla e conferma.")
            self.btn_use.setEnabled(True)
        else:
            self.wave.suggest = None
            self.sugg.setText("Non ho trovato un punto di inizio sicuro: scegli tu inizio e fine, oppure tieni tutto.")
            self.btn_use.setEnabled(False)
        word, kind, expl = sync_quality(pr.sync_confidence)
        self.badge.set(word, kind)
        self.badge.setToolTip(f"Valore tecnico: {pr.sync_confidence:.1f}")
        self.badge_txt.setText(expl)
        has_drift = pr.offset_corrected_s is not None and pr.drift_s is not None and abs(pr.drift_s) > 0.05
        self.drift.setVisible(has_drift)
        self.drift_lbl.setVisible(has_drift)
        if has_drift:
            self.drift_lbl.setText(f"Telecamera e registratore vanno a velocità leggermente diverse: alla fine la voce "
                                   f"è sfasata di circa {seconds_text(pr.drift_s)}. Attivando questa opzione il programma la corregge.")
        self.drift.blockSignals(True)
        self.drift.setChecked(pr.use_drift_correction)
        self.drift.blockSignals(False)
        self._refresh_shift()
        self.warn.setText("\n".join("⚠ " + w for w in st.warnings))
        self._refresh_trim()
        self._slide_marks()

    def _refresh_shift(self):
        pr = self.state.project
        v = pr.effective_offset
        self.offset.blockSignals(True)
        self.offset.setValue(v)
        self.offset.blockSignals(False)
        manual = abs(v - self._auto) > 0.0005
        self.shift_lbl.setText(f"Spostamento applicato: {seconds_text(v)}" + (" (modificato da te)" if manual else " (automatico)"))
        self.wave.offset = v
        self.wave.update()

    # ------------------------------------------------------------------ anteprima a finestre
    def _need_window(self, t: float):
        pr = self.state.project
        a, b = proxy.window_around(pr, t)
        self.player.set_message("Sto preparando l'anteprima di questo punto: ci vuole qualche secondo…")
        self._queue_job(("window", a, b, t))

    def _queue_job(self, job: tuple):
        if self.worker and self.worker.isRunning():
            self._queued = job
            return
        self._start_job(job)

    def _start_job(self, job: tuple):
        st = self.state
        pr = st.project
        self._n += 1
        out = paths.temp_dir() / f"win_{self._n}.mp4"
        kind, a, b, seek = job
        if kind == "window":
            fn = lambda c, r: proxy.build_window(pr, st.clips, a, b, out, lambda f, s: None, c)  # noqa: E731
        else:   # solo audio: il video dell'anteprima viene copiato
            src = st.proxy
            fn = lambda c, r: proxy.rebuild_audio(pr, src, out, a, b - a, c)  # noqa: E731
        self.worker = Worker(fn)
        self.worker.finished_ok.connect(lambda p, a=a, b=b, seek=seek: self._job_done(p, a, b, seek))
        self.worker.failed.connect(self._job_failed)
        self.worker.finished.connect(self._next_job)
        self.worker.start()

    def _job_done(self, path, a, b, seek):
        st = self.state
        old = st.proxy
        st.proxy, st.proxy_range, st.proxy_stale = path, (a, b), False
        self.player.load(path, a, b - a, st.project.total_duration)
        self.player.set_position(seek if seek is not None else a)
        self.sync_status.setText("Audio aggiornato: premi «Guarda e ascolta» per controllare.")
        self.status.setText("")
        try:
            if old and old != path:
                old.unlink(missing_ok=True)
        except OSError:
            pass

    def _job_failed(self, msg: str):
        log.error("Anteprima non riuscita: %s", msg)
        self.player.set_message("Non sono riuscito a preparare l'anteprima di questo punto. Riprova o scegli un altro punto.")

    def _next_job(self):
        if self._queued:
            job, self._queued = self._queued, None
            self._start_job(job)

    # ------------------------------------------------------------------ sincronia
    def _pos(self, t: float):
        self.wave.pos = t
        self.wave.update()

    def _nudge(self, sign: int):
        big = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
        self._set_offset(self.state.project.effective_offset + sign * (BIG_STEP_S if big else STEP_S))

    def _offset_edited(self, v: float):
        self._set_offset(v, from_spin=True)

    def _set_offset(self, v: float, from_spin: bool = False):
        pr = self.state.project
        if pr.use_drift_correction:
            pr.offset_corrected_s = v
        else:
            pr.offset_s = v
        self._refresh_shift()
        self.state.proxy_stale = True
        self.sync_status.setText("Sto aggiornando l'audio dell'anteprima: tra un attimo potrai riascoltare.")
        self._offset_timer.start()

    def _reset_offset(self):
        self._set_offset(self._auto)

    def _drift_toggled(self, on: bool):
        pr = self.state.project
        pr.use_drift_correction = on
        self._auto = pr.effective_offset
        self._refresh_shift()
        self.state.proxy_stale = True
        self._offset_timer.start()

    def apply_offset(self):
        st = self.state
        if not st.proxy or not st.project:
            return
        a, b = st.proxy_range
        pos = self.player.position()
        self.sync_status.setText("Aggiorno l'audio dell'anteprima…")
        self._queue_job(("audio", a, b, pos))

    def listen_sync(self):
        st = self.state
        out = paths.temp_dir() / "sync_listen.wav"
        self.status.setText("Preparo l'ascolto…")
        center = self.player.position()
        w = Worker(lambda c, r: proxy.sync_preview(st.project, st.clips, center, out))
        w.finished_ok.connect(self._play_wav)
        w.failed.connect(lambda m: self.status.setText(f"Non riesco a preparare l'ascolto: {m}"))
        self._eco_worker = w
        w.start()

    def _play_wav(self, path):
        self.player.player.pause()
        self._wav = QMediaPlayer(self)
        self._wav_out = QAudioOutput(self)
        self._wav.setAudioOutput(self._wav_out)
        self._wav.setSource(QUrl.fromLocalFile(str(path)))
        self._wav.play()
        self.status.setText("Ascolta: se senti l'eco, voce e registrazione non sono allineate.")

    # ------------------------------------------------------------------ tagli
    def _refresh_trim(self):
        pr = self.state.project
        s, e = pr.trim_start, pr.trim_end
        self.start_lbl.setText(f"Inizio: {fmt_simple(s)}" if s is not None else "Inizio: dall'inizio del video")
        self.end_lbl.setText(f"Fine: {fmt_simple(e)}" if e is not None else "Fine: fino alla fine del video")
        if s is None and e is None:
            self.trim_status.setText("Taglio non ancora scelto: se non fai nulla, il video resta intero.")
            self.trim_status.setProperty("role", "muted")
        else:
            self.trim_status.setText("✓ Taglio scelto. Puoi cambiarlo trascinando le barre sulla forma d'onda.")
            self.trim_status.setProperty("role", "ok")
        self.trim_status.style().unpolish(self.trim_status)
        self.trim_status.style().polish(self.trim_status)
        self.start_edit.setText(fmt_simple(s) if s is not None else "")
        self.end_edit.setText(fmt_simple(e) if e is not None else "")
        self.wave.start, self.wave.end = s, e
        self.wave.update()

    @staticmethod
    def _parse(text: str) -> float | None:
        try:
            t = 0.0
            for x in text.strip().replace(",", ".").split(":"):
                t = t * 60 + float(x)
            return t
        except ValueError:
            return None

    def _edit_markers(self):
        self.wave.start, self.wave.end = self._parse(self.start_edit.text()), self._parse(self.end_edit.text())
        self._markers_from_wave(from_edit=True)

    def _markers_from_wave(self, from_edit: bool = False):
        pr = self.state.project
        pr.trim_start, pr.trim_end = self.wave.start, self.wave.end
        if not from_edit:
            self._refresh_trim()
        self.state.spec_changed.emit()

    def set_start_here(self):
        self.wave.start = self.player.position()
        self._markers_from_wave()

    def set_end_here(self):
        self.wave.end = self.player.position()
        self._markers_from_wave()

    def _goto_start(self):
        if self.wave.start is not None:
            self.player.set_position(self.wave.start)

    def _goto_end(self):
        if self.wave.end is not None:
            self.player.set_position(max(0.0, self.wave.end - 10))

    def apply_suggestion(self):
        pr = self.state.project
        if pr and pr.suggested_start is not None:
            self.wave.start, self.wave.end = pr.suggested_start, pr.suggested_end
            self._markers_from_wave()

    def keep_all(self):
        self.wave.start = self.wave.end = None
        self._markers_from_wave()

    def _slide_marks(self):
        st = self.state
        self.wave.marks = [st.from_out(c.t) for c in st.spec.slides.changes] if st.spec.slides.enabled else []
        self.wave.update()

    # ------------------------------------------------------------------ tastiera
    def keyPressEvent(self, e):
        k, mod = e.key(), e.modifiers()
        if k in (Qt.Key_Space, Qt.Key_K):
            self.player.toggle()
        elif k == Qt.Key_Left:
            self.player.step(-1.0 if mod & Qt.ShiftModifier else -0.04)
        elif k == Qt.Key_Right:
            self.player.step(1.0 if mod & Qt.ShiftModifier else 0.04)
        elif k == Qt.Key_J:
            self.player.step(-5.0)
        elif k == Qt.Key_L:
            self.player.step(5.0)
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
        self.status.setText(f"Cambio slide {nxt + 1} segnato a {fmt_simple(t)}")
