"""Slide (PDF via QtPdf, immagini) e geometrie/PNG per picture-in-picture, tutto disegnato con QPainter."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from .render.text_renderer import blur_image, new_image, qcolor
from .spec import LayoutSpan, PipSettings, SlideChange, SlideSettings

PDF_RENDER_WIDTH = 1920


def load_slides(files: list[str], width: int = PDF_RENDER_WIDTH) -> list[QImage]:
    """Carica PDF (QtPdf) e immagini in un'unica lista di pagine/slide."""
    out: list[QImage] = []
    for f in files:
        if f.lower().endswith(".pdf"):
            from PySide6.QtPdf import QPdfDocument
            doc = QPdfDocument()
            doc.load(f)
            if doc.status() != QPdfDocument.Status.Ready:
                raise ValueError(f"Impossibile aprire il PDF «{Path(f).name}»")
            for i in range(doc.pageCount()):
                pt = doc.pagePointSize(i)
                h = max(1, round(width * pt.height() / pt.width()))
                out.append(doc.render(i, QSize(width, h)).convertToFormat(QImage.Format_ARGB32_Premultiplied))
        else:
            img = QImage(f)
            if img.isNull():
                raise ValueError(f"Impossibile aprire l'immagine «{Path(f).name}»")
            out.append(img.convertToFormat(QImage.Format_ARGB32_Premultiplied))
    return out


@dataclass
class Interval:
    a: float
    b: float
    layout: str
    slide: int


def intervals(sl: SlideSettings, duration: float, n_slides: int = 1) -> list[Interval]:
    """Suddivide [0,D] ai cambi di slide e di layout."""
    layouts = sorted(sl.layouts, key=lambda s: s.t) or [LayoutSpan(0.0, "slide_full")]
    changes = sorted(sl.changes, key=lambda c: c.t)
    cuts = {0.0, duration}
    cuts.update(s.t for s in layouts if 0 < s.t < duration)
    cuts.update(c.t for c in changes if 0 < c.t < duration)
    pts = sorted(cuts)
    out = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 1e-3:
            continue
        lay = next((s.layout for s in reversed(layouts) if s.t <= a + 1e-6), layouts[0].layout)
        idx = next((c.index for c in reversed(changes) if c.t <= a + 1e-6), 0)
        out.append(Interval(a, b, lay, max(0, min(idx, max(0, n_slides - 1)))))
    return out


def pip_rect(pip: PipSettings, W: int, H: int, aspect: float | None = None) -> QRectF:
    """Rettangolo del riquadro piccolo; aspect = larghezza/altezza (default: del frame)."""
    aspect = aspect or W / H
    pw = round(pip.size * W / 2) * 2
    ph = round(pw / aspect / 2) * 2
    m = pip.margin * W
    x = m if pip.corner in ("tl", "bl") else W - pw - m
    y = m if pip.corner in ("tl", "tr") else H - ph - m
    return QRectF(round(x), round(y), pw, ph)


def side_rects(pip: PipSettings, W: int, H: int) -> tuple[QRectF, QRectF]:
    """Affiancati: relatore a sinistra, slide a destra (metà frame ciascuno, centrati verticalmente)."""
    m = pip.margin * W / 2
    half = W / 2 - m * 1.5
    h = H * 0.9
    left = QRectF(m, (H - h) / 2, half, h)
    right = QRectF(W / 2 + m * 0.5, (H - h) / 2, half, h)
    return left, right


def fit_rect(src_w: int, src_h: int, box: QRectF) -> QRectF:
    s = min(box.width() / src_w, box.height() / src_h)
    w, h = src_w * s, src_h * s
    return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)


def _decor(p: QPainter, rect: QRectF, pip: PipSettings, H: int, W: int) -> None:
    """Ombra e bordo attorno a un riquadro (sotto il contenuto)."""
    if pip.shadow:
        sh = new_image(W, H)
        q = QPainter(sh)
        q.setRenderHint(QPainter.Antialiasing)
        q.setPen(Qt.NoPen)
        q.setBrush(QColor(0, 0, 0, 170))
        q.drawRoundedRect(rect.translated(0, H * 0.006), pip.radius * H, pip.radius * H)
        q.end()
        p.drawImage(0, 0, blur_image(sh, H * 0.012))
    if pip.border > 0:
        b = pip.border * H
        p.setPen(Qt.NoPen)
        p.setBrush(qcolor(pip.border_color))
        p.drawRoundedRect(rect.adjusted(-b, -b, b, b), pip.radius * H + b, pip.radius * H + b)


def decor_png(rect: QRectF, pip: PipSettings, W: int, H: int) -> QImage:
    img = new_image(W, H)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    _decor(p, rect, pip, H, W)
    p.end()
    return img


def mask_png(w: int, h: int, radius_px: float) -> QImage:
    img = QImage(w, h, QImage.Format_Grayscale8)
    img.fill(Qt.black)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(Qt.white)
    p.drawRoundedRect(QRectF(0, 0, w, h), radius_px, radius_px)
    p.end()
    return img


def full_slide_png(slide: QImage, W: int, H: int) -> QImage:
    img = new_image(W, H)
    p = QPainter(img)
    p.fillRect(0, 0, W, H, Qt.black)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(fit_rect(slide.width(), slide.height(), QRectF(0, 0, W, H)), slide)
    p.end()
    return img


def small_slide_png(slide: QImage, pip: PipSettings, W: int, H: int, rect: QRectF | None = None) -> QImage:
    """Layer trasparente W×H con la slide in piccolo (ombra, bordo, angoli arrotondati)."""
    box = rect or pip_rect(pip, W, H, slide.width() / slide.height())
    r = fit_rect(slide.width(), slide.height(), box)
    img = new_image(W, H)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    _decor(p, r, pip, H, W)
    path = QPainterPath()
    path.addRoundedRect(r, pip.radius * H, pip.radius * H)
    p.setClipPath(path)
    p.drawImage(r, slide)
    p.end()
    return img


def side_by_side_png(slide: QImage, pip: PipSettings, W: int, H: int) -> QImage:
    """Sfondo nero a schermo intero con la slide a destra; il relatore viene sovrapposto a sinistra."""
    left, right = side_rects(pip, W, H)
    img = new_image(W, H)
    p = QPainter(img)
    p.fillRect(0, 0, W, H, Qt.black)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    r = fit_rect(slide.width(), slide.height(), right)
    _decor(p, r, pip, H, W)
    path = QPainterPath()
    path.addRoundedRect(r, pip.radius * H, pip.radius * H)
    p.setClipPath(path)
    p.drawImage(r, slide)
    p.end()
    return img


def nearest_change_index(changes: list[SlideChange], t: float) -> int:
    idx = 0
    for c in sorted(changes, key=lambda c: c.t):
        if c.t <= t:
            idx = c.index
    return idx
