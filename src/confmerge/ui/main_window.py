"""Finestra principale: intestazione (titolo, profilo, modalità, tema) e due viste sullo stesso progetto."""
from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import paths
from ..project import Project
from .about import AboutDialog
from .advanced import AdvancedShell
from .brand_dialog import BrandDialog
from .history_dialog import HistoryDialog
from .home import HomePage
from .social_shell import SocialShell
from .brand import app_icon, logo_pixmap
from .settings_dialog import SettingsDialog, ShortcutsDialog
from .simple import SimpleShell
from .state import AppState
from .theme import S1, S2, S3, theme
from .widgets import IconButton, Segmented, label, toast
from .widgets.anim import fade_in


AUTOSAVE_MS = 30_000


class ElidedLabel(QLabel):
    """Etichetta che accorcia il testo con «…» quando lo spazio non basta (non allarga mai l'intestazione)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(self.width(), 20)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def minimumSizeHint(self):
        return QSize(40, super().minimumSizeHint().height())


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None, social_state: AppState | None = None):
        super().__init__()
        self.state = state or AppState()
        self.social_state = social_state or AppState(self.state.settings, kind="social")      # lavoro di Studio Social
        self.setWindowTitle("ConfMerge")
        self.setWindowIcon(app_icon())
        self.resize(1280, 820)
        self.setMinimumSize(1100, 700)
        st = self.state
        self.simple = SimpleShell(st)
        self.adv = AdvancedShell(st)
        # alias usati dai test e dagli strumenti
        self.select, self.review, self.graphics, self.export = self.adv.select, self.adv.review, self.adv.graphics, self.adv.export
        self.shells = QStackedWidget()
        self.shells.addWidget(self.simple)
        self.shells.addWidget(self.adv)
        self.social = SocialShell(self.social_state, self.settings_dialog)
        self.home = HomePage()
        self.shells.addWidget(self.social)
        self.shells.addWidget(self.home)
        self.app = "merge"                                  # strumento attivo: social | merge | home

        central = QWidget()
        central.setObjectName("Root")
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._header())
        lay.addWidget(self.shells, 1)
        self.setCentralWidget(central)
        self._menu_icons: list[tuple[QAction, str]] = []
        self._menus()
        self._shortcuts()
        self.simple.moreOptions.connect(lambda: self.set_mode("advanced"))
        self.simple.newProject.connect(self.new)
        self.social.newProject.connect(self.new)
        self.home.chosen.connect(self.set_app)
        self.selection: list[Path] = []                      # i file scelti: uno solo per tutti gli strumenti
        self.simple.start.picked.connect(self.open_sources)
        self.adv.picked.connect(self.open_sources)
        self.social.start.picked.connect(self.open_sources)
        self.social_state.project_changed.connect(self._project_changed)
        self.social_state.spec_changed.connect(self._history_buttons)
        self.social_state.profile_changed.connect(self._history_buttons)
        st.project_changed.connect(self._project_changed)
        st.profile_changed.connect(self._fill_profiles)
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: theme.mode == "system" and theme.apply())
        except Exception:  # noqa: BLE001
            pass
        theme.changed.connect(self._theme_icon)
        theme.changed.connect(self._refresh_menu_icons)
        self.set_mode(theme.prefs.get("mode", "simple"), animate=False, remember=False)
        start = os.environ.get("CONFMERGE_APP") or theme.prefs.get("app", "") or "home"
        self.set_app(start if start in ("social", "merge", "home") else "home", animate=False, remember=False)
        self._fill_profiles()
        self._theme_icon()
        st.spec_changed.connect(self._history_buttons)
        st.profile_changed.connect(self._history_buttons)
        self._history_buttons()
        self._autosave_timer = QTimer(self)             # salvataggio automatico ogni 30 secondi
        self._autosave_timer.setInterval(AUTOSAVE_MS)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()
        self._recovery_checked = False

    # ------------------------------------------------------------------ intestazione
    def _header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Header")
        row = QHBoxLayout(bar)
        row.setContentsMargins(S3, S1, S3, S1)
        row.setSpacing(S2)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(28))
        row.addWidget(logo)
        row.addWidget(label("ConfMerge", "h2"))
        self.project_lbl = ElidedLabel("Nessun progetto")
        self.project_lbl.setProperty("role", "muted")
        row.addWidget(self.project_lbl, 1)
        self.back_btn = IconButton("undo-2", "Indietro: annulla l'ultima modifica (Ctrl+Z)")
        self.fwd_btn = IconButton("redo-2", "Avanti: ripristina la modifica annullata (Ctrl+Maiusc+Z)")
        self.hist_btn = IconButton("clock", "Cronologia delle modifiche: torna a un punto qualsiasi")
        self.back_btn.clicked.connect(self._undo)
        self.fwd_btn.clicked.connect(self._redo)
        self.hist_btn.clicked.connect(self.history_dialog)
        for b in (self.back_btn, self.fwd_btn, self.hist_btn):
            row.addWidget(b)
        row.addSpacing(S2)
        self.app_seg = Segmented([("Social", "social"), ("Conferenze", "merge")],
                                 icons=["scissors", "film"])
        self.app_seg.changed.connect(self.switch_tool)
        self.app_seg.setToolTip("Social: Studio Social, video pronti per le piattaforme. Conferenze: Merge Conferenze, per unire riprese e audio esterno.")
        row.addWidget(self.app_seg)
        row.addSpacing(S2)
        self.profile_lbl = label("", "muted")                # segnaposto (il nome sta nel suggerimento del menu)
        self.profile_lbl.setVisible(False)
        row.addWidget(self.profile_lbl)
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(150)
        self.profile_box.setToolTip("Profilo: decide titolo, logo, scritte e credito")
        self.profile_box.currentTextChanged.connect(self._profile_picked)
        row.addWidget(self.profile_box)
        self.mode_seg = Segmented([("Semplice", "simple"), ("Avanzata", "advanced")], icons=["sparkles", "sliders-horizontal"])
        self.mode_seg.changed.connect(self.set_mode)
        self.mode_seg.setToolTip("Semplice: tre passi. Avanzata: tutte le funzioni.")
        row.addWidget(self.mode_seg)
        self.theme_btn = IconButton("moon", "Cambia tra tema chiaro e scuro")
        self.theme_btn.clicked.connect(self._toggle_theme)
        row.addWidget(self.theme_btn)
        sb = IconButton("settings", "Impostazioni")
        sb.clicked.connect(self.settings_dialog)
        row.addWidget(sb)
        return bar

    def _fill_profiles(self):
        names = self.state.settings.list_profiles()
        if self.state.profile_name not in names:
            names.append(self.state.profile_name)
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        self.profile_box.addItems(names)
        self.profile_box.setCurrentText(self.state.profile_name)
        self.profile_box.blockSignals(False)

    def _profile_picked(self, name: str):
        if name and name != self.state.profile_name:
            self.state.apply_profile(name)

    def _toggle_theme(self):
        theme.set_mode("light" if theme.t.name == "dark" else "dark")

    def _theme_icon(self):
        self.theme_btn.set_icon("sun" if theme.t.name == "dark" else "moon")

    def _project_changed(self):
        st = self.active_state
        pr = st.project if self.app != "home" else None
        if not pr:
            self._saved_note = ""
            self.project_lbl.setText("Nessun progetto" if self.app != "home" else "")
            self.setWindowTitle("ConfMerge")
            return
        name = st.project_path.stem if st.project_path else (Path(pr.clips[0]).parent.name or "Nuovo progetto")
        note = getattr(self, "_saved_note", "")
        self.project_lbl.setText(f"·  {name}" + (f"  ({note})" if note else ""))
        self.setWindowTitle(f"{name} – ConfMerge")

    # ------------------------------------------------------------------ modalità
    def set_mode(self, mode: str, animate: bool = True, remember: bool = True) -> None:
        mode = "advanced" if mode == "advanced" else "simple"
        for p in (self.simple.check.player, self.adv.review.player):
            p.player.pause()
        if remember:
            theme.prefs.set("mode", mode)
        self.mode_seg.setValue(mode)
        self.shells.setCurrentIndex(1 if mode == "advanced" else 0)
        w = self.shells.currentWidget()
        if mode == "advanced" and self.state.project and self.adv.current() == 0:
            self.adv.goto(1, animate=False)
        if mode == "simple" and self.state.project and self.simple.step == 0:
            self.simple.show_step(1, animate=False)
        if animate:
            fade_in(w, slide=0)
        self.adv.refresh_nav()

    @property
    def mode(self) -> str:
        i = self.shells.currentIndex()
        return "advanced" if i == 1 else "simple" if i == 0 else theme.prefs.get("mode", "simple")

    @property
    def active_state(self) -> AppState:
        return self.social_state if self.app == "social" else self.state

    def open_sources(self, items, kind: str | None = None) -> None:
        """Unico punto d'ingresso dei file: riconosce se è una conferenza o un video social e apre lo strumento giusto."""
        from .. import detect
        det = detect.classify(items)
        start = self.social.start if self.app == "social" else self.simple.start
        if not det.kind:
            start.problem.setText(det.reason + " Trascina video (mp4, mov) o la cartella che li contiene.")
            return
        kind = kind or det.kind
        target = self.social_state if kind == "social" else self.state
        if target.project and not self.confirm_discard(only=target):
            return
        self.selection = [Path(p) for p in det.sources]
        if kind != self.app:
            self.set_app(kind)
        if kind == "social":
            self.social.start.start(det.videos)
        else:
            self.simple.start.use_paths(det.sources)          # la pagina Sorgenti dell'Avanzata si aggiorna da sola
        toast(self, det.reason if kind == det.kind else
              ("Uso gli stessi file come conferenza." if kind == "merge" else "Uso gli stessi file come video social."), "info")

    def switch_tool(self, app: str) -> None:
        """Dal selettore in alto: cambia strumento tenendo gli stessi file (una sola selezione per tutti)."""
        if app == self.app:
            return
        self.set_app(app)
        st = self.active_state
        busy = st.social.running if app == "social" else st.analysis.running
        if self.selection and not st.project and not busy:
            self.open_sources(self.selection, kind=app)

    def set_app(self, app: str, animate: bool = True, remember: bool = True) -> None:
        """Cambia strumento: Studio Social o Merge Conferenze (ognuno tiene il suo lavoro)."""
        app = app if app in ("social", "merge", "home") else "home"
        for p in (self.simple.check.player, self.adv.review.player, self.social.cut.player, self.social.look.player):
            p.player.pause()
        self.app = app
        if remember and app != "home":
            theme.prefs.set("app", app)
        if app == "social":
            self.shells.setCurrentIndex(2)
        elif app == "home":
            self.shells.setCurrentIndex(3)
        else:
            self.set_mode(theme.prefs.get("mode", "simple"), animate=False, remember=False)
        merge = app == "merge"
        for w in (self.mode_seg, self.profile_box):
            w.setVisible(merge)
        self.app_seg.setVisible(app != "home")
        if app != "home":
            self.app_seg.setValue(app)
        if animate:
            fade_in(self.shells.currentWidget(), slide=0)
        self._project_changed()
        self._history_buttons()

    # ------------------------------------------------------------------ menu e scorciatoie
    def _menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        for text, icon, fn, key in (("&Nuovo progetto", "plus", self.new, QKeySequence.New),
                                    ("&Apri un progetto…", "folder-open", self.open_project, QKeySequence.Open),
                                    ("&Salva il progetto…", "save", self.save_project, QKeySequence.Save)):
            a = QAction(theme.icon(icon, theme.t.text2), text, self)
            self._menu_icons.append((a, icon))
            a.setShortcut(key)
            a.triggered.connect(fn)
            f.addAction(a)
        f.addSeparator()
        q = QAction("&Esci", self)
        q.triggered.connect(self.close)
        f.addAction(q)
        e = mb.addMenu("&Modifica")
        self.act_undo = QAction(theme.icon("undo-2", theme.t.text2), "&Annulla", self)
        self._menu_icons.append((self.act_undo, "undo-2"))
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_undo.triggered.connect(self._undo)
        self.act_redo = QAction(theme.icon("redo-2", theme.t.text2), "&Ripristina", self)
        self._menu_icons.append((self.act_redo, "redo-2"))
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        self.act_redo.triggered.connect(self._redo)
        e.addAction(self.act_undo)
        e.addAction(self.act_redo)
        s = mb.addMenu("&Impostazioni")
        a = QAction(theme.icon("settings", theme.t.text2), "&Aspetto, profili e credito…", self)
        self._menu_icons.append((a, "settings"))
        a.triggered.connect(self.settings_dialog)
        s.addAction(a)
        a = QAction(theme.icon("palette", theme.t.text2), "&Kit del marchio…", self)
        self._menu_icons.append((a, "palette"))
        a.triggered.connect(lambda: BrandDialog(self.active_state, self).exec())
        s.addAction(a)
        h = mb.addMenu("&Aiuto")
        for text, icon, fn in (("&Scorciatoie da tastiera", "keyboard", lambda: ShortcutsDialog(self).exec()),
                               ("Apri la cartella dei &log", "folder", self._open_logs),
                               ("&Copia informazioni per l'assistenza", "copy", self.copy_support_info)):
            a = QAction(theme.icon(icon, theme.t.text2), text, self)
            self._menu_icons.append((a, icon))
            a.triggered.connect(fn)
            h.addAction(a)
        a = QAction(theme.icon("download", theme.t.text2), "Cerca &aggiornamenti…", self)
        self._menu_icons.append((a, "download"))
        a.triggered.connect(lambda: self.check_updates(manual=True))
        h.addAction(a)
        self.act_auto_update = QAction("Cerca gli aggiornamenti all'avvio", self)
        self.act_auto_update.setCheckable(True)
        self.act_auto_update.setChecked(bool(theme.prefs.get("update_check", True)))
        self.act_auto_update.toggled.connect(lambda on: theme.prefs.set("update_check", bool(on)))
        h.addAction(self.act_auto_update)
        h.addSeparator()
        a = QAction(theme.icon("info", theme.t.text2), "&Informazioni", self)
        a.triggered.connect(lambda: AboutDialog(self).exec())
        h.addAction(a)
        h.actions()[0].setShortcut(QKeySequence("F1"))

    def _shortcuts(self):
        pass   # le scorciatoie sono sulle voci di menu (valgono in tutta la finestra)

    def _refresh_menu_icons(self):
        for act, name in self._menu_icons:
            act.setIcon(theme.icon(name, theme.t.text2))

    def _history_buttons(self):
        st = self.active_state
        self.back_btn.setEnabled(st.can_undo and self.app != "home")
        self.fwd_btn.setEnabled(st.can_redo and self.app != "home")

    def history_dialog(self):
        HistoryDialog(self.active_state, self).exec()

    def _undo(self):
        if not self.active_state.undo():
            toast(self, "Non c'è niente da annullare.", "info")

    def _redo(self):
        if not self.active_state.redo():
            toast(self, "Non c'è niente da ripristinare.", "info")

    def _open_logs(self):
        from .. import diagnostics
        diagnostics.open_log_folder()

    def copy_support_info(self):
        from PySide6.QtWidgets import QApplication
        from .. import diagnostics
        QApplication.clipboard().setText(diagnostics.support_info())
        toast(self, "Informazioni copiate. Incollale in un messaggio (Ctrl+V) per chiedere assistenza.", "ok")

    def settings_dialog(self):
        SettingsDialog(self.active_state, self).exec()
        for st in (self.state, self.social_state):
            st.keys_changed.emit()                      # le schede dei sottotitoli rileggono la chiave appena salvata

    # ------------------------------------------------------------------ progetto
    def _states(self) -> list[AppState]:
        """Gli stati dei due strumenti, quello in uso per primo."""
        return [self.active_state] + [x for x in (self.state, self.social_state) if x is not self.active_state]

    @staticmethod
    def _tool(st: AppState) -> str:
        return "Studio Social" if st.kind == "social" else "Merge Conferenze"

    def confirm_discard(self, only: AppState | None = None) -> bool:
        """True se si può chiudere/sostituire il lavoro: già salvato, oppure l'utente ha scelto cosa farne."""
        return all(self._confirm_one(st) for st in ([only] if only else self._states()))

    def _confirm_one(self, st: AppState) -> bool:
        from ..autosave import clear_recovery
        if os.environ.get("CONFMERGE_NO_CONFIRM") or not st.project or not st.is_dirty():
            return True
        if st.project_path is not None and st.settings.data.get("autosave_named", True):
            st.autosave()                                # progetto con nome: il salvataggio automatico basta
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Lavoro non salvato")
        box.setText(f"Hai modifiche non salvate in {self._tool(st)}.")
        box.setInformativeText("Vuoi salvare il progetto prima di continuare? Se non lo salvi, il lavoro andrà perso.")
        save = box.addButton("Salva…", QMessageBox.AcceptRole)
        drop = box.addButton("Non salvare", QMessageBox.DestructiveRole)
        box.addButton("Annulla", QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.save_project(st)
        if box.clickedButton() is drop:
            clear_recovery(st.settings.root, st.slot)
            return True
        return False

    def new(self):
        st = self.active_state
        if not self.confirm_discard(only=st):
            return
        st.project = None
        st.project_path = None
        self.selection = []
        if st.kind == "social":
            self.social.reset()
        else:
            st.sources.clear()
            self.simple.reset()
            self.adv.goto(0, animate=False)
        st.reset_history()
        st.mark_clean()
        self._project_changed()

    def save_project(self, st: AppState | None = None) -> bool:
        st = st if isinstance(st, AppState) else self.active_state
        if not st.project:
            QMessageBox.information(self, "ConfMerge", "Non c'è ancora niente da salvare: prima scegli i video e lascia finire la preparazione.")
            return False
        start = str(st.project_path) if st.project_path else ""
        f, _ = QFileDialog.getSaveFileName(self, "Salva il progetto", start, "Progetto ConfMerge (*.confmerge)")
        if not f:
            return False
        st.save_to(f if f.endswith(".confmerge") else f + ".confmerge")
        self._project_changed()
        toast(self, "Progetto salvato.", "ok")
        return True

    def open_project(self, path: str = "", recovery: bool = False):
        f = path or QFileDialog.getOpenFileName(self, "Apri un progetto", "", "Progetto ConfMerge (*.confmerge)")[0]
        if not f:
            return
        try:
            proj = Project.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "ConfMerge", f"Questo file non sembra un progetto valido: {e}")
            return
        target = self.social_state if proj.kind == "social" else self.state
        if not self.confirm_discard(only=target):
            return
        self._opening = (target, None if recovery else Path(f), recovery)
        self.set_app(target.kind if target.kind == "social" else "merge")
        runner = target.social if target.kind == "social" else target.analysis
        runner.finished.connect(self._opened)
        runner.failed.connect(lambda m: QMessageBox.critical(self, "ConfMerge", m))
        if target.kind == "social":
            self.social.start.stack.setCurrentIndex(1)
            target.social.open_project(proj)
        else:
            if self.mode == "simple":
                self.simple.start.stack.setCurrentIndex(1)
            runner.open_project(proj)

    def _opened(self):
        target, path, recovery = getattr(self, "_opening", (self.state, None, False))
        runner = target.social if target.kind == "social" else target.analysis
        try:
            runner.finished.disconnect(self._opened)
        except (TypeError, RuntimeError):
            pass
        target.project_path = path
        if recovery:
            target._clean_fp = ""                         # il lavoro recuperato non è ancora salvato: resta «da salvare»
        self._project_changed()
        if target.kind == "social":
            return                                         # SocialShell passa da sola al passo «Taglia»
        if self.mode == "advanced":
            self.adv.goto(1)
        else:
            self.simple.show_step(1)

    def _autosave(self):
        for st in (self.state, self.social_state):
            if st.analysis.running or st.social.running or not st.project:
                continue
            kind = st.autosave()
            if kind and st is self.active_state:
                hhmm = time.strftime("%H:%M")
                self._saved_note = f"salvato automaticamente alle {hhmm}" if kind == "file" else f"copia di sicurezza alle {hhmm}"
                self._project_changed()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._recovery_checked:
            self._recovery_checked = True
            QTimer.singleShot(600, self._offer_recovery)
            QTimer.singleShot(5000, self.check_updates)

    # --- aggiornamenti (una sola richiesta a GitHub, al massimo ogni 20 ore; mai se spento)
    def check_updates(self, manual: bool = False):
        if not manual:
            if os.environ.get("CONFMERGE_NO_UPDATE_CHECK") or not theme.prefs.get("update_check", True):
                return
            if time.time() - float(theme.prefs.get("update_checked_at", 0)) < 20 * 3600:
                return
        from .update_check import UpdateChecker
        self._updater = UpdateChecker(self)
        self._updater.done.connect(lambda rel, err: self._update_result(rel, err, manual))
        self._updater.start()

    def _update_result(self, rel, err: str, manual: bool):
        if not err:
            theme.prefs.set("update_checked_at", time.time())
        if err:
            if manual:
                QMessageBox.information(self, "Aggiornamenti", err)
            return
        if rel is None:
            if manual:
                from .. import __version__
                QMessageBox.information(self, "Aggiornamenti", f"Hai già l'ultima versione ({__version__}).")
            return
        if not manual and theme.prefs.get("update_skipped", "") == rel.tag:
            return
        from .. import __version__
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Nuova versione disponibile")
        box.setText(f"È uscita la versione {rel.tag.lstrip('v')} di ConfMerge (tu hai la {__version__}).")
        box.setInformativeText("Scarica il file e sostituisci quello che usi adesso: i tuoi progetti non cambiano.")
        go = box.addButton("Scarica", QMessageBox.AcceptRole)
        notes = box.addButton("Novità", QMessageBox.HelpRole)
        later = box.addButton("Più tardi", QMessageBox.RejectRole)
        skip = box.addButton("Salta questa versione", QMessageBox.DestructiveRole)
        box.exec()
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        c = box.clickedButton()
        if c is go:
            QDesktopServices.openUrl(QUrl(rel.download))
        elif c is notes:
            QDesktopServices.openUrl(QUrl(rel.page))
        elif c is skip:
            theme.prefs.set("update_skipped", rel.tag)
        del later

    def _offer_recovery(self):
        from ..autosave import clear_recovery, has_recovery, recovery_file, recovery_info
        if os.environ.get("CONFMERGE_NO_RECOVERY"):
            return
        for st in (self.state, self.social_state):
            root, slot = st.settings.root, st.slot
            if st.project or not has_recovery(root, slot):
                continue
            info = recovery_info(root, slot)
            when = time.strftime("%d/%m/%Y alle %H:%M", time.localtime(info["saved_at"])) if info.get("saved_at") else "una volta"
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Lavoro non salvato")
            box.setText(f"Ho trovato un lavoro non salvato in {self._tool(st)}.")
            box.setInformativeText(f"L'ultima copia di sicurezza è del {when}. Vuoi riprenderlo?")
            yes = box.addButton("Riprendi il lavoro", QMessageBox.AcceptRole)
            no = box.addButton("Scarta", QMessageBox.DestructiveRole)
            box.setDefaultButton(yes)
            box.exec()
            if box.clickedButton() is yes:
                self.open_project(str(recovery_file(root, slot)), recovery=True)
                return
            if box.clickedButton() is no:
                clear_recovery(root, slot)

    def closeEvent(self, e):
        if not self.confirm_discard():
            e.ignore()
            return
        self._autosave_timer.stop()
        self.state.settings.save()
        for p in (self.simple.check.player, self.adv.review.player, self.social.cut.player, self.social.look.player):
            p.player.stop()
        paths.cleanup_temp()
        super().closeEvent(e)
