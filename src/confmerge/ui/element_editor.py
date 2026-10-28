"""Editor delle proprietà di un elemento grafico (testo, immagine, forma, barra)."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFileDialog, QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..render.masks import MASKS
from ..render.model import ANIM_KINDS, EASINGS, Element
from ..render.text_renderer import element_bbox
from . import bind
from .widgets import Section, Toggle

ANIM_LABELS = {"none": "Nessuna", "fade": "Dissolvenza", "slide_left": "Scorri da sinistra", "slide_right": "Scorri da destra",
               "slide_up": "Scorri dall'alto", "slide_down": "Scorri dal basso", "pop": "Scala (pop)",
               "reveal": "Rivelazione a maschera", "blur": "Sfocatura che si dissolve", "typewriter": "Macchina da scrivere",
               "by_word": "Per parola (a cascata)", "by_letter": "Per lettera (a cascata)"}
EASE_LABELS = {"linear": "Lineare", "ease_in_out": "Ease in-out", "cubic": "Cubica", "back": "Back (rimbalzo)", "expo": "Esponenziale"}


class ElementEditor(QWidget):
    changed = Signal()
    textLikeChanged = Signal()

    def __init__(self, parent=None, show_targets: bool = True, show_timing: bool = True):
        super().__init__(parent)
        self.show_targets, self.show_timing = show_targets, show_timing
        self.el: Element | None = None
        self.frame_wh = (1920, 1080)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        self.holder = QWidget()
        self.lay = QVBoxLayout(self.holder)
        sc.setWidget(self.holder)
        outer.addWidget(sc)

    def _clear(self):
        while self.lay.count():
            it = self.lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def set_element(self, el: Element | None):
        self.el = el
        self._clear()
        if el is None:
            self.lay.addWidget(QLabel("Seleziona o aggiungi un elemento."))
            self.lay.addStretch(1)
            return
        cb = self.changed.emit
        gen = Section("Posizione e aspetto", "g:" + "Posizione e aspetto")
        f = gen.form()
        f.addRow("X (%)", bind.spin(el, "x", -20, 120, 0.5, 1, "", 100, cb))
        f.addRow("Y (%)", bind.spin(el, "y", -20, 120, 0.5, 1, "", 100, cb))
        f.addRow("Rotazione (°)", bind.spin(el, "rotation", -360, 360, 1, 1, "", 1, cb))
        f.addRow("Opacità (%)", bind.spin(el, "opacity", 0, 1, 0.05, 2, "", 1, cb))
        if self.show_timing:
            f.addRow("Inizio (s)", bind.spin(el, "start", 0, 36000, 0.5, 2, "", 1, cb))
            f.addRow("Fine (s)", self._end_spin(el))
        self.lay.addWidget(gen)
        if el.kind == "text":
            self._text(el)
        elif el.kind in ("image", "clip"):
            self._image(el)
            if el.kind == "clip":
                self.lay.insertWidget(self.lay.count(), bind.check(el, "loop", "Si ripete finché è visibile", cb))
        elif el.kind == "shape":
            self._shape(el)
        elif el.kind == "bar":
            self._bar(el)
        if self.show_targets:
            self._targets(el)
        self._anims(el)
        self.lay.addStretch(1)

    def _end_spin(self, el):
        from PySide6.QtWidgets import QDoubleSpinBox
        w = QDoubleSpinBox()
        w.setRange(0, 36000)
        w.setDecimals(2)
        w.setSingleStep(0.5)
        w.setSpecialValueText("fino alla fine")
        w.setValue(el.end or 0.0)
        w.valueChanged.connect(lambda v: (setattr(el, "end", v if v > 0 else None), self.changed.emit()))
        return w

    def _text(self, el):
        cb = self.changed.emit
        g = Section("Testo", "g:" + "Testo")
        f = g.form()
        te = QPlainTextEdit(el.text)
        te.setMinimumHeight(72)
        te.textChanged.connect(lambda: (setattr(el, "text", te.toPlainText()), cb()))
        f.addRow(te)
        fc = QFontComboBox()
        fc.setCurrentFont(QFont(el.font))
        fc.currentFontChanged.connect(lambda ft: (setattr(el, "font", ft.family()), cb()))
        f.addRow("Font", fc)
        f.addRow("Dimensione (%)", bind.spin(el, "size", 0.5, 60, 0.5, 1, "", 100, cb))
        row = QHBoxLayout()
        row.addWidget(bind.check(el, "bold", "Grassetto", cb))
        row.addWidget(bind.check(el, "italic", "Corsivo", cb))
        w = QWidget()
        w.setLayout(row)
        f.addRow(w)
        f.addRow("Allineamento", bind.combo(el, "align", [("Sinistra", "left"), ("Centro", "center"), ("Destra", "right")], cb))
        f.addRow("Interlinea", bind.spin(el, "line_spacing", 0.5, 3, 0.05, 2, "", 1, cb))
        f.addRow("Spazio lettere (%)", bind.spin(el, "letter_spacing", -5, 20, 0.1, 1, "", 100, cb))
        self.lay.addWidget(g)
        g = Section("Colore e contorno", "g:" + "Colore e contorno")
        f = g.form()
        f.addRow("Riempimento", bind.combo(el.fill, "kind", [("Tinta unita", "solid"), ("Sfumatura", "gradient")], cb))
        f.addRow("Colore", bind.color(el.fill, "color", cb))
        f.addRow("Colore 2", bind.color(el.fill, "color2", cb))
        f.addRow("Angolo (°)", bind.spin(el.fill, "angle", 0, 360, 5, 0, "", 1, cb))
        f.addRow("Contorno (%)", bind.spin(el.outline, "width", 0, 5, 0.1, 2, "", 100, cb))
        f.addRow("Colore contorno", bind.color(el.outline, "color", cb))
        self.lay.addWidget(g)
        self._shadow(el)
        g = Section("Box di sfondo", "g:" + "Box di sfondo")
        f = g.form()
        f.addRow(bind.check(el.box, "enabled", "Attivo", cb))
        f.addRow("Colore", bind.color(el.box, "color", cb))
        f.addRow("Opacità", bind.spin(el.box, "opacity", 0, 1, 0.05, 2, "", 1, cb))
        f.addRow("Margine (%)", bind.spin(el.box, "padding", 0, 10, 0.1, 1, "", 100, cb))
        f.addRow("Angoli (%)", bind.spin(el.box, "radius", 0, 10, 0.1, 1, "", 100, cb))
        self.lay.addWidget(g)

    def _shadow(self, el):
        cb = self.changed.emit
        g = Section("Ombra", "g:" + "Ombra")
        f = g.form()
        f.addRow(bind.check(el.shadow, "enabled", "Attiva", cb))
        f.addRow("Colore", bind.color(el.shadow, "color", cb))
        f.addRow("Sfocatura (%)", bind.spin(el.shadow, "blur", 0, 5, 0.1, 1, "", 100, cb))
        f.addRow("Distanza (%)", bind.spin(el.shadow, "distance", 0, 5, 0.1, 1, "", 100, cb))
        f.addRow("Angolo (°)", bind.spin(el.shadow, "angle", 0, 360, 5, 0, "", 1, cb))
        f.addRow("Opacità", bind.spin(el.shadow, "opacity", 0, 1, 0.05, 2, "", 1, cb))
        self.lay.addWidget(g)

    def _image(self, el):
        cb = self.changed.emit
        g = Section("Immagine / logo", "g:" + "Immagine / logo")
        f = g.form()
        row = QHBoxLayout()
        le = bind.line(el, "path", cb)
        btn = QPushButton("Scegli…")

        def pick():
            p, _ = QFileDialog.getOpenFileName(self, "Immagine", "", "Immagini e overlay (*.png *.svg *.jpg *.jpeg *.webp *.gif *.webm *.mov)")
            if p:
                el.path = p
                le.setText(p)
                cb()
        btn.clicked.connect(pick)
        row.addWidget(le)
        row.addWidget(btn)
        w = QWidget()
        w.setLayout(row)
        f.addRow(w)
        f.addRow("Larghezza (%)", bind.spin(el, "width", 1, 100, 0.5, 1, "", 100, cb))
        f.addRow("Maschera", bind.combo(el, "mask", [(v, k) for k, v in MASKS.items()], cb))
        f.addRow("Angoli (%)", bind.spin(el, "mask_radius", 0, 50, 1, 0, "", 100, cb))
        f.addRow("Margine angolo (%)", bind.spin(el, "margin", 0, 20, 0.5, 1, "", 100, cb))
        corners = QHBoxLayout()
        for text, c in (("↖", "tl"), ("↗", "tr"), ("↙", "bl"), ("↘", "br")):
            b = QPushButton(text)
            b.setToolTip("Posiziona nell'angolo")
            b.clicked.connect(lambda _=False, cc=c: self.corner(cc))
            corners.addWidget(b)
        w = QWidget()
        w.setLayout(corners)
        f.addRow("Angolo", w)
        self.lay.addWidget(g)
        self._shadow(el)

    def corner(self, c: str):
        el = self.el
        if not el:
            return
        W, H = self.frame_wh
        b = element_bbox(el, W, H)
        m = el.margin if el.margin > 0 else 0.03
        mx, my = m * W, m * W
        el.x = ((mx + b.width() / 2) if c in ("tl", "bl") else (W - mx - b.width() / 2)) / W
        el.y = ((my + b.height() / 2) if c in ("tl", "tr") else (H - my - b.height() / 2)) / H
        self.changed.emit()
        self.set_element(el)

    def _shape(self, el):
        cb = self.changed.emit
        g = Section("Forma", "g:" + "Forma")
        f = g.form()
        f.addRow("Tipo", bind.combo(el, "shape", [("Rettangolo", "rect"), ("Ellisse", "ellipse"), ("Linea", "line")], cb))
        f.addRow("Larghezza (%)", bind.spin(el, "w", 0.5, 150, 0.5, 1, "", 100, cb))
        f.addRow("Altezza (%)", bind.spin(el, "h", 0.1, 150, 0.5, 1, "", 100, cb))
        f.addRow("Angoli (%)", bind.spin(el, "radius", 0, 50, 0.2, 1, "", 100, cb))
        f.addRow("Riempimento", bind.combo(el.fill, "kind", [("Tinta unita", "solid"), ("Sfumatura", "gradient")], cb))
        f.addRow("Colore", bind.color(el.fill, "color", cb))
        f.addRow("Colore 2", bind.color(el.fill, "color2", cb))
        f.addRow("Contorno (%)", bind.spin(el.outline, "width", 0, 5, 0.1, 2, "", 100, cb))
        f.addRow("Colore contorno", bind.color(el.outline, "color", cb))
        self.lay.addWidget(g)
        self._shadow(el)

    def _bar(self, el):
        cb = self.changed.emit
        g = Section("Barra di avanzamento", "g:" + "Barra di avanzamento")
        f = g.form()
        f.addRow("Posizione", bind.combo(el, "position", [("In basso", "bottom"), ("In alto", "top")], cb))
        f.addRow("Spessore (%)", bind.spin(el, "thickness", 0.1, 5, 0.1, 2, "", 100, cb))
        f.addRow("Margine (%)", bind.spin(el, "margin", 0, 10, 0.1, 1, "", 100, cb))
        f.addRow("Angoli (%)", bind.spin(el, "radius", 0, 3, 0.1, 2, "", 100, cb))
        f.addRow("Riempimento", bind.combo(el.fill, "kind", [("Tinta unita", "solid"), ("Sfumatura", "gradient")], cb))
        f.addRow("Colore", bind.color(el.fill, "color", cb))
        f.addRow("Colore 2", bind.color(el.fill, "color2", cb))
        self.lay.addWidget(g)

    def _targets(self, el):
        g = Section("Dove si applica", "g:targets")
        l = g.body_lay
        for key, text in (("main", "Video principale"), ("title", "Titolo iniziale"), ("outro", "Logo / schermata finale")):
            c = Toggle(text)
            c.setChecked(key in el.targets)

            def tg(on, k=key):
                if on and k not in el.targets:
                    el.targets.append(k)
                if not on and k in el.targets:
                    el.targets.remove(k)
                self.changed.emit()
            c.toggled.connect(tg)
            l.addWidget(c)
        self.lay.addWidget(g)

    def _anims(self, el):
        cb = self.changed.emit
        kinds = [(ANIM_LABELS[k], k) for k in ANIM_KINDS]
        if el.kind != "text":
            kinds = [(l, k) for l, k in kinds if k not in ("typewriter", "by_word", "by_letter")]
        eases = [(EASE_LABELS[k], k) for k in EASINGS]
        for title, a in (("Animazione di entrata", el.anim_in), ("Animazione di uscita", el.anim_out)):
            g = Section(title, "g:" + title)
            f = g.form()
            f.addRow("Tipo", bind.combo(a, "kind", kinds, cb))
            f.addRow("Durata (s)", bind.spin(a, "duration", 0.05, 10, 0.1, 2, "", 1, cb))
            f.addRow("Curva", bind.combo(a, "easing", eases, cb))
            f.addRow("Ritardo cascata (s)", bind.spin(a, "stagger", 0, 1, 0.01, 2, "", 1, cb))
            self.lay.addWidget(g)
