"""Studio Social: quattro passi guidati. Video → Taglia → Aspetto → Esporta."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QSlider, QSplitter, QStackedWidget, QVBoxLayout,
                               QWidget)

from .. import platforms as PF
from ..media_scan import VIDEO_EXT
from .cut_waveform import CutWaveform, fmt_clock
from .brand_card import BrandCard
from .graphics_page import scrolled
from .music_card import MusicCard
from .player import PlayerWidget
from .social_style import OverlaysCard, StyleTemplateCard
from .subtitles_tab import SimpleSubtitlesCard
from .theme import S2
from .widgets import (Card, DropZone, GhostButton, LinkButton, PrimaryButton, ProgressBarThin, SecondaryButton, Segmented,
                      StepIndicator, Toggle, label)
from .widgets.anim import fade_in, stagger_cards

STEPS = ["Video", "Taglia", "Aspetto", "Esporta"]
ZONE_COLORS = {"youtube": "#3B82F6", "shorts": "#EF4444", "reels": "#D946EF", "tiktok": "#22D3EE", "threads": "#F59E0B",
               "instagram": "#84CC16", "x": "#94A3B8"}
SENSITIVITY = [("Delicata", (45.0, 1.0)), ("Normale", (35.0, 0.7)), ("Decisa", (25.0, 0.45))]


def mmss(t: float) -> str:
    t = int(round(max(0.0, t)))
    return f"{t // 60}:{t % 60:02d}"


def video_files(items) -> list[Path]:
    out: list[Path] = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            out += sorted((f for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT))
        elif p.suffix.lower() in VIDEO_EXT:
            out.append(p)
    return out


# ------------------------------------------------------------------------------------------------------------ 1. video
class SocialStart(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.ctl = state.social
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)
        pick = QWidget()
        pl = QVBoxLayout(pick)
        pl.setAlignment(Qt.AlignCenter)
        self.drop = DropZone("Trascina qui i tuoi video",
                             "Uno o più file (mp4, mov…). Se sono più di uno li metto uno dopo l'altro.", "Scegli i video…")
        self.drop.setMinimumSize(620, 300)
        self.drop.setMaximumWidth(820)
        self.drop.dropped.connect(self._dropped)
        self.drop.browse.connect(self.browse)
        pl.addWidget(self.drop, 0, Qt.AlignHCenter)
        self.problem = label("", "warn", True)
        self.problem.setAlignment(Qt.AlignCenter)
        self.problem.setMinimumWidth(480)
        pl.addWidget(self.problem, 0, Qt.AlignHCenter)
        howto = label("Poi togli le pause, scegli dove pubblicare e il programma prepara una versione per ogni "
                      "piattaforma.", "muted", True)
        howto.setMinimumWidth(560)
        howto.setMinimumHeight(40)
        howto.setAlignment(Qt.AlignCenter)
        pl.addWidget(howto, 0, Qt.AlignHCenter)
        self.stack.addWidget(pick)
        work = QWidget()
        wl = QVBoxLayout(work)
        wl.setAlignment(Qt.AlignCenter)
        wl.addWidget(label("Un attimo, preparo i video", "title"), 0, Qt.AlignHCenter)
        self.bar = ProgressBarThin()
        self.bar.setMinimumWidth(420)
        wl.addWidget(self.bar, 0, Qt.AlignHCenter)
        self.msg = label("Leggo i video…", "h2")
        self.msg.setAlignment(Qt.AlignCenter)
        wl.addWidget(self.msg, 0, Qt.AlignHCenter)
        cancel = GhostButton("Annulla", "x")
        cancel.clicked.connect(self.ctl.cancel)
        wl.addWidget(cancel, 0, Qt.AlignHCenter)
        self.stack.addWidget(work)
        self.ctl.progress.connect(lambda f, m: (self.bar.setValue(f), self.msg.setText(m)))
        self.ctl.failed.connect(self._failed)
        self.ctl.cancelled.connect(lambda: self.stack.setCurrentIndex(0))
        self.ctl.finished.connect(lambda: self.stack.setCurrentIndex(0))

    def browse(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Scegli i video", "", "Video (*.mp4 *.mov *.m4v)")
        if files:
            self.start(files)

    def _dropped(self, items):
        files = video_files(items)
        if not files:
            self.problem.setText("Non ho trovato video: trascina file mp4 o mov.")
            return
        self.start(files)

    def start(self, files):
        from .. import social
        files = social.sort_by_name([Path(f) for f in files]) if len(files) > 1 else [Path(files[0])]
        self.problem.setText("")
        self.stack.setCurrentIndex(1)
        self.bar.setValue(0)
        self.ctl.load(files)

    def _failed(self, msg: str):
        self.stack.setCurrentIndex(0)
        self.problem.setText(msg)

    def reset(self):
        self.stack.setCurrentIndex(0)
        self.problem.setText("")


# ------------------------------------------------------------------------------------------------------------ 2. taglia
class SocialCut(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.ctl = state.social
        main = QVBoxLayout(self)
        main.addWidget(label("Taglia", "title"))
        main.addWidget(label("Togli le pause e gli errori. Quello che togli resta scuro sulla forma d'onda e viene saltato.",
                             "muted", True))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.player = PlayerWidget(state)
        self.player.canvas.mode = "crop"
        ll.addWidget(self.player, 1)
        self.wave = CutWaveform()
        ll.addWidget(self.wave)
        row = QHBoxLayout()
        self.sel_lbl = label("Trascina sulla forma d'onda per scegliere una parte. La rotellina ingrandisce.", "caption", True)
        row.addWidget(self.sel_lbl, 1)
        self.all_btn = GhostButton("Mostra tutto")
        self.all_btn.clicked.connect(self.wave.zoom_all)
        row.addWidget(self.all_btn)
        ll.addLayout(row)
        split.addWidget(left)
        panel = self._panel()
        sa = scrolled(panel)
        sa.setMinimumWidth(max(400, panel.minimumSizeHint().width() + 30))     # mai una barra orizzontale, anche con testo grande
        split.addWidget(sa)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        split.setSizes([700, 420])
        main.addWidget(split, 1)
        # collegamenti
        self.wave.seek.connect(self.player.set_position)
        self.wave.selectionChanged.connect(self._sel_changed)
        self.player.positionChanged.connect(self._pos)
        state.cuts_changed.connect(self.refresh)
        state.profile_changed.connect(self.refresh)
        self.ctl.finished.connect(self._loaded)
        QShortcut(QKeySequence.Delete, self, activated=self.remove_selection, context=Qt.WidgetWithChildrenShortcut)
        self._sel: tuple[float, float] | None = None
        self.refresh()

    def _panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(S2)
        c = Card()
        c.add(label("Togli i silenzi", "h2", True))
        c.add(label("Il programma trova le pause e le toglie, lasciando un po' di margine prima e dopo il parlato.",
                    "caption", True))
        self.sens = Segmented([(n, i) for i, (n, _) in enumerate(SENSITIVITY)])
        self.sens.changed.connect(self._sens)
        c.add(self.sens)
        self.found = label("", "caption", True)
        c.add(self.found)
        r = QHBoxLayout()
        self.sil_btn = PrimaryButton("Togli i silenzi", "sparkles")
        self.sil_btn.clicked.connect(self.remove_silences)
        r.addWidget(self.sil_btn)
        r.addStretch(1)
        c.lay.addLayout(r)
        lay.addWidget(c)
        c2 = Card()
        c2.add(label("Taglia a mano", "h2", True))
        c2.add(label("Scegli una parte sulla forma d'onda (trascinando) e poi:", "caption", True))
        self.sel_info = label("Nessuna parte scelta.", "", True)
        c2.add(self.sel_info)
        r2 = QHBoxLayout()
        self.rm_btn = SecondaryButton("Togli", "trash-2", "Togli la parte scelta (scorciatoia: Canc)")
        self.rm_btn.clicked.connect(self.remove_selection)
        self.rs_btn = SecondaryButton("Rimetti", "rotate-ccw", "Rimetti la parte scelta")
        self.rs_btn.clicked.connect(self.restore_selection)
        self.play_btn = SecondaryButton("Ascolta", "play", "Ascolta la parte scelta")
        self.play_btn.clicked.connect(self.play_selection)
        for b in (self.rm_btn, self.rs_btn, self.play_btn):
            r2.addWidget(b)
        r2.addStretch(1)
        c2.lay.addLayout(r2)
        lay.addWidget(c2)
        c3 = Card()
        c3.add(label("Risultato", "h2", True))
        self.summary = label("", "", True)
        c3.add(self.summary)
        r3 = QHBoxLayout()
        self.reset_btn = GhostButton("Rimetti tutto", "rotate-ccw")
        self.reset_btn.clicked.connect(self.ctl.reset)
        r3.addWidget(self.reset_btn)
        r3.addStretch(1)
        c3.lay.addLayout(r3)
        lay.addWidget(c3)
        lay.addStretch(1)
        self.sens.setValue(1)
        return w

    # --- dati
    def _loaded(self):
        st = self.state
        pr = st.project
        if not pr:
            return
        self.player.load(st.proxy, 0.0, pr.total_duration, pr.total_duration)
        ref = st.clips[0]
        self.player.canvas.fixed_size = (ref.width, ref.height)
        self.wave.set_data(st.cam, 8000, pr.total_duration)
        self.player.set_position(0.0)
        self.refresh()

    def refresh(self):
        st = self.state
        pr = st.project
        self.wave.set_removed(self.ctl.removed())
        if not pr:
            self.summary.setText("")
            return
        total, kept = pr.total_duration, self.ctl.kept_seconds()
        gone = total - kept
        self.summary.setText(f"Durata finale: {mmss(kept)}" + (f"  (tolti {mmss(gone)} su {mmss(total)})" if gone > 0.5 else
                                                                 "  (non hai ancora tolto niente)"))
        self.reset_btn.setEnabled(bool(pr.keep))
        n, secs = self.ctl.preview_silences()
        self.found.setText(f"Con questa sensibilità trovo {n} pause, circa {mmss(secs)} da togliere." if n else
                           "Con questa sensibilità non trovo pause da togliere: prova «Decisa».")
        self.sil_btn.setEnabled(n > 0)

    def _sens(self, i):
        db, mn = SENSITIVITY[int(i)][1]
        so = self.state.spec.social
        so.skip_silence_db, so.skip_silence_min = db, mn
        self.refresh()

    # --- azioni
    def remove_silences(self):
        n, secs = self.ctl.remove_silences()
        self.found.setText(f"Tolte {n} pause ({mmss(secs)}). Puoi annullare con «Indietro» in alto." if n else "")

    def _sel_changed(self, sel):
        self._sel = sel
        on = sel is not None
        for b in (self.rm_btn, self.rs_btn, self.play_btn):
            b.setEnabled(on)
        self.sel_info.setText(f"Parte scelta: da {fmt_clock(sel[0])} a {fmt_clock(sel[1])} ({sel[1] - sel[0]:.1f} s)."
                              if on else "Nessuna parte scelta.")

    def remove_selection(self):
        if self._sel:
            self.ctl.remove(*self._sel)
            self.wave.clear_selection()

    def restore_selection(self):
        if self._sel:
            self.ctl.restore(*self._sel)
            self.wave.clear_selection()

    def play_selection(self):
        if self._sel:
            self.player.play_range(self._sel[0])
            self.player.play_for(min(self._sel[1] - self._sel[0], 30.0))

    def _pos(self, t: float):
        self.wave.set_pos(t)
        if self.player.player.playbackState() == QMediaPlayer.PlayingState:
            for a, b in self.ctl.removed():             # in riproduzione le parti tolte si saltano
                if a <= t < b - 0.05:
                    self.player.set_position(b)
                    break


# ------------------------------------------------------------------------------------------------------------ 3. aspetto
class SocialLook(QWidget):
    def __init__(self, state, open_settings=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.root = state.settings.root
        self._hidden: set[str] = set()
        main = QVBoxLayout(self)
        main.addWidget(label("Aspetto", "title"))
        main.addWidget(label("Scegli dove pubblicare e come entra l'immagine. Le zone rosse sono coperte dall'app: "
                             "tieni lì dentro i testi importanti.", "muted", True))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.player = PlayerWidget(state)
        ll.addWidget(self.player, 1)
        row = QHBoxLayout()
        row.addWidget(label("Anteprima per:"))
        self.prev_box = QComboBox()
        self.prev_box.currentIndexChanged.connect(self._preview_changed)
        row.addWidget(self.prev_box, 1)
        ll.addLayout(row)
        split.addWidget(left)
        panel = QWidget()
        pl = QVBoxLayout(panel)
        pl.setSpacing(S2)
        # piattaforme
        self.plat_card = Card()
        self.plat_card.add(label("Dove lo pubblichi", "h2", True))
        self.toggles: dict[str, Toggle] = {}
        for p in PF.all_platforms(self.root):
            t = Toggle(f"{p.name}   ·   {p.aspect}")
            t.setToolTip(p.note)
            t.toggled.connect(lambda on, pid=p.id: self._toggle(pid, on))
            self.toggles[p.id] = t
            self.plat_card.add(t)
        self.warn = label("", "warn", True)
        self.plat_card.add(self.warn)
        pl.addWidget(self.plat_card)
        # inquadratura
        self.fr_card = Card()
        self.fr_card.add(label("Inquadratura", "h2", True))
        self.fr_card.add(label("Il tuo video è orizzontale: come lo metto nel formato verticale?", "caption", True))
        self.fr_mode = Segmented([("Riempi", "fill"), ("Sfocato", "blur"), ("Bande", "bars")])
        self.fr_mode.changed.connect(self._frame_mode)
        self.fr_card.add(self.fr_mode)
        self.fr_note = label("", "caption", True)
        self.fr_card.add(self.fr_note)
        self.fr_pos = QSlider(Qt.Horizontal)
        self.fr_pos.setRange(0, 100)
        self.fr_pos.valueChanged.connect(self._frame_pos)
        self.fr_pos_lbl = label("Sposta l'inquadratura a sinistra o a destra:", "caption", True)
        self.fr_card.add(self.fr_pos_lbl)
        self.fr_card.add(self.fr_pos)
        pl.addWidget(self.fr_card)
        self.safe = Toggle("Mostra le zone coperte dall'app")
        self.safe.toggled.connect(self._safe)
        sc = Card()
        sc.add(self.safe)
        self.legend_box = QWidget()
        self.legend_lay = QVBoxLayout(self.legend_box)
        self.legend_lay.setContentsMargins(0, 0, 0, 0)
        sc.add(self.legend_box)
        sc.add(label("Ogni piattaforma ha la sua zona colorata (la loro interfaccia copre quelle parti). La linea verde è "
                     "l'area sicura per tutte: tieni lì dentro i testi importanti.", "caption", True))
        pl.addWidget(sc)
        pl.addWidget(StyleTemplateCard(state))
        pl.addWidget(BrandCard(state))
        pl.addWidget(OverlaysCard(state))
        pl.addWidget(SimpleSubtitlesCard(state, open_settings))
        pl.addWidget(MusicCard(state))
        pl.addStretch(1)
        sa = scrolled(panel)
        sa.setMinimumWidth(max(400, panel.minimumSizeHint().width() + 30))
        split.addWidget(sa)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        split.setSizes([620, 460])
        main.addWidget(split, 1)
        state.profile_changed.connect(self.sync)
        state.social.finished.connect(self._loaded)
        self.sync()

    def selected(self) -> list[PF.Platform]:
        ids = self.state.spec.social.platforms
        return [p for p in PF.all_platforms(self.root) if p.id in ids]

    def _loaded(self):
        st = self.state
        if st.proxy and st.project:
            self.player.load(st.proxy, 0.0, st.project.total_duration, st.project.total_duration)
            self.player.set_position(0.0)
        self.sync()

    def sync(self):
        so = self.state.spec.social
        for pid, t in self.toggles.items():
            t.blockSignals(True)
            t.setChecked(pid in so.platforms)
            t.blockSignals(False)
        cur = self.prev_box.currentData()
        self.prev_box.blockSignals(True)
        self.prev_box.clear()
        for p in self.selected():
            self.prev_box.addItem(f"{p.name} ({p.aspect})", p.id)
        i = self.prev_box.findData(cur)
        self.prev_box.setCurrentIndex(max(0, i))
        self.prev_box.blockSignals(False)
        self.safe.blockSignals(True)
        self.safe.setChecked(so.show_safe)
        self.safe.blockSignals(False)
        self._preview_changed()

    def _toggle(self, pid: str, on: bool):
        so = self.state.spec.social
        ids = [x for x in so.platforms if x != pid] + ([pid] if on else [])
        if not ids:                                    # almeno una piattaforma
            self.toggles[pid].blockSignals(True)
            self.toggles[pid].setChecked(True)
            self.toggles[pid].blockSignals(False)
            return
        so.platforms = [p.id for p in PF.all_platforms(self.root) if p.id in ids]
        self.state.touch()
        self.sync()

    def _current(self) -> PF.Platform | None:
        pid = self.prev_box.currentData()
        sel = self.selected()
        return next((p for p in sel if p.id == pid), sel[0] if sel else None)

    def _preview_changed(self, *_):
        p = self._current()
        if p is None:
            return
        st = self.state
        st.spec.image.aspect = p.aspect                 # l'anteprima mostra il formato scelto
        st.spec.export.preset, st.spec.export.custom_height = "Personalizzato", p.short
        same_aspect = [q for q in self.selected() if q.aspect == p.aspect]
        safe = PF.common_safe(same_aspect)
        st.spec.brand.safe = list(safe)                  # loghi e testi stanno sempre dentro la zona non coperta dall'app
        self._legend(same_aspect)
        shown = [q for q in same_aspect if q.id not in self._hidden and any(q.safe)]
        cv = self.player.canvas
        cv.safe_zones = [{"name": q.name, "color": ZONE_COLORS.get(q.id, "#EF4444"), "safe": q.safe}
                         for q in shown] if st.spec.social.show_safe else []
        cv.safe_common = PF.common_safe(shown)
        self.player.canvas.update()
        # inquadratura: serve solo se il video non ha già il formato scelto
        ref = st.clips[0] if st.clips else None
        differs = bool(ref) and abs(ref.width / max(ref.height, 1) - _ratio(p.aspect)) > 0.02
        self.fr_card.setVisible(differs)
        im = st.spec.image
        self.fr_mode.setValue(im.reframe)
        self.fr_pos.blockSignals(True)
        self.fr_pos.setValue(int(im.reframe_x * 100))
        self.fr_pos.blockSignals(False)
        self._frame_ui()
        durs = [PF.duration_warning(q, self.state.social.kept_seconds()) for q in self.selected()]
        self.warn.setText("\n".join(d for d in durs if d))
        self.warn.setVisible(any(durs))
        st.touch()

    def _frame_ui(self):
        mode = self.state.spec.image.reframe
        self.fr_pos.setVisible(mode == "fill")
        self.fr_pos_lbl.setVisible(mode == "fill")
        self.fr_note.setText({"fill": "Riempie tutto lo schermo: si perdono i lati.",
                              "blur": "Si vede tutto il video, con uno sfondo sfocato sopra e sotto.",
                              "bars": "Si vede tutto il video, con bande nere sopra e sotto."}[mode])

    def _frame_mode(self, v):
        self.state.spec.image.reframe = v
        self._frame_ui()
        self.state.touch()
        self.player.canvas.update()

    def _frame_pos(self, v: int):
        self.state.spec.image.reframe_x = v / 100
        self.state.touch()
        self.player.canvas.update()

    def _legend(self, plats):
        """Una riga per piattaforma con il suo colore: si può accendere o spegnere la sua zona nell'anteprima."""
        while self.legend_lay.count():
            it = self.legend_lay.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for q in plats:
            if not any(q.safe):
                continue
            col = ZONE_COLORS.get(q.id, "#EF4444")
            t = Toggle(f"{q.name}")
            t.setStyleSheet(f"QCheckBox {{ color: {col}; font-weight: 600; }}")
            t.setChecked(q.id not in self._hidden)
            t.toggled.connect(lambda on, pid=q.id: self._zone_toggle(pid, on))
            self.legend_lay.addWidget(t)

    def _zone_toggle(self, pid: str, on: bool):
        self._hidden.discard(pid) if on else self._hidden.add(pid)
        self._preview_changed()

    def _safe(self, on: bool):
        self.state.spec.social.show_safe = on
        self._preview_changed()


