"""Studio Social: quattro passi guidati. Video → Taglia → Aspetto → Esporta."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QSlider, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import platforms as PF
from ..media_scan import VIDEO_EXT
from .cut_waveform import CutWaveform, fmt_clock
from .brand_card import BrandCard
from .graphics_page import scrolled
from .music_card import MusicCard
from .player import PlayerWidget
from .social_style import OverlaysCard, StyleTemplateCard
from .split_card import SplitCard
from .subtitles_tab import SimpleSubtitlesCard
from .theme import S2
from .widgets import (Card, DropZone, GhostButton, LinkButton, PrimaryButton, ProgressBarThin, SecondaryButton, Segmented,
                      FlowBar, StepIndicator, Toggle, label)
from .widgets.anim import fade_in, stagger_cards

STEPS = ["Video", "Taglia", "Formato", "Due video", "Grafica", "Sottotitoli", "Audio", "Esporta"]
LOOK_FIRST, EXPORT = 2, 7           # passi 2…6 sono i pannelli di SocialLook, 7 è l'esportazione
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
    picked = Signal(object)          # file o cartelle scelti: li smista la finestra (riconosce conferenza o social)

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
        self.drop = DropZone("Trascina qui i tuoi video o la cartella",
                             "Riconosco da solo se è un video per i social o una conferenza (video + registrazione audio).",
                             "Scegli i video…")
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
            self.picked.emit([Path(f) for f in files])

    def _dropped(self, items):
        self.picked.emit([Path(p) for p in items])

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
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(label("Togli le pause e gli errori. Quello che togli resta scuro sulla forma d'onda e viene saltato.",
                             "caption", True))
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
        panel.setMinimumWidth(max(380, panel.minimumSizeHint().width()))
        split.addWidget(panel)
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
        self.sens = Segmented([(n, i) for i, (n, _) in enumerate(SENSITIVITY)])
        self.sens.changed.connect(self._sens)
        c.add(self.sens)
        self.found = label("", "caption", True)
        c.add(self.found)
        r = QHBoxLayout()
        self.sil_btn = PrimaryButton("Togli i silenzi", "sparkles")
        self.sil_btn.clicked.connect(self.remove_silences)
        r.addWidget(self.sil_btn)
        self.unsil_btn = SecondaryButton("Rimetti i silenzi", "rotate-ccw",
                                         "Rimette le pause tolte con «Togli i silenzi» (i tagli a mano restano)")
        self.unsil_btn.clicked.connect(self.restore_silences)
        r.addWidget(self.unsil_btn)
        r.addStretch(1)
        c.lay.addLayout(r)
        lay.addWidget(c)
        c2 = Card()
        c2.add(label("Taglia a mano", "h2", True))
        self.sel_info = label("Nessuna parte scelta: trascina sulla forma d'onda.", "", True)
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
        self.unsil_btn.setVisible(bool(self.ctl.silence_removed))
        self.sil_btn.setVisible(not self.ctl.silence_removed)

    def _sens(self, i):
        db, mn = SENSITIVITY[int(i)][1]
        so = self.state.spec.social
        so.skip_silence_db, so.skip_silence_min = db, mn
        self.refresh()

    # --- azioni
    def remove_silences(self):
        n, secs = self.ctl.remove_silences()
        self.found.setText(f"Tolte {n} pause ({mmss(secs)}). Puoi annullare con «Indietro» in alto." if n else "")

    def restore_silences(self):
        n = self.ctl.restore_silences()
        self.found.setText(f"Rimesse {n} pause." if n else "")

    def _sel_changed(self, sel):
        self._sel = sel
        on = sel is not None
        for b in (self.rm_btn, self.rs_btn, self.play_btn):
            b.setEnabled(on)
        self.sel_info.setText(f"Parte scelta: da {fmt_clock(sel[0])} a {fmt_clock(sel[1])} ({sel[1] - sel[0]:.1f} s)."
                              if on else "Nessuna parte scelta: trascina sulla forma d'onda.")

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
        self.open_settings = open_settings
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
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
        # elementi sull'anteprima: si trascinano; qui i pulsanti per centrarli
        self.player.canvas.social_edit = True
        self.player.canvas.itemSelected.connect(self._item_selected)
        self.player.canvas.itemsChanged.connect(self._items_changed)
        self.sel_lbl = label("Trascina testi, logo e sottotitoli sull'anteprima (Alt = senza aggancio).", "caption", True)
        ll.addWidget(self.sel_lbl)
        pr = QHBoxLayout()
        self.c_ref = Segmented([("Area sicura", "safe"), ("Video intero", "video")])
        self.c_ref.setToolTip("Rispetto a cosa centrare: l'area sicura (linea verde) o tutto il fotogramma")
        pr.addWidget(self.c_ref)
        self.c_h = SecondaryButton("Centra ↔")
        self.c_v = SecondaryButton("Centra ↕")
        self.c_h.setToolTip("Centra in orizzontale")
        self.c_v.setToolTip("Centra in verticale")
        self.c_h.clicked.connect(lambda: self._center(True, False))
        self.c_v.clicked.connect(lambda: self._center(False, True))
        for b in (self.c_h, self.c_v):
            b.setEnabled(False)
            pr.addWidget(b)
        pr.addStretch(1)
        ll.addLayout(pr)
        split.addWidget(left)
        # --- pannelli: uno per passo, a due colonne, senza scorrimento (pensati per un portatile 1366×768)
        self.panels = QStackedWidget()
        self.plat_card = Card()
        self.plat_card.add(label("Dove lo pubblichi", "h2", True))
        self.toggles: dict[str, Toggle] = {}
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        for i, p in enumerate(PF.all_platforms(self.root)):
            t = Toggle(f"{p.name}  ·  {p.aspect}")
            t.setToolTip(p.note)
            t.toggled.connect(lambda on, pid=p.id: self._toggle(pid, on))
            self.toggles[p.id] = t
            grid.addWidget(t, i // 2, i % 2)
        self.plat_card.add(grid_host)
        self.warn = label("", "warn", True)
        self.plat_card.add(self.warn)
        self.fr_card = Card()
        self.fr_card.add(label("Inquadratura", "h2", True))
        self.fr_card.add(label("Il tuo video non ha il formato scelto: come lo metto?", "caption", True))
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
        self.safe = Toggle("Mostra le zone coperte dall'app")
        self.safe.toggled.connect(self._safe)
        sc = Card()
        sc.add(self.safe)
        self.legend_box = QWidget()
        self.legend_lay = QVBoxLayout(self.legend_box)
        self.legend_lay.setContentsMargins(0, 0, 0, 0)
        sc.add(self.legend_box)
        sc.add(label("Ogni piattaforma ha la sua zona colorata (la loro interfaccia copre quelle parti). La linea verde è "
                     "l'area sicura per tutte.", "caption", True))
        self.panels.addWidget(self._page("Formato", "Dove lo pubblichi e come entra l'immagine. Le zone colorate sono coperte "
                                         "dall'app: tieni lì dentro i testi importanti.", [self.plat_card, sc], [self.fr_card]))
        self.split_card = SplitCard(state)
        self.panels.addWidget(self._page("Due video nello stesso reel (facoltativo)", "Un secondo video sopra o sotto il tuo, "
                                         "per esempio quello a cui rispondi. Si può saltare.", [self.split_card]))
        self.panels.addWidget(self._page("Grafica", "Marchio, testi e immagini sul video. Trascinali sull'anteprima.",
                                         [StyleTemplateCard(state), BrandCard(state)], [OverlaysCard(state)]))
        self.subs_card = SimpleSubtitlesCard(state, open_settings, wide=True)
        self.panels.addWidget(self._page("Sottotitoli", "Scrivili con l'intelligenza artificiale, scegli come si vedono e "
                                         "provali nell'anteprima prima di esportare.", [self.subs_card]))
        self.panels.addWidget(self._page("Audio", "Musica di sottofondo sotto la voce.", [MusicCard(state)]))
        split.addWidget(self.panels)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 5)
        split.setSizes([520, 700])
        main.addWidget(split, 1)
        state.profile_changed.connect(self.sync)
        state.social.finished.connect(self._loaded)
        self.sync()

    def _page(self, title: str, desc: str, left: list, right: list | None = None) -> QWidget:
        """Un pannello: titolo e frase, poi una o due colonne di schede. Non scorre: ogni pannello sta in una schermata."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(S2)
        lay.addWidget(label(title, "h2"))
        lay.addWidget(label(desc, "caption", True))
        cols = QHBoxLayout()
        cols.setSpacing(S2)
        for items in (left, right):
            if not items:
                continue
            col = QVBoxLayout()
            col.setSpacing(S2)
            for it in items:
                col.addWidget(it)
            col.addStretch(1)
            cols.addLayout(col, 1)
        lay.addLayout(cols)
        lay.addStretch(1)
        return w

    def set_panel(self, i: int) -> None:
        self.panels.setCurrentIndex(max(0, min(self.panels.count() - 1, i)))

    def _item_selected(self, kind: str, idx: int):
        from . import placement
        on = bool(kind)
        self.c_h.setEnabled(on)
        self.c_v.setEnabled(on)
        self.sel_lbl.setText(placement.label_of(self.state, kind, idx) if on
                             else "Trascina testi, logo e sottotitoli sull'anteprima (Alt = senza aggancio).")

    def _items_changed(self):
        self.state.touch()
        self.state.profile_changed.emit()                   # le schede mostrano «Libero» e la nuova posizione

    def _center(self, h: bool, v: bool):
        from . import placement
        cv = self.player.canvas
        if not cv.sel_item:
            return
        W, H = cv.frame_size()
        safe = cv.safe_common if self.c_ref.value() == "safe" else None
        placement.center(self.state, *cv.sel_item, W, H, h, v, safe)
        cv.update()
        self._items_changed()

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
        lay.setContentsMargins(24, 8, 24, 8)
        lay.setSpacing(4)
        self.flow = FlowBar(STEPS)                        # passi cliccabili + Indietro/Avanti in alto
        self.steps, self.back, self.next = self.flow.steps, self.flow.back, self.flow.next
        lay.addWidget(self.flow)
        self.hint = label("", "caption", True)
        self.hint.setVisible(False)
        lay.addWidget(self.hint)
        self.stack = QStackedWidget()
        self.start = SocialStart(state)
        self.cut = SocialCut(state)
        self.look = SocialLook(state, open_settings)
        self.export = SocialExport(state, self.cut.player.position)
        for w in (self.start, self.cut, self.look, self.export):
            self.stack.addWidget(w)
        lay.addWidget(self.stack, 1)
        self.steps.clicked.connect(self.goto)
        self.back.clicked.connect(lambda: self.show_step(max(0, self.step - 1)))
        self.next.clicked.connect(lambda: self.show_step(min(EXPORT, self.step + 1)))
        state.social.finished.connect(lambda: self.show_step(1))
        state.project_changed.connect(self._gate)
        self.export.newProject.connect(self.newProject)
        self._step = 0
        self.show_step(0, animate=False)

    @property
    def step(self) -> int:
        return self._step

    def goto(self, i: int) -> None:
        """Clic su un passo: tutti si possono visitare appena c'è un video."""
        if self.state.project or i == 0:
            self.show_step(i)

    def show_step(self, i: int, animate: bool = True) -> None:
        if i > 0 and not self.state.project:
            i = 0
        i = max(0, min(EXPORT, i))
        for w in (self.cut.player, self.look.player):
            w.player.pause()
        self._step = i
        page = 0 if i == 0 else 1 if i == 1 else 3 if i == EXPORT else 2
        self.stack.setCurrentIndex(page)
        if page == 2:
            self.look.set_panel(i - LOOK_FIRST)
        self.steps.set_state(i)
        self.back.setVisible(i > 0)
        self.next.setVisible(0 < i < EXPORT)
        self.next.setText("Avanti" if i < EXPORT - 1 else "Esporta")
        self._gate()
        if i in (2, 3, 4, 5, 6):
            self.look.sync()
        if animate:
            fade_in(self.stack.currentWidget(), slide=12)
            QTimer.singleShot(60, lambda: stagger_cards(self.stack.currentWidget()))

    def _gate(self):
        ok = bool(self.state.project)
        self.next.setEnabled(ok)
        self.steps.set_reach(EXPORT if ok else 0)

    def reset(self):
        self.start.reset()
        self.show_step(0, animate=False)
