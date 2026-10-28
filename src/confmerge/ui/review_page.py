"""«Controlla il video»: sincronia e tagli. Pannelli riutilizzati da entrambe le modalità; la logica sta in ReviewController."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QHBoxLayout, QLineEdit, QScrollArea, QSplitter, QVBoxLayout, QWidget

from .. import paths, proxy
from ..worker import Worker
from .controllers import seconds_text, sync_quality
from .player import PlayerWidget, fmt_simple
from .theme import S1, S2
from .waveform import WaveformWidget
from .widgets import (Badge, Card, GhostButton, LinkButton, PrimaryButton, SecondaryButton, Section, Toggle, label)

log = logging.getLogger(__name__)


class PreviewBinder(QObject):
    """Collega un player + una forma d'onda al ReviewController (ogni modalità ha i suoi, il controller è uno)."""

    def __init__(self, state, player: PlayerWidget, wave: WaveformWidget, parent=None):
        super().__init__(parent)
        self.state, self.player, self.wave = state, player, wave
        self.ctl = state.review
        state.project_changed.connect(self.load)
        self.ctl.windowReady.connect(self._window_ready)
        self.ctl.message.connect(player.set_message)
        self.ctl.syncChanged.connect(self._sync_changed)
        self.ctl.trimChanged.connect(self._trim_changed)
        player.windowNeeded.connect(self.ctl.need_window)
        player.positionChanged.connect(self._pos)
        wave.seek.connect(player.set_position)
        wave.markersChanged.connect(lambda: self.ctl.set_trim(wave.start, wave.end))
        state.spec_changed.connect(self._slide_marks)

    def load(self):
        st = self.state
        pr = st.project
        if not pr or not st.proxy:
            return
        a, b = st.proxy_range
        self.player.load(st.proxy, a, b - a, pr.total_duration)
        self.player.set_position(a)
        self.wave.set_data(st.cam, st.ext, pr.total_duration)
        self.wave.offset = pr.effective_offset
        self.wave.start, self.wave.end = pr.trim_start, pr.trim_end
        self.wave.suggest = (pr.suggested_start, pr.suggested_end) if pr.suggested_start is not None else None
        self.wave.update()
        self._slide_marks()

    def _window_ready(self, path, a, b, seek):
        st = self.state
        pos = self.player.position() if seek is None else seek
        self.player.load(path, a, b - a, st.project.total_duration)
        self.player.set_position(pos if pos is not None else a)

    def _pos(self, t: float):
        self.wave.pos = t
        self.wave.update()

    def _sync_changed(self):
        self.wave.offset = self.state.project.effective_offset
        self.wave.update()

    def _trim_changed(self):
        pr = self.state.project
        self.wave.start, self.wave.end = pr.trim_start, pr.trim_end
        self.wave.update()

    def _slide_marks(self):
        st = self.state
        self.wave.marks = [st.from_out(c.t) for c in st.spec.slides.changes] if st.spec.slides.enabled else []
        self.wave.update()


