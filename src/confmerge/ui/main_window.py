"""Finestra principale: wizard a schermate con indietro/avanti."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import paths, proxy
from ..ffmpeg_wrapper import decode_audio_mono
from ..media_scan import media_info
from ..project import Project
from ..worker import Worker
from .about import AboutDialog
from .export_page import ExportPage
from .graphics_page import CreditTab, GraphicsPage, ProfileBar
from .pages import AnalysisPage, ReviewPage, SelectPage
from .state import AppState

STEPS = ["Selezione", "Analisi", "Revisione", "Grafica", "Export"]


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None):
        super().__init__()
        self.state = state or AppState()
        self.setWindowTitle("ConfMerge")
        self.resize(1280, 820)
        self.stack = QStackedWidget()
        self.select = SelectPage(self.state)
        self.analysis = AnalysisPage(self.state)
        self.review = ReviewPage(self.state)
        self.graphics = GraphicsPage(self.state, self.review)
        self.export = ExportPage(self.state, self.review)
        for p in (self.select, self.analysis, self.review, self.graphics, self.export):
            self.stack.addWidget(p)
        central = QWidget()
        lay = QVBoxLayout(central)
        self.crumb = QLabel()
        lay.addWidget(self.crumb)
        lay.addWidget(self.stack, 1)
        row = QHBoxLayout()
        self.back = QPushButton("◀ Indietro")
        self.next = QPushButton("Avanti ▶")
        self.back.clicked.connect(self.go_back)
        self.next.clicked.connect(self.go_next)
        row.addWidget(self.back)
        row.addStretch(1)
        row.addWidget(self.next)
        lay.addLayout(row)
        self.setCentralWidget(central)
        self._menus()
        self.select.ready.connect(lambda ok: self.next.setEnabled(ok and self.stack.currentIndex() == 0))
        self.analysis.done.connect(lambda: self.show_step(2))
        self.analysis.failed.connect(lambda: self.show_step(0))
        self.show_step(0)
        self.select.refresh()

    def _menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        for text, fn, key in (("&Nuovo", self.new, QKeySequence.New), ("&Apri progetto…", self.open_project, QKeySequence.Open),
                              ("&Salva progetto…", self.save_project, QKeySequence.Save)):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(fn)
            f.addAction(a)
        f.addSeparator()
        q = QAction("&Esci", self)
        q.triggered.connect(self.close)
        f.addAction(q)
        s = mb.addMenu("&Impostazioni")
        a = QAction("&Credito e profili…", self)
        a.triggered.connect(self.settings_dialog)
        s.addAction(a)
        h = mb.addMenu("&Aiuto")
        a = QAction("&Informazioni", self)
        a.triggered.connect(lambda: AboutDialog(self).exec())
        h.addAction(a)

    def settings_dialog(self):
        d = QDialog(self)
        d.setWindowTitle("Impostazioni — Credito e profili")
        lay = QVBoxLayout(d)
        lay.addWidget(ProfileBar(self.state))
        lay.addWidget(CreditTab(self.state))
        d.resize(780, 320)
        d.exec()

    # --- navigazione
    def show_step(self, i: int):
        self.stack.setCurrentIndex(i)
        self.crumb.setText(" › ".join(f"<b>{s}</b>" if k == i else s for k, s in enumerate(STEPS)))
        self.back.setEnabled(i in (2, 3, 4))
        self.next.setVisible(i != 1 and i != 4)
        self.next.setEnabled(i != 0 or bool(self.select.videos and self.select.audio))
        self.next.setText("Analizza ▶" if i == 0 else "Avanti ▶")
        if i == 2:
            self.review.setFocus()

    def go_back(self):
        i = self.stack.currentIndex()
        self.show_step(0 if i == 2 else i - 1)

    def go_next(self):
        i = self.stack.currentIndex()
        if i == 0:
            if not (self.select.videos and self.select.audio):
                return
            self.show_step(1)
            self.analysis.start(self.select.videos, self.select.audio, self.select.slides)
        elif i == 2:
            if self.state.project and self.state.project.trim_start is None and self.state.project.suggested_start is not None:
                r = QMessageBox.question(self, "Taglio", "Nessun taglio impostato: esportare il video intero?\n"
                                         "(Puoi applicare il taglio suggerito nella Revisione.)")
                if r != QMessageBox.Yes:
                    return
            self.show_step(3)
        else:
            self.show_step(i + 1)

    # --- progetto
    def new(self):
        self.state.project = None
        self.select.videos, self.select.audio, self.select.slides, self.select.infos = [], None, [], []
        self.select.refresh()
        self.show_step(0)

    def save_project(self):
        if not self.state.project:
            QMessageBox.information(self, "ConfMerge", "Nessun progetto da salvare: esegui prima l'analisi.")
            return
        f, _ = QFileDialog.getSaveFileName(self, "Salva progetto", "", "Progetto ConfMerge (*.confmerge)")
        if f:
            self.state.sync_spec_to_project()
            self.state.project.save(f if f.endswith(".confmerge") else f + ".confmerge")

    def open_project(self):
        f, _ = QFileDialog.getOpenFileName(self, "Apri progetto", "", "Progetto ConfMerge (*.confmerge)")
        if not f:
            return
        try:
            proj = Project.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "ConfMerge", f"Progetto non valido: {e}")
            return
        self.show_step(1)
        st = self.state

        def job(cancel, report):
            clips = [media_info(c) for c in proj.clips]
            report(0.2, "Lettura dell'audio…")
            cam = []
            import numpy as np
            for c in clips:
                cam.append(decode_audio_mono(c.path, 8000, c.duration) if c.has_audio else np.zeros(int(c.duration * 8000), np.float32))
            ext = decode_audio_mono(proj.audio, 8000)
            report(0.5, "Creazione dell'anteprima…")
            out = paths.temp_dir() / "proxy.mp4"
            proxy.build_proxy(proj, clips, out, lambda fr, s: report(0.5 + fr * 0.5), cancel)
            return clips, np.concatenate(cam), ext, out

        w = Worker(job)
        w.progress.connect(lambda fr, m: (self.analysis.bar.setValue(int(fr * 1000)), m and self.analysis.msg.setText(m)))

        def ok(res):
            st.clips, st.cam, st.ext, st.proxy = res
            st.load_project(proj)
            self.show_step(2)
        w.finished_ok.connect(ok)
        w.failed.connect(lambda m: (QMessageBox.critical(self, "ConfMerge", m), self.show_step(0)))
        self.analysis.worker = w
        w.start()

    def closeEvent(self, e):
        self.state.settings.save()
        for p in (self.review.player.player,):
            p.stop()
        paths.cleanup_temp()
        super().closeEvent(e)
