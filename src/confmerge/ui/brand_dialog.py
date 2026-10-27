"""Kit del marchio: un elenco di marchi (anche molti), ognuno con colori, caratteri, slogan e loghi."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QSlider,
                               QSplitter, QVBoxLayout, QWidget)

from .. import brand
from ..brand_kit import CORNERS, ROLES, BrandKit, KitLogo
from ..render import compositor
from ..render.model import substitute
from . import bind
from .graphics_page import scrolled
from .widgets import Card, GhostButton, SecondaryButton, Segmented, Toggle, label

PREVIEW_W, PREVIEW_H = 480, 270


class BrandDialog(QDialog):
    """Gestione dei marchi. `chosen(kit_id)` quando si preme «Usa questo marchio»."""
    chosen = Signal(str)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state, self.store = state, state.kits
        self.kit: BrandKit | None = None
        self.setWindowTitle("Kit del marchio")
        self.resize(980, 680)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Kit del marchio", "h2"))
        lay.addWidget(label("Un marchio per ogni associazione, partito o candidato: colori, caratteri, slogan e loghi. "
                            "Lo scegli poi con un clic in ogni lavoro.", "muted", True))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._pick)
        ll.addWidget(self.list, 1)
        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setSpacing(6)
        for n, (text, ic, fn) in enumerate((("Nuovo", "plus", self.new), ("Duplica", "copy", self.duplicate),
                                            ("Elimina", "trash-2", self.delete), ("Importa…", "download", self.import_kit),
                                            ("Esporta…", "upload", self.export_kit))):
            b = SecondaryButton(text, ic)
            b.clicked.connect(fn)
            grid.addWidget(b, n // 2, n % 2)
        ll.addLayout(grid)
        left.setMinimumWidth(260)
        split.addWidget(left)
        self.editor = QWidget()
        self.ed_lay = QVBoxLayout(self.editor)
        self.ed_lay.setSpacing(10)
        sa = scrolled(self.editor)
        split.addWidget(sa)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([240, 740])
        lay.addWidget(split, 1)
        bb = QDialogButtonBox()
        self.use_btn = bb.addButton("Usa questo marchio nel lavoro", QDialogButtonBox.AcceptRole)
        bb.addButton("Chiudi", QDialogButtonBox.RejectRole)
        self.use_btn.clicked.connect(self._use)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.refresh_list(self.state.spec.brand.kit_id)

    # --- elenco
    def refresh_list(self, select: str = ""):
        kits = self.store.list()
        self.list.blockSignals(True)
        self.list.clear()
        for k in kits:
            it = QListWidgetItem(k.name)
            it.setData(Qt.UserRole, k.id)
            self.list.addItem(it)
        self.list.blockSignals(False)
        if kits:
            i = next((n for n, k in enumerate(kits) if k.id == select), 0)
            self.list.blockSignals(True)
            self.list.setCurrentRow(i)
            self.list.blockSignals(False)
            self._pick(i)
        else:
            self.kit = None
            self._build_editor()

    def _pick(self, row: int):
        it = self.list.item(row)
        self.kit = self.store.get(it.data(Qt.UserRole)) if it else None
        self._build_editor()

    def new(self):
        name, ok = QInputDialog.getText(self, "Nuovo marchio", "Nome del marchio (es. il nome dell'associazione):")
        if ok and name.strip():
            self.refresh_list(self.store.new(name.strip()).id)

    def duplicate(self):
        if self.kit:
            k = self.store.duplicate(self.kit.id)
            if k:
                self.refresh_list(k.id)

    def delete(self):
        if self.kit and QMessageBox.question(self, "Elimina il marchio", f"Eliminare «{self.kit.name}» con i suoi loghi?") == QMessageBox.Yes:
            kid = self.kit.id
            self.store.delete(kid)
            if self.state.spec.brand.kit_id == kid:
                brand.clear_kit(self.state.spec)
                self.state.touch()
            self.refresh_list()

    def import_kit(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importa un marchio", "", "Kit del marchio (*.zip)")
        if f:
            try:
                self.refresh_list(self.store.import_zip(f).id)
            except (OSError, ValueError, KeyError) as e:
                QMessageBox.warning(self, "ConfMerge", f"Non riesco a importarlo: {e}")

    def export_kit(self):
        if self.kit:
            f, _ = QFileDialog.getSaveFileName(self, "Esporta il marchio", f"{self.kit.name}.zip", "Kit del marchio (*.zip)")
            if f:
                self.store.export_zip(self.kit.id, f)

    # --- editor
    def _build_editor(self):
        while self.ed_lay.count():
            it = self.ed_lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)           # via subito: niente schede vecchie che restano sovrapposte
                it.widget().deleteLater()
        kit = self.kit
        self.use_btn.setEnabled(kit is not None)
        if kit is None:
            self.ed_lay.addWidget(label("Non c'è ancora nessun marchio. Premi «Nuovo» per crearne uno.", "muted", True))
            self.ed_lay.addStretch(1)
            return
        cb = self._changed
        c1 = Card()
        c1.add(label("Nome e slogan", "h2", True))
        f = QFormLayout()
        name = QLineEdit(kit.name)
        name.textEdited.connect(lambda t: (setattr(kit, "name", t), self._changed(rename=True)))
        f.addRow("Nome", name)
        f.addRow("Slogan", bind.line(kit, "slogan", cb))
        f.addRow("Canale o social", bind.line(kit, "social", cb))
        c1.lay.addLayout(f)
        self.ed_lay.addWidget(c1)
        c2 = Card()
        c2.add(label("Colori", "h2", True))
        f = QFormLayout()
        from ..brand_kit import COLOR_NAMES
        for attr, nm in COLOR_NAMES.items():
            f.addRow(nm, bind.color(kit.colors, attr, cb))
        c2.lay.addLayout(f)
        self.ed_lay.addWidget(c2)
        c3 = Card()
        c3.add(label("Caratteri", "h2", True))
        f = QFormLayout()
        for attr, nm in (("font_title", "Titoli"), ("font_body", "Testi e sottotitoli")):
            fc = QFontComboBox()
            fc.setCurrentFont(QFont(getattr(kit, attr)))
            fc.currentFontChanged.connect(lambda fnt, a=attr: (setattr(kit, a, fnt.family()), self._changed()))
            f.addRow(nm, fc)
        c3.lay.addLayout(f)
        seg = Segmented([("Sfondo colorato", "box"), ("Bordo scuro", "outline")])
        seg.setValue(kit.caption_style)
        seg.changed.connect(lambda v: (setattr(kit, "caption_style", v), self._changed()))
        c3.add(label("Sottotitoli:", "caption"))
        c3.add(seg)
        self.ed_lay.addWidget(c3)
        c4 = Card()
        c4.add(label("Loghi", "h2", True))
        c4.add(label("Meglio PNG con sfondo trasparente. Il «simbolo» è quello del partito o del movimento.", "caption", True))
        self.logo_box = QVBoxLayout()
        c4.lay.addLayout(self.logo_box)
        add = SecondaryButton("Aggiungi un logo…", "image-plus")
        add.clicked.connect(self.add_logo)
        c4.add(add)
        self.ed_lay.addWidget(c4)
        self._fill_logos()
        c5 = Card()
        c5.add(label("Dove si mettono sul video", "h2", True))
        f = QFormLayout()
        f.addRow("Logo principale", bind.combo(kit, "main_corner", [(v, k) for k, v in CORNERS.items()], cb))
        f.addRow("Simbolo", bind.combo(kit, "symbol_corner", [(v, k) for k, v in CORNERS.items()], cb))
        f.addRow("Grandezza (%)", bind.spin(kit, "logo_size", 4, 30, 0.5, 1, "", 100, cb))
        c5.lay.addLayout(f)
        self.ed_lay.addWidget(c5)
        c6 = Card()
        c6.add(label("Anteprima", "h2", True))
        self.preview = QLabel()
        self.preview.setFixedSize(PREVIEW_W, PREVIEW_H)
        c6.add(self.preview)
        self.ed_lay.addWidget(c6)
        self.ed_lay.addStretch(1)
        self._preview()

    def _fill_logos(self):
        while self.logo_box.count():
            it = self.logo_box.takeAt(0)
            if it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
            elif it.widget():
                it.widget().deleteLater()
        kit = self.kit
        for lg in kit.logos:
            row = QHBoxLayout()
            ic = QLabel()
            path = self.store.logo_path(kit, lg)
            if path:
                ic.setPixmap(QPixmap(path).scaled(56, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            ic.setFixedWidth(60)
            row.addWidget(ic)
            nm = QLineEdit(lg.name)
            nm.textEdited.connect(lambda t, l=lg: (setattr(l, "name", t), self._changed()))
            row.addWidget(nm, 1)
            role = bind.combo(lg, "role", [(v, k) for k, v in ROLES.items()], self._changed)
            row.addWidget(role, 1)
            rm = GhostButton("Togli")
            rm.clicked.connect(lambda _=False, l=lg: self.remove_logo(l))
            row.addWidget(rm)
            self.logo_box.addLayout(row)

    def add_logo(self):
        if not self.kit:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Scegli il logo", "", "Immagini (*.png *.svg *.jpg *.jpeg *.webp)")
        if not f:
            return
        role = "main" if not self.kit.logos else ("symbol" if not self.kit.logo("symbol") else "other")
        try:
            self.store.add_logo(self.kit, f, Path(f).stem, role)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "ConfMerge", str(e))
            return
        self._fill_logos()
        self._preview()

    def remove_logo(self, logo: KitLogo):
        self.store.remove_logo(self.kit, logo)
        self._fill_logos()
        self._preview()

    def _changed(self, rename: bool = False):
        self.store.save(self.kit)
        if rename:
            it = self.list.currentItem()
            if it:
                it.setText(self.kit.name)
        self._preview()

    def _preview(self):
        kit = self.kit
        if kit is None or not hasattr(self, "preview"):
            return
        W, H = PREVIEW_W, PREVIEW_H
        sc = brand.brand_title_scene(kit, self.store)
        base = compositor.render_scene_background(sc, W, H)
        vars_ = {"titolo": kit.name, "sottotitolo": "Un esempio di titolo", "data": "12 maggio 2026"}
        img = compositor.render_frame(substitute(sc.elements, vars_), W, H, 3.0, 4.0, base)
        self.preview.setPixmap(QPixmap.fromImage(img))

    def _use(self):
        if self.kit:
            self.chosen.emit(self.kit.id)
            self.accept()