# ------------------------------------------------------------------------------------------------------------ pannelli
class SyncPanel(Card):
    """1. La voce coincide con le labbra? (in modalità Semplice le frecce sono nascoste dietro «Correggi»)."""

    def __init__(self, state, player: PlayerWidget, simple: bool = False, parent=None):
        super().__init__(parent)
        self.state, self.player, self.simple = state, player, simple
        self.ctl = state.review
        self.add(label("La voce coincide con le labbra?" if simple else "1. La voce coincide con le labbra?", "h2", True))
        row = QHBoxLayout()
        row.addWidget(label("Sincronizzazione:"))
        self.badge = Badge("—", "neutral")
        row.addWidget(self.badge)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.badge_txt = label("", "muted", True)
        self.add(self.badge_txt)
        self.btn_watch = PrimaryButton("Ascolta 10 secondi" if simple else "Guarda e ascolta 10 secondi", "play",
                                       "Riproduce 10 secondi dal punto attuale, con l'audio della registrazione")
        self.btn_watch.clicked.connect(lambda: self.player.play_for(10))
        self.add(self.btn_watch)
        self.add(label("Guarda chi parla: la voce deve coincidere con il movimento delle labbra.", "caption", True))
        self.fix_box = QWidget()
        fb = QVBoxLayout(self.fix_box)
        fb.setContentsMargins(0, 0, 0, 0)
        fb.setSpacing(S2)
        fb.addWidget(label("Se non coincide:"))
        r = QHBoxLayout()
        tip = "Un clic = un decimo di secondo. Tieni premuto Maiusc per mezzo secondo."
        self.b_early = SecondaryButton("Anticipa la voce", "chevron-left", tip)
        self.b_late = SecondaryButton("Ritarda la voce", "chevron-right", tip)
        self.b_early.clicked.connect(lambda: self._nudge(-1))
        self.b_late.clicked.connect(lambda: self._nudge(+1))
        r.addWidget(self.b_early)
        r.addWidget(self.b_late)
        fb.addLayout(r)
        fb.addWidget(label("«Anticipa» se la voce arriva dopo le labbra; «Ritarda» se arriva prima.", "caption", True))
        self.shift_lbl = label("", "", True)
        fb.addWidget(self.shift_lbl)
        rb = GhostButton("Ripristina il valore automatico", "rotate-ccw")
        rb.clicked.connect(lambda: self.ctl.reset_offset(self.player.position()))
        fb.addWidget(rb)
        self.add(self.fix_box)
        self.fix_link = LinkButton("Non coincide? Correggi")
        self.fix_link.clicked.connect(lambda: self.fix_box.setVisible(not self.fix_box.isVisible()))
        self.add(self.fix_link)
        self.drift = Toggle("Correggi anche lo sfasamento che cresce col tempo")
        self.drift.toggled.connect(lambda on: self.ctl.set_drift(on, self.player.position()))
        self.add(self.drift)
        self.drift_lbl = label("", "caption", True)
        self.add(self.drift_lbl)
        self.status = label("", "caption", True)
        self.add(self.status)
        if not simple:
            sec = Section("Altre opzioni di sincronia", "review-sync-adv", opened=False)
            f = sec.form()
            self.offset = QDoubleSpinBox()
            self.offset.setRange(-36000, 36000)
            self.offset.setDecimals(3)
            self.offset.setSingleStep(0.05)
            self.offset.setSuffix(" s")
            self.offset.valueChanged.connect(lambda v: self.ctl.set_offset(v, self.player.position()))
            f.addRow("Spostamento preciso", self.offset)
            b2 = SecondaryButton("Prova l'eco (10 secondi)", "headphones",
                                 "Sovrappone l'audio della telecamera e quello registrato: se non sono allineati si sente l'eco")
            b2.clicked.connect(self.listen_sync)
            sec.add(b2)
            self.add(sec)
        self.fix_box.setVisible(not simple)
        self.fix_link.setVisible(simple)
        self._wav = None
        state.project_changed.connect(self.refresh)
        self.ctl.syncChanged.connect(self.refresh_shift)
        self.ctl.message.connect(self.status.setText)

    def _nudge(self, sign: int):
        self.ctl.nudge(sign, bool(QApplication.keyboardModifiers() & Qt.ShiftModifier), self.player.position())

    def refresh(self):
        pr = self.state.project
        if not pr:
            return
        word, kind, expl = sync_quality(pr.sync_confidence)
        self.badge.set(word, kind)
        self.badge.setToolTip(f"Valore tecnico: {pr.sync_confidence:.1f}")
        self.badge_txt.setText(expl)
        has = self.ctl.has_drift()
        self.drift.setVisible(has)
        self.drift_lbl.setVisible(has)
        if has:
            self.drift_lbl.setText("Telecamera e registratore vanno a velocità leggermente diverse: alla fine la voce è "
                                   f"sfasata di circa {seconds_text(pr.drift_s)}. Attivando questa opzione il programma la corregge.")
        self.drift.blockSignals(True)
        self.drift.setChecked(pr.use_drift_correction)
        self.drift.blockSignals(False)
        if pr.sync_confidence < 7 and self.simple:
            self.fix_box.setVisible(True)
        self.refresh_shift()

    def refresh_shift(self):
        pr = self.state.project
        if not pr:
            return
        v = pr.effective_offset
        self.shift_lbl.setText(f"Spostamento applicato: {seconds_text(v)}"
                               + (" (modificato da te)" if self.ctl.offset_is_manual() else " (automatico)"))
        if hasattr(self, "offset"):
            self.offset.blockSignals(True)
            self.offset.setValue(v)
            self.offset.blockSignals(False)

    def listen_sync(self):
        st = self.state
        out = paths.temp_dir() / "sync_listen.wav"
        self.status.setText("Preparo l'ascolto…")
        center = self.player.position()
        w = Worker(lambda c, r: proxy.sync_preview(st.project, st.clips, center, out))
        w.finished_ok.connect(self._play_wav)
        w.failed.connect(lambda m: self.status.setText(f"Non riesco a preparare l'ascolto: {m}"))
        self._eco = w
        w.start()

    def _play_wav(self, path):
        self.player.player.pause()
        self._wav = QMediaPlayer(self)
        self._wav_out = QAudioOutput(self)
        self._wav.setAudioOutput(self._wav_out)
        self._wav.setSource(QUrl.fromLocalFile(str(path)))
        self._wav.play()
        self.status.setText("Ascolta: se senti l'eco, voce e registrazione non sono allineate.")


