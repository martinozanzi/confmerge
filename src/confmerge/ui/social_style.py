"""Studio Social, passo «Aspetto»: testi e immagini sul video e modelli di stile."""
from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QSlider, QVBoxLayout,
                               QWidget)

from .. import style_templates as ST
from ..overlay_library import OverlayLibrary
from ..render.anchors import ANCHORS
from ..render.model import Element, Fill, Outline, Shadow
from ..render.text_renderer import is_video_overlay
from . import bind
from .widgets import Card, GhostButton, SecondaryButton, label


def new_text(state, anchor: str = "tc") -> Element:
    kit = state.kits.get(state.spec.brand.kit_id) if state.spec.brand.kit_id else None
    return Element(id=uuid.uuid4().hex[:6], kind="text", text="Il tuo testo", size=0.055, bold=True, anchor=anchor, fit_width=0.86,
                   font=kit.font_body if kit else "Poppins", fill=Fill(color=kit.colors.text if kit else "#FFFFFF"),
                   outline=Outline(0.004, "#000000"), shadow=Shadow(enabled=True, opacity=0.6), targets=["main"])


class OverlaysCard(Card):
    """Testi e immagini sempre nello stesso punto (angoli e lati), anche cambiando formato: dentro le zone sicure."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.add(label("Testi e overlay sul video", "h2", True))
        self.add(label("Titolo fisso, @canale, adesivi, immagini o video con sfondo trasparente (PNG, GIF, WebM, MOV). Restano nel punto "
                       "scelto in ogni formato; puoi metterne quanti vuoi.", "caption", True))
        self.library = OverlayLibrary(state.settings.root)
        self.rows = QVBoxLayout()
        self.lay.addLayout(self.rows)
        r = QHBoxLayout()
        a = SecondaryButton("Aggiungi un testo", "type")
        a.clicked.connect(self.add_text)
        b = SecondaryButton("Aggiungi un overlay…", "image-plus")
        b.setToolTip("Immagine o video, anche con sfondo trasparente")
        b.clicked.connect(self.add_image)
        r.addWidget(a)
        r.addWidget(b)
        r.addStretch(1)
        self.lay.addLayout(r)
        lr = QHBoxLayout()
        self.saved = QComboBox()
        self.saved.activated.connect(self._add_saved)
        lr.addWidget(self.saved, 1)
        self.del_saved = GhostButton("Elimina")
        self.del_saved.setToolTip("Toglie dai salvati l'overlay scelto nel menu")
        self.del_saved.clicked.connect(self._delete_saved)
        lr.addWidget(self.del_saved)
        self.lay.addLayout(lr)
        state.profile_changed.connect(self.sync)
        self.sync()

    def _refresh_saved(self) -> None:
        names = self.library.list()
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem("Overlay salvati: aggiungi…" if names else "Nessun overlay salvato", "")
        for n in names:
            self.saved.addItem(n, n)
        self.saved.blockSignals(False)
        self.saved.setEnabled(bool(names))
        self.del_saved.setEnabled(bool(names))

    def _add_saved(self, _=0):
        name = self.saved.currentData()
        el = self.library.load(name) if name else None
        if el:
            self.state.spec.graphics.elements.append(el)
            self.state.touch()
            self.sync()

    def _delete_saved(self):
        name = self.saved.currentData()
        if name and QMessageBox.question(self, "Elimina l'overlay", f"Togliere «{name}» dai salvati?") == QMessageBox.Yes:
            self.library.delete(name)
            self._refresh_saved()

    def save_element(self, el: Element):
        name, ok = QInputDialog.getText(self, "Salva l'overlay", "Nome (es. Bollino «Diretta»):")
        if ok and name.strip():
            self.library.save(name.strip(), el)
            self._refresh_saved()

    def elements(self) -> list[Element]:
        return [e for e in self.state.spec.graphics.elements if "main" in e.targets and e.kind in ("text", "image", "clip")]

    def _set_anchor(self, el, anchor: str) -> None:
        """Passando a «Libero» l'elemento resta dove si vede (non salta alla posizione scritta nel modello)."""
        if not anchor and el.anchor:
            from ..render import anchors
            from dataclasses import replace
            r = anchors.resolve([replace(el)], 1920, 1080, self.state.spec.brand.safe)[0]
            el.x, el.y = r.x, r.y
        el.anchor = anchor

    def sync(self):
        self._refresh_saved()
        while self.rows.count():
            it = self.rows.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for e in self.elements():
            self.rows.addWidget(self._row(e))

    def _row(self, e: Element) -> QWidget:
        st = self.state
        box = Card(flat=True, padding=6)
        top = QHBoxLayout()
        if e.kind == "text":
            ed = QLineEdit(e.text)
            ed.textEdited.connect(lambda t, el=e: (setattr(el, "text", t), st.touch()))
            top.addWidget(ed, 1)
            top.addWidget(bind.color(e.fill, "color", st.touch))
        else:
            top.addWidget(label(Path(e.path).name or "immagine", "", False), 1)
        keep = GhostButton("Salva")
        keep.setToolTip("Salva questo overlay per riusarlo in altri lavori")
        keep.clicked.connect(lambda _=False, el=e: self.save_element(el))
        top.addWidget(keep)
        look = GhostButton("Aspetto…")
        look.setToolTip("Carattere, colori, contorno, ombra, sfondo, animazione…")
        look.clicked.connect(lambda _=False, el=e: self.customize(el))
        top.addWidget(look)
        rm = GhostButton("Togli")
        rm.clicked.connect(lambda _=False, el=e: self.remove(el))
        top.addWidget(rm)
        box.lay.addLayout(top)
        row = QHBoxLayout()
        anchor = QComboBox()
        anchor.addItem("Libero", "")
        for k, v in ANCHORS.items():
            anchor.addItem(v, k)
        anchor.setCurrentIndex(max(0, anchor.findData(e.anchor)))
        anchor.currentIndexChanged.connect(lambda _, el=e, c=anchor: (self._set_anchor(el, c.currentData()), st.touch()))
        row.addWidget(anchor, 1)
        row.addWidget(label("Grandezza", "caption"))
        sl = QSlider(Qt.Horizontal)
        if e.kind == "text":
            sl.setRange(20, 150)
            sl.setValue(round(e.size * 1000))
            sl.valueChanged.connect(lambda v, el=e: (setattr(el, "size", v / 1000), st.touch()))
        else:
            sl.setRange(40, 600)
            sl.setValue(round(e.width * 1000))
            sl.valueChanged.connect(lambda v, el=e: (setattr(el, "width", v / 1000), st.touch()))
        row.addWidget(sl, 1)
        box.lay.addLayout(row)
        return box

    def customize(self, el: Element):
        """Finestra con tutte le proprietà dell'elemento: l'anteprima dietro si aggiorna a ogni modifica."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        from .element_editor import ElementEditor
        dlg = QDialog(self)
        dlg.setWindowTitle("Aspetto del testo" if el.kind == "text" else "Aspetto dell'immagine")
        dlg.resize(460, 640)
        lay = QVBoxLayout(dlg)
        ed = ElementEditor(show_targets=False)
        from ..spec import output_size
        ed.frame_wh = output_size(self.state.spec.image, self.state.spec.export)
        ed.changed.connect(self.state.touch)
        ed.set_element(el)
        lay.addWidget(ed, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec()
        self.sync()

    def add_text(self):
        self.state.spec.graphics.elements.append(new_text(self.state))
        self.state.touch()
        self.sync()

    def add_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "Scegli l'overlay", "",
                                           "Immagini e overlay (*.png *.svg *.jpg *.jpeg *.webp *.gif *.webm *.mov)")
        if not f:
            return
        kind = "clip" if is_video_overlay(f) else "image"                  # GIF, WebM e MOV si muovono: sono video
        e = Element(id=uuid.uuid4().hex[:6], kind=kind, path=f, width=0.14, anchor="tr", targets=["main"])
        self.state.spec.graphics.elements.append(e)
        self.state.touch()
        self.sync()

    def remove(self, el: Element):
        els = self.state.spec.graphics.elements
        if el in els:
            els.remove(el)
        self.state.touch()
        self.sync()


class StyleTemplateCard(Card):
    """Modelli di stile: sottotitoli, loghi, testi e immagini salvati con un nome e riapplicabili con un clic."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.store = ST.StyleStore(state.settings.root)
        self.add(label("Modello di stile", "h2", True))
        self.add(label("Salva sottotitoli (tipo, grandezza, posizione), loghi, testi e immagini come modello e riusalo negli altri video.",
                       "caption", True))
        self.combo = QComboBox()
        self.combo.activated.connect(self._applied)
        self.add(self.combo)
        r = QHBoxLayout()
        sv = SecondaryButton("Salva lo stile attuale…", "save")
        sv.clicked.connect(self.save)
        dl = GhostButton("Elimina")
        dl.clicked.connect(self.delete)
        r.addWidget(sv)
        r.addWidget(dl)
        r.addStretch(1)
        self.lay.addLayout(r)
        self.sync()

    def sync(self, select: str = ""):
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("Scegli un modello…", "")
        for n in self.store.list():
            self.combo.addItem(n, n)
        self.combo.setCurrentIndex(max(0, self.combo.findData(select)))
        self.combo.blockSignals(False)

    def _applied(self, _):
        name = self.combo.currentData()
        data = self.store.load(name) if name else None
        if data:
            ST.apply(self.state.spec, data)
            self.state.touch()
            self.state.profile_changed.emit()          # le schede (sottotitoli, marchio, testi) si ricostruiscono

    def save(self):
        name, ok = QInputDialog.getText(self, "Salva il modello", "Nome del modello (es. Reel del sindaco):")
        if ok and name.strip():
            self.store.save(name.strip(), self.state.spec)
            self.sync(name.strip())

    def delete(self):
        name = self.combo.currentData()
        if name and QMessageBox.question(self, "Elimina il modello", f"Eliminare «{name}»?") == QMessageBox.Yes:
            self.store.delete(name)
            self.sync()
