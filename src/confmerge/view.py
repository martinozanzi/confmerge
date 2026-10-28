"""Geometria di visualizzazione: stessa logica di crop/zoom/adattamento usata dall'export (anteprima WYSIWYG)."""
from __future__ import annotations

from PySide6.QtCore import QRectF

from .spec import ImageSettings, view_transform


def fit_mode(im: ImageSettings, social: bool) -> tuple[str, float, float]:
    """Come si adatta un video a un formato diverso: (crop | bars, posizione x, posizione y).
    Studio Social usa «riempi / sfocato / bande» e la posizione scelta; Merge Conferenze usa la modalità verticale."""
    if social:
        return ("crop" if im.reframe == "fill" else "bars"), im.reframe_x, im.reframe_y
    return im.vertical_mode, 0.5, 0.5


MIN_VSCALE, MAX_VSCALE = 0.4, 3.0


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def zoom_window(s: float, vx: float, vy: float, W: int, H: int) -> tuple[int, int, int, int]:
    """Ingrandimento (s > 1): finestra (x, y, w, h) del fotogramma W×H da mostrare a tutto schermo, centrata su (vx, vy)."""
    s = min(max(s, 1.0), MAX_VSCALE)
    w, h = _even(W / s), _even(H / s)
    x = int(round(min(max(vx * W - w / 2, 0), W - w)))
    y = int(round(min(max(vy * H - h / 2, 0), H - h)))
    return x, y, w, h


def shrink_rect(s: float, vx: float, vy: float, W: int, H: int) -> tuple[int, int, int, int]:
    """Riduzione (s < 1): dove sta il video rimpicciolito (x, y, w, h) dentro il fotogramma W×H, tenuto dentro i bordi."""
    s = min(max(s, MIN_VSCALE), 1.0)
    w, h = _even(W * s), _even(H * s)
    x = int(round(min(max(vx * W - w / 2, 0), W - w)))
    y = int(round(min(max(vy * H - h / 2, 0), H - h)))
    return x, y, w, h


def has_transform(im: ImageSettings) -> bool:
    """Il video principale è stato ingrandito o rimpicciolito (la posizione conta solo allora)."""
    return abs(im.vscale - 1.0) > 0.005


def mask_radius_px(mask: str, radius: float, w: float, h: float) -> float:
    """Raggio (px) degli angoli di una forma w×h: «circle» arrotonda al massimo (cerchio, o pillola se non è quadrata)."""
    half = min(w, h) / 2
    return half if mask == "circle" else min(half, max(0.0, radius) * min(w, h))


def source_to_frame(src_w: float, src_h: float, im: ImageSettings, W: int, H: int, out_t: float,
                    social: bool = False) -> tuple[QRectF, QRectF]:
    """(rettangolo sorgente da prelevare, rettangolo di destinazione nel frame W×H)."""
    mode, rx, ry = fit_mode(im, social)
    x0, y0 = src_w * im.crop_l, src_h * im.crop_t
    cw = max(1.0, src_w * (1 - im.crop_l - im.crop_r))
    ch = max(1.0, src_h * (1 - im.crop_t - im.crop_b))
    z, cx, cy = view_transform(im, out_t)
    if im.kenburns:
        # l'export adatta prima il frame a W×H e poi zooma: il rettangolo visibile è quello dell'immagine adattata
        dst_full, _ = _fit(cw, ch, W, H, mode, rx, ry)
        src = QRectF(x0, y0, cw, ch)
        vis_w, vis_h = W / z, H / z
        vx = min(max(0.0, cx * W - vis_w / 2), W - vis_w)
        vy = min(max(0.0, cy * H - vis_h / 2), H - vis_h)
        # frame adattato → coordinate sorgente
        fx, fy = dst_full.x(), dst_full.y()
        sx = cw / dst_full.width()
        sy = ch / dst_full.height()
        r = QRectF(x0 + (vx - fx) * sx, y0 + (vy - fy) * sy, vis_w * sx, vis_h * sy)
        return _clip_to(r, src, QRectF(0, 0, W, H), vx, vy, vis_w, vis_h, dst_full)
    if z > 1.001:
        vw, vh = cw / z, ch / z
        vx = min(max(0.0, cx * cw - vw / 2), cw - vw)
        vy = min(max(0.0, cy * ch - vh / 2), ch - vh)
        cw2, ch2 = vw, vh
        x0, y0 = x0 + vx, y0 + vy
        cw, ch = cw2, ch2
    dst, src_crop = _fit(cw, ch, W, H, mode, rx, ry)
    src = QRectF(x0 + src_crop.x(), y0 + src_crop.y(), src_crop.width(), src_crop.height()) if src_crop else QRectF(x0, y0, cw, ch)
    return src, dst


def _fit(cw: float, ch: float, W: int, H: int, mode: str, rx: float = 0.5, ry: float = 0.5) -> tuple[QRectF, QRectF | None]:
    """(destinazione, porzione sorgente relativa se si ritaglia, altrimenti None)."""
    ar_s, ar_o = cw / ch, W / H
    if abs(ar_s - ar_o) < 0.01:
        return QRectF(0, 0, W, H), None
    if mode == "crop":
        if ar_s > ar_o:
            w = ch * ar_o
            return QRectF(0, 0, W, H), QRectF((cw - w) * rx, 0, w, ch)
        h = cw / ar_o
        return QRectF(0, 0, W, H), QRectF(0, (ch - h) * ry, cw, h)
    if ar_s > ar_o:
        h = W / ar_s
        return QRectF(0, (H - h) / 2, W, h), None
    w = H * ar_s
    return QRectF((W - w) / 2, 0, w, H), None


def _clip_to(r, src, frame, vx, vy, vis_w, vis_h, dst_full):
    """Ken Burns: parte visibile del frame adattato, ritagliata ai bordi dell'immagine."""
    vis = QRectF(vx, vy, vis_w, vis_h).intersected(dst_full)
    sx = src.width() / dst_full.width()
    sy = src.height() / dst_full.height()
    s = QRectF(src.x() + (vis.x() - dst_full.x()) * sx, src.y() + (vis.y() - dst_full.y()) * sy,
               vis.width() * sx, vis.height() * sy)
    d = QRectF((vis.x() - vx) / vis_w * frame.width(), (vis.y() - vy) / vis_h * frame.height(),
               vis.width() / vis_w * frame.width(), vis.height() / vis_h * frame.height())
    return s, d
