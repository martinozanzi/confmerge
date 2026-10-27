"""Schede della sezione «Titoli e scritte»: modelli pronti + campi di testo + (in fondo) l'editor dettagliato."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import templates as T
from .. import transitions as TR
from ..render.model import VARIABLES, LowerThird
from . import bind
from .template_gallery import TemplateGallery, VariablesForm
from .transition_gallery import TransitionGallery
from .widgets import SecondaryButton, Section, label

KIND_INFO = {
    "title": ("Titolo iniziale", "Scegli lo stile del titolo che appare all'inizio, poi scrivi i testi. Passa il mouse sulle anteprime per i dettagli."),
    "outro": ("Schermata finale", "La schermata che chiude il video (ringraziamenti, iscrizione al canale…)."),
    "lower_third": ("Nome del relatore", "Il nome e il ruolo che compaiono in basso quando parla qualcuno. Lo stile vale per tutti i relatori."),
    "caption": ("Scritte sul video", "Aggiungi una scritta (data, hashtag, citazione…) con un clic. Poi si sposta trascinandola sull'anteprima."),
}


def scene_variables(spec, kind: str) -> list[str]:
    gr = spec.graphics
    sc = gr.title if kind == "title" else gr.outro
    texts = [e.text for e in sc.elements if e.kind == "text"]
    return [k for k in VARIABLES if any("{" + k + "}" in t for t in texts)]


class TemplateTab(QWidget):
    """Una scheda a modelli. `inner` è l'editor dettagliato già esistente (OverlayTab o LowerThirdTab)."""
    goDecorations = Signal()

    def __init__(self, state, page, kind: str, inner: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.state, self.page, self.kind, self.inner = state, page, kind, inner
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        title, hint = KIND_INFO[kind]
        lay.addWidget(label(hint, "muted", True))
        self.gallery = TemplateGallery(kind)
        self.gallery.picked.connect(self._picked)
        lay.addWidget(self.gallery)
        self.vars_box = QWidget()
        self.vars_lay = QVBoxLayout(self.vars_box)
        self.vars_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.vars_box)
        self.note = label("", "caption", True)
        lay.addWidget(self.note)
        if kind == "caption":
            b = SecondaryButton("Sposta o modifica le scritte…", "layers", "Apre «Logo e grafica»")
            b.clicked.connect(self.goDecorations)
            row = QHBoxLayout()
            row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
        if inner is not None:
            self.detail = Section("Modifica ogni dettaglio", f"detail:{kind}", opened=False)
            self.detail.body_lay.addWidget(inner)
            inner.setMinimumHeight(480)
            lay.addWidget(self.detail)
        lay.addStretch(1)
        state.profile_changed.connect(self.sync)
        state.spec_changed.connect(self._spec_changed)
        self.sync()

    # --- stato
    def current_id(self) -> str:
        gr = self.state.spec.graphics
        return gr.title_template if self.kind == "title" else gr.outro_template if self.kind == "outro" else ""

    def sync(self):
        self.gallery.set_current(self.current_id())
        self._rebuild_vars()

    def _spec_changed(self):
        if getattr(self, "_keys", None) != self._wanted_keys():
            self._rebuild_vars()

    def _wanted_keys(self) -> list[str]:
        if self.kind in ("title", "outro"):
            return scene_variables(self.state.spec, self.kind)
        if self.kind == "lower_third":
            return []
        return []

    def _rebuild_vars(self):
        while self.vars_lay.count():
            it = self.vars_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._keys = self._wanted_keys()
        if self._keys:
            self.vars_lay.addWidget(label("Testi", "h3"))
            self.vars_lay.addWidget(VariablesForm(self.state, self._keys))
        if self.kind == "lower_third":
            n = len(self.state.spec.graphics.lower_thirds)
            self.note.setText("Nomi e ruoli si scrivono nella tabella qui sotto («Modifica ogni dettaglio»)." if n else
                              "Non c'è ancora nessun nome: scegliendo uno stile ne creo uno, poi lo modifichi nella tabella.")
        elif self.kind in ("title", "outro"):
            sc = self.state.spec.graphics.title if self.kind == "title" else self.state.spec.graphics.outro
            self.note.setText("" if sc.enabled else "Questa schermata è disattivata: scegliendo un modello viene attivata.")

    # --- azioni
    def _picked(self, tid: str):
        st, spec = self.state, self.state.spec
        if self.kind == "title":
            T.apply_title(spec, tid)
            spec.graphics.title.enabled = True
        elif self.kind == "outro":
            T.apply_outro(spec, tid)
            spec.graphics.outro.enabled = True
        elif self.kind == "lower_third":
            if not spec.graphics.lower_thirds:
                spec.graphics.lower_thirds.append(LowerThird(name="Nome Cognome", role="Ruolo", start=3.0,
                                                             font=st.settings.data.get("font", "Segoe UI")))
            T.apply_lower_third_style(spec, tid)
        else:
            T.add_caption(spec, tid)
            self.note.setText("Scritta aggiunta. Per spostarla o cambiarla usa «Sposta o modifica le scritte».")
        st.touch()
        if self.inner is not None and hasattr(self.inner, "refresh"):
            self.inner.refresh()
        self.page.after_template(self.kind)
        self._rebuild_vars()


