"""Galleria dei modelli pronti: anteprime disegnate con lo stesso motore dell'export, scelta con un clic."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLineEdit,
                               QVBoxLayout, QWidget)

from .. import templates as T
from ..render import compositor as C
from ..render.model import VARIABLES, lower_third_elements, substitute
from .theme import theme
from .widgets import label

THUMB_W, THUMB_H = 176, 99
_CACHE: dict[tuple, QPixmap] = {}


def _backdrop(w: int, h: int) -> QImage:
    """Fondo neutro che somiglia a un video: serve per i modelli che stanno sopra le immagini."""
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#6B7385"))
    g.setColorAt(1, QColor("#363C4A"))
    p.fillRect(0, 0, w, h, g)
    p.end()
    return img


def render_template(tpl: T.Template, w: int = THUMB_W * 2, h: int = THUMB_H * 2) -> QImage:
    sample = T.SAMPLE
    if tpl.kind in ("title", "outro"):
        sc = tpl.build()
        base = _backdrop(w, h) if sc.over_video or sc.background.kind == "transparent" else C.render_scene_background(sc, w, h)
        return C.render_frame(substitute(sc.elements, sample), w, h, sc.duration * 0.6, sc.duration, base)
    if tpl.kind == "lower_third":
        lt = tpl.build()
        els = lower_third_elements(lt, 0, sample)
        return C.render_frame(els, w, h, lt.start + 2.2, 30.0, _backdrop(w, h))
    els = substitute(tpl.build(), sample)
    t = max((e.start for e in els), default=0.0) + 1.6
    return C.render_frame(els, w, h, t, 30.0, _backdrop(w, h))


def thumbnail(tpl: T.Template) -> QPixmap:
    key = (tpl.kind, tpl.id)
    if key not in _CACHE:
        img = render_template(tpl)
        _CACHE[key] = QPixmap.fromImage(img.scaled(THUMB_W * 2, THUMB_H * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return _CACHE[key]


class _Card(QAbstractButton):
    """Anteprima cliccabile con il nome sotto; il modello in uso ha il bordo evidenziato."""

    def __init__(self, tpl: T.Template, parent=None):
        super().__init__(parent)
        self.tpl = tpl
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(THUMB_W + 12, THUMB_H + 40)
        self.setToolTip(tpl.description)
        self.setAccessibleName(f"Modello {tpl.name}")

    def sizeHint(self):
        return QSize(THUMB_W + 12, THUMB_H + 40)

    def paintEvent(self, e):
        t = theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        hot = self.underMouse()
        p.setBrush(QColor(t.surface2 if hot else t.surface))
        p.setPen(QPen(QColor(t.accent if self.isChecked() else t.border), 2 if self.isChecked() else 1))
        p.drawRoundedRect(r, 10, 10)
        pr = QRectF(6, 6, THUMB_W, THUMB_H)
        clip = QPainterPath()
        clip.addRoundedRect(pr, 6, 6)
        p.save()
        p.setClipPath(clip)
        p.drawPixmap(pr.toRect(), thumbnail(self.tpl))
        p.restore()
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(self.isChecked())
        p.setFont(f)
        p.setPen(QColor(t.text))
        p.drawText(QRectF(8, THUMB_H + 10, THUMB_W - 4, 24), Qt.AlignVCenter | Qt.AlignLeft,
                   self.fontMetrics().elidedText(self.tpl.name, Qt.ElideRight, THUMB_W - 4))
        p.end()

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class TemplateGallery(QWidget):
    """Griglia dei modelli di una categoria, con filtro per genere. Emette `picked(id)`."""
    picked = Signal(str)

    def __init__(self, kind: str, current: str = "", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.current = current
        self._cards: list[_Card] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        tags = sorted({tag for t in T.ALL[kind] for tag in t.tags})
        self._filter = ""
        if len(tags) > 1:
            row = QHBoxLayout()
            row.addWidget(label("Genere:"))
            self.seg = QComboBox()
            self.seg.addItem("Tutti", "")
            for tag in tags:
                self.seg.addItem(tag.capitalize(), tag)
            self.seg.currentIndexChanged.connect(lambda _=0: self._set_filter(self.seg.currentData()))
            row.addWidget(self.seg)
            row.addStretch(1)
            lay.addLayout(row)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.grid_host)
        for tpl in T.ALL[kind]:
            c = _Card(tpl)
            c.clicked.connect(lambda _=False, i=tpl.id: self._pick(i))
            self._cards.append(c)
        self._cols = 0
        self._layout_cards()

    def set_current(self, tid: str):
        self.current = tid
        for c in self._cards:
            c.setChecked(c.tpl.id == tid)

    def _pick(self, tid: str):
        self.set_current(tid)
        self.picked.emit(tid)

    def _set_filter(self, tag):
        self._filter = tag if isinstance(tag, str) else ""
        self._cols = 0
        self._layout_cards()

    def _layout_cards(self):
        w = max(self.width(), THUMB_W + 12)
        cols = max(1, (w + 10) // (THUMB_W + 22))
        if cols == self._cols:
            return
        self._cols = cols
        while self.grid.count():
            self.grid.takeAt(0)
        n = 0
        for c in self._cards:
            show = not self._filter or self._filter in c.tpl.tags
            c.setVisible(show)
            if show:
                self.grid.addWidget(c, n // cols, n % cols)
                n += 1
        self.set_current(self.current)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_cards()


class TemplateDialog(QDialog):
    """Finestra «Scegli un modello» per la modalità Semplice."""

    def __init__(self, kind: str, current: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.chosen = ""
        lay = QVBoxLayout(self)
        lay.addWidget(label(title, "h2"))
        lay.addWidget(label("Scegli lo stile: potrai sempre cambiarlo. I testi si compilano nella schermata precedente.", "muted", True))
        from .graphics_page import scrolled
        self.gal = TemplateGallery(kind, current)
        self.gal.picked.connect(self._picked)
        sa = scrolled(self.gal)
        lay.addWidget(sa, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(760, 620)

    def _picked(self, tid: str):
        self.chosen = tid
        self.accept()


class VariablesForm(QWidget):
    """Campi di testo per i segnaposto: l'utente scrive «Titolo» e «Data», senza toccare l'editor."""
    PLACEHOLDERS = {"titolo": "es. Convegno sul futuro della città", "sottotitolo": "es. Seconda giornata",
                    "data": "es. 12 maggio 2026", "relatore": "es. Mario Rossi", "ruolo": "es. Sindaco",
                    "social": "es. @ilmiocanale"}

    def __init__(self, state, keys: list[str], parent=None):
        super().__init__(parent)
        self.state = state
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setHorizontalSpacing(10)
        lay.setVerticalSpacing(6)
        lay.setColumnStretch(1, 1)
        self.edits: dict[str, QLineEdit] = {}
        for r, k in enumerate(keys):
            lay.addWidget(label(VARIABLES[k]), r, 0)
            e = QLineEdit(state.spec.variables.get(k, ""))
            e.setPlaceholderText(self.PLACEHOLDERS.get(k, ""))
            e.textChanged.connect(lambda t, kk=k: self._set(kk, t))
            lay.addWidget(e, r, 1)
            self.edits[k] = e

    def _set(self, k: str, text: str):
        self.state.spec.variables[k] = text
        self.state.touch()

    def sync(self):
        for k, e in self.edits.items():
            v = self.state.spec.variables.get(k, "")
            if e.text() != v:
                e.blockSignals(True)
                e.setText(v)
                e.blockSignals(False)
