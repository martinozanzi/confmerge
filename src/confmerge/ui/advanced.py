"""Modalità Avanzata: barra laterale delle fasi + spazio di lavoro (anteprima a sinistra, proprietà a destra)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from .audio_page import AudioPage
from .export_page import ExportPage
from .graphics_page import GraphicsPage
from .pages import AnalysisPage, SelectPage
from .review_page import ReviewPage
from .widgets import SideNav
from .widgets.anim import fade_in

class _WidthWatcher(QObject):
    """Avvisa quando cambia la larghezza visibile di un contenitore con scroll."""

    def __init__(self, target, callback):
        super().__init__(target)
        self.callback = callback
        target.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            self.callback(obj.width())
        return False


PHASES = [("folder-open", "Sorgenti"), ("audio-waveform", "Sincronia e tagli"), ("image", "Immagine"),
          ("layers", "Grafica"), ("presentation", "Slide e PiP"), ("volume-2", "Audio"), ("download", "Export e coda")]


class AdvancedShell(QWidget):
    phaseChanged = Signal(int)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.visited: set[int] = {0}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = SideNav(PHASES)
        self.nav.setFixedWidth(232)
        lay.addWidget(self.nav)
        self.stack = QStackedWidget()
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.addWidget(self.stack)
        lay.addWidget(body, 1)

        # 0 Sorgenti (selezione + avanzamento dell'analisi)
        self.src_stack = QStackedWidget()
        self.select = SelectPage(state)
        self.analysis = AnalysisPage(state)
        self.src_stack.addWidget(self.select)
        self.src_stack.addWidget(self.analysis)
        self.stack.addWidget(self.src_stack)
        self.review = ReviewPage(state)
        self.stack.addWidget(self.review)
        self.image = GraphicsPage(state, self.review, ("image",), "Immagine",
                                  "Formato, ritaglio, zoom e dissolvenze. L'anteprima mostra il risultato.")
        self.graphics = GraphicsPage(state, self.review, ("overlay", "title", "outro", "lt", "credit"), "Grafica",
                                     "Titoli, logo, testi, lower third, schermata finale e credito.")
        self.slides = GraphicsPage(state, self.review, ("slides",), "Slide e PiP",
                                   "Slide a schermo intero o in piccolo accanto al relatore.")
        self.audio = AudioPage(state)
        self.export = ExportPage(state, self.review)
        for w in (self.image, self.graphics, self.slides, self.audio):
            self.stack.addWidget(w)
        from .graphics_page import scrolled
        sa = scrolled(self.export)
        self._export_filter = _WidthWatcher(sa.viewport(), self.export.set_available_width)
        self.stack.addWidget(sa)

        self.nav.selected.connect(self.goto)
        self.select.analyzeRequested.connect(self.start_analysis)
        state.analysis.finished.connect(self._analysis_done)
        state.analysis.failed.connect(self._analysis_failed)
        state.analysis.cancelled.connect(lambda: self.src_stack.setCurrentIndex(0))
        state.project_changed.connect(self.refresh_nav)
        state.review.trimChanged.connect(self.refresh_nav)
        self.refresh_nav()
        self.goto(0, animate=False)

    # --- navigazione
    def start_analysis(self):
        if not self.state.sources.ready:
            return
        self.src_stack.setCurrentIndex(1)
        self.analysis.start()

    def _analysis_done(self):
        if self.isVisible() or True:
            self.src_stack.setCurrentIndex(0)
            self.visited.add(0)
            self.goto(1)

    def _analysis_failed(self, msg: str):
        self.src_stack.setCurrentIndex(0)
        if self.isVisible():
            QMessageBox.critical(self, "Non sono riuscito ad analizzare i video",
                                 msg + "\n\nIl dettaglio è nel file di log (menu Aiuto → Apri la cartella dei log).")

    def goto(self, i: int, animate: bool = True) -> None:
        if i > 0 and not self.state.project:
            i = 0
        self.stack.setCurrentIndex(i)
        self.nav.set_current(i)
        self.visited.add(i)
        self.refresh_nav()
        w = self.stack.currentWidget()
        if animate:
            fade_in(w, slide=10)
        if i == 1:
            self.review.setFocus()
        self.phaseChanged.emit(i)

    def refresh_nav(self) -> None:
        has = self.state.project is not None
        pr = self.state.project
        for i in range(len(PHASES)):
            if i == 0:
                st = "done" if has else "idle"
            elif not has:
                st = "locked"
            elif i == 1:
                st = "done" if (pr and pr.trim_confirmed) else "idle"
            else:
                st = "done" if i in self.visited else "idle"
            self.nav.set_state(i, st)

    def current(self) -> int:
        return self.stack.currentIndex()