def _ratio(aspect: str) -> float:
    a, b = aspect.split(":")
    return float(a) / float(b)


# ------------------------------------------------------------------------------------------------------------ 4. esporta
class SocialExport(QWidget):
    newProject = Signal()

    def __init__(self, state, pos_fn=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.pos_fn = pos_fn or (lambda: state.trim_start)
        self.ctl = state.export
        self.root = state.settings.root
        lay = QVBoxLayout(self)
        lay.addWidget(label("Esporta", "title"))
        self.summary = label("", "muted", True)
        lay.addWidget(self.summary)
        self.list_card = Card()
        lay.addWidget(self.list_card)
        opts = Card()
        r = QHBoxLayout()
        r.addWidget(label("Dove salvarli:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.textChanged.connect(lambda t: setattr(self.state.spec.export, "out_dir", t))
        r.addWidget(self.dir_edit, 1)
        b = SecondaryButton("Cambia…", "folder-open")
        b.clicked.connect(self._pick_dir)
        r.addWidget(b)
        opts.lay.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(label("Nome:"))
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(lambda t: setattr(self.state.spec.export, "name", t))
        r.addWidget(self.name_edit, 1)
        opts.lay.addLayout(r)
        lay.addWidget(opts)
        self.go = PrimaryButton("Esporta i video", "download")
        self.go.setMinimumHeight(48)
        self.go.clicked.connect(self.start)
        gr = QHBoxLayout()
        gr.addWidget(self.go)
        self.thumb_btn = SecondaryButton("Miniatura YouTube…", "image", "Crea la miniatura con titolo, colori e loghi del marchio")
        self.thumb_btn.clicked.connect(self._thumb)
        gr.addWidget(self.thumb_btn)
        gr.addStretch(1)
        lay.addLayout(gr)
        self.run_card = Card()
        self.run_lay = self.run_card.lay
        self.run_card.setVisible(False)
        lay.addWidget(self.run_card)
        self.done_lbl = label("", "h2", True)
        self.open_btn = SecondaryButton("Apri la cartella", "folder-open")
        self.open_btn.clicked.connect(self._open)
        self.new_btn = SecondaryButton("Nuovo lavoro", "plus")
        self.new_btn.clicked.connect(self.newProject)
        self.done_box = Card()
        self.done_box.add(self.done_lbl)
        rr = QHBoxLayout()
        rr.addWidget(self.open_btn)
        rr.addWidget(self.new_btn)
        rr.addStretch(1)
        self.done_box.lay.addLayout(rr)
        self.done_box.setVisible(False)
        lay.addWidget(self.done_box)
        lay.addStretch(1)
        self.rows: dict[int, tuple[object, ProgressBarThin]] = {}
        self._items: list = []
        self.ctl.queueChanged.connect(self._queue)
        self.ctl.finished.connect(self._finished)

    def selected(self) -> list[PF.Platform]:
        ids = self.state.spec.social.platforms
        return [p for p in PF.all_platforms(self.root) if p.id in ids]

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def refresh(self):
        st = self.state
        if not st.project or self.ctl.running:
            return
        ex = st.spec.export
        if not ex.name or ex.name == "conferenza":
            ex.name = Path(st.project.clips[0]).stem
        self.dir_edit.blockSignals(True)
        self.dir_edit.setText(ex.out_dir or str(Path(st.project.clips[0]).parent))
        self.dir_edit.blockSignals(False)
        ex.out_dir = self.dir_edit.text()
        self.name_edit.blockSignals(True)
        self.name_edit.setText(ex.name)
        self.name_edit.blockSignals(False)
        kept = st.social.kept_seconds()
        sel = self.selected()
        self.summary.setText(f"Durata del video: {mmss(kept)}. Preparo {len(sel)} "
                             + ("versione" if len(sel) == 1 else "versioni") + " dallo stesso lavoro.")
        while self.list_card.lay.count():
            it = self.list_card.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.list_card.add(label("Verranno creati", "h2", True))
        for p in sel:
            w, h = _size(p)
            self.list_card.add(label(f"{p.name}  ·  {w}×{h}", "", True))
            warn = PF.duration_warning(p, kept)
            if warn:
                self.list_card.add(label(warn, "warn", True))
        self.go.setText(f"Esporta {len(sel)} " + ("video" if len(sel) == 1 else "video"))
        self.go.setEnabled(bool(sel))

    def _thumb(self):
        from .thumbnail_dialog import ThumbnailDialog
        if self.state.project:
            ThumbnailDialog(self.state, Path(self.dir_edit.text() or "."), self.name_edit.text() or "video", self.pos_fn,
                            self).exec()

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella di destinazione", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def start(self):
        st = self.state
        self.done_box.setVisible(False)
        self._items = []
        for p in self.selected():
            spec = PF.variant_spec(st.spec, p)
            prep = self.ctl.prepare_social(spec, p.id)
            if prep is None:
                continue
            self._items.append(self.ctl.enqueue(prep))
        if not self._items:
            return
        self._build_rows()
        self.go.setEnabled(False)
        self.ctl.start_queue()

    def _build_rows(self):
        while self.run_lay.count():
            it = self.run_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.run_card.setVisible(True)
        self.run_lay.addWidget(label("Sto preparando i video…", "h2"))
        self.rows.clear()
        self.row_lbls = {}
        for it in self._items:
            lbl = label(it.name, "", True)
            bar = ProgressBarThin()
            self.run_lay.addWidget(lbl)
            self.run_lay.addWidget(bar)
            self.rows[id(it)] = (it, bar)
            self.row_lbls[id(it)] = lbl

    def _queue(self):
        for it, bar in self.rows.values():
            bar.setValue(it.progress)
            self.row_lbls[id(it)].setText(f"{it.name}  ·  {it.status}" + (f" ({it.error})" if it.error else ""))

    def _finished(self, results):
        mine = [(it, rep) for it, rep in results if id(it) in self.rows]
        if not mine:
            return
        ok = [it for it, _ in mine if it.status == "completato"]
        bad = [it for it, _ in mine if it.status == "errore"]
        self.done_lbl.setText(f"Fatto: {len(ok)} video pronti." + (f" {len(bad)} non riusciti: {bad[0].error}" if bad else ""))
        self.done_box.setVisible(True)
        self.go.setEnabled(True)
        self._last = Path(ok[-1].path).parent if ok else None

    def _open(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        d = getattr(self, "_last", None) or Path(self.dir_edit.text())
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))


def _size(p: PF.Platform) -> tuple[int, int]:
    from ..spec import ImageSettings, output_size, ExportSettings
    im, ex = ImageSettings(aspect=p.aspect), ExportSettings(preset="Personalizzato", custom_height=p.short)
    return output_size(im, ex)


# ------------------------------------------------------------------------------------------------------------ guscio
class SocialShell(QWidget):
    newProject = Signal()

    def __init__(self, state, open_settings=None, parent=None):
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
        lay.addLayout(top)
        self.stack = QStackedWidget()
        self.start = SocialStart(state)
        self.cut = SocialCut(state)
        self.look = SocialLook(state, open_settings)
        self.export = SocialExport(state, self.cut.player.position)
        for w in (self.start, self.cut, self.look, self.export):
            self.stack.addWidget(w)
        lay.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.back = SecondaryButton("Indietro", "chevron-left")
        self.next = PrimaryButton("Avanti", "chevron-right")
        self.hint = label("", "caption", True)
        self.back.clicked.connect(lambda: self.show_step(max(0, self.step - 1)))
        self.next.clicked.connect(lambda: self.show_step(min(3, self.step + 1)))
        nav.addWidget(self.back)
        nav.addWidget(self.hint, 1)
        nav.addWidget(self.next)
        lay.addLayout(nav)
        state.social.finished.connect(lambda: self.show_step(1))
        state.project_changed.connect(self._gate)
        self.export.newProject.connect(self.newProject)
        self.show_step(0, animate=False)

    @property
    def step(self) -> int:
        return self.stack.currentIndex()

    def show_step(self, i: int, animate: bool = True) -> None:
        if i > 0 and not self.state.project:
            i = 0
        for w in (self.cut.player, self.look.player):
            w.player.pause()
        self.stack.setCurrentIndex(i)
        self.steps.set_state(i)
        self.back.setVisible(i > 0)
        self.next.setVisible(0 < i < 3)
        self.next.setText("Avanti")
        self._gate()
        if i == 2:
            self.look.sync()
        if animate:
            fade_in(self.stack.currentWidget(), slide=12)
            QTimer.singleShot(60, lambda: stagger_cards(self.stack.currentWidget()))

    def _gate(self):
        self.next.setEnabled(bool(self.state.project))

    def reset(self):
        self.start.reset()
        self.show_step(0, animate=False)