class TrimPanel(Card):
    """2. Dove inizia e finisce la conferenza? Il taglio non viene applicato senza conferma esplicita."""

    def __init__(self, state, player: PlayerWidget, wave: WaveformWidget, simple: bool = False, parent=None):
        super().__init__(parent)
        self.state, self.player, self.wave, self.simple = state, player, wave, simple
        self.ctl = state.review
        self.add(label("Dove inizia e finisce la conferenza?" if simple else "2. Dove inizia e finisce la conferenza?", "h2", True))
        self.sugg = label("", "muted", True)
        self.add(self.sugg)
        self.btn_use = PrimaryButton("Usa inizio e fine suggeriti", "check")
        self.btn_use.clicked.connect(self.ctl.apply_suggestion)
        self.add(self.btn_use)
        self.btn_all = SecondaryButton("Non tagliare: tengo tutto", "film")
        self.btn_all.clicked.connect(self.ctl.keep_all)
        self.add(self.btn_all)
        self.start_lbl, self.end_lbl = label("", ""), label("", "")
        for lab, name, goto, here in ((self.start_lbl, "Inizio", self._goto_start, self.set_start_here),
                                      (self.end_lbl, "Fine", self._goto_end, self.set_end_here)):
            self.add(lab)
            rr = QHBoxLayout()
            g = SecondaryButton("Vai all'inizio" if name == "Inizio" else "Vai alla fine", None)
            g.clicked.connect(goto)
            h = SecondaryButton(f"{name} qui", "scissors",
                                f"Imposta {'l’inizio' if name == 'Inizio' else 'la fine'} nel punto in cui si trova il video")
            h.clicked.connect(here)
            rr.addWidget(g)
            rr.addWidget(h)
            self.lay.addLayout(rr)
        self.status = label("", "", True)
        self.add(self.status)
        sec = Section("Scrivi i tempi a mano", "review-trim-adv", opened=False)
        f2 = sec.form()
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for e in (self.start_edit, self.end_edit):
            e.setPlaceholderText("minuti:secondi, es. 12:30")
            e.editingFinished.connect(self._edit_markers)
        f2.addRow("Inizio", self.start_edit)
        f2.addRow("Fine", self.end_edit)
        self.add(sec)
        state.project_changed.connect(self.refresh)
        self.ctl.trimChanged.connect(self.refresh_trim)

    def refresh(self):
        pr = self.state.project
        if not pr:
            return
        if pr.suggested_start is not None:
            self.sugg.setText("Il programma ha cercato quando si inizia a parlare. Suggerisce: inizio a "
                              f"{fmt_simple(pr.suggested_start)}, fine a {fmt_simple(pr.suggested_end)}. Controlla e conferma.")
        else:
            self.sugg.setText("Non ho trovato un punto di inizio sicuro: scegli tu inizio e fine, oppure tieni tutto.")
        self.btn_use.setEnabled(pr.suggested_start is not None)
        self.refresh_trim()

    def refresh_trim(self):
        pr = self.state.project
        s, e = pr.trim_start, pr.trim_end
        self.start_lbl.setText(f"Inizio: {fmt_simple(s)}" if s is not None else "Inizio: dall'inizio del video")
        self.end_lbl.setText(f"Fine: {fmt_simple(e)}" if e is not None else "Fine: fino alla fine del video")
        if pr.trim_confirmed:
            self.status.setText("✓ Taglio confermato. Puoi cambiarlo trascinando le barre sulla forma d'onda."
                                if (s is not None or e is not None) else "✓ Tengo il video intero.")
            role = "ok"
        else:
            self.status.setText("Taglio non ancora confermato: scegli «Usa inizio e fine suggeriti» o «Non tagliare».")
            role = "warn"
        self.status.setProperty("role", role)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.start_edit.setText(fmt_simple(s) if s is not None else "")
        self.end_edit.setText(fmt_simple(e) if e is not None else "")

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
        self.ctl.set_trim(self._parse(self.start_edit.text()), self._parse(self.end_edit.text()))

    def set_start_here(self):
        self.ctl.set_trim(self.player.position(), self.state.project.trim_end)

    def set_end_here(self):
        self.ctl.set_trim(self.state.project.trim_start, self.player.position())

    def _goto_start(self):
        s = self.state.project.trim_start
        if s is not None:
            self.player.set_position(s)

    def _goto_end(self):
        e = self.state.project.trim_end
        if e is not None:
            self.player.set_position(max(0.0, e - 10))


