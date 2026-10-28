"""Scheda «Marchio» dentro i lavori: scegli il kit, accendi o spegni i loghi, usa titolo e finale del marchio."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout

from .. import brand
from ..brand_kit import CORNERS, ROLE_SHORT
from .brand_dialog import BrandDialog
from .widgets import Card, SecondaryButton, Toggle, label


class BrandCard(Card):
    def __init__(self, state, scenes: bool = False, parent=None):
        super().__init__(parent)
        self.state, self.scenes = state, scenes
        self.add(label("Marchio", "h2", True))
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._picked)
        row.addWidget(self.combo, 1)
        self.manage = SecondaryButton("Gestisci…", "palette", "Crea e modifica i marchi: colori, caratteri, loghi")
        self.manage.clicked.connect(self.open_manager)
        row.addWidget(self.manage)
        self.lay.addLayout(row)
        self.logos_box = Card(flat=True, padding=0)
        self.add(self.logos_box)
        if scenes:
            self.t_btn = SecondaryButton("Titolo con il marchio", "type", "Titolo iniziale con colori e logo del marchio")
            self.o_btn = SecondaryButton("Finale con il marchio", "film", "Schermata finale con logo, slogan e @canale")
            self.t_btn.clicked.connect(lambda: self._scene("title"))
            self.o_btn.clicked.connect(lambda: self._scene("outro"))
            self.add(self.t_btn)                       # uno sotto l'altro: nei pannelli stretti non allargano la scheda
            self.add(self.o_btn)
        self.sync()
        state.profile_changed.connect(self.sync)

    def sync(self):
        st = self.state
        kits = st.kits.list()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("Nessun marchio", "")
        for k in kits:
            self.combo.addItem(k.name, k.id)
        i = self.combo.findData(st.spec.brand.kit_id)
        self.combo.setCurrentIndex(max(0, i))
        self.combo.blockSignals(False)
        while self.logos_box.lay.count():
            it = self.logos_box.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for lg in st.spec.brand.logos:
            t = Toggle(f"Mostra il {ROLE_SHORT.get(lg.role, 'logo').lower()}" + (f" ({lg.name})" if lg.name else ""))
            t.setChecked(lg.enabled)
            t.toggled.connect(lambda on, l=lg: (setattr(l, "enabled", on), st.touch()))
            self.logos_box.lay.addWidget(t)
            cb = QComboBox()
            for k, v in {**CORNERS, "free": "Libero (trascinato)"}.items():
                cb.addItem(v, k)
            cb.setCurrentIndex(max(0, cb.findData(lg.corner)))
            cb.currentIndexChanged.connect(lambda _, l=lg, c=cb: (setattr(l, "corner", c.currentData()), st.touch()))
            self.logos_box.lay.addWidget(cb)
        has = bool(st.spec.brand.kit_id)
        if self.scenes:
            self.t_btn.setEnabled(has)
            self.o_btn.setEnabled(has)
        self.logos_box.setVisible(bool(st.spec.brand.logos))

    def _picked(self, _):
        kid = self.combo.currentData()
        st = self.state
        if not kid:
            brand.clear_kit(st.spec)
        else:
            kit = st.kits.get(kid)
            if kit:
                brand.apply_kit(st.spec, kit, st.kits)
        st.touch()
        st.profile_changed.emit()

    def _scene(self, which: str):
        st = self.state
        kit = st.kits.get(st.spec.brand.kit_id)
        if kit:
            brand.apply_brand_scene(st.spec, kit, st.kits, which)
            st.touch()
            st.profile_changed.emit()

    def open_manager(self):
        dlg = BrandDialog(self.state, self.window())
        dlg.chosen.connect(self._chosen)
        dlg.exec()
        cur = self.state.spec.brand.kit_id
        kit = self.state.kits.get(cur) if cur else None
        if kit:                                    # il kit può essere stato modificato: si riapplica (restano acceso/spento e angoli)
            keep = {lg.role: (lg.enabled, lg.corner) for lg in self.state.spec.brand.logos}
            brand.apply_kit(self.state.spec, kit, self.state.kits)
            for lg in self.state.spec.brand.logos:
                if lg.role in keep:
                    lg.enabled, lg.corner = keep[lg.role]
            self.state.touch()
        elif cur:
            brand.clear_kit(self.state.spec)
        self.sync()

    def _chosen(self, kid: str):
        kit = self.state.kits.get(kid)
        if kit:
            brand.apply_kit(self.state.spec, kit, self.state.kits)
            self.state.touch()
        self.sync()
