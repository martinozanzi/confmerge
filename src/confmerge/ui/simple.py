"""Modalità Semplice: da cartella a video pronto in 3 passi, senza termini tecnici.

È una vista sullo stesso AppState e sugli stessi controller della modalità Avanzata."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QScrollArea, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from ..queue import DONE, FAILED
from ..render.model import VARIABLES
from ..spec import RenderSpec
from .canvas import Canvas
from .controllers import fmt_dur
from .export_page import start_export
from .player import PlayerWidget, fmt_simple
from .review_page import PreviewBinder, SyncPanel, TrimPanel
from .theme import S1, S2, S3, S4, pixmap, theme
from .thumbnail_dialog import ThumbnailDialog
from .waveform import WaveformWidget
from .widgets import (Card, DropZone, GhostButton, LinkButton, PrimaryButton, ProgressBarThin, ProgressRing, SecondaryButton,
                      StepIndicator, Toggle, label)
from .widgets.anim import fade_in, stagger_cards

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre"]
STEPS = ["Cartella", "Controlla", "Esporta"]


def italian_date(dt) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}"


def used_variables(spec: RenderSpec) -> list[str]:
    """Segnaposto ({titolo}, {relatore}…) davvero usati dal profilo: sono gli unici campi da mostrare."""
    gr = spec.graphics
    texts = [e.text for e in gr.elements + gr.title.elements + gr.outro.elements if e.kind == "text"]
    texts += [t for lt in gr.lower_thirds for t in (lt.name, lt.role)]
    return [k for k in VARIABLES if any("{" + k + "}" in t for t in texts)]


# ------------------------------------------------------------------------------------------------------------ 1. cartella
class SimpleStart(QWidget):
    started = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.runner = state.analysis
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)
        # --- scelta
        pick = QWidget()
        pl = QVBoxLayout(pick)
        pl.setAlignment(Qt.AlignCenter)
        self.drop = DropZone("Trascina qui la cartella della conferenza",
                             "Dentro devono esserci i video della telecamera e la registrazione audio.", "Sfoglia…")
        self.drop.setMinimumHeight(300)
        self.drop.setMinimumWidth(620)
        self.drop.setMaximumWidth(820)
        self.drop.dropped.connect(self._dropped)
        self.drop.browse.connect(self.browse)
        pl.addWidget(self.drop, 0, Qt.AlignHCenter)
        self.problem = label("", "warn", True)
        self.problem.setAlignment(Qt.AlignCenter)
        self.problem.setMinimumWidth(480)
        self.problem.setMaximumWidth(760)
        pl.addWidget(self.problem, 0, Qt.AlignHCenter)
        self.audio_btn = SecondaryButton("Scegli la registrazione audio…", "headphones")
        self.audio_btn.clicked.connect(self._pick_audio)
        self.audio_btn.setVisible(False)
        pl.addWidget(self.audio_btn, 0, Qt.AlignHCenter)
        self.recent_box = QWidget()
        self.recent_lay = QVBoxLayout(self.recent_box)
        self.recent_lay.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.recent_box, 0, Qt.AlignHCenter)
        self.stack.addWidget(pick)
        # --- avanzamento
        work = QWidget()
        wl = QVBoxLayout(work)
        wl.setAlignment(Qt.AlignCenter)
        wl.addWidget(label("Un attimo, sto preparando tutto", "title"), 0, Qt.AlignHCenter)
        self.ring = ProgressRing(150)
        wl.addWidget(self.ring, 0, Qt.AlignHCenter)
        self.msg = label("Guardo i video…", "h2")
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setMinimumWidth(360)
        wl.addWidget(self.msg, 0, Qt.AlignHCenter)
        self.found = label("", "muted", True)
        self.found.setAlignment(Qt.AlignCenter)
        self.found.setMinimumWidth(480)
        wl.addWidget(self.found, 0, Qt.AlignHCenter)
        self.order_note = label("", "warn", True)
        self.order_note.setAlignment(Qt.AlignCenter)
        self.order_note.setMinimumWidth(480)
        self.order_note.setMaximumWidth(700)
        wl.addWidget(self.order_note, 0, Qt.AlignHCenter)
        cancel = GhostButton("Annulla", "x")
        cancel.clicked.connect(self.runner.cancel)
        wl.addWidget(cancel, 0, Qt.AlignHCenter)
        self.stack.addWidget(work)
        self.runner.progress.connect(self._progress)
        self.runner.failed.connect(self._failed)
        self.runner.cancelled.connect(lambda: self._back_to_pick(""))
        self.runner.finished.connect(lambda: self._back_to_pick(""))
        self.render_recent()

    def render_recent(self):
        while self.recent_lay.count():
            it = self.recent_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        recents = [r for r in self.state.settings.data.get("recent_folders", []) if Path(r).is_dir()][:5]
        self.recent_box.setVisible(bool(recents))
        if recents:
            self.recent_lay.addWidget(label("Ultime cartelle usate", "caption"), 0, Qt.AlignHCenter)
            for r in recents:
                b = LinkButton(Path(r).name or r, r)
                b.clicked.connect(lambda _=False, rr=r: self.use_folder(Path(rr)))
                self.recent_lay.addWidget(b, 0, Qt.AlignHCenter)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella della conferenza", self.state.settings.data.get("last_folder", ""))
        if d:
            self.use_folder(Path(d))

    def _dropped(self, items):
        folder = next((p for p in items if p.is_dir()), None)
        if folder:
            self.use_folder(folder)
        elif items:
            self.use_folder(items[0].parent)

    def use_folder(self, folder: Path):
        m = self.state.sources
        self.problem.setText("")
        self.audio_btn.setVisible(False)
        try:
            m.clear()
            m.load_folder(folder)
        except Exception as e:  # noqa: BLE001
            self.problem.setText(f"Non riesco a leggere questa cartella: {e}")
            return
        s = self.state.settings
        s.data["last_folder"] = str(folder)
        rec = [r for r in s.data.get("recent_folders", []) if r != str(folder)]
        s.data["recent_folders"] = [str(folder)] + rec[:4]
        s.save()
        self.render_recent()
        if not m.videos:
            self.problem.setText("In questa cartella non ho trovato video (file .mp4 o .mov). Prova con un'altra cartella.")
            return
        if not m.audio:
            self.problem.setText("Ho trovato i video ma non la registrazione audio (mp3, wav, m4a…). Scegli il file qui sotto.")
            self.audio_btn.setVisible(True)
            return
        self.begin()

    def _pick_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "Registrazione audio", str(self.state.sources.folder or ""),
                                           "Audio (*.mp3 *.wav *.ogg *.m4a *.flac)")
        if f:
            self.state.sources.set_audio(Path(f))
            self.problem.setText("")
            self.audio_btn.setVisible(False)
            self.begin()

    def begin(self):
        m = self.state.sources
        n = len(m.videos)
        self.found.setText(f"Ho trovato {n} video e la registrazione «{m.audio.name}»."
                           + (f" Ci sono anche {len(m.slides)} file di slide." if m.slides else ""))
        notes = [w for w in m.warnings() if "ordine" in w.lower() or "date" in w.lower()]
        self.order_note.setText(("⚠ " + notes[0] + " Se non è giusto, scegli «Più opzioni»." if notes else ""))
        self.order_note.setVisible(bool(notes))
        self.ring.setValue(0)
        self.msg.setText("Guardo i video…")
        self.stack.setCurrentIndex(1)
        self.started.emit()
        self.runner.start(list(m.videos), m.audio, list(m.slides))

    def _progress(self, f: float, m: str):
        self.ring.setValue(f)
        if m:
            self.msg.setText(m)

    def _failed(self, msg: str):
        self._back_to_pick("Non sono riuscito a preparare questa conferenza. Controlla che i file si aprano con un lettore "
                           "video, poi riprova. (Il dettaglio è nel file di log: menu Aiuto.)")

    def _back_to_pick(self, text: str):
        self.stack.setCurrentIndex(0)
        if text:
            self.problem.setText(text)

    def reset(self):
        self.stack.setCurrentIndex(0)
        self.problem.setText("")
        self.audio_btn.setVisible(False)
        self.render_recent()


# ------------------------------------------------------------------------------------------------------------ 2. controlla
class SimpleCheck(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        main = QVBoxLayout(self)
        main.addWidget(label("Controlla", "title"))
        main.addWidget(label("Guarda il video, controlla che voce e labbra coincidano e conferma dove inizia e finisce "
                             "la conferenza.", "muted", True))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.player = PlayerWidget(state)
        ll.addWidget(self.player, 1)
        self.wave = WaveformWidget()
        self.wave.setMinimumHeight(100)
        ll.addWidget(self.wave)
        ll.addWidget(label("Le barre verde e rossa sono l'inizio e la fine. Puoi trascinarle.", "caption", True))
        split.addWidget(left)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sa.setMinimumWidth(475)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(S2)
        self.sync = SyncPanel(state, self.player, simple=True)
        self.trim = TrimPanel(state, self.player, self.wave, simple=True)
        rl.addWidget(self.sync)
        rl.addWidget(self.trim)
        rl.addWidget(self._profile_card())
        rl.addStretch(1)
        sa.setWidget(right)
        split.addWidget(sa)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        split.setSizes([620, 480])
        main.addWidget(split, 1)
        self.binder = PreviewBinder(state, self.player, self.wave)
        state.project_changed.connect(self._on_project)
        state.profile_changed.connect(self._build_fields)
        state.spec_changed.connect(self._refresh_previews)

    # --- scheda profilo: titolo, logo finale e testi da compilare
    def _profile_card(self) -> Card:
        c = Card()
        c.add(label("Titolo e grafica", "h2", True))
        row = QHBoxLayout()
        row.addWidget(label("Profilo:"))
        self.profile = QComboBox()
        self.profile.setMinimumWidth(180)
        self.profile.currentTextChanged.connect(self._profile_picked)
        row.addWidget(self.profile, 1)
        c.lay.addLayout(row)
        c.add(label("Il profilo decide titolo iniziale, logo, scritte e credito.", "caption", True))
        pv = QHBoxLayout()
        self.prev_title = self._mini_canvas("title")
        self.prev_outro = self._mini_canvas("outro")
        for cap, cv in (("Titolo iniziale", self.prev_title), ("Schermata finale", self.prev_outro)):
            col = QVBoxLayout()
            col.addWidget(cv)
            col.addWidget(label(cap, "caption"))
            pv.addLayout(col)
        c.lay.addLayout(pv)
        self.fields_box = QWidget()
        self.fields_lay = QVBoxLayout(self.fields_box)
        self.fields_lay.setContentsMargins(0, 0, 0, 0)
        c.add(self.fields_box)
        self._fields: dict[str, QLineEdit] = {}
        return c

    def _mini_canvas(self, which: str) -> Canvas:
        cv = Canvas(self.state)
        cv.mode = "scene"
        cv.scene_target = which
        cv.fixed_size = (1280, 720)
        cv.setMinimumSize(190, 107)
        cv.setProperty("which", which)
        return cv

    def _refresh_previews(self):
        gr = self.state.spec.graphics
        for cv, sc in ((self.prev_title, gr.title), (self.prev_outro, gr.outro)):
            cv.scene = sc
            cv.seg_dur = max(sc.duration, 0.1)
            cv.out_t = min(1.2, sc.duration)
            cv.update()
            cv.setToolTip("" if sc.enabled else "Questo profilo non ha questa schermata.")

    def _fill_profiles(self):
        names = self.state.settings.list_profiles()
        if self.state.profile_name not in names:
            names.append(self.state.profile_name)
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItems(names)
        self.profile.setCurrentText(self.state.profile_name)
        self.profile.blockSignals(False)

    def _profile_picked(self, name: str):
        if name and name != self.state.profile_name:
            self.state.apply_profile(name)

    def _build_fields(self):
        self._fill_profiles()
        while self.fields_lay.count():
            it = self.fields_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._fields = {}
        used = used_variables(self.state.spec)
        if not used:
            self.fields_lay.addWidget(label("Questo profilo non ha testi da compilare.", "caption", True))
        for k in used:
            self.fields_lay.addWidget(label(VARIABLES[k]))
            e = QLineEdit(self.state.spec.variables.get(k, ""))
            e.setPlaceholderText({"titolo": "es. Convegno sul futuro della città", "relatore": "es. Mario Rossi",
                                  "ruolo": "es. Sindaco", "data": "es. 12 maggio 2026"}[k])
            e.textChanged.connect(lambda t, kk=k: self._set_var(kk, t))
            self.fields_lay.addWidget(e)
            self._fields[k] = e
        self._refresh_previews()

    def _set_var(self, k: str, text: str):
        self.state.spec.variables[k] = text
        self.state.touch()

    def _on_project(self):
        st = self.state
        if st.clips and not st.spec.variables.get("data") and st.clips[0].creation_time:
            st.spec.variables["data"] = italian_date(st.clips[0].creation_time.astimezone())
        self._build_fields()

    def showEvent(self, e):
        super().showEvent(e)
        self._build_fields()          # allinea campi e anteprime a ciò che è stato cambiato nell'altra modalità


# ------------------------------------------------------------------------------------------------------------ 3. esporta
QUALITIES = [
    ("recommended", "Consigliata per YouTube", "Ottima qualità e dimensione ragionevole. È la scelta giusta quasi sempre.", "sparkles"),
    ("fast", "Più veloce", "Si prepara prima. L'immagine è un po' meno definita.", "zap"),
    ("max", "Massima qualità", "File più grande e tempi più lunghi.", "film"),
]


def apply_quality(state, key: str) -> None:
    ex = state.spec.export
    src_h = max((min(c.width, c.height) for c in state.clips), default=1080)
    ex.crf_mode, ex.bitrate_mbps, ex.encoder = False, None, "auto"
    if key == "fast":
        ex.preset, ex.custom_height, ex.bitrate_mbps = "Personalizzato", 720, 4.0
    elif key == "max":
        ex.preset = "YouTube 4K" if src_h >= 2160 else "YouTube 1440p" if src_h >= 1440 else "YouTube 1080p"
        ex.crf_mode, ex.crf = True, 16
    else:
        ex.preset = "YouTube 1080p"
    state.touch()


def current_quality(state) -> str:
    ex = state.spec.export
    if ex.preset == "Personalizzato" and ex.custom_height <= 720:
        return "fast"
    if ex.crf_mode and ex.crf <= 17:
        return "max"
    return "recommended"


class QualityCard(Card):
    clicked = Signal(str)

    def __init__(self, key, title, desc, icon, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.ic = QLabel()
        self.ic.setFixedHeight(32)
        self._icon = icon
        self.lay.addWidget(self.ic)
        self.lay.addWidget(label(title, "h2", True))
        self.lay.addWidget(label(desc, "muted", True))
        self.set_selected(False)
        theme.changed.connect(lambda: self.set_selected(self._sel))

    def set_selected(self, on: bool):
        self._sel = on
        t = theme.t
        self.setStyleSheet(f"QFrame#Card {{ border: 2px solid {t.accent if on else t.border}; }}"
                           f"QFrame#Card:focus {{ border: 2px dashed {t.accent}; }}")
        self.ic.setPixmap(pixmap(self._icon, t.accent if on else t.text2, 28))

    def mousePressEvent(self, e):
        self.clicked.emit(self.key)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.key)
        else:
            super().keyPressEvent(e)


class SimpleExport(QWidget):
    newProject = Signal()

    def __init__(self, state, check_page: SimpleCheck, parent=None):
        super().__init__(parent)
        self.state, self.check = state, check_page
        self.ctl = state.export
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)
        self.stack.addWidget(self._options())
        self.stack.addWidget(self._working())
        self.stack.addWidget(self._done())
        self.ctl.estimateStarted.connect(self._est_started)
        self.ctl.estimateReady.connect(self._est_ready)
        self.ctl.estimateFailed.connect(lambda m: self.est_big.setText("Non riesco a calcolare la durata"))
        self.ctl.progress.connect(self._progress)
        self.ctl.finished.connect(self._finished)
        self.ctl.powerRequested.connect(lambda a: None)
        state.spec_changed.connect(self.ctl.request_estimate)
        state.project_changed.connect(self._on_project)
        self._last_item = None

    # --- opzioni
    def _options(self) -> QWidget:
        w = QWidget()
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        sa.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setSpacing(S2)
        lay.addWidget(label("Esporta", "title"))
        lay.addWidget(label("Scegli la qualità e premi «Esporta»: il programma prepara il video pronto da caricare su YouTube.",
                            "muted", True))
        row = QHBoxLayout()
        row.setSpacing(S2)
        self.q_cards: dict[str, QualityCard] = {}
        for key, title, desc, icon in QUALITIES:
            qc = QualityCard(key, title, desc, icon)
            qc.clicked.connect(self._choose)
            row.addWidget(qc)
            self.q_cards[key] = qc
        lay.addLayout(row)
        opts = Card()
        self.loud = Toggle("Volume uniforme per YouTube")
        self.loud.setChecked(self.state.spec.audio.loudnorm)
        self.loud.toggled.connect(lambda on: (setattr(self.state.spec.audio, "loudnorm", on), self.state.touch()))
        opts.add(self.loud)
        opts.add(label("La voce avrà sempre un livello giusto: né troppo bassa né troppo alta.", "caption", True))
        r = QHBoxLayout()
        r.addWidget(label("Dove salvarlo:"))
        self.dir_edit = QLineEdit(self.state.spec.export.out_dir)
        self.dir_edit.textChanged.connect(lambda t: (setattr(self.state.spec.export, "out_dir", t), self.ctl.request_estimate()))
        r.addWidget(self.dir_edit, 1)
        b = SecondaryButton("Cambia…", "folder-open")
        b.clicked.connect(self._pick_dir)
        r.addWidget(b)
        opts.lay.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(label("Nome del video:"))
        self.name_edit = QLineEdit(self.state.spec.export.name)
        self.name_edit.textChanged.connect(lambda t: setattr(self.state.spec.export, "name", t))
        r.addWidget(self.name_edit, 1)
        opts.lay.addLayout(r)
        lay.addWidget(opts)
        est = Card()
        est.add(label("Quanto ci vuole e quanto pesa", "h2", True))
        self.est_big = label("calcolo in corso…", "h2", True)
        est.add(self.est_big)
        self.est_small = label("", "caption", True)
        est.add(self.est_small)
        self.est_warn = label("", "warn", True)
        est.add(self.est_warn)
        lay.addWidget(est)
        lay.addStretch(1)
        wl = QVBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(sa)
        return w

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Dove salvare il video", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _choose(self, key: str):
        apply_quality(self.state, key)
        self._mark(key)

    def _mark(self, key: str):
        for k, c in self.q_cards.items():
            c.set_selected(k == key)

    def _on_project(self):
        pr = self.state.project
        if not pr:
            return
        if not self.dir_edit.text():
            self.dir_edit.setText(str(Path(pr.clips[0]).parent))
        if self.state.spec.export.name in ("", "conferenza"):
            self.name_edit.setText(Path(pr.clips[0]).parent.name or "conferenza")
        self.loud.setChecked(self.state.spec.audio.loudnorm)
        self._mark(current_quality(self.state))

    def showEvent(self, e):
        super().showEvent(e)
        self.ctl.active = True
        self._mark(current_quality(self.state))
        self.loud.setChecked(self.state.spec.audio.loudnorm)
        self.ctl.run_estimate()
        stagger_cards(self)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.ctl.active = False

    def _est_started(self):
        q = self.ctl.quick_size()
        prev = self.ctl.est
        self.est_big.setText("Calcolo in corso…" + (f" (circa {q})" if q else ""))
        self.est_small.setText("Sto facendo una prova veloce per stimare i tempi sul tuo computer."
                               if not prev else "Aggiorno la stima…")

    def _est_ready(self, est):
        self.est_big.setText(f"{est.time_text}, {est.size_text}")
        self.est_small.setText("Il tempo dipende dal computer. La dimensione è " + ("approssimativa." if est.approximate else "precisa."))
        self.est_warn.setText("\n".join("⚠ " + w for w in self.ctl.warnings()))

    def _export(self):
        item = start_export(self, self.ctl, self.state, True)
        if item:
            self._last_item = item
            self.ring.setValue(0)
            self.work_msg.setText("Sto creando il video…")
            self.work_sub.setText("Puoi lasciare il computer acceso: non serve fare altro.")
            self.stack.setCurrentIndex(1)

    # --- in corso
    def _working(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(label("Sto creando il tuo video", "title"), 0, Qt.AlignHCenter)
        self.ring = ProgressRing(170)
        lay.addWidget(self.ring, 0, Qt.AlignHCenter)
        self.work_msg = label("Sto creando il video…", "h2")
        self.work_msg.setAlignment(Qt.AlignCenter)
        self.work_msg.setMinimumWidth(360)
        lay.addWidget(self.work_msg, 0, Qt.AlignHCenter)
        self.work_sub = label("", "muted", True)
        self.work_sub.setAlignment(Qt.AlignCenter)
        self.work_sub.setMinimumWidth(420)
        lay.addWidget(self.work_sub, 0, Qt.AlignHCenter)
        c = GhostButton("Annulla", "x")
        c.clicked.connect(lambda: self.ctl.cancel(self.state.queue.items.index(self._last_item)) if self._last_item else None)
        lay.addWidget(c, 0, Qt.AlignHCenter)
        return w

    def _progress(self, item, frac, remaining, size):
        self.ring.setValue(frac)
        self.work_sub.setText(("Mancano circa " + fmt_dur(remaining) + ". " if remaining is not None else "Sto calcolando il tempo che manca… ")
                              + f"Finora il file pesa {size / 1e6:.0f} MB.")

    # --- finito
    def _done(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        self.done_icon = QLabel()
        self.done_icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.done_icon, 0, Qt.AlignHCenter)
        self.done_title = label("Il video è pronto!", "title")
        lay.addWidget(self.done_title, 0, Qt.AlignHCenter)
        self.done_info = label("", "muted", True)
        self.done_info.setAlignment(Qt.AlignCenter)
        self.done_info.setMinimumWidth(480)
        lay.addWidget(self.done_info, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        row.setAlignment(Qt.AlignCenter)
        for text, icon, fn in (("Apri la cartella", "folder-open", self._open_folder), ("Guarda il video", "play", self._open_video),
                               ("Crea la miniatura", "image", self._thumb)):
            b = SecondaryButton(text, icon)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        nb = PrimaryButton("Nuovo progetto", "plus")
        nb.clicked.connect(self.newProject)
        lay.addWidget(nb, 0, Qt.AlignHCenter)
        self.retry = SecondaryButton("Riprova", "rotate-cw")
        self.retry.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.retry.setVisible(False)
        lay.addWidget(self.retry, 0, Qt.AlignHCenter)
        return w

    def _finished(self, results):
        mine = [(it, rep) for it, rep in results if it is self._last_item]
        if not mine:
            return
        it, rep = mine[-1]
        ok = it.status == DONE
        self.done_icon.setPixmap(pixmap("circle-check" if ok else "circle-x", theme.t.success if ok else theme.t.error, 72))
        self.retry.setVisible(not ok)
        if ok:
            self.done_title.setText("Il video è pronto!")
            self.done_info.setText(f"{it.path}\n" + (f"Ci sono voluti {fmt_dur(rep.wall_s)} e il file pesa {rep.size_bytes / 1e6:.0f} MB." if rep else ""))
        else:
            self.done_title.setText("Non è riuscito")
            self.done_info.setText("Qualcosa è andato storto durante la creazione del video. Puoi riprovare; se succede ancora, "
                                   "usa il menu Aiuto → Copia informazioni per l'assistenza.")
        self.stack.setCurrentIndex(2)

    def _open_folder(self):
        if self._last_item:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._last_item.path).parent)))

    def _open_video(self):
        if self._last_item:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_item.path)))

    def _thumb(self):
        if self._last_item and self.state.project:
            p = Path(self._last_item.path)
            ThumbnailDialog(self.state, p.parent, p.stem, self.check.player.position, self).exec()

    def reset(self):
        self.stack.setCurrentIndex(0)


# ------------------------------------------------------------------------------------------------------------ guscio
class SimpleShell(QWidget):
    moreOptions = Signal()
    newProject = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 12, 24, 12)
        top = QHBoxLayout()
        self.steps = StepIndicator(STEPS)
        self.steps.setMaximumWidth(620)
        top.addStretch(1)
        top.addWidget(self.steps, 3)
        top.addStretch(1)
        more = LinkButton("Più opzioni", "Passa alla modalità Avanzata con lo stesso progetto")
        more.clicked.connect(self.moreOptions)
        top.addWidget(more)
        lay.addLayout(top)
        self.stack = QStackedWidget()
        self.start = SimpleStart(state)
        self.check = SimpleCheck(state)
        self.export = SimpleExport(state, self.check)
        for w in (self.start, self.check, self.export):
            self.stack.addWidget(w)
        lay.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.back = SecondaryButton("Indietro", "chevron-left")
        self.next = PrimaryButton("Avanti", "chevron-right")
        self.hint = label("", "caption", True)
        self.back.clicked.connect(self.go_back)
        self.next.clicked.connect(self.go_next)
        nav.addWidget(self.back)
        nav.addWidget(self.hint, 1)
        nav.addWidget(self.next)
        lay.addLayout(nav)
        state.analysis.finished.connect(lambda: self.show_step(1))
        state.review.trimChanged.connect(self._gate)
        state.project_changed.connect(self._gate)
        self.export.newProject.connect(self.newProject)
        self.export.stack.currentChanged.connect(lambda _: self._gate())
        self.show_step(0, animate=False)

    @property
    def step(self) -> int:
        return self.stack.currentIndex()

    def show_step(self, i: int, animate: bool = True) -> None:
        self.stack.setCurrentIndex(i)
        self.steps.set_state(i)
        self.back.setVisible(i in (1, 2))
        self.next.setVisible(i in (1, 2))
        self.next.setText("Esporta il video" if i == 2 else "Avanti")
        self.next.set_icon("download" if i == 2 else "chevron-right")
        self.next.setMinimumHeight(48 if i == 2 else 0)
        self._gate()
        if animate:
            fade_in(self.stack.currentWidget(), slide=12)
            QTimer.singleShot(60, lambda: stagger_cards(self.stack.currentWidget()))
        if i == 0:
            self.start.render_recent()

    def _gate(self):
        pr = self.state.project
        ok = bool(pr and pr.trim_confirmed)
        if self.step == 2:
            self.next.setVisible(self.export.stack.currentIndex() == 0)
            self.next.setEnabled(True)
            self.hint.setText("")
            return
        self.next.setEnabled(ok)
        self.hint.setText("" if self.step != 1 or ok else "Per andare avanti, conferma prima inizio e fine (nel riquadro «Dove inizia e finisce»).")

    def go_back(self):
        if self.step == 2:
            self.export.reset()
        self.show_step(max(0, self.step - 1))

    def go_next(self):
        if self.step == 1 and self.next.isEnabled():
            self.show_step(2)
        elif self.step == 2:
            self.export._export()

    def reset(self):
        self.start.reset()
        self.export.reset()
        self.show_step(0)
