"""Schermata 4: immagine, titoli e overlay, lower third, slide/PiP, credito, profili."""
from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QLineEdit, QFrame, QScrollArea, QAbstractItemView, QGridLayout, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox, QPushButton,
                               QSlider, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..credit import CREDIT_TEXT
from ..render.model import Anim, Background, Element, Fill, LowerThird, Outline
from ..spec import ASPECTS, LAYOUTS, RES_SHORT, LayoutSpan, SlideChange, output_size
from . import bind
from .layer_list import LayerList
from .mini_timeline import MiniTimeline
from .widgets import Badge, GhostButton, IconButton, PrimaryButton, SecondaryButton, Section, Toggle, label
from .canvas import Canvas
from .element_editor import ElementEditor
from .player import fmt
from .subtitles_tab import SubtitlesTab
from .titles_tabs import TemplateTab, TransitionsTab


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
        el.fill = Fill("gradient", "#2F80ED", "#22D3EE")
        el.x = el.y = 0.5
    elif kind == "image":
        el.width = 0.12
    return el


class ProfileBar(QWidget):
    """Barra profili, presente in ogni schermata grafica: «salva come profilo»."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel("Profilo:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(180)
        row.addWidget(self.combo, 1)
        col.addLayout(row)
        row = QHBoxLayout()                    # i pulsanti su una seconda riga: la barra non allarga mai la finestra
        for text, fn in (("Applica", self.apply), ("💾 Salva come profilo…", self.save_as), ("Duplica…", self.dup),
                         ("Elimina", self.delete), ("Importa…", self.imp), ("Esporta…", self.exp)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        col.addLayout(row)
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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if which == "main":
            from .brand_card import BrandCard
            lay.addWidget(BrandCard(state, scenes=True))
        self.split = QSplitter(Qt.Horizontal)       # in finestre strette diventa verticale (vedi resizeEvent)
        lay.addWidget(self.split)
        left = QVBoxLayout()
        self.scene_box = Section("Scena", "g:scene")
        self.scene_form = self.scene_box.form()
        left.addWidget(self.scene_box)
        self.list = LayerList()
        self.list.selectedIndex.connect(self.pick)
        self.list.edited.connect(self.on_edit)
        self.list.reordered.connect(self._reorder)
        left.addWidget(label("Livelli: il primo in alto è davanti. Trascina per riordinare.", "caption", True))
        left.addWidget(self.list, 1)
        grid = QGridLayout()
        grid.setSpacing(8)
        for n, (text, kind, ic) in enumerate((("Testo", "text", "type"), ("Logo", "image", "image-plus"),
                                              ("Forma", "shape", "shapes"), ("Barra", "bar", "activity"))):
            b = SecondaryButton(text, ic, f"Aggiungi: {text.lower()}")
            b.clicked.connect(lambda _=False, k=kind: self.add(k))
            grid.addWidget(b, n // 2, n % 2)
        left.addLayout(grid)
        row = QHBoxLayout()
        row.setSpacing(8)
        for ic, tip, fn in (("copy", "Duplica", self.dup), ("arrow-up", "Porta davanti", lambda: self.move(+1)),
                            ("arrow-down", "Porta dietro", lambda: self.move(-1)), ("trash-2", "Elimina", self.delete)):
            b = IconButton(ic, tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        left.addLayout(row)
        lw = QWidget()
        lw.setLayout(left)
        self.list.setMinimumHeight(120)
        lsa = scrolled(lw)
        lsa.setMinimumWidth(345)
        self.lsa = lsa
        self.split.addWidget(lsa)
        self.editor = ElementEditor()
        self.editor.changed.connect(self.on_edit)
        self.split.addWidget(self.editor)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 3)
        self.split.setSizes([360, 600])
        state.profile_changed.connect(self.refresh)
        self.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        vertical = self.width() < 820
        want = Qt.Vertical if vertical else Qt.Horizontal
        if self.split.orientation() != want:
            self.split.setOrientation(want)
            self.lsa.setMaximumWidth(16777215 if vertical else 420)
            self.lsa.setMaximumHeight(16777215)

    def elements(self) -> list[Element]:
        gr = self.state.spec.graphics
        return gr.elements if self.which == "main" else (gr.title.elements if self.which == "title" else gr.outro.elements)

    def scene(self):
        gr = self.state.spec.graphics
        return None if self.which == "main" else (gr.title if self.which == "title" else gr.outro)

    def refresh(self):
        self._build_scene_form()
        els = self.elements()
        cur = self.list.currentRow()
        self.list.set_elements(els, cur if 0 <= cur < len(els) else (len(els) - 1 if els else -1))
        if els:
            self.pick(self.list.currentRow())
        else:
            self.editor.set_element(None)

    def _reorder(self, order: list):
        els = self.elements()
        els[:] = [els[i] for i in order]
        self.refresh()
        self.on_edit()

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
        """d = +1 porta davanti, -1 porta dietro (indice nella lista degli elementi)."""
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
        if 0 <= i < len(self.elements()):
            self.list.update_label(i)
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
                                     style=last.style if last else "bar",
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
        lay.addWidget(bind.check(sl, "enabled", "Usa slide / secondo video", cb))
        for text, fn in (("Scegli PDF o immagini…", self.pick_files), ("Scegli un secondo video…", self.pick_video)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            lay.addWidget(b)
        b = QPushButton("Sincronizza il secondo video")
        b.clicked.connect(self.sync_video)
        lay.addWidget(b)
        self.src = QLabel()
        self.src.setWordWrap(True)
        lay.addWidget(self.src)
        self.sync_badge = Badge("", "info")
        self.sync_badge.setVisible(False)
        lay.addWidget(self.sync_badge, 0, Qt.AlignLeft)
        nudge = QHBoxLayout()
        nudge.addWidget(QLabel("Ritocco a mano (s):"))
        self.off_spin = QDoubleSpinBox()
        self.off_spin.setRange(-120.0, 120.0)
        self.off_spin.setDecimals(2)
        self.off_spin.setSingleStep(0.1)
        self.off_spin.setToolTip("Se nello schermo condiviso qualcosa arriva troppo presto o troppo tardi rispetto al "
                                 "relatore, sposta il secondo video di qualche decimo di secondo.")
        self.off_spin.valueChanged.connect(self._off_changed)
        nudge.addWidget(self.off_spin)
        for txt, d in (("−0,1", -0.1), ("+0,1", 0.1)):
            nb = QPushButton(txt)
            nb.setToolTip("Sposta il secondo video di un decimo di secondo")
            nb.clicked.connect(lambda _=False, dd=d: self.off_spin.setValue(self.off_spin.value() + dd))
            nudge.addWidget(nb)
        nudge.addStretch(1)
        lay.addLayout(nudge)
        split = QVBoxLayout()   # una sotto l'altra: affiancate non ci stanno nel pannello
        g = Section("Cambi di slide", "g:slide-changes")
        gl = g.body_lay
        hint = QLabel("Mentre guardi il video nella schermata «Controlla», premi N a ogni cambio slide.")
        hint.setWordWrap(True)
        hint.setProperty("role", "caption")
        gl.addWidget(hint)
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
        g = Section("Disposizione nel tempo", "g:slide-layouts")
        gl = g.body_lay
        hint = QLabel("Ogni riga vale da quel secondo in poi.")
        hint.setProperty("role", "caption")
        gl.addWidget(hint)
        self.lt = QTableWidget(0, 2)
        self.lt.setHorizontalHeaderLabels(["Tempo (s)", "Layout"])
        self.lt.itemChanged.connect(self.layouts_edited)
        self.lt.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        gl.addWidget(self.lt)
        row = QHBoxLayout()
        self.lay_combo = QComboBox()
        self.lay_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.lay_combo.setMinimumContentsLength(16)
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
        if hasattr(self, "off_spin") and abs(self.off_spin.value() - sl.video_offset) > 1e-6:
            self.off_spin.blockSignals(True)
            self.off_spin.setValue(sl.video_offset)
            self.off_spin.blockSignals(False)
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

    def _off_changed(self, v: float):
        sl = self.state.spec.slides
        if abs(sl.video_offset - v) > 1e-6:
            sl.video_offset = v
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
        from .controllers import sync_quality
        word, kind, why = sync_quality(res.confidence)
        self.sync_badge.set(f"Sincronia: {word}", kind)
        self.sync_badge.setVisible(True)
        self.sync_badge.setToolTip(why)
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


def apply_search(root: QWidget, query: str) -> int:
    """Ricerca rapida: mostra solo le sezioni che contengono la parola cercata (titolo, etichette, interruttori).
    Con la ricerca vuota ripristina solo le sezioni nascoste dalla ricerca stessa."""
    q = query.strip().lower()
    shown = 0
    for sec in root.findChildren(Section):
        if not q:
            if sec.property("hid_by_search"):
                sec.setProperty("hid_by_search", False)
                sec.setVisible(True)
            continue
        texts = [sec.header.text()] + [w.text() for w in sec.findChildren(QLabel)] + \
                [w.text() for w in sec.findChildren(Toggle)] + [w.text() for w in sec.findChildren(QPushButton)]
        hit = any(q in t.lower() for t in texts if t)
        if hit:
            sec.setProperty("hid_by_search", False)
            sec.setVisible(True)
            sec.set_open(True)
            shown += 1
        elif sec.isVisibleTo(root):
            sec.setProperty("hid_by_search", True)
            sec.setVisible(False)
    return shown


TAB_TITLES = {"image": "Formato", "overlay": "Elementi", "title": "Titolo iniziale", "outro": "Schermata finale",
              "lt": "Nome relatore", "caption": "Scritte", "subs": "Sottotitoli", "trans": "Transizioni", "slides": "Slide e PiP", "credit": "Credito"}


class GraphicsPage(QWidget):
    goPhase = Signal(str)          # "decorations": apre la fase «Logo e decorazioni»

    """Spazio di lavoro con l'anteprima sempre visibile a sinistra e le impostazioni a destra.
    `kinds` sceglie le schede: la stessa classe serve per Immagine, Grafica e Slide e PiP."""

    def __init__(self, state, review_page, kinds=("image", "overlay", "title", "outro", "lt", "slides", "credit"),
                 title="Grafica", subtitle="", parent=None):
        super().__init__(parent)
        self.state = state
        self.review = review_page
        self.kinds = tuple(kinds)
        self.canvas = Canvas(state)
        self.canvas.elementMoved.connect(lambda *_: self.state.touch())
        main = QVBoxLayout(self)
        main.addWidget(label(title, "title"))
        if subtitle:
            main.addWidget(label(subtitle, "muted", True))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca un'impostazione…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        self.search.setMaximumWidth(360)
        self.search.textChanged.connect(self._search)
        bar.addWidget(self.search)
        bar.addStretch(1)
        self.undo_btn = IconButton("undo-2", "Annulla (Ctrl+Z)")
        self.redo_btn = IconButton("redo-2", "Ripristina (Ctrl+Maiusc+Z)")
        self.undo_btn.clicked.connect(self.state.undo)
        self.redo_btn.clicked.connect(self.state.redo)
        bar.addWidget(self.undo_btn)
        bar.addWidget(self.redo_btn)
        sv = SecondaryButton("Salva come profilo…", "save", "Salva grafica, credito e impostazioni come profilo con nome")
        sv.clicked.connect(self._save_profile)
        bar.addWidget(sv)
        main.addLayout(bar)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.canvas, 1)
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Momento:"))
        self.tslider = QSlider(Qt.Horizontal)
        self.tslider.setRange(0, 1000)
        self.tslider.valueChanged.connect(self._tchanged)
        trow.addWidget(self.tslider, 1)
        self.tlabel = QLabel("0 s")
        trow.addWidget(self.tlabel)
        ll.addLayout(trow)
        self.mini = MiniTimeline(state)
        self.mini.timeSelected.connect(self._mini_time)
        self.mini.setVisible("overlay" in self.kinds or "title" in self.kinds)
        ll.addWidget(self.mini)
        self.tip = label("Trascina gli elementi sull'anteprima (guide e aggancio al centro e ai margini).", "caption", True)
        ll.addWidget(self.tip)
        split.addWidget(left)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.image_tab = self.ov_main = self.ov_title = self.ov_outro = self.lt_tab = None
        for k in self.kinds:
            if k == "image":
                self.image_tab = ImageTab(state, self)
                self.tabs.addTab(scrolled(self.image_tab), TAB_TITLES[k])
            elif k == "overlay":
                self.ov_main = OverlayTab(state, self, "main")
                self.tabs.addTab(self.ov_main, TAB_TITLES[k])
            elif k == "title":
                self.ov_title = OverlayTab(state, self, "title")
                self.tabs.addTab(scrolled(TemplateTab(state, self, "title", self.ov_title)), TAB_TITLES[k])
            elif k == "outro":
                self.ov_outro = OverlayTab(state, self, "outro")
                self.tabs.addTab(scrolled(TemplateTab(state, self, "outro", self.ov_outro)), TAB_TITLES[k])
            elif k == "lt":
                self.lt_tab = LowerThirdTab(state, self)
                self.tabs.addTab(scrolled(TemplateTab(state, self, "lower_third", self.lt_tab)), TAB_TITLES[k])
            elif k == "caption":
                tt = TemplateTab(state, self, "caption")
                tt.goDecorations.connect(lambda: self.goPhase.emit("decorations"))
                self.tabs.addTab(scrolled(tt), TAB_TITLES[k])
            elif k == "subs":
                self.tabs.addTab(scrolled(SubtitlesTab(state, self)), TAB_TITLES[k])
            elif k == "trans":
                self.tabs.addTab(scrolled(TransitionsTab(state, self)), TAB_TITLES[k])
            elif k == "slides":
                self.tabs.addTab(scrolled(SlidesTab(state, self)), TAB_TITLES[k])
            elif k == "credit":
                self.tabs.addTab(scrolled(CreditTab(state)), TAB_TITLES[k])
        if len(self.kinds) == 1:
            self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self._tab)
        self.tabs.setMinimumWidth(545)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 4)
        main.addWidget(split, 1)
        if self.image_tab:
            self.canvas.cropChanged.connect(self.image_tab.set_crop)
        self.canvas.elementPicked.connect(self._picked)
        state.spec_changed.connect(self.canvas.update)
        state.spec_changed.connect(self._undo_state)
        state.profile_changed.connect(self._undo_state)
        self._undo_state()

    def _undo_state(self):
        self.undo_btn.setEnabled(self.state.can_undo)
        self.redo_btn.setEnabled(self.state.can_redo)

    def _save_profile(self):
        name, ok = QInputDialog.getText(self, "Salva come profilo", "Nome del profilo (es. canale o evento):",
                                        text=self.state.profile_name)
        if ok and name.strip():
            self.state.save_profile(name.strip())

    def _search(self, q: str):
        apply_search(self.tabs.currentWidget(), q)

    def review_pos(self) -> float:
        return self.review.player.position()

    def showEvent(self, e):
        super().showEvent(e)
        self.canvas.set_frame(self.state.last_frame)
        self._tab(self.tabs.currentIndex())

    def _tab(self, i: int):
        w = self.tabs.widget(i)
        w = self._inner(w)
        c = self.canvas
        c.mode = "video"
        c.scene = None
        c.scene_target = "main"
        c.elements_override = None
        if self.ov_title is not None and w is self.ov_title:
            c.mode, c.scene, c.scene_target = "scene", self.state.spec.graphics.title, "title"
            c.seg_dur = c.scene.duration
        elif self.ov_outro is not None and w is self.ov_outro:
            c.mode, c.scene, c.scene_target = "scene", self.state.spec.graphics.outro, "outro"
            c.seg_dur = c.scene.duration
        else:
            c.seg_dur = 1e9
        if isinstance(w, OverlayTab):
            w.refresh()
        self._range()
        c.set_frame(self.state.last_frame)
        c.update()
        self._search(self.search.text())

    def _inner(self, w):
        """Cerca l'editor dentro la scheda (le schede sono avvolte in un'area con scroll)."""
        if isinstance(w, QScrollArea):
            w = w.widget()
        return getattr(w, "inner", None) or w

    def after_template(self, kind: str):
        """Dopo la scelta di un modello: ridisegna e mostra un momento in cui il testo è visibile."""
        self._tab(self.tabs.currentIndex())
        if kind in ("title", "outro"):
            sc = self.state.spec.graphics.title if kind == "title" else self.state.spec.graphics.outro
            self.tslider.setValue(int(min(0.6, 1.8 / max(sc.duration, 1.0)) * 1000))
        elif kind == "lower_third" and self.state.spec.graphics.lower_thirds:
            self.seek_out(self.state.spec.graphics.lower_thirds[0].start + 1.5)
        elif kind == "caption":
            self.seek_out(3.5)

    def seek_out(self, t: float):
        self.tslider.setValue(int(min(1.0, t / max(self._max_t, 1e-6)) * 1000))

    def _range(self):
        c = self.canvas
        if c.mode == "scene" and c.scene:
            self._max_t = c.scene.duration
        else:
            self._max_t = max(1.0, self.state.trim_end - self.state.trim_start) if self.state.project else 30.0
        self.mini.set_scene(c.scene if c.mode == "scene" else None, self._max_t)
        start = int(min(0.6, 1.8 / max(self._max_t, 1.0)) * 1000) if c.mode == "scene" else 0   # testi già visibili
        self.tslider.blockSignals(True)
        self.tslider.setValue(start)
        self.tslider.blockSignals(False)
        self._tchanged(start)

    def _tchanged(self, v: int):
        t = v / 1000 * getattr(self, "_max_t", 10.0)
        self.tlabel.setText(f"{t:.1f} s")
        self.canvas.set_time(t)
        self.mini.set_time(t)

    def _mini_time(self, t: float):
        self.tslider.setValue(int(t / max(self._max_t, 1e-6) * 1000))

    def _picked(self, i: int):
        w = self._inner(self.tabs.currentWidget())
        if isinstance(w, OverlayTab) and i >= 0:
            w.list.setCurrentRow(i)
