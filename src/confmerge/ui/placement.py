"""Studio Social: elementi che si trascinano sull'anteprima (testi, immagini, loghi, sottotitoli) con aggancio e centratura.

Ogni elemento ha un rettangolo nel fotogramma (frazioni della larghezza e dell'altezza). Si aggancia al centro, a un terzo,
e ai bordi della zona sicura (margine + zona coperta dall'app); tenendo premuto Alt l'aggancio si spegne."""
from __future__ import annotations

from PySide6.QtCore import QRectF

from .. import subtitles
from ..render import anchors
from ..render.model import substitute
from ..render.text_renderer import element_bbox

SNAP = 0.012                  # distanza di aggancio (frazione del lato)


def items(state, W: int, H: int) -> list[tuple[str, int, QRectF]]:
    """Gli elementi spostabili, dal fondo alla cima: (tipo, indice, rettangolo in pixel del fotogramma).
    Tipi: «el» testo/immagine, «logo» logo del marchio, «sub» sottotitoli."""
    from ..brand import brand_elements
    spec = state.spec
    out = []
    safe = spec.brand.safe
    for i, e in enumerate(spec.graphics.elements):
        if "main" in e.targets and e.visible and e.kind in ("text", "image", "shape"):
            r = anchors.resolve(substitute([e], spec.variables), W, H, safe)[0]
            out.append(("el", i, element_bbox(r, W, H)))
    for be in brand_elements(spec, W, H):
        out.append(("logo", int(be.id.replace("__logo", "")), element_bbox(be, W, H)))
    st = spec.subtitles
    if st.enabled:
        lines = subtitles.chunked_lines(st)
        text = subtitles.SAMPLE_TEXT if not lines else lines[0].text
        if not lines and st.chunk_words:
            text = " ".join(text.split()[:st.chunk_words])
        out.append(("sub", 0, element_bbox(subtitles.preview_element(st, text, W, H, safe), W, H)))
    return out


def hit(its, x: float, y: float):
    """L'elemento più in alto sotto il punto (x, y in pixel del fotogramma), o None."""
    for kind, i, r in reversed(its):
        if r.adjusted(-6, -6, 6, 6).contains(x, y):
            return kind, i, r
    return None


def snap(cx: float, cy: float, hw: float, hh: float, W: int, H: int, safe) -> tuple[float, float, list[tuple[str, float]]]:
    """Aggancia il centro (cx, cy) e restituisce anche le guide da disegnare. Tutto in frazioni del fotogramma."""
    top, bottom, left, right = (list(safe or []) + [0.0] * 4)[:4]
    m = anchors.MARGIN
    my = m * W / H
    xs = [("c", 0.5), ("c", 1 / 3), ("c", 2 / 3), ("l", left + m), ("r", 1 - right - m)]
    ys = [("c", 0.5), ("c", 1 / 3), ("c", 2 / 3), ("l", top + my), ("r", 1 - bottom - my)]
    if left or right:
        xs.append(("c", (left + 1 - right) / 2))               # centro dell'area sicura
    if top or bottom:
        ys.append(("c", (top + 1 - bottom) / 2))
    guides: list[tuple[str, float]] = []

    def one(c: float, half: float, cands, axis: str) -> float:
        best, bd, line = c, SNAP, None
        for kind, v in cands:
            target = v if kind == "c" else (v + half if kind == "l" else v - half)       # l = bordo vicino, r = bordo lontano
            d = abs(c - target)
            if d < bd:
                best, bd, line = target, d, v
        if line is not None:
            guides.append((axis, line))
        return best

    return one(cx, hw, xs, "x"), one(cy, hh, ys, "y"), guides


def center(state, kind: str, idx: int, W: int, H: int, horizontal: bool, vertical: bool, safe=None) -> None:
    """Centra l'elemento (orizzontalmente e/o verticalmente); il resto della posizione non cambia.
    `safe` = (sopra, sotto, sinistra, destra): centra nell'area sicura invece che nel video intero."""
    spec = state.spec
    its = {(k, i): r for k, i, r in items(state, W, H)}
    r = its.get((kind, idx))
    if r is None:
        return
    cx, cy = r.center().x() / W, r.center().y() / H
    top, bottom, left, right = (list(safe or []) + [0.0] * 4)[:4]
    if horizontal:
        cx = (left + 1 - right) / 2
    if vertical:
        cy = (top + 1 - bottom) / 2
    place(state, kind, idx, cx, cy, r.width() / W, r.height() / H, W, H)


def place(state, kind: str, idx: int, cx: float, cy: float, w: float, h: float, W: int, H: int) -> None:
    """Scrive la nuova posizione (centro in frazioni) nel modello: l'elemento diventa «libero»."""
    spec = state.spec
    if kind == "el":
        e = spec.graphics.elements[idx]
        e.anchor, e.x, e.y = "", cx, cy
    elif kind == "logo":
        lg = spec.brand.logos[idx]
        lg.corner, lg.x, lg.y = "free", cx, cy
    elif kind == "sub":
        st = spec.subtitles
        st.x, st.y = cx, cy                                  # posizione libera: vale al posto di «posizione» e «distanza»


def label_of(state, kind: str, idx: int) -> str:
    spec = state.spec
    if kind == "sub":
        return "Sottotitoli"
    if kind == "logo":
        lg = spec.brand.logos[idx]
        from ..brand_kit import ROLE_SHORT
        return f"{ROLE_SHORT.get(lg.role, 'Logo')}: {lg.name or 'senza nome'}"
    e = spec.graphics.elements[idx]
    return f"Testo: «{e.text[:24]}»" if e.kind == "text" else f"Immagine: {e.path.split('/')[-1][:24]}"
