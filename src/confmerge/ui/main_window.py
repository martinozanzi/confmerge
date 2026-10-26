"""Finestra principale: intestazione (titolo, profilo, modalità, tema) e due viste sullo stesso progetto."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import paths
from ..project import Project
from .about import AboutDialog
from .advanced import AdvancedShell
from .brand import app_icon, logo_pixmap
from .settings_dialog import SettingsDialog, ShortcutsDialog
from .simple import SimpleShell
from .state import AppState
from .theme import S1, S2, S3, theme
from .widgets import IconButton, Segmented, label, toast
from .widgets.anim import fade_in


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
        self.project_lbl = label("Nessun progetto", "muted")
        row.addWidget(self.project_lbl)
        row.addStretch(1)
        row.addWidget(label("Profilo:", "muted"))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(190)
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
        pr = self.state.project
        self.project_lbl.setText("·  " + (Path(pr.clips[0]).parent.name or "Nuovo progetto") if pr else "Nessun progetto")

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
    def new(self):
        st = self.state
        st.project = None
        st.sources.clear()
        self.simple.reset()
        self.adv.goto(0, animate=False)
        self._project_changed()

    def save_project(self):
        if not self.state.project:
            QMessageBox.information(self, "ConfMerge", "Non c'è ancora niente da salvare: prima scegli una cartella e lascia finire l'analisi.")
            return
        f, _ = QFileDialog.getSaveFileName(self, "Salva il progetto", "", "Progetto ConfMerge (*.confmerge)")
        if f:
            self.state.sync_spec_to_project()
            self.state.project.save(f if f.endswith(".confmerge") else f + ".confmerge")
            toast(self, "Progetto salvato.", "ok")

    def open_project(self):
        f, _ = QFileDialog.getOpenFileName(self, "Apri un progetto", "", "Progetto ConfMerge (*.confmerge)")
        if not f:
            return
        try:
            proj = Project.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "ConfMerge", f"Questo file non sembra un progetto valido: {e}")
            return
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
        if self.mode == "advanced":
            self.adv.goto(1)
        else:
            self.simple.show_step(1)

    def closeEvent(self, e):
        self.state.settings.save()
        for p in (self.simple.check.player.player, self.adv.review.player.player):
            p.stop()
        paths.cleanup_temp()
        super().closeEvent(e)
