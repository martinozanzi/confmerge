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
    r2 = split_rect(state, W, H)
    if r2 is not None:
        out.append(("split", 0, r2))                          # il riquadro del secondo video sta sotto a tutto il resto
    for i, e in enumerate(spec.graphics.elements):
        if "main" in e.targets and e.visible and e.kind in ("text", "image", "clip", "shape"):
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


def split_rect(state, W: int, H: int) -> QRectF | None:
    """Rettangolo (pixel) del riquadro del secondo video, se c'è."""
    sp = state.spec.split
    if not (sp.enabled and sp.path and getattr(state.project, "kind", "") == "social"):
        return None
    from ..spec import split_heights
    top, gap, bot = split_heights(sp, H)
    return QRectF(0, top + gap, W, bot) if sp.main_on_top else QRectF(0, 0, W, top)


def split_boundary(state, H: int) -> float | None:
    """Altezza (frazione) del bordo fra i due riquadri."""
    sp = state.spec.split
    if not (sp.enabled and sp.path):
        return None
    from ..spec import split_heights
    top, gap, _ = split_heights(sp, H)
    return (top + gap / 2) / H


def hit(its, x: float, y: float):
    """L'elemento più in alto sotto il punto (x, y in pixel del fotogramma), o None."""
    for kind, i, r in reversed(its):
        if kind == "split":
            if r.contains(x, y):
                return kind, i, r                              # il secondo video si prende dentro, non attorno
        elif r.adjusted(-6, -6, 6, 6).contains(x, y):
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
    if kind == "split":
        return "Secondo video"
    if kind == "logo":
        lg = spec.brand.logos[idx]
        from ..brand_kit import ROLE_SHORT
        return f"{ROLE_SHORT.get(lg.role, 'Logo')}: {lg.name or 'senza nome'}"
    e = spec.graphics.elements[idx]
    return f"Testo: «{e.text[:24]}»" if e.kind == "text" else f"Immagine: {e.path.split('/')[-1][:24]}"


# ------------------------------------------------------------------------------------------------ ridimensionamento
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
HANDLE_PX = 8                      # lato della maniglia disegnata (pixel dello schermo)