WAVE_CAPTION = ("Le due righe mostrano il suono della telecamera (blu) e quello della registrazione (arancione). "
                "Se sono uguali una sopra l'altra, l'audio è sincronizzato. Clicca per spostarti; "
                "trascina le barre verde (inizio) e rossa (fine).")


class ReviewPage(QWidget):
    """Modalità Avanzata: anteprima a sinistra, pannelli a destra."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        main = QVBoxLayout(self)
        main.setSpacing(6)
        main.addWidget(label("Due controlli veloci: la voce deve coincidere con le labbra e bisogna scegliere dove "
                             "inizia e finisce la conferenza.", "caption", True))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.player = PlayerWidget(state)
        ll.addWidget(self.player, 1)
        self.wave = WaveformWidget()
        ll.addWidget(self.wave)
        ll.addWidget(label(WAVE_CAPTION, "caption", True))
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
        self.sync = SyncPanel(state, self.player)
        self.trim = TrimPanel(state, self.player, self.wave)
        rl.addWidget(self.sync)
        rl.addWidget(self.trim)
        self.warn = label("", "warn", True)
        rl.addWidget(self.warn)
        rl.addStretch(1)
        split.addWidget(sa)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        split.setSizes([700, 440])
        main.addWidget(split, 1)
        self.binder = PreviewBinder(state, self.player, self.wave)
        state.project_changed.connect(lambda: self.warn.setText("\n".join("⚠ " + w for w in state.warnings)))

    # compatibilità: schermate e test usano questi metodi
    def apply_suggestion(self):
        self.state.review.apply_suggestion()

    def set_start_here(self):
        self.trim.set_start_here()

    def set_end_here(self):
        self.trim.set_end_here()

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
            self.trim.set_start_here()
        elif k == Qt.Key_O:
            self.trim.set_end_here()
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
