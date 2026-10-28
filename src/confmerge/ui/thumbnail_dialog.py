"""Miniatura YouTube: layout pronti, un fotogramma del video, titolo grande, colori e loghi del marchio. Export JPG (<2 MB) e PNG."""
from __future__ import annotations

from pathlib import Path

import copy
import uuid
from types import SimpleNamespace

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFontComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QSlider, QSplitter, QVBoxLayout, QWidget)

from .. import paths, thumb_layouts as TL, thumbnail
from ..ffmpeg_wrapper import FFmpegError
from ..render.model import Element, Fill, Outline, Shadow
from ..render.text_renderer import element_bbox
from . import bind, placement
from .graphics_page import scrolled
from .widgets import Card, GhostButton, PrimaryButton, SecondaryButton, Toggle, label

FONT_CHOICES = [("Anton (consigliato)", "Anton"), ("Bebas Neue", "Bebas Neue"), ("Poppins", "Poppins"), ("Del marchio", "")]
PREVIEW_W = 640


class _LayoutCard(QWidget):
    """Anteprima cliccabile di un layout, con il nome."""
    from PySide6.QtCore import Signal
    clicked = Signal(str)

    def __init__(self, layout: TL.Layout, parent=None):
        super().__init__(parent)
        self.layout_id = layout.id
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.pic = QLabel()
        self.pic.setFixedSize(176, 99)
        self.pic.setScaledContents(True)
        lay.addWidget(self.pic)
        self.name = QLabel(layout.name)
        self.name.setProperty("role", "caption")
        lay.addWidget(self.name)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(layout.description)
        self.set_selected(False)

    def set_selected(self, on: bool):
        self.setStyleSheet("QWidget{border:2px solid #4C8DF6; border-radius:8px;}" if on else
                           "QWidget{border:2px solid transparent; border-radius:8px;}")

    def mousePressEvent(self, e):
        self.clicked.emit(self.layout_id)


class _Preview(QLabel):
    """Anteprima grande: gli elementi aggiunti a mano si trascinano con il mouse (con aggancio al centro e ai terzi)."""
    pressed = Signal(float, float)       # frazioni della miniatura
    moved = Signal(float, float, bool)   # x, y, Alt premuto (niente aggancio)
    released = Signal()

    def _frac(self, e) -> tuple[float, float]:
        return e.position().x() / max(1, self.width()), e.position().y() / max(1, self.height())

    def mousePressEvent(self, e):
        self.pressed.emit(*self._frac(e))

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.moved.emit(*self._frac(e), bool(e.modifiers() & Qt.AltModifier))

    def mouseReleaseEvent(self, e):
        self.released.emit()


