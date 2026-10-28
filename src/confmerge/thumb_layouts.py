"""Miniature YouTube 1280×720 con layout pronti: un fotogramma del video + titolo grande + colori e loghi del marchio.

Ogni layout è una piccola funzione che disegna lo sfondo (fotogramma, fasce, sfumature) e restituisce i testi come
elementi del motore grafico: così carattere, bordo e ombra sono gli stessi dei video."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

from .brand_kit import KitColors, contrast_color, logo_size
from .render import compositor
from .render.model import Box, Element, Fill, Outline, Shadow

W, H = 1280, 720


@dataclass
class Palette:
    colors: KitColors = field(default_factory=lambda: KitColors(primary="#DC2626", secondary="#111827", accent="#FACC15",
                                                                  text="#FFFFFF", background="#0B1220"))
    font_title: str = "Anton"
    font_body: str = "Poppins"


@dataclass
class Fields:
    title: str = "IL TUO TITOLO"
    sub: str = ""
    uppercase: bool = True
    frame_x: float = 0.5          # parte del fotogramma da mostrare (0 = sinistra, 1 = destra)
    logos: list[tuple[str, str]] = field(default_factory=list)      # (percorso, ruolo: main | symbol)
    size_scale: float = 1.0       # ingrandisce o rimpicciolisce i testi del layout
    dx: float = 0.0               # sposta i testi (frazione della larghezza / dell'altezza)
    dy: float = 0.0
    title_color: str = ""         # vuoto = quello del layout
    sub_color: str = ""
    dim: float = 0.0              # scurisce la foto (0 … 0,7)
    saturation: float = 1.0       # colori della foto più vivi (>1) o spenti (<1)
    extras: list[Element] = field(default_factory=list)             # testi e immagini aggiunti a mano, liberi sulla miniatura


@dataclass
class Layout:
    id: str
    name: str
    description: str
    sub_label: str                # a che cosa serve il secondo campo
    draw: Callable[[QPainter, QImage | None, Fields, Palette], list[Element]]
    logo_corners: tuple[str, str] = ("tr", "br")      # dove stanno logo principale e simbolo senza coprire il testo


def balanced(text: str, max_chars: int) -> str:
    """A capo automatico con righe di lunghezza simile, così il titolo resta grande invece di rimpicciolirsi."""
    text = " ".join(text.split()) if "\n" not in text else text
    if "\n" in text or len(text) <= max_chars:
        return text
    n = -(-len(text) // max_chars)
    limit = -(-len(text) // n) + 1
    lines, cur = [], ""
    for w in text.split(" "):
        if cur and len(cur) + 1 + len(w) > limit and len(lines) < n - 1:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    return "\n".join(lines)


def lines_size(text: str, size: float, max_h: float, spacing: float = 1.0) -> float:
    """Corpo che fa stare tutte le righe dentro `max_h` (frazione dell'altezza): il titolo non esce dall'immagine."""
    n = text.count("\n") + 1
    return min(size, max_h / (n * spacing * 1.25))


def _cover(p: QPainter, frame: QImage | None, rect: QRectF, fx: float = 0.5, fy: float = 0.5) -> None:
    """Il fotogramma riempie `rect` (ritagliato, non deformato); `fx` sceglie la parte da mostrare."""
    if frame is None or frame.isNull():
        p.fillRect(rect, QColor("#2B3140"))
        return
    s = max(rect.width() / frame.width(), rect.height() / frame.height())
    sw, sh = rect.width() / s, rect.height() / s
    src = QRectF((frame.width() - sw) * fx, (frame.height() - sh) * fy, sw, sh)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(rect, frame, src)


def _grad(p: QPainter, rect: QRectF, top: str, bottom: str, a_top: float, a_bottom: float) -> None:
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    c1, c2 = QColor(top), QColor(bottom)
    c1.setAlphaF(a_top)
    c2.setAlphaF(a_bottom)
    g.setColorAt(0, c1)
    g.setColorAt(1, c2)
    p.fillRect(rect, g)


def _veil(p: QPainter, color: str, alpha: float, rect: QRectF | None = None) -> None:
    c = QColor(color)
    c.setAlphaF(alpha)
    p.fillRect(rect or QRectF(0, 0, W, H), c)


def _text(id_: str, text: str, x: float, y: float, size: float, color: str, f: Fields, pal: Palette, *, body: bool = False,
          align: str = "center", fit: float = 0.9, outline: str = "#000000", ow: float = 0.0, shadow: bool = True,
          box: Box | None = None, line_spacing: float = 0.95, upper: bool | None = None, rot: float = 0.0) -> Element:
    return Element(id=id_, kind="text", text=text, x=x, y=y, size=size, font=pal.font_body if body else pal.font_title,
                   bold=body or pal.font_title not in ("Anton", "Bebas Neue"), fill=Fill(color=color), align=align,
                   uppercase=f.uppercase if upper is None else upper, fit_width=fit, line_spacing=line_spacing,
                   outline=Outline(ow, outline), shadow=Shadow(enabled=shadow, color="#000000", blur=0.01, distance=0.008, opacity=0.6),
                   box=box or Box(), rotation=rot)


# ---------------------------------------------------------------------------------------------------------- layout
def _volto_titolo(p, frame, f, pal):
    _cover(p, frame, QRectF(0, 0, W, H), f.frame_x)
    _grad(p, QRectF(0, H * 0.35, W, H * 0.65), "#000000", "#000000", 0.0, 0.88)
    title = balanced(f.title, 17)
    els = [_text("t", title, 0.06, 0.70, lines_size(title, 0.19, 0.42, 0.95), pal.colors.text, f, pal, align="left", fit=0.88, ow=0.006)]
    if f.sub:
        c = pal.colors
        els.append(_text("s", f.sub, 0.06, 0.915, 0.062, contrast_color(c.accent), f, pal, body=True, align="left", fit=0.6,
                         shadow=False, box=Box(True, c.accent, 1.0, 0.012, 0.01), upper=False))
    return els


def _a_lato(p, frame, f, pal):
    p.fillRect(QRectF(0, 0, W, H), QColor(pal.colors.primary))
    _cover(p, frame, QRectF(0, 0, W * 0.54, H), f.frame_x)
    ink = contrast_color(pal.colors.primary)
    title = balanced(f.title, 11)
    els = [_text("t", title, 0.57, 0.44, lines_size(title, 0.17, 0.68, 0.95), ink, f, pal, align="left", fit=0.4, line_spacing=0.95, shadow=False)]
    if f.sub:
        els.append(_text("s", f.sub, 0.57, 0.88, 0.06, pal.colors.accent, f, pal, body=True, align="left", fit=0.4, upper=False, shadow=False))
    return els


def _citazione(p, frame, f, pal):
    _cover(p, frame, QRectF(0, 0, W, H), f.frame_x)
    _veil(p, pal.colors.secondary, 0.78)
    els = [_text("q", "“", 0.1, 0.27, 0.5, pal.colors.accent, f, pal, body=True, upper=False, fit=0.2, shadow=False),
           _text("t", balanced(f.title, 24), 0.5, 0.55, 0.1, pal.colors.text, f, pal, body=True, fit=0.8, upper=False, shadow=False,
                 line_spacing=1.1)]
    if f.sub:
        els.append(_text("s", "— " + f.sub, 0.5, 0.86, 0.06, pal.colors.accent, f, pal, body=True, fit=0.7, upper=False, shadow=False))
    return els


def _dato(p, frame, f, pal):
    _cover(p, frame, QRectF(0, 0, W, H), f.frame_x)
    _veil(p, pal.colors.secondary, 0.82)
    els = [_text("t", f.title, 0.5, 0.42, 0.42, pal.colors.accent, f, pal, fit=0.9, ow=0.004, shadow=True, upper=False)]
    if f.sub:
        els.append(_text("s", f.sub, 0.5, 0.78, 0.085, pal.colors.text, f, pal, fit=0.85, shadow=False))
    return els


def _evento(p, frame, f, pal):
    _cover(p, frame, QRectF(0, 0, W, H), f.frame_x)
    p.fillRect(QRectF(0, 0, W, H * 0.24), QColor(pal.colors.primary))
    els = [_text("t", f.title, 0.5, 0.12, 0.15, contrast_color(pal.colors.primary), f, pal, fit=0.92, shadow=False)]
    if f.sub:
        p.fillRect(QRectF(0, H * 0.86, W, H * 0.14), QColor(pal.colors.accent))
        els.append(_text("s", f.sub, 0.5, 0.93, 0.075, contrast_color(pal.colors.accent), f, pal, body=True, fit=0.9, shadow=False))
    return els


def _fascia(p, frame, f, pal):
    _cover(p, frame, QRectF(0, 0, W, H), f.frame_x)
    _veil(p, "#000000", 0.18)
    p.save()
    p.translate(W / 2, H * 0.68)
    p.rotate(-5)
    p.fillRect(QRectF(-W, -H * 0.15, 2 * W, H * 0.30), QColor(pal.colors.accent))
    p.restore()
    els = [_text("t", balanced(f.title, 20), 0.5, 0.67, 0.15, contrast_color(pal.colors.accent), f, pal, fit=0.88, shadow=False, rot=-5)]
    if f.sub:
        els.append(_text("s", f.sub, 0.5, 0.9, 0.06, pal.colors.text, f, pal, body=True, fit=0.8, upper=False, ow=0.004))
    return els


def _evidenziatore(p, frame, f, pal):
    _cover(p, frame, QRectF(0, 0, W, H), f.frame_x)
    _veil(p, "#000000", 0.25)
    c = pal.colors
    title = balanced(f.title, 14)
    els = [_text("t", title, 0.06, 0.36, lines_size(title, 0.16, 0.52, 1.15), contrast_color(c.accent), f, pal, align="left", fit=0.62,
                 shadow=False, box=Box(True, c.accent, 1.0, 0.014, 0.008), line_spacing=1.15)]
    if f.sub:
        els.append(_text("s", f.sub, 0.06, 0.8, 0.07, contrast_color(c.primary), f, pal, body=True, align="left", fit=0.6, shadow=False,
                         box=Box(True, c.primary, 1.0, 0.012, 0.008), upper=False))
    return els


def _minimale(p, frame, f, pal):
    g = QLinearGradient(QPointF(0, 0), QPointF(W, H))
    g.setColorAt(0, QColor(pal.colors.primary))
    g.setColorAt(1, QColor(pal.colors.secondary))
    p.fillRect(QRectF(0, 0, W, H), g)
    els = [_text("t", balanced(f.title, 16), 0.5, 0.46, 0.18, pal.colors.text, f, pal, fit=0.84, shadow=False, line_spacing=0.95)]
    if f.sub:
        els.append(_text("s", f.sub, 0.5, 0.82, 0.075, pal.colors.accent, f, pal, body=True, fit=0.8, upper=False, shadow=False))
    return els


LAYOUTS = [
    Layout("volto_titolo", "Titolo sull'immagine", "Immagine a tutto schermo e titolo grande in basso.", "Etichetta (facoltativa)", _volto_titolo, ("tr", "tl")),
    Layout("a_lato", "Immagine e titolo a lato", "Metà immagine, metà colore con il titolo.", "Frase sotto il titolo", _a_lato, ("br", "tl")),
    Layout("evidenziatore", "Titolo evidenziato", "Titolo su fondo giallo, come i canali più visti.", "Etichetta (facoltativa)", _evidenziatore, ("tr", "br")),
    Layout("fascia", "Fascia in diagonale", "Una fascia colorata taglia l'immagine.", "Frase sotto la fascia", _fascia, ("tr", "tl")),
    Layout("evento", "Evento", "Titolo in alto, data e luogo in basso.", "Data e luogo", _evento, ("bl", "br")),
    Layout("citazione", "Citazione", "Una frase detta da qualcuno, con il nome.", "Chi la dice", _citazione, ("tr", "br")),
    Layout("dato", "Dato in evidenza", "Un numero enorme e una riga che lo spiega.", "Che cosa indica", _dato, ("tr", "br")),
    Layout("minimale", "Solo titolo", "Titolo su fondo colorato, senza immagine.", "Frase sotto il titolo", _minimale, ("tr", "br")),
]
BY_ID = {lay.id: lay for lay in LAYOUTS}
SAMPLES = {"volto_titolo": ("COSA È CAMBIATO", "Novità"), "a_lato": ("IL FUTURO DELLA NOSTRA CITTÀ INSIEME", "Incontro pubblico"),
           "evidenziatore": ("PERCHÉ NESSUNO NE PARLA DI QUESTO", "Da vedere"), "fascia": ("LA SVOLTA", "Tutto quello che c'è da sapere"),
           "evento": ("ASSEMBLEA CITTADINA", "Sabato 12 maggio · Sala civica"), "citazione": ("Il bene comune non è un\nfavore: è un dovere.", "Mario Rossi"),
           "dato": ("73%", "dei cittadini ha partecipato"), "minimale": ("RELAZIONE ANNUALE", "Bilancio 2026")}


def _logo_elements(f: Fields, corners: tuple[str, str]) -> list[Element]:
    out, m = [], 0.03
    for i, (path, role) in enumerate(f.logos):
        if not path or not os.path.exists(path):
            continue
        iw, ih = logo_size(path)
        if not iw:
            continue
        corner = corners[0] if role == "main" else corners[1]
        w = 0.14 if role == "main" else 0.1
        wp, hp = w * W, w * W * ih / iw
        x = (m * W + wp / 2) if corner in ("tl", "bl") else (W - m * W - wp / 2)
        y = (m * W + hp / 2) if corner in ("tl", "tr") else (H - m * W - hp / 2)
        out.append(Element(id=f"__tl{i}", kind="image", path=path, width=w, x=x / W, y=y / H))
    return out


def adjust_frame(frame: QImage | None, dim: float, saturation: float) -> QImage | None:
    """Foto più scura o con i colori più vivi/spenti: serve a far risaltare il titolo."""
    if frame is None or frame.isNull() or (dim <= 0.001 and abs(saturation - 1.0) < 0.01):
        return frame
    import numpy as np
    img = frame.convertToFormat(QImage.Format_ARGB32).copy()
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.bits(), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w].astype(np.float32)   # B G R A
    rgb = arr[..., 2::-1]
    gray = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114)[..., None]       # colori vivi o spenti, poi più scuro
    out = np.clip((gray + (rgb - gray) * saturation) * (1.0 - dim), 0, 255).astype(np.uint8)
    res = np.ascontiguousarray(np.dstack([out[..., 2], out[..., 1], out[..., 0], arr[..., 3].astype(np.uint8)]))
    return QImage(res.data, w, h, w * 4, QImage.Format_ARGB32).copy()


def render(layout_id: str, frame: QImage | None, fields: Fields, palette: Palette | None = None,
           width: int = W, height: int = H) -> QImage:
    """Miniatura finita. `width`/`height` solo per le anteprime piccole (le proporzioni sono sempre 16:9)."""
    pal = palette or Palette()
    lay = BY_ID[layout_id]
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(pal.colors.background))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    if frame is not None and (fields.dim > 0.001 or abs(fields.saturation - 1.0) > 0.01):
        small = frame.scaled(W, H, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation) if frame.width() > W else frame
        frame = adjust_frame(small, fields.dim, fields.saturation)
    els = lay.draw(p, frame, fields, pal)
    p.end()
    for e in els:                                                    # personalizzazioni sopra il layout scelto
        if e.kind != "text":
            continue
        e.size *= fields.size_scale
        e.x, e.y = e.x + fields.dx, e.y + fields.dy
        if fields.title_color and e.id in ("t", "q"):
            e.fill.color = fields.title_color
        if fields.sub_color and e.id == "s":
            e.fill.color = fields.sub_color
    els += _logo_elements(fields, lay.logo_corners)
    els += [e for e in fields.extras if e.visible]
    out = compositor.render_frame(els, W, H, 0.0, 1e9, img)
    return out if (width, height) == (W, H) else out.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
