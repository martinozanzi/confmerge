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
from .history_dialog import HistoryDialog
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
    def __init__(self, state: AppState | None = None):
        super().__init__()
        self.state = state or AppState()
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
        st.project_changed.connect(self._project_changed)
        st.profile_changed.connect(self._fill_profiles)
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: theme.mode == "system" and theme.apply())
        except Exception:  # noqa: BLE001
            pass
        theme.changed.connect(self._theme_icon)
        theme.changed.connect(self._refresh_menu_icons)
        self.set_mode(theme.prefs.get("mode", "simple"), animate=False, remember=False)
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
        row.addWidget(label("Profilo:", "muted"))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(150)
        self.profile_box.setToolTip("Il profilo decide titolo, logo, scritte e credito")
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
        st = self.state
        pr = st.project
        if not pr:
            self._saved_note = ""
            self.project_lbl.setText("Nessun progetto")
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
        return "advanced" if self.shells.currentIndex() == 1 else "simple"

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
        h = mb.addMenu("&Aiuto")
        for text, icon, fn in (("&Scorciatoie da tastiera", "keyboard", lambda: ShortcutsDialog(self).exec()),
                               ("Apri la cartella dei &log", "folder", self._open_logs),
                               ("&Copia informazioni per l'assistenza", "copy", self.copy_support_info)):
            a = QAction(theme.icon(icon, theme.t.text2), text, self)
            self._menu_icons.append((a, icon))
            a.triggered.connect(fn)
            h.addAction(a)
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
        self.back_btn.setEnabled(self.state.can_undo)
        self.fwd_btn.setEnabled(self.state.can_redo)

    def history_dialog(self):
        HistoryDialog(self.state, self).exec()

    def _undo(self):
        if not self.state.undo():
            toast(self, "Non c'è niente da annullare.", "info")

    def _redo(self):
        if not self.state.redo():
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
        SettingsDialog(self.state, self).exec()

    # ------------------------------------------------------------------ progetto
    def confirm_discard(self) -> bool:
        """True se si può chiudere/sostituire il lavoro: già salvato, oppure l'utente ha scelto cosa farne."""
        from ..autosave import clear_recovery
        st = self.state
        if os.environ.get("CONFMERGE_NO_CONFIRM") or not st.project or not st.is_dirty():
            return True
        if st.project_path is not None and st.settings.data.get("autosave_named", True):
            st.autosave()                                # progetto con nome: il salvataggio automatico basta
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Lavoro non salvato")
        box.setText("Hai modifiche non salvate.")
        box.setInformativeText("Vuoi salvare il progetto prima di continuare? Se non lo salvi, il lavoro andrà perso.")
        save = box.addButton("Salva…", QMessageBox.AcceptRole)
        drop = box.addButton("Non salvare", QMessageBox.DestructiveRole)
        box.addButton("Annulla", QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.save_project()
        if box.clickedButton() is drop:
            clear_recovery(st.settings.root)
            return True
        return False

    def new(self):
        if not self.confirm_discard():
            return
        st = self.state
        st.project = None
        st.project_path = None
        st.sources.clear()
        self.simple.reset()
        self.adv.goto(0, animate=False)
        st.reset_history()
        st.mark_clean()
        self._project_changed()

    def save_project(self) -> bool:
        st = self.state
        if not st.project:
            QMessageBox.information(self, "ConfMerge", "Non c'è ancora niente da salvare: prima scegli una cartella e lascia finire l'analisi.")
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
        if not self.confirm_discard():
            return
        f = path or QFileDialog.getOpenFileName(self, "Apri un progetto", "", "Progetto ConfMerge (*.confmerge)")[0]
        if not f:
            return
        try:
            proj = Project.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "ConfMerge", f"Questo file non sembra un progetto valido: {e}")
            return
        self._opening = (None if recovery else Path(f), recovery)
        runner = self.state.analysis
        runner.finished.connect(self._opened)
        runner.failed.connect(lambda m: QMessageBox.critical(self, "ConfMerge", m))
        if self.mode == "simple":
            self.simple.start.stack.setCurrentIndex(1)
        runner.open_project(proj)

    def _opened(self):
        try:
            self.state.analysis.finished.disconnect(self._opened)
        except (TypeError, RuntimeError):
            pass
        path, recovery = getattr(self, "_opening", (None, False))
        self.state.project_path = path
        if recovery:
            self.state._clean_fp = ""                     # il lavoro recuperato non è ancora salvato: resta «da salvare»
        self._project_changed()
        if self.mode == "advanced":
            self.adv.goto(1)
        else:
            self.simple.show_step(1)

    def _autosave(self):
        st = self.state
        if st.analysis.running or not st.project:
            return
        kind = st.autosave()
        if kind:
            hhmm = time.strftime("%H:%M")
            self._saved_note = f"salvato automaticamente alle {hhmm}" if kind == "file" else f"copia di sicurezza alle {hhmm}"
            self._project_changed()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._recovery_checked:
            self._recovery_checked = True
            QTimer.singleShot(600, self._offer_recovery)

    def _offer_recovery(self):
        from ..autosave import clear_recovery, has_recovery, recovery_file, recovery_info
        root = self.state.settings.root
        if os.environ.get("CONFMERGE_NO_RECOVERY") or self.state.project or not has_recovery(root):
            return
        info = recovery_info(root)
        when = time.strftime("%d/%m/%Y alle %H:%M", time.localtime(info["saved_at"])) if info.get("saved_at") else "una volta"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Lavoro non salvato")
        box.setText("Ho trovato un lavoro non salvato.")
        box.setInformativeText(f"L'ultima copia di sicurezza è del {when}. Vuoi riprenderlo?")
        yes = box.addButton("Riprendi il lavoro", QMessageBox.AcceptRole)
        no = box.addButton("Scarta", QMessageBox.DestructiveRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is yes:
            self.open_project(str(recovery_file(root)), recovery=True)
        elif box.clickedButton() is no:
            clear_recovery(root)

    def closeEvent(self, e):
        if not self.confirm_discard():
            e.ignore()
            return
        self._autosave_timer.stop()
        self.state.settings.save()
        for p in (self.simple.check.player.player, self.adv.review.player.player):
            p.stop()
        paths.cleanup_temp()
        super().closeEvent(e)