def handle_points(r: QRectF) -> dict[str, tuple[float, float]]:
    """Le 8 maniglie di un rettangolo: angoli e metà dei lati."""
    x0, y0, x1, y1, cx, cy = r.left(), r.top(), r.right(), r.bottom(), r.center().x(), r.center().y()
    return {"nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0), "e": (x1, cy), "se": (x1, y1), "s": (cx, y1), "sw": (x0, y1), "w": (x0, cy)}


def handle_at(r: QRectF, x: float, y: float, tol: float) -> str:
    """Maniglia sotto il punto (stesse unità di `r`), o «»."""
    best, bd = "", tol
    for name, (hx, hy) in handle_points(r).items():
        d = max(abs(hx - x), abs(hy - y))
        if d <= bd:
            best, bd = name, d
    return best


def has_handles(state, kind: str, idx: int) -> bool:
    return kind in ("el", "logo", "sub")


def sizes(state, kind: str, idx: int) -> dict:
    """Le grandezze di un elemento, per poterle riportare com'erano (e per il ridimensionamento)."""
    spec = state.spec
    if kind == "sub":
        return {"size": spec.subtitles.size}
    if kind == "logo":
        return {"size": spec.brand.logos[idx].size}
    e = spec.graphics.elements[idx]
    return {"size": e.size, "width": e.width, "w": e.w, "h": e.h, "fit_width": e.fit_width}


def scale_values(state, kind: str, idx: int, orig: dict, fx: float, fy: float, free: bool = False) -> None:
    """Applica un fattore di scala: testo → corpo, immagine → larghezza, logo/sottotitoli → grandezza, forma → larghezza e
    altezza (`free`: i due fattori sono indipendenti)."""
    spec = state.spec
    f = max(fx, fy)
    if kind == "sub":
        spec.subtitles.size = min(0.2, max(0.015, orig["size"] * f))
    elif kind == "logo":
        spec.brand.logos[idx].size = min(0.9, max(0.03, orig["size"] * f))
    else:
        e = spec.graphics.elements[idx]
        if e.kind == "text":
            e.size = min(0.5, max(0.01, orig["size"] * f))
            e.fit_width = 0.0                                     # grandezza decisa a mano: non si rimpicciolisce più da sola
        elif e.kind in ("image", "clip"):
            e.width = min(1.5, max(0.02, orig["width"] * f))
        elif e.kind == "shape":
            gx, gy = (fx, fy) if free else (f, f)
            e.w, e.h = min(2.0, max(0.005, orig["w"] * gx)), min(2.0, max(0.005, orig["h"] * gy))


def restore_sizes(state, kind: str, idx: int, orig: dict) -> None:
    spec = state.spec
    if kind == "sub":
        spec.subtitles.size = orig["size"]
    elif kind == "logo":
        spec.brand.logos[idx].size = orig["size"]
    else:
        e = spec.graphics.elements[idx]
        e.size, e.width, e.w, e.h, e.fit_width = orig["size"], orig["width"], orig["w"], orig["h"], orig["fit_width"]


def snap_lines(W: int, H: int, safe) -> tuple[list[float], list[float]]:
    """Posizioni (frazioni) a cui si agganciano i bordi: centro, terzi, margini e area sicura."""
    top, bottom, left, right = (list(safe or []) + [0.0] * 4)[:4]
    m = anchors.MARGIN
    my = m * W / H
    xs = [0.5, 1 / 3, 2 / 3, left + m, 1 - right - m]
    ys = [0.5, 1 / 3, 2 / 3, top + my, 1 - bottom - my]
    if left or right:
        xs.append((left + 1 - right) / 2)
    if top or bottom:
        ys.append((top + 1 - bottom) / 2)
    return xs, ys


def snap_value(v: float, lines: list[float], axis: str, guides: list) -> float:
    best, bd = v, SNAP
    for ln in lines:
        d = abs(v - ln)
        if d < bd:
            best, bd = ln, d
    if best != v:
        guides.append((axis, best))
    return best


def resize_rect(r0: QRectF, handle: str, px: float, py: float, W: int, H: int, safe=None, snap_on: bool = True,
                keep_ratio: bool = True, min_px: float = 6.0):
    """Trascinando la maniglia `handle` fino al punto (px, py) (pixel del fotogramma): il lato opposto resta fermo.
    Restituisce (nuovo rettangolo, fattore x, fattore y, guide). Con `keep_ratio` i due fattori sono uguali."""
    guides: list[tuple[str, float]] = []
    xs, ys = snap_lines(W, H, safe)
    side_x, side_y = ("e" in handle or "w" in handle), ("n" in handle or "s" in handle)
    if snap_on:
        if side_x:
            px = snap_value(px / W, xs, "x", guides) * W
        if side_y:
            py = snap_value(py / H, ys, "y", guides) * H
    ax = r0.right() if "w" in handle else r0.left()          # punto fermo (lato o angolo opposto)
    ay = r0.bottom() if "n" in handle else r0.top()
    w0, h0 = max(r0.width(), 1.0), max(r0.height(), 1.0)
    nw = max(min_px, abs(px - ax)) if side_x else w0
    nh = max(min_px, abs(py - ay)) if side_y else h0
    fx, fy = nw / w0, nh / h0
    if keep_ratio:
        f = max(fx, fy) if (side_x and side_y) else (fx if side_x else fy)
        fx = fy = f
        nw, nh = w0 * f, h0 * f
    left = ax if "w" not in handle else ax - nw
    top = ay if "n" not in handle else ay - nh
    if not side_x:
        left = r0.center().x() - nw / 2                      # lato n/s: la larghezza (se proporzionale) cresce attorno al centro
    if not side_y:
        top = r0.center().y() - nh / 2
    return QRectF(left, top, nw, nh), fx, fy, guides


def resize_item(state, kind: str, idx: int, orig: dict, r0: QRectF, handle: str, px: float, py: float, W: int, H: int,
                safe=None, snap_on: bool = True, free: bool = False) -> list:
    """Ridimensiona un elemento trascinando una maniglia: il lato (o l'angolo) opposto resta dov'è. Restituisce le guide."""
    shape = kind == "el" and state.spec.graphics.elements[idx].kind == "shape"
    side = handle in ("n", "s", "e", "w")
    independent = shape and (free or side)                       # le forme coi lati (o con Maiusc) cambiano una sola dimensione
    r, fx, fy, guides = resize_rect(r0, handle, px, py, W, H, safe, snap_on, keep_ratio=not independent)
    scale_values(state, kind, idx, orig, fx, fy, free=independent)
    its = {(k, i): rr for k, i, rr in items(state, W, H)}
    real = its.get((kind, idx), r)                               # il rettangolo vero può differire da quello chiesto
    cx = r0.left() + real.width() / 2 if "w" not in handle else r0.right() - real.width() / 2
    cy = r0.top() + real.height() / 2 if "n" not in handle else r0.bottom() - real.height() / 2
    if handle in ("n", "s"):
        cx = r0.center().x()
    if handle in ("e", "w"):
        cy = r0.center().y()
    place(state, kind, idx, cx / W, cy / H, real.width() / W, real.height() / H, W, H)
    return guides


# ------------------------------------------------------------------------------------------------ allinea, ripristina, tastiera
def align(state, kind: str, idx: int, W: int, H: int, h: str = "", v: str = "", safe=None) -> None:
    """Allinea l'elemento a un lato: h = l | c | r (sinistra, centro, destra), v = t | m | b (alto, metà, basso), dentro l'area
    sicura (o il video intero se `safe` è vuoto), con lo stesso margine dell'aggancio."""
    if kind == "split":
        return
    r = {(k, i): rr for k, i, rr in items(state, W, H)}.get((kind, idx))
    if r is None:
        return
    top, bottom, left, right = (list(safe or []) + [0.0] * 4)[:4]
    m = anchors.MARGIN
    my = m * W / H
    cx, cy = r.center().x() / W, r.center().y() / H
    w, hh = r.width() / W, r.height() / H
    if h == "l":
        cx = left + m + w / 2
    elif h == "c":
        cx = (left + 1 - right) / 2
    elif h == "r":
        cx = 1 - right - m - w / 2
    if v == "t":
        cy = top + my + hh / 2
    elif v == "m":
        cy = (top + 1 - bottom) / 2
    elif v == "b":
        cy = 1 - bottom - my - hh / 2
    place(state, kind, idx, cx, cy, w, hh, W, H)


def snapshot(state, kind: str, idx: int) -> dict:
    """Posizione e grandezza di un elemento adesso (per «Ripristina»)."""
    spec = state.spec
    if kind == "split":
        return {"ratio": spec.split.ratio, "second_x": spec.split.second_x}
    if kind == "sub":
        st = spec.subtitles
        return {"x": st.x, "y": st.y, "size": st.size}
    if kind == "logo":
        lg = spec.brand.logos[idx]
        return {"corner": lg.corner, "x": lg.x, "y": lg.y, "size": lg.size}
    e = spec.graphics.elements[idx]
    return {"anchor": e.anchor, "x": e.x, "y": e.y, **sizes(state, kind, idx)}


def restore(state, kind: str, idx: int, snap: dict) -> None:
    spec = state.spec
    if kind == "split":
        spec.split.ratio, spec.split.second_x = snap["ratio"], snap["second_x"]
    elif kind == "sub":
        st = spec.subtitles
        st.x, st.y, st.size = snap["x"], snap["y"], snap["size"]
    elif kind == "logo":
        lg = spec.brand.logos[idx]
        lg.corner, lg.x, lg.y, lg.size = snap["corner"], snap["x"], snap["y"], snap["size"]
    else:
        e = spec.graphics.elements[idx]
        e.anchor, e.x, e.y = snap["anchor"], snap["x"], snap["y"]
        restore_sizes(state, kind, idx, snap)


def defaults(state, kind: str, idx: int) -> dict:
    """Valori di partenza quando non c'è una posizione precedente da ripristinare."""
    spec = state.spec
    if kind == "split":
        return {"ratio": 0.5, "second_x": 0.5}
    if kind == "sub":
        return {"x": 0.5, "y": -1.0, "size": 0.048}
    if kind == "logo":
        lg = spec.brand.logos[idx]
        kit = state.kits.get(spec.brand.kit_id) if spec.brand.kit_id else None
        corner = (kit.main_corner if lg.role == "main" else kit.symbol_corner) if kit else "tr"
        return {"corner": corner, "x": 0.5, "y": 0.5, "size": kit.logo_size if kit else 0.11}
    e = spec.graphics.elements[idx]
    return {"anchor": "tc" if e.kind == "text" else "tr", "x": 0.5, "y": 0.5, "size": 0.055 if e.kind == "text" else e.size,
            "width": 0.14, "w": e.w, "h": e.h, "fit_width": 0.86 if e.kind == "text" else e.fit_width}


def nudge(state, kind: str, idx: int, dx: float, dy: float, W: int, H: int) -> None:
    """Sposta l'elemento di (dx, dy) pixel del fotogramma. Secondo video: ← → sposta l'inquadratura, ↑ ↓ il bordo."""
    if kind == "split":
        sp = state.spec.split
        sp.second_x = min(1.0, max(0.0, sp.second_x - dx / 200.0))
        sp.ratio = min(0.75, max(0.25, sp.ratio + dy / (H * 2.0)))
        return
    r = {(k, i): rr for k, i, rr in items(state, W, H)}.get((kind, idx))
    if r is None:
        return
    place(state, kind, idx, (r.center().x() + dx) / W, (r.center().y() + dy) / H, r.width() / W, r.height() / H, W, H)


def remove(state, kind: str, idx: int) -> bool:
    """Toglie un testo o un overlay (non i sottotitoli, i loghi del kit o il secondo video). True se l'ha tolto."""
    if kind != "el":
        return False
    els = state.spec.graphics.elements
    if 0 <= idx < len(els):
        del els[idx]
        return True
    return False
