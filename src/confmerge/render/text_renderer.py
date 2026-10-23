"""Disegno di un elemento (testo, immagine, forma) con QPainter su QImage RGBA."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen)

from .animations import AnimState, ease
from .model import Background, Element, Fill


def new_image(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    return img


def qcolor(c: str, alpha: float = 1.0) -> QColor:
    col = QColor(c)
    col.setAlphaF(max(0.0, min(1.0, alpha)) * col.alphaF())
    return col


def make_brush_gradient(fill: Fill, rect: QRectF):
    cx, cy = rect.center().x(), rect.center().y()
    dx, dy = math.cos(math.radians(fill.angle)), math.sin(math.radians(fill.angle))  # 90° = alto → basso
    half = abs(dx) * rect.width() / 2 + abs(dy) * rect.height() / 2
    g = QLinearGradient(cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half)
    g.setColorAt(0, qcolor(fill.color))
    g.setColorAt(1, qcolor(fill.color2))
    return g


def fill_brush(fill: Fill, rect: QRectF):
    if fill.kind == "gradient":
        return make_brush_gradient(fill, rect)
    return qcolor(fill.color)


def blur_image(img: QImage, radius_px: float) -> QImage:
    """Sfocatura rapida: riduzione e ingrandimento con interpolazione (due passaggi)."""
    if radius_px < 1:
        return img
    f = max(1, int(radius_px / 1.5))
    w, h = img.width(), img.height()
    out = img
    for k in (f, max(1, f // 2)):
        small = out.scaled(max(1, w // k), max(1, h // k), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        out = small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return out


@lru_cache(maxsize=64)
def _load_image(path: str, px_w: int, px_h: int = 0) -> QImage | None:
    if path.lower().endswith(".svg"):
        from PySide6.QtSvg import QSvgRenderer
        r = QSvgRenderer(path)
        if not r.isValid():
            return None
        sz = r.defaultSize()
        if sz.isEmpty():
            return None
        w = max(1, px_w)
        h = max(1, round(w * sz.height() / sz.width()))
        img = new_image(w, h)
        p = QPainter(img)
        r.render(p)
        p.end()
        return img
    img = QImage(path)
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    if px_w > 0:
        img = img.scaledToWidth(px_w, Qt.SmoothTransformation)
    return img


def paint_background(img: QImage, bg: Background) -> None:
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    rect = QRectF(0, 0, img.width(), img.height())
    if bg.kind == "black":
        p.fillRect(rect, QColor("#000000"))
    elif bg.kind == "solid":
        p.fillRect(rect, qcolor(bg.color))
    elif bg.kind == "gradient":
        p.fillRect(rect, make_brush_gradient(Fill("gradient", bg.color, bg.color2, bg.angle), rect))
    elif bg.kind == "image" and bg.path:
        src = QImage(bg.path)
        if not src.isNull():
            s = src.scaled(img.width(), img.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawImage((img.width() - s.width()) // 2, (img.height() - s.height()) // 2, s)
        else:
            p.fillRect(rect, QColor("#000000"))
    p.end()  # "transparent": lascia l'immagine com'è


class _Block:
    """Layout del testo: righe, unità (lettere/parole) e rettangolo del blocco."""

    def __init__(self, el: Element, W: int, H: int):
        self.font = QFont(el.font)
        self.font.setPixelSize(max(4, round(el.size * H)))
        self.font.setBold(el.bold)
        self.font.setItalic(el.italic)
        if el.letter_spacing:
            self.font.setLetterSpacing(QFont.AbsoluteSpacing, el.letter_spacing * H)
        fm = QFontMetricsF(self.font)
        self.lines = el.text.split("\n") if el.text else [""]
        lh = fm.height() * el.line_spacing
        widths = [fm.horizontalAdvance(s) for s in self.lines]
        bw = max(widths + [1.0])
        bh = lh * len(self.lines)
        ax = el.x * W
        if el.align == "left":
            left = ax
        elif el.align == "right":
            left = ax - bw
        else:
            left = ax - bw / 2
        top = el.y * H - bh / 2
        self.rect = QRectF(left, top, bw, bh)
        self.fm, self.lh, self.widths = fm, lh, widths
        self.align = el.align

    def line_x(self, i: int) -> float:
        w = self.widths[i]
        if self.align == "left":
            return self.rect.left()
        if self.align == "right":
            return self.rect.right() - w
        return self.rect.center().x() - w / 2

    def units(self, mode: str):
        """Lista di (x, baseline, testo, indice_globale)."""
        out, n = [], 0
        for i, line in enumerate(self.lines):
            lx = self.line_x(i)
            base = self.rect.top() + i * self.lh + (self.lh - self.fm.height()) / 2 + self.fm.ascent()
            if mode == "by_letter":
                for j, ch in enumerate(line):
                    if ch.isspace():
                        continue
                    out.append((lx + self.fm.horizontalAdvance(line[:j]), base, ch, n))
                    n += 1
            elif mode == "by_word":
                pos = 0
                for word in line.split(" "):
                    if word:
                        out.append((lx + self.fm.horizontalAdvance(line[:pos]), base, word, n))
                        n += 1
                    pos += len(word) + 1
            else:
                out.append((lx, base, line, n))
                n += 1
        return out


def _draw_text_content(p: QPainter, el: Element, W: int, H: int, st: AnimState, blk: _Block) -> None:
    if el.box.enabled and el.text:
        pad = el.box.padding * H
        r = blk.rect.adjusted(-pad, -pad * 0.6, pad, pad * 0.6)
        p.setPen(Qt.NoPen)
        p.setBrush(qcolor(el.box.color, el.box.opacity))
        p.drawRoundedRect(r, el.box.radius * H, el.box.radius * H)
    mode = el.anim_in.kind if (st.unit_progress is not None and el.anim_in.kind in ("by_word", "by_letter")) else None
    if st.unit_progress is not None and mode is None:
        mode = el.anim_out.kind if el.anim_out.kind in ("by_word", "by_letter") else None
    units = blk.units(mode or "line")
    total = max(1, len(units))
    text = el.text
    if st.chars < 1.0:  # macchina da scrivere: prefisso, layout del testo completo
        units = _prefix_units(blk, text[:int(round(st.chars * len(text)))])
    pen = Qt.NoPen
    if el.outline.width > 0:
        pen = QPen(qcolor(el.outline.color), el.outline.width * H, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    for (x, base, s, n) in units:
        a = 1.0
        rise = 0.0
        if st.unit_progress is not None and mode:
            stag = (el.anim_in.stagger if st.unit_progress is not None else 0.05)
            dur = max(1e-3, el.anim_in.duration if mode == el.anim_in.kind else el.anim_out.duration)
            span = dur + stag * (total - 1)
            local = (st.unit_progress * span - n * stag) / dur
            e = ease(el.anim_in.easing, local)
            a = e
            rise = (1 - e) * 0.015 * H
            if a <= 0:
                continue
        path = QPainterPath()
        path.addText(QPointF(x, base + rise), blk.font, s)
        p.save()
        p.setOpacity(p.opacity() * a)
        p.setPen(pen)
        p.setBrush(fill_brush(el.fill, blk.rect))
        p.drawPath(path)
        p.restore()


def _prefix_units(blk: _Block, text: str):
    """Unità di riga limitate al prefisso `text` (mantiene la posizione del layout completo)."""
    out, remaining = [], len(text)
    for i, line in enumerate(blk.lines):
        if remaining <= 0:
            break
        part = line[:remaining]
        remaining -= len(line) + 1
        base = blk.rect.top() + i * blk.lh + (blk.lh - blk.fm.height()) / 2 + blk.fm.ascent()
        out.append((blk.line_x(i), base, part, i))
    return out


def _draw_shape(p: QPainter, el: Element, W: int, H: int) -> QRectF:
    r = QRectF(0, 0, el.w * W, el.h * H)
    r.moveCenter(QPointF(el.x * W, el.y * H))
    p.setBrush(fill_brush(el.fill, r))
    p.setPen(QPen(qcolor(el.outline.color), el.outline.width * H) if el.outline.width > 0 else Qt.NoPen)
    if el.shape == "ellipse":
        p.drawEllipse(r)
    elif el.shape == "line":
        p.setPen(QPen(qcolor(el.fill.color), max(1.0, el.h * H)))
        p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
    else:
        rad = el.radius * H
        p.drawRoundedRect(r, rad, rad)
    return r


def _draw_image(p: QPainter, el: Element, W: int, H: int) -> QRectF:
    px = max(1, round(el.width * W))
    img = _load_image(el.path, px) if el.path else None
    if img is None:
        r = QRectF(0, 0, px, px * 0.6)
        r.moveCenter(QPointF(el.x * W, el.y * H))
        p.setPen(QPen(QColor("#888888"), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        return r
    r = QRectF(0, 0, img.width(), img.height())
    r.moveCenter(QPointF(el.x * W, el.y * H))
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(r.topLeft(), img)
    return r


def render_element(el: Element, W: int, H: int, st: AnimState | None = None) -> QImage:
    """Elemento su un layer RGBA W×H, con trasformazioni, ombra e animazione applicate."""
    st = st or AnimState()
    content = new_image(W, H)
    p = QPainter(content)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    cx, cy = el.x * W, el.y * H
    p.translate(cx + st.dx * W, cy + st.dy * H)
    p.rotate(el.rotation)
    p.scale(max(st.scale, 1e-3), max(st.scale, 1e-3))
    p.translate(-cx, -cy)
    bbox: QRectF
    if el.kind == "text":
        blk = _Block(el, W, H)
        bbox = blk.rect
        if st.reveal < 1.0:
            p.setClipRect(QRectF(bbox.left() - 4, bbox.top() - 4, bbox.width() * st.reveal + 8, bbox.height() + 8))
        _draw_text_content(p, el, W, H, st, blk)
    elif el.kind == "image":
        px = max(1, round(el.width * W))
        img = _load_image(el.path, px) if el.path else None
        bbox = QRectF(0, 0, px, img.height() if img else px * 0.6)
        bbox.moveCenter(QPointF(cx, cy))
        if st.reveal < 1.0:
            p.setClipRect(QRectF(bbox.left(), bbox.top(), bbox.width() * st.reveal, bbox.height()))
        _draw_image(p, el, W, H)
    else:
        bbox = QRectF(0, 0, el.w * W, el.h * H)
        bbox.moveCenter(QPointF(cx, cy))
        if st.reveal < 1.0:
            p.setClipRect(QRectF(bbox.left(), bbox.top(), bbox.width() * st.reveal, bbox.height()))
        _draw_shape(p, el, W, H)
    p.end()

    out = content
    if st.blur > 0:
        out = blur_image(out, st.blur * H)
    if el.shadow.enabled and el.kind in ("text", "image", "shape"):
        sh = content.copy()
        q = QPainter(sh)
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        q.fillRect(sh.rect(), qcolor(el.shadow.color, el.shadow.opacity))
        q.end()
        sh = blur_image(sh, el.shadow.blur * H)
        ang = math.radians(el.shadow.angle)
        dist = el.shadow.distance * H
        res = new_image(W, H)
        q = QPainter(res)
        q.drawImage(round(math.cos(ang) * dist), round(math.sin(ang) * dist), sh)
        q.drawImage(0, 0, out)
        q.end()
        out = res
    return out