class TransitionsTab(QWidget):
    """Tre scelte semplici: dal titolo al video, tra le clip, dal video alla schermata finale."""

    def __init__(self, state, page, parent=None):
        super().__init__(parent)
        self.state, self.page = state, page
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(label("Come si passa da una scena all'altra. Passa il mouse su un effetto per vederlo in movimento.",
                            "muted", True))
        self.sections: list[tuple[Section, TransitionGallery]] = []
        self._add("Dal titolo al video", "t1", lambda: state.spec.graphics.title, False)
        self._add("Tra una clip e l'altra", "t2", None, True)
        self._add("Dal video alla schermata finale", "t3", lambda: state.spec.graphics.outro, False)
        lay.addStretch(1)
        state.profile_changed.connect(self.sync)
        self.sync()

    def _add(self, title: str, key: str, scene_fn, join: bool):
        sec = Section(title, f"trans:{key}", opened=True)
        gal = TransitionGallery("cut" if join else "fade", join_only=join)
        sec.body_lay.addWidget(gal)
        sec.form_ = sec.form()
        sec.note = label("", "caption", True)
        sec.body_lay.addWidget(sec.note)
        sec.scene_fn, sec.join = scene_fn, join
        gal.picked.connect(lambda tid, j=join, f=scene_fn: self._picked(tid, j, f))
        self.layout().addWidget(sec)
        self.sections.append((sec, gal))

    def sync(self):
        st = self.state
        for sec, gal in self.sections:
            while sec.form_.rowCount():
                sec.form_.removeRow(0)
            if sec.join:
                im = st.spec.image
                gal.set_current(im.clip_transition)
                n = len(st.clips)
                sec.note.setText("" if n > 1 else "Hai una sola clip: questo effetto si userà solo se ne aggiungi altre.")
                sec.form_.addRow("Durata (s)", bind.spin(im, "clip_transition_dur", 0.2, 2.0, 0.1, 1, "", 1, st.touch))
            else:
                sc = sec.scene_fn()
                gal.set_current(sc.transition)
                sec.note.setText("" if sc.enabled else "Questa schermata è disattivata nel profilo.")
                if sc.over_video:
                    sec.note.setText("Il titolo è sopra il video: non serve una transizione.")
                sec.form_.addRow("Durata (s)", bind.spin(sc, "fade", 0.2, 3.0, 0.1, 1, "", 1, st.touch))

    def _picked(self, tid: str, join: bool, scene_fn):
        st = self.state
        tr = TR.get(tid)
        if join:
            st.spec.image.clip_transition = tid
        else:
            sc = scene_fn()
            sc.transition = tid
            if tr.duration:
                sc.fade = tr.duration
        st.touch()
        self.sync()
