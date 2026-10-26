"""Schermata 4: immagine, titoli e overlay, lower third, slide/PiP, credito, profili."""
from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QScrollArea, QAbstractItemView, QGridLayout, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox, QPushButton,
                               QSlider, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..credit import CREDIT_TEXT
from ..render.model import Anim, Background, Element, Fill, LowerThird, Outline
from ..spec import ASPECTS, LAYOUTS, RES_SHORT, LayoutSpan, SlideChange, output_size
from . import bind
from .widgets import IconButton, SecondaryButton, Section
from .canvas import Canvas
from .element_editor import ElementEditor
from .player import fmt


def scrolled(w: QWidget) -> QScrollArea:
    """Scheda con scroll verticale: il contenuto prende l'altezza che gli serve, mai schiacciato."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)   # mai contenuto tagliato in silenzio
    sa.setWidget(w)
    return sa


def new_element(kind: str, font: str = "Segoe UI") -> Element:
    el = Element(id=uuid.uuid4().hex[:6], kind=kind, font=font)
    if kind == "text":
        el.text = "Nuovo testo"
        el.shadow.enabled = True
    elif kind == "shape":
        el.fill = Fill(color="#E94F37")
    elif kind == "bar":
        el.kind, el.thickness, el.radius = "bar", 0.008, 0.004
        el.fill = Fill("gradient", "#00C2FF", "#7B2FF7")
        el.x = el.y = 0.5
    elif kind == "image":
        el.width = 0.12
    return el


class ProfileBar(QWidget):
    """Barra profili, presente in ogni schermata grafica: «salva come profilo»."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Profilo:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(180)
        row.addWidget(self.combo)
        for text, fn in (("Applica", self.apply), ("💾 Salva come profilo…", self.save_as), ("Duplica…", self.dup),
                         ("Elimina", self.delete), ("Importa…", self.imp), ("Esporta…", self.exp)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        state.profile_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        names = self.state.settings.list_profiles()
        if self.state.profile_name not in names:
            names.append(self.state.profile_name)
        self.combo.addItems(names)
        self.combo.setCurrentText(self.state.profile_name)
        self.combo.blockSignals(False)

    def apply(self):
        self.state.apply_profile(self.combo.currentText())

    def save_as(self):
        name, ok = QInputDialog.getText(self, "Salva come profilo", "Nome del profilo (es. canale o evento):",
                                        text=self.state.profile_name)
        if ok and name.strip():
            self.state.save_profile(name.strip())

    def dup(self):
        name, ok = QInputDialog.getText(self, "Duplica profilo", "Nome della copia:", text=self.combo.currentText() + " copia")
        if ok and name.strip():
            self.state.settings.duplicate_profile(self.combo.currentText(), name.strip())
            self.refresh()

    def delete(self):
        n = self.combo.currentText()
        if QMessageBox.question(self, "ConfMerge", f"Eliminare il profilo «{n}»?") == QMessageBox.Yes:
            self.state.settings.delete_profile(n)
            self.refresh()

    def imp(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importa profilo", "", "Profilo ConfMerge (*.json)")
        if f:
            try:
                self.state.settings.import_profile(f)
            except (ValueError, OSError) as e:
                QMessageBox.warning(self, "ConfMerge", f"Profilo non valido: {e}")
            self.refresh()

    def exp(self):
        n = self.combo.currentText()
        f, _ = QFileDialog.getSaveFileName(self, "Esporta profilo", f"{n}.json", "Profilo ConfMerge (*.json)")
        if f:
            self.state.save_profile(n)
            self.state.settings.export_profile(n, f)


class ImageTab(QWidget):
    def __init__(self, state, page, parent=None):
        super().__init__(parent)
        self.state, self.page = state, page
        self.build()
        state.profile_changed.connect(self.build)

    def build(self):
        old = self.layout()
        if old:
            QWidget().setLayout(old)
        im = self.state.spec.image
        cb = self.state.touch
        lay = QVBoxLayout(self)
        g = Section("Formato di uscita", "g:" + "Formato di uscita")
        f = g.form()
        f.addRow("Risoluzione (lato corto)", bind.combo(im, "resolution", list(RES_SHORT), cb))
        f.addRow("Formato", bind.combo(im, "aspect", [*ASPECTS, ("Personalizzato", "custom")], cb))
        f.addRow("Personalizzato L", bind.spin(im, "custom_w", 1, 100, 1, 1, "", 1, cb))
        f.addRow("Personalizzato A", bind.spin(im, "custom_h", 1, 100, 1, 1, "", 1, cb))
        f.addRow("Fps (0 = originali)", self._fps(im, cb))
        f.addRow("Video verticali / formato diverso", bind.combo(im, "vertical_mode", [("Bande nere", "bars"), ("Ritaglia", "crop")], cb))
        lay.addWidget(g)
        g = Section("Ritaglio (% rimosso dai lati)", "g:" + "Ritaglio (% rimosso dai lati)")
        f = g.form()
        self.crop_spins = []
        for lab, a in (("Sinistra", "crop_l"), ("Alto", "crop_t"), ("Destra", "crop_r"), ("Basso", "crop_b")):
            s = bind.spin(im, a, 0, 90, 0.5, 1, "", 100, cb)
            self.crop_spins.append(s)
            f.addRow(lab, s)
        self.draw_btn = QPushButton("✂ Disegna il ritaglio sull'anteprima")
        self.draw_btn.setCheckable(True)
        self.draw_btn.toggled.connect(self.toggle_crop)
        f.addRow(self.draw_btn)
        rb = QPushButton("Azzera ritaglio")
        rb.clicked.connect(self.reset_crop)
        f.addRow(rb)
        lay.addWidget(g)
        g = Section("Zoom e posizione", "g:" + "Zoom e posizione")
        f = g.form()
        f.addRow("Zoom", bind.spin(im, "zoom", 1, 5, 0.05, 2, "×", 1, cb))
        f.addRow("Centro X (%)", bind.spin(im, "cx", 0, 100, 1, 0, "", 100, cb))
        f.addRow("Centro Y (%)", bind.spin(im, "cy", 0, 100, 1, 0, "", 100, cb))
        f.addRow(bind.check(im, "kenburns", "Zoom animato (Ken Burns) tra due inquadrature", lambda: (cb(), None)))
        f.addRow("Zoom finale", bind.spin(im, "zoom2", 1, 5, 0.05, 2, "×", 1, cb))
        f.addRow("Centro X finale (%)", bind.spin(im, "cx2", 0, 100, 1, 0, "", 100, cb))
        f.addRow("Centro Y finale (%)", bind.spin(im, "cy2", 0, 100, 1, 0, "", 100, cb))
        f.addRow("Da (s di uscita)", bind.spin(im, "kb_t0", 0, 36000, 1, 1, "", 1, cb))
        f.addRow("A (s di uscita)", bind.spin(im, "kb_t1", 0, 36000, 1, 1, "", 1, cb))
        lay.addWidget(g)
        g = Section("Dissolvenze video e audio", "g:" + "Dissolvenze video e audio")
        f = g.form()
        f.addRow("In apertura (s)", bind.spin(im, "fade_in", 0, 10, 0.1, 1, "", 1, cb))
        f.addRow("In chiusura (s)", bind.spin(im, "fade_out", 0, 10, 0.1, 1, "", 1, cb))
        lay.addWidget(g)
        lay.addStretch(1)

    def _fps(self, im, cb):
        w = QDoubleSpinBox()
        w.setRange(0, 120)
        w.setValue(im.fps or 0)
        w.valueChanged.connect(lambda v: (setattr(im, "fps", v or None), cb()))
        return w

    def toggle_crop(self, on: bool):
        self.page.canvas.mode = "crop" if on else "video"
        self.page.canvas.update()

    def reset_crop(self):
        im = self.state.spec.image
        im.crop_l = im.crop_t = im.crop_r = im.crop_b = 0.0
        for s in self.crop_spins:
            s.setValue(0)
        self.state.touch()

    def set_crop(self, l, t, r, b):
        im = self.state.spec.image
        im.crop_l, im.crop_t, im.crop_r, im.crop_b = l, t, r, b
        for s, v in zip(self.crop_spins, (l, t, r, b)):
            s.blockSignals(True)
            s.setValue(v * 100)
            s.blockSignals(False)
        self.draw_btn.setChecked(False)
        self.state.touch()


class OverlayTab(QWidget):
    """Elenco di elementi (overlay globali, titolo iniziale o schermata finale) + editor delle proprietà."""

    def __init__(self, state, page, which: str, parent=None):
        super().__init__(parent)
        self.state, self.page, self.which = state, page, which   # which: main | title | outro
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.scene_box = Section("Scena", "g:scene")
        self.scene_form = self.scene_box.form()
        left.addWidget(self.scene_box)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.pick)
        left.addWidget(self.list, 1)
        grid = QGridLayout()
        grid.setSpacing(8)
        for n, (text, kind, ic) in enumerate((("Testo", "text", "type"), ("Logo / immagine", "image", "image-plus"),
                                              ("Forma", "shape", "shapes"), ("Barra", "bar", "activity"))):
            b = SecondaryButton(text, ic, f"Aggiungi: {text.lower()}")
            b.clicked.connect(lambda _=False, k=kind: self.add(k))
            grid.addWidget(b, n // 2, n % 2)
        left.addLayout(grid)
        row = QHBoxLayout()
        row.setSpacing(8)
        for ic, tip, fn in (("copy", "Duplica", self.dup), ("arrow-up", "Sposta su", lambda: self.move(-1)),
                            ("arrow-down", "Sposta giù", lambda: self.move(1)), ("trash-2", "Elimina", self.delete)):
            b = IconButton(ic, tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        left.addLayout(row)
        lw = QWidget()
        lw.setLayout(left)
        self.list.setMinimumHeight(120)
        lsa = scrolled(lw)
        lsa.setMinimumWidth(270)
        lsa.setMaximumWidth(360)
        lay.addWidget(lsa)
        self.editor = ElementEditor()
        self.editor.changed.connect(self.on_edit)
        lay.addWidget(self.editor, 1)
        state.profile_changed.connect(self.refresh)
        self.refresh()

    def elements(self) -> list[Element]:
        gr = self.state.spec.graphics
        return gr.elements if self.which == "main" else (gr.title.elements if self.which == "title" else gr.outro.elements)

    def scene(self):
        gr = self.state.spec.graphics
        return None if self.which == "main" else (gr.title if self.which == "title" else gr.outro)

    def refresh(self):
        self._build_scene_form()
        cur = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        names = {"text": "Testo", "image": "Immagine", "shape": "Forma", "bar": "Barra"}
        for e in self.elements():
            label = e.text.replace("\n", " ")[:28] if e.kind == "text" else (Path(e.path).name if e.kind == "image" and e.path else "")
            self.list.addItem(f"{names.get(e.kind, e.kind)} {label}".strip())
        self.list.blockSignals(False)
        if self.elements():
            self.list.setCurrentRow(min(max(cur, 0), len(self.elements()) - 1))
        else:
            self.editor.set_element(None)

    def _build_scene_form(self):
        while self.scene_form.rowCount():
            self.scene_form.removeRow(0)
        sc = self.scene()
        self.scene_box.setVisible(sc is not None)
        if sc is None:
            return
        cb = self.on_edit
        self.scene_form.addRow(bind.check(sc, "enabled", "Attivo", cb))
        if self.which == "title":
            self.scene_form.addRow(bind.check(sc, "over_video", "Sopra il video (sfondo trasparente)", cb))
        self.scene_form.addRow("Durata (s)", bind.spin(sc, "duration", 0.5, 60, 0.5, 1, "", 1, cb))
        self.scene_form.addRow("Dissolvenza (s)", bind.spin(sc, "fade", 0, 3, 0.1, 1, "", 1, cb))
        bg = sc.background
        self.scene_form.addRow("Sfondo", bind.combo(bg, "kind", [("Nero", "black"), ("Tinta unita", "solid"),
                                                                 ("Sfumatura", "gradient"), ("Immagine", "image"),
                                                                 ("Trasparente", "transparent")], cb))
        self.scene_form.addRow("Colore", bind.color(bg, "color", cb))
        self.scene_form.addRow("Colore 2", bind.color(bg, "color2", cb))
        self.scene_form.addRow("Immagine", self._bg_image(bg))

    def _bg_image(self, bg):
        b = QPushButton(Path(bg.path).name if bg.path else "Scegli…")

        def pick():
            p, _ = QFileDialog.getOpenFileName(self, "Immagine di sfondo", "", "Immagini (*.png *.jpg *.jpeg)")
            if p:
                bg.path = p
                b.setText(Path(p).name)
                self.on_edit()
        b.clicked.connect(pick)
        return b

    def pick(self, i: int):
        els = self.elements()
        self.editor.frame_wh = self.page.canvas.frame_size()
        self.editor.set_element(els[i] if 0 <= i < len(els) else None)
        self.page.canvas.selected = i
        self.page.canvas.update()

    def add(self, kind: str):
        self.elements().append(new_element(kind, self.state.settings.data.get("font", "Segoe UI")))
        if kind == "image":
            p, _ = QFileDialog.getOpenFileName(self, "Immagine / logo", "", "Immagini (*.png *.svg *.jpg *.jpeg)")
            if p:
                self.elements()[-1].path = p
        self.refresh()
        self.list.setCurrentRow(len(self.elements()) - 1)
        self.on_edit()

    def dup(self):
        i = self.list.currentRow()
        if i >= 0:
            e = Element.from_dict(self.elements()[i].to_dict())
            e.id = uuid.uuid4().hex[:6]
            e.x, e.y = min(e.x + 0.03, 1), min(e.y + 0.03, 1)
            self.elements().insert(i + 1, e)
            self.refresh()
            self.list.setCurrentRow(i + 1)
            self.on_edit()

    def delete(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.elements()[i]
            self.refresh()
            self.on_edit()

    def move(self, d: int):
        i = self.list.currentRow()
        els = self.elements()
        j = i + d
        if 0 <= i < len(els) and 0 <= j < len(els):
            els[i], els[j] = els[j], els[i]
            self.refresh()
            self.list.setCurrentRow(j)
            self.on_edit()

    def on_edit(self):
        i = self.list.currentRow()
        els = self.elements()
        if 0 <= i < len(els):
            e = els[i]
            names = {"text": "Testo", "image": "Immagine", "shape": "Forma", "bar": "Barra"}
            label = e.text.replace("\n", " ")[:28] if e.kind == "text" else (Path(e.path).name if e.kind == "image" and e.path else "")
            it = self.list.item(i)
            if it:
                it.setText(f"{names.get(e.kind, e.kind)} {label}".strip())
        self.state.touch()
        self.page.canvas.update()


class LowerThirdTab(QWidget):
    def __init__(self, state, page, parent=None):
        super().__init__(parent)
        self.state, self.page = state, page
        lay = QVBoxLayout(self)
        hint = QLabel("Un lower third per relatore, con tempi propri (secondi dall'inizio del video di uscita).")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nome", "Ruolo", "Inizio (s)", "Durata (s)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self.edited)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, fn in (("+ Aggiungi", self.add), ("Aggiungi alla posizione corrente", self.add_here), ("Elimina", self.delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.style_box = Section("Stile e animazione", "g:lt-style")
        self.style_form = self.style_box.form()
        lay.addWidget(self.style_box)
        self.table.currentCellChanged.connect(lambda r, *_: self.build_style(r))
        state.profile_changed.connect(self.refresh)
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def lts(self) -> list[LowerThird]:
        return self.state.spec.graphics.lower_thirds

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for lt in self.lts():
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate((lt.name, lt.role, f"{lt.start:g}", f"{lt.duration:g}")):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)
        self.build_style(0)

    def build_style(self, r: int):
        while self.style_form.rowCount():
            self.style_form.removeRow(0)
        if not (0 <= r < len(self.lts())):
            return
        lt = self.lts()[r]
        cb = self.state.touch
        self.style_form.addRow("Colore accento", bind.color(lt, "accent", cb))
        self.style_form.addRow("Posizione X (%)", bind.spin(lt, "x", 0, 90, 1, 0, "", 100, cb))
        self.style_form.addRow("Posizione Y (%)", bind.spin(lt, "y", 5, 95, 1, 0, "", 100, cb))
        from .element_editor import ANIM_LABELS, EASE_LABELS
        kinds = [(ANIM_LABELS[k], k) for k in ("none", "fade", "slide_left", "slide_right", "slide_up", "slide_down", "pop", "reveal", "blur")]
        eases = [(EASE_LABELS[k], k) for k in EASE_LABELS]
        for title, a in (("Entrata", lt.anim_in), ("Uscita", lt.anim_out)):
            self.style_form.addRow(title, bind.combo(a, "kind", kinds, cb))
            self.style_form.addRow("  durata (s)", bind.spin(a, "duration", 0.1, 5, 0.1, 2, "", 1, cb))
            self.style_form.addRow("  curva", bind.combo(a, "easing", eases, cb))

    def edited(self, it: QTableWidgetItem):
        r, c = it.row(), it.column()
        if r >= len(self.lts()):
            return
        lt = self.lts()[r]
        try:
            if c == 0:
                lt.name = it.text()
            elif c == 1:
                lt.role = it.text()
            elif c == 2:
                lt.start = max(0.0, float(it.text().replace(",", ".")))
            else:
                lt.duration = max(0.5, float(it.text().replace(",", ".")))
        except ValueError:
            pass
        self.state.touch()

    def add(self, start: float | None = None):
        last = self.lts()[-1] if self.lts() else None
        s = start if isinstance(start, float) else ((last.start + last.duration + 5) if last else 10.0)
        self.lts().append(LowerThird(name="Nome Cognome", role="Ruolo", start=round(s, 1),
                                     font=self.state.settings.data.get("font", "Segoe UI")))
        self.refresh()
        self.state.touch()

    def add_here(self):
        self.add(max(0.0, round(self.state.to_out(self.page.review_pos()), 1)))

    def delete(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.lts()):
            del self.lts()[r]
            self.refresh()
            self.state.touch()


class SlidesTab(QWidget):
    def __init__(self, state, page, parent=None):
        super().__init__(parent)
        self.state, self.page = state, page
        lay = QVBoxLayout(self)
        self.build(lay)
        state.profile_changed.connect(lambda: None)
        state.spec_changed.connect(self.refresh_tables)

    def build(self, lay):
        sl = self.state.spec.slides
        cb = self.state.touch
        top = QHBoxLayout()
        top.addWidget(bind.check(sl, "enabled", "Usa slide / secondo video", cb))
        for text, fn in (("Scegli PDF/immagini…", self.pick_files), ("Scegli secondo video…", self.pick_video),
                         ("Sincronizza secondo video", self.sync_video)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            top.addWidget(b)
        top.addStretch(1)
        lay.addLayout(top)
        self.src = QLabel()
        self.src.setWordWrap(True)
        lay.addWidget(self.src)
        split = QHBoxLayout()
        g = Section("Cambi slide (premi N nella Revisione mentre guardi il video)", "g:slide-changes")
        gl = g.body_lay
        self.ct = QTableWidget(0, 2)
        self.ct.setHorizontalHeaderLabels(["Tempo (s)", "Slide n."])
        self.ct.itemChanged.connect(self.changes_edited)
        gl.addWidget(self.ct)
        b = QPushButton("+ Cambio alla posizione corrente")
        b.clicked.connect(self.add_change)
        gl.addWidget(b)
        b = QPushButton("Elimina")
        b.clicked.connect(lambda: self.del_row(self.ct, sl.changes))
        gl.addWidget(b)
        split.addWidget(g)
        g = Section("Layout nella timeline (da questo istante in poi)", "g:slide-layouts")
        gl = g.body_lay
        self.lt = QTableWidget(0, 2)
        self.lt.setHorizontalHeaderLabels(["Tempo (s)", "Layout"])
        self.lt.itemChanged.connect(self.layouts_edited)
        self.lt.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        gl.addWidget(self.lt)
        row = QHBoxLayout()
        self.lay_combo = QComboBox()
        for k, v in LAYOUTS.items():
            self.lay_combo.addItem(v, k)
        row.addWidget(self.lay_combo, 1)
        b = QPushButton("+ Aggiungi qui")
        b.clicked.connect(self.add_layout)
        row.addWidget(b)
        gl.addLayout(row)
        b = QPushButton("Elimina")
        b.clicked.connect(lambda: self.del_row(self.lt, sl.layouts))
        gl.addWidget(b)
        split.addWidget(g)
        lay.addLayout(split, 1)
        g = Section("Riquadro piccolo (PiP)", "g:" + "Riquadro piccolo (PiP)")
        f = g.form()
        pip = sl.pip
        f.addRow("Angolo", bind.combo(pip, "corner", [("In basso a destra", "br"), ("In basso a sinistra", "bl"),
                                                       ("In alto a destra", "tr"), ("In alto a sinistra", "tl")], cb))
        f.addRow("Dimensione (% larghezza)", bind.spin(pip, "size", 8, 60, 1, 0, "", 100, cb))
        f.addRow("Margine (%)", bind.spin(pip, "margin", 0, 15, 0.5, 1, "", 100, cb))
        f.addRow("Bordo (% altezza)", bind.spin(pip, "border", 0, 3, 0.1, 2, "", 100, cb))
        f.addRow("Colore bordo", bind.color(pip, "border_color", cb))
        f.addRow("Angoli (% altezza)", bind.spin(pip, "radius", 0, 10, 0.2, 1, "", 100, cb))
        f.addRow(bind.check(pip, "shadow", "Ombra", cb))
        lay.addWidget(g)
        self.refresh_tables()

    def refresh_tables(self):
        sl = self.state.spec.slides
        self.src.setText("Sorgente: " + (", ".join(Path(f).name for f in sl.files) if sl.files else
                                         (f"video {Path(sl.video).name} (offset {sl.video_offset * 1000:+.0f} ms)" if sl.video else "nessuna")))
        for t, rows in ((self.ct, [(f"{c.t:g}", str(c.index + 1)) for c in sl.changes]),
                        (self.lt, [(f"{s.t:g}", LAYOUTS.get(s.layout, s.layout)) for s in sl.layouts])):
            t.blockSignals(True)
            t.setRowCount(len(rows))
            for r, vals in enumerate(rows):
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    if t is self.lt and c == 1:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    t.setItem(r, c, it)
            t.blockSignals(False)

    def pick_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Slide", "", "Slide (*.pdf *.png *.jpg *.jpeg)")
        if fs:
            sl = self.state.spec.slides
            sl.files, sl.video, sl.enabled = fs, "", True
            self.refresh_tables()
            self.state.touch()

    def pick_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "Secondo video (cattura schermo)", "", "Video (*.mp4 *.mov *.m4v *.mkv)")
        if f:
            sl = self.state.spec.slides
            sl.video, sl.files, sl.enabled = f, [], True
            self.refresh_tables()
            self.state.touch()

    def sync_video(self):
        """Sincronizza il secondo video con lo stesso metodo (GCC-PHAT) usato per l'audio esterno."""
        st, sl = self.state, self.state.spec.slides
        if not sl.video or st.cam is None:
            QMessageBox.information(self, "ConfMerge", "Scegli prima un secondo video e analizza il progetto.")
            return
        from ..ffmpeg_wrapper import decode_audio_mono
        from ..sync import analyze_sync
        try:
            ext = decode_audio_mono(sl.video, 8000)
            res = analyze_sync(st.cam, ext, check_drift=False)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "ConfMerge", f"Sincronizzazione non riuscita: {e}")
            return
        sl.video_offset = res.offset_s
        msg = f"Offset del secondo video: {res.offset_s * 1000:+.0f} ms (confidenza {res.confidence:.1f})"
        if res.low_confidence:
            msg += "\n⚠ Confidenza bassa: il secondo video potrebbe non avere audio utile."
        QMessageBox.information(self, "ConfMerge", msg)
        self.refresh_tables()
        st.touch()

    def add_change(self):
        sl = self.state.spec.slides
        t = max(0.0, round(self.state.to_out(self.page.review_pos()), 2))
        sl.changes.append(SlideChange(t, (max((c.index for c in sl.changes), default=-1) + 1)))
        sl.changes.sort(key=lambda c: c.t)
        self.refresh_tables()
        self.state.touch()

    def add_layout(self):
        sl = self.state.spec.slides
        t = max(0.0, round(self.state.to_out(self.page.review_pos()), 2))
        sl.layouts = [s for s in sl.layouts if abs(s.t - t) > 1e-3] + [LayoutSpan(t, self.lay_combo.currentData())]
        sl.layouts.sort(key=lambda s: s.t)
        self.refresh_tables()
        self.state.touch()

    def del_row(self, table, lst):
        r = table.currentRow()
        if 0 <= r < len(lst):
            del lst[r]
            self.refresh_tables()
            self.state.touch()

    def changes_edited(self, it):
        sl = self.state.spec.slides
        r = it.row()
        try:
            if it.column() == 0:
                sl.changes[r].t = max(0.0, float(it.text().replace(",", ".")))
            else:
                sl.changes[r].index = max(0, int(it.text()) - 1)
        except (ValueError, IndexError):
            return
        self.state.touch()

    def layouts_edited(self, it):
        sl = self.state.spec.slides
        try:
            if it.column() == 0:
                sl.layouts[it.row()].t = max(0.0, float(it.text().replace(",", ".")))
        except (ValueError, IndexError):
            return
        self.state.touch()


class CreditTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        self.g = Section("Credito finale", "g:credit")
        self.f = self.g.form()
        lay.addWidget(self.g)
        lay.addStretch(1)
        state.profile_changed.connect(self.build)
        self.build()

    def build(self):
        while self.f.rowCount():
            self.f.removeRow(0)
        c = self.state.spec.credit
        cb = self.state.touch
        info = QLabel(f"Dopo la schermata finale: «{CREDIT_TEXT}» e il link al repository (in inglese, su fondo nero, "
                      "con dissolvenza in entrata e uscita). L'impostazione è salvata nel profilo.")
        info.setWordWrap(True)
        info.setProperty("role", "muted")
        self.f.addRow(info)
        self.f.addRow(bind.check(c, "enabled", "Aggiungi il credito «Created with ConfMerge»", cb))
        self.f.addRow("Durata (s, 2–5)", bind.spin(c, "duration", 2, 5, 0.5, 1, "", 1, cb))
        self.f.addRow(bind.check(c, "qr", "Mostra anche un QR code del repository", cb))


class GraphicsPage(QWidget):
    def __init__(self, state, review_page, parent=None):
        super().__init__(parent)
        self.state = state
        self.review = review_page
        self.canvas = Canvas(state)
        self.canvas.elementMoved.connect(lambda *_: self.state.touch())
        main = QVBoxLayout(self)
        main.addWidget(QLabel("<h2>4. Grafica</h2>"))
        main.addWidget(ProfileBar(state))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.canvas, 1)
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Tempo anteprima:"))
        self.tslider = QSlider(Qt.Horizontal)
        self.tslider.setRange(0, 1000)
        self.tslider.valueChanged.connect(self._tchanged)
        trow.addWidget(self.tslider, 1)
        self.tlabel = QLabel("0.0 s")
        trow.addWidget(self.tlabel)
        ll.addLayout(trow)
        self.tip = QLabel("Trascina gli elementi sull'anteprima (guide e snap al centro/margini).")
        ll.addWidget(self.tip)
        split.addWidget(left)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.image_tab = ImageTab(state, self)
        self.tabs.addTab(scrolled(self.image_tab), "Immagine")
        self.ov_main = OverlayTab(state, self, "main")
        self.ov_title = OverlayTab(state, self, "title")
        self.ov_outro = OverlayTab(state, self, "outro")
        self.tabs.addTab(self.ov_main, "Overlay")
        self.tabs.addTab(self.ov_title, "Titolo")
        self.tabs.addTab(self.ov_outro, "Finale")
        self.tabs.addTab(scrolled(LowerThirdTab(state, self)), "Lower third")
        self.tabs.addTab(scrolled(SlidesTab(state, self)), "Slide e PiP")
        self.tabs.addTab(scrolled(CreditTab(state)), "Credito")
        self.tabs.currentChanged.connect(self._tab)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 4)
        main.addWidget(split, 1)
        self.canvas.cropChanged.connect(self.image_tab.set_crop)
        self.canvas.elementPicked.connect(self._picked)
        state.spec_changed.connect(self.canvas.update)

    def review_pos(self) -> float:
        return self.review.player.position()

    def showEvent(self, e):
        super().showEvent(e)
        self.canvas.set_frame(self.state.last_frame)
        self._tab(self.tabs.currentIndex())

    def _tab(self, i: int):
        w = self.tabs.widget(i)
        c = self.canvas
        c.mode = "video"
        c.scene = None
        c.scene_target = "main"
        c.elements_override = None
        if w is self.ov_title:
            c.mode, c.scene, c.scene_target = "scene", self.state.spec.graphics.title, "title"
            c.seg_dur = c.scene.duration
        elif w is self.ov_outro:
            c.mode, c.scene, c.scene_target = "scene", self.state.spec.graphics.outro, "outro"
            c.seg_dur = c.scene.duration
        else:
            c.seg_dur = 1e9
        if isinstance(w, OverlayTab):
            w.refresh()
        self._range()
        c.set_frame(self.state.last_frame)
        c.update()

    def _range(self):
        c = self.canvas
        if c.mode == "scene" and c.scene:
            self._max_t = c.scene.duration
        else:
            self._max_t = max(1.0, self.state.trim_end - self.state.trim_start) if self.state.project else 30.0
        self.tslider.blockSignals(True)
        self.tslider.setValue(0)
        self.tslider.blockSignals(False)
        self._tchanged(0)

    def _tchanged(self, v: int):
        t = v / 1000 * getattr(self, "_max_t", 10.0)
        self.tlabel.setText(f"{t:.1f} s")
        self.canvas.set_time(t)

    def _picked(self, i: int):
        w = self.tabs.currentWidget()
        if isinstance(w, OverlayTab) and i >= 0:
            w.list.setCurrentRow(i)
