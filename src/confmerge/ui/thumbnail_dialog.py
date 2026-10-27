"""Miniatura YouTube: layout pronti, un fotogramma del video, titolo grande, colori e loghi del marchio. Export JPG (<2 MB) e PNG."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QSlider, QSplitter, QVBoxLayout, QWidget)

from .. import paths, thumb_layouts as TL, thumbnail
from ..ffmpeg_wrapper import FFmpegError
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
        self.big = QLabel()
        self.big.setFixedSize(PREVIEW_W, PREVIEW_W * 9 // 16)
        self.big.setScaledContents(True)
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
        self.font_box.setCurrentIndex(max(0, self.font_box.findData(self.font_choice)))
        self.font_box.currentIndexChanged.connect(self._font)
        fr.addWidget(self.font_box, 1)
        c2.lay.addLayout(fr)
        pl.addWidget(c2)
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
        return pal

    def _fields_now(self) -> TL.Fields:
        f = TL.Fields(self.title.text(), self.sub.text(), self.upper.isChecked(), self.fx.value() / 100)
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
                                            "font": self.font_box.currentData(), "t": self.t}

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