class ThumbnailDialog(QDialog):
    def __init__(self, state, out_dir: Path, name: str, pos_fn, parent=None):
        super().__init__(parent)
        self.state, self.out_dir, self.name, self.pos_fn = state, Path(out_dir), name, pos_fn
        self.setWindowTitle("Miniatura YouTube")
        self.resize(1180, 760)
        pr = state.project
        saved = (pr.thumbnail if pr else {}) or {}
        self.layout_id = saved.get("layout", "volto_titolo") if saved.get("layout") in TL.BY_ID else "volto_titolo"
        self.fields = TL.Fields(title=saved.get("title", "") or TL.SAMPLES[self.layout_id][0], sub=saved.get("sub", ""),
                                uppercase=saved.get("uppercase", True), frame_x=saved.get("frame_x", 0.5))
        f = self.fields
        f.size_scale, f.dx, f.dy = saved.get("size", 1.0), saved.get("dx", 0.0), saved.get("dy", 0.0)
        f.title_color, f.sub_color = saved.get("title_color", ""), saved.get("sub_color", "")
        f.dim, f.saturation = saved.get("dim", 0.0), saved.get("sat", 1.0)
        f.extras = [Element.from_dict(copy.deepcopy(d)) for d in saved.get("extras", [])]
        self.pal_over = SimpleNamespace(primary=saved.get("c_primary", ""), accent=saved.get("c_accent", ""),
                                        secondary=saved.get("c_secondary", ""), text=saved.get("c_text", ""),
                                        title=f.title_color, sub=f.sub_color)
        self.font_other = saved.get("font_other", "")
        self._drag: tuple[int, QPointF] | None = None
        self.font_choice = saved.get("font", "Anton")
        self.t = saved.get("t", (state.trim_start + state.trim_end) / 2 if pr else 0.0)
        self.frame: QImage | None = None
        self.show_logo = self.show_symbol = True
        self._cards: dict[str, _LayoutCard] = {}

        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)
        # --- sinistra: anteprima grande, anteprime piccole, fotogramma
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.big = _Preview()
        self.big.setFixedSize(PREVIEW_W, PREVIEW_W * 9 // 16)
        self.big.setScaledContents(True)
        self.big.setCursor(Qt.OpenHandCursor)
        self.big.setToolTip("Trascina i testi e le immagini che hai aggiunto (Alt = senza aggancio)")
        self.big.pressed.connect(self._press)
        self.big.moved.connect(self._move)
        self.big.released.connect(self._release)
        ll.addWidget(self.big, 0, Qt.AlignHCenter)
        ll.addWidget(label("Così si vede sul telefono e nell'elenco di YouTube: il titolo deve restare leggibile.", "caption", True))
        small = QHBoxLayout()
        self.s1, self.s2 = QLabel(), QLabel()
        for lb, w in ((self.s1, 246), (self.s2, 168)):
            lb.setFixedSize(w, w * 9 // 16)
            lb.setScaledContents(True)
            small.addWidget(lb)
        small.addStretch(1)
        ll.addLayout(small)
        ll.addWidget(label("Fotogramma del video", "h3"))
        self.cands = QListWidget()
        self.cands.setViewMode(QListWidget.IconMode)
        self.cands.setIconSize(QSize(120, 68))
        self.cands.setFlow(QListWidget.LeftToRight)
        self.cands.setWrapping(False)
        self.cands.setFixedHeight(104)
        self.cands.itemClicked.connect(lambda it: self.set_time(it.data(Qt.UserRole)))
        ll.addWidget(self.cands)
        row = QHBoxLayout()
        cur = SecondaryButton("Usa il punto in cui è il video", "image")
        cur.clicked.connect(lambda: self.set_time(self.pos_fn()))
        row.addWidget(cur)
        row.addWidget(label("Sposta l'inquadratura:"))
        self.fx = QSlider(Qt.Horizontal)
        self.fx.setRange(0, 100)
        self.fx.setValue(int(self.fields.frame_x * 100))
        self.fx.valueChanged.connect(self._fx)
        row.addWidget(self.fx, 1)
        ll.addLayout(row)
        split.addWidget(left)
        # --- destra: layout, testi, marchio
        panel = QWidget()
        pl = QVBoxLayout(panel)
        pl.setSpacing(10)
        c1 = Card()
        c1.add(label("Scegli un layout", "h2", True))
        grid = QWidget()
        from PySide6.QtWidgets import QGridLayout
        g = QGridLayout(grid)
        g.setContentsMargins(0, 0, 0, 0)
        for i, lyt in enumerate(TL.LAYOUTS):
            c = _LayoutCard(lyt)
            c.clicked.connect(self.pick_layout)
            self._cards[lyt.id] = c
            g.addWidget(c, i // 2, i % 2)
        c1.add(grid)
        pl.addWidget(c1)
        c2 = Card()
        c2.add(label("Testi", "h2", True))
        c2.add(label("Titolo (poche parole: si legge meglio)", "caption", True))
        self.title = QLineEdit(self.fields.title)
        self.title.textChanged.connect(self._text)
        c2.add(self.title)
        self.sub_lbl = label("", "caption", True)
        c2.add(self.sub_lbl)
        self.sub = QLineEdit(self.fields.sub)
        self.sub.textChanged.connect(self._text)
        c2.add(self.sub)
        self.upper = Toggle("Tutto maiuscolo")
        self.upper.setChecked(self.fields.uppercase)
        self.upper.toggled.connect(self._upper)
        c2.add(self.upper)
        fr = QHBoxLayout()
        fr.addWidget(label("Carattere:"))
        self.font_box = QComboBox()
        for t, v in FONT_CHOICES:
            self.font_box.addItem(t, v)
        self.font_box.setCurrentIndex(-1 if self.font_other else max(0, self.font_box.findData(self.font_choice)))
        self.font_box.currentIndexChanged.connect(self._font)
        fr.addWidget(self.font_box, 1)
        c2.lay.addLayout(fr)
        fo = QHBoxLayout()
        fo.addWidget(label("Oppure un altro:"))
        self.font_any = QFontComboBox()
        if self.font_other:
            from PySide6.QtGui import QFont
            self.font_any.setCurrentFont(QFont(self.font_other))
        self.font_any.currentFontChanged.connect(self._font_other)
        fo.addWidget(self.font_any, 1)
        c2.lay.addLayout(fo)
        pl.addWidget(c2)
        pl.addWidget(self._tune_card())
        pl.addWidget(self._extras_card())
        c3 = Card()
        c3.add(label("Marchio", "h2", True))
        self.kit_lbl = label("", "caption", True)
        c3.add(self.kit_lbl)
        self.logo_t = Toggle("Logo principale")
        self.sym_t = Toggle("Simbolo del partito")
        for t, attr in ((self.logo_t, "show_logo"), (self.sym_t, "show_symbol")):
            t.setChecked(True)
            t.toggled.connect(lambda on, a=attr: (setattr(self, a, on), self.schedule()))
            c3.add(t)
        pl.addWidget(c3)
        pl.addStretch(1)
        sa = scrolled(panel)
        sa.setMinimumWidth(440)
        split.addWidget(sa)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        # --- fondo
        foot = QHBoxLayout()
        foot.addStretch(1)
        close = GhostButton("Chiudi")
        close.clicked.connect(self.reject)
        self.go = PrimaryButton("Salva JPG e PNG", "download")
        self.go.clicked.connect(self.export)
        foot.addWidget(close)
        foot.addWidget(self.go)
        lay.addLayout(foot)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.redraw)
        self._brand_info()
        self.fill_candidates()
        self.set_time(self.t)
        self.pick_layout(self.layout_id, keep_text=True)

    # --- personalizzazione
    def _slider(self, card, text_fn, lo, hi, value, setter):
        lb = label("", "caption", True)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(value)

        def changed(v):
            setter(v)
            lb.setText(text_fn(v))
            self.schedule()
        sl.valueChanged.connect(changed)
        lb.setText(text_fn(value))
        card.add(lb)
        card.add(sl)
        return sl

    def _color_row(self, card, text: str, attr: str):
        row = QHBoxLayout()
        row.addWidget(label(text))
        btn = bind.color(self.pal_over, attr, self._colors_changed)
        row.addWidget(btn)
        rs = GhostButton("Come il layout")
        rs.setToolTip("Torna al colore del layout o del marchio")
        rs.clicked.connect(lambda _=False, a=attr, b=btn: (setattr(self.pal_over, a, ""), b.setStyleSheet(""), self._colors_changed()))
        row.addWidget(rs)
        row.addStretch(1)
        card.lay.addLayout(row)

    def _colors_changed(self):
        self.fields.title_color, self.fields.sub_color = self.pal_over.title, self.pal_over.sub
        self.schedule()
        self._gallery()

    def _tune_card(self) -> Card:
        f = self.fields
        c = Card()
        c.add(label("Personalizza", "h2", True))
        self._slider(c, lambda v: f"Grandezza dei testi: {v} %", 50, 150, round(f.size_scale * 100),
                     lambda v: setattr(f, "size_scale", v / 100))
        self._slider(c, lambda v: f"Sposta i testi a destra/sinistra: {v:+d} %", -30, 30, round(f.dx * 100),
                     lambda v: setattr(f, "dx", v / 100))
        self._slider(c, lambda v: f"Sposta i testi in alto/basso: {v:+d} %", -30, 30, round(f.dy * 100),
                     lambda v: setattr(f, "dy", v / 100))
        self._slider(c, lambda v: f"Scurisci la foto: {v} %", 0, 70, round(f.dim * 100), lambda v: setattr(f, "dim", v / 100))
        self._slider(c, lambda v: f"Colori della foto: {v} % (100 = originali)", 0, 200, round(f.saturation * 100),
                     lambda v: setattr(f, "saturation", v / 100))
        c.add(label("Colori", "h3"))
        for text, attr in (("Titolo", "title"), ("Frase", "sub"), ("Principale", "primary"), ("Evidenza", "accent"),
                           ("Sfondo scuro", "secondary"), ("Testo del layout", "text")):
            self._color_row(c, text, attr)
        return c

    def _extras_card(self) -> Card:
        c = Card()
        c.add(label("Testi e immagini in più", "h2", True))
        c.add(label("Aggiungi un bollino, un logo o una scritta e trascinali sull'anteprima. Le immagini PNG possono avere lo sfondo "
                    "trasparente.", "caption", True))
        r = QHBoxLayout()
        a = SecondaryButton("Aggiungi un testo", "type")
        a.clicked.connect(self._add_text)
        b = SecondaryButton("Aggiungi un'immagine…", "image-plus")
        b.clicked.connect(self._add_image)
        r.addWidget(a)
        r.addWidget(b)
        r.addStretch(1)
        c.lay.addLayout(r)
        self.extra_rows = QVBoxLayout()
        c.lay.addLayout(self.extra_rows)
        self._fill_extras()
        return c

    def _fill_extras(self):
        while self.extra_rows.count():
            it = self.extra_rows.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
                it.widget().deleteLater()
        for el in self.fields.extras:
            box = Card(flat=True, padding=6)
            row = QHBoxLayout()
            if el.kind == "text":
                ed = QLineEdit(el.text)
                ed.textEdited.connect(lambda t, e=el: (setattr(e, "text", t), self.schedule()))
                row.addWidget(ed, 1)
            else:
                row.addWidget(label(Path(el.path).name, "", False), 1)
            look = GhostButton("Aspetto…")
            look.clicked.connect(lambda _=False, e=el: self._look(e))
            rm = GhostButton("Togli")
            rm.clicked.connect(lambda _=False, e=el: (self.fields.extras.remove(e), self._fill_extras(), self.schedule()))
            row.addWidget(look)
            row.addWidget(rm)
            box.lay.addLayout(row)
            self.extra_rows.addWidget(box)

    def _add_text(self):
        el = Element(id=uuid.uuid4().hex[:6], kind="text", text="NOVITÀ", size=0.09, bold=True, x=0.78, y=0.14, fit_width=0.5,
                     font="Anton", uppercase=True, fill=Fill(color="#FFFFFF"), outline=Outline(0.004, "#000000"),
                     shadow=Shadow(enabled=True, opacity=0.6))
        self.fields.extras.append(el)
        self._fill_extras()
        self.schedule()

    def _add_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "Scegli l'immagine", "", "Immagini (*.png *.svg *.jpg *.jpeg *.webp)")
        if f:
            self.fields.extras.append(Element(id=uuid.uuid4().hex[:6], kind="image", path=f, width=0.2, x=0.85, y=0.2))
            self._fill_extras()
            self.schedule()

    def _look(self, el: Element):
        from PySide6.QtWidgets import QDialogButtonBox
        from .element_editor import ElementEditor
        dlg = QDialog(self)
        dlg.setWindowTitle("Aspetto")
        dlg.resize(460, 640)
        lay = QVBoxLayout(dlg)
        ed = ElementEditor(show_targets=False, show_timing=False)
        ed.frame_wh = (TL.W, TL.H)
        ed.changed.connect(self.schedule)
        ed.set_element(el)
        lay.addWidget(ed, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()
        self._fill_extras()
        self.schedule()

    # --- trascinamento sull'anteprima
    def _press(self, fx: float, fy: float):
        self._drag = None
        for i in range(len(self.fields.extras) - 1, -1, -1):
            el = self.fields.extras[i]
            if el.visible and element_bbox(el, TL.W, TL.H).adjusted(-8, -8, 8, 8).contains(fx * TL.W, fy * TL.H):
                self._drag = (i, QPointF(el.x - fx, el.y - fy))
                self.big.setCursor(Qt.ClosedHandCursor)
                return

    def _move(self, fx: float, fy: float, free: bool):
        if self._drag is None:
            return
        i, off = self._drag
        el = self.fields.extras[i]
        cx, cy = fx + off.x(), fy + off.y()
        if not free:
            r = element_bbox(el, TL.W, TL.H)
            cx, cy, _ = placement.snap(cx, cy, r.width() / TL.W / 2, r.height() / TL.H / 2, TL.W, TL.H, None)
        el.x, el.y = min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)
        self.redraw()

    def _release(self):
        self._drag = None
        self.big.setCursor(Qt.OpenHandCursor)

    def _font_other(self, ft):
        self.font_other = ft.family()
        self.font_box.blockSignals(True)
        self.font_box.setCurrentIndex(-1)
        self.font_box.blockSignals(False)
        self.schedule()
        self._gallery()

    # --- marchio e palette
    def _kit(self):
        kid = self.state.spec.brand.kit_id
        return self.state.kits.get(kid) if kid else None

    def _brand_info(self):
        kit, st = self._kit(), self.state
        self.kit_lbl.setText(f"Colori e loghi di «{kit.name}» (si cambia dalla scheda «Marchio»)." if kit else
                             "Nessun marchio scelto: uso i colori classici. Scegli un marchio per usare i tuoi colori e i tuoi loghi.")
        roles = {lg.role for lg in st.spec.brand.logos}
        self.logo_t.setVisible("main" in roles)
        self.sym_t.setVisible("symbol" in roles)

    def palette(self) -> TL.Palette:
        kit = self._kit()
        pal = TL.Palette()
        if kit:
            pal.colors, pal.font_body = kit.colors, kit.font_body
            pal.font_title = kit.font_title
        choice = self.font_box.currentData()
        if choice:
            pal.font_title = choice
        elif self.font_box.currentIndex() < 0 and self.font_other:
            pal.font_title = self.font_other
        o = self.pal_over
        for attr in ("primary", "accent", "secondary", "text"):
            if getattr(o, attr):
                setattr(pal.colors, attr, getattr(o, attr))
        return pal

    def _fields_now(self) -> TL.Fields:
        f = copy.copy(self.fields)
        f.title, f.sub, f.uppercase, f.frame_x = self.title.text(), self.sub.text(), self.upper.isChecked(), self.fx.value() / 100
        f.logos = []
        for lg in self.state.spec.brand.logos:
            if lg.path and ((lg.role == "main" and self.show_logo) or (lg.role == "symbol" and self.show_symbol)):
                f.logos.append((lg.path, lg.role))
        return f

    # --- fotogramma
    def fill_candidates(self):
        st = self.state
        if not st.clips or not st.project:
            return
        for t in thumbnail.suggest_times(st.trim_start, st.trim_end, 6):
            try:
                clip, local = thumbnail.locate(st.clips, t)
                img = thumbnail.grab_frame(clip.path, local, paths.temp_dir() / f"cand_{int(t)}.png", 240)
            except FFmpegError:
                continue
            it = QListWidgetItem(QIcon(QPixmap.fromImage(img)), f"{int(t) // 60}:{int(t) % 60:02d}")
            it.setData(Qt.UserRole, t)
            self.cands.addItem(it)

    def set_time(self, t: float):
        self.t = t
        st = self.state
        try:
            clip, local = thumbnail.locate(st.clips, t)
            self.frame = thumbnail.grab_frame(clip.path, local, paths.temp_dir() / "thumb_frame.png", 1280)
        except (FFmpegError, IndexError):
            self.frame = st.last_frame
        self.schedule()
        self._gallery()

    # --- eventi
    def pick_layout(self, lid: str, keep_text: bool = False):
        old = TL.SAMPLES.get(self.layout_id, ("", ""))
        self.layout_id = lid
        lay = TL.BY_ID[lid]
        for k, c in self._cards.items():
            c.set_selected(k == lid)
        self.sub_lbl.setText(lay.sub_label)
        sample_t, sample_s = TL.SAMPLES[lid]
        if not keep_text:                                  # se il testo è ancora quello di esempio, cambia con il layout
            if self.title.text() in (old[0], ""):
                self.title.setText(sample_t)
            if self.sub.text() in (old[1], ""):
                self.sub.setText(sample_s)
        self.schedule()

    def _text(self, _=None):
        self.schedule()

    def _upper(self, on: bool):
        self.schedule()

    def _font(self, _=None):
        self.font_other = ""
        self.schedule()
        self._gallery()

    def _fx(self, _=None):
        self.schedule()
        self._gallery()

    def schedule(self):
        self._timer.start()

    def redraw(self):
        img = TL.render(self.layout_id, self.frame, self._fields_now(), self.palette())
        self._last = img
        pm = QPixmap.fromImage(img)
        self.big.setPixmap(pm)
        self.s1.setPixmap(pm)
        self.s2.setPixmap(pm)

    def _gallery(self):
        """Anteprime dei layout con il fotogramma e i colori attuali (testi di esempio)."""
        pal = self.palette()
        small = self.frame.scaled(640, 360, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation) if self.frame else None
        for lid, card in self._cards.items():
            t, s = TL.SAMPLES[lid]
            f = TL.Fields(t, s, True, self.fx.value() / 100)
            card.pic.setPixmap(QPixmap.fromImage(TL.render(lid, small, f, pal, 352, 198)))

    # --- salvataggio
    def _save_state(self):
        if self.state.project:
            self.state.project.thumbnail = {"layout": self.layout_id, "title": self.title.text(), "sub": self.sub.text(),
                                            "uppercase": self.upper.isChecked(), "frame_x": self.fx.value() / 100,
                                            "font": self.font_box.currentData(), "t": self.t,
                                            "font_other": self.font_other, "size": self.fields.size_scale,
                                            "dx": self.fields.dx, "dy": self.fields.dy, "dim": self.fields.dim,
                                            "sat": self.fields.saturation, "title_color": self.pal_over.title,
                                            "sub_color": self.pal_over.sub, "c_primary": self.pal_over.primary,
                                            "c_accent": self.pal_over.accent, "c_secondary": self.pal_over.secondary,
                                            "c_text": self.pal_over.text,
                                            "extras": [e.to_dict() for e in self.fields.extras]}

    def export(self):
        self.redraw()
        img = self._last
        self.out_dir.mkdir(parents=True, exist_ok=True)
        jpg, png = self.out_dir / f"{self.name}_miniatura.jpg", self.out_dir / f"{self.name}_miniatura.png"
        try:
            size = thumbnail.save_jpg_under_limit(img, jpg)
            img.save(str(png), "PNG")
        except FFmpegError as e:
            QMessageBox.warning(self, "ConfMerge", str(e))
            return
        self._save_state()
        QMessageBox.information(self, "ConfMerge", f"Miniature salvate:\n{jpg} ({size / 1e6:.2f} MB)\n{png}")
