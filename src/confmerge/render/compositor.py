"""Compositor: unisce gli elementi in un frame RGBA (anteprima) e prepara i layer per ffmpeg (export)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from .animations import state_at, static_window
from .model import Element, Scene
from .text_renderer import blur_image, new_image, paint_background, qcolor, render_element, make_brush_gradient  # noqa: F401


def elements_for(elements: list[Element], target: str) -> list[Element]:
    return [e for e in elements if target in e.targets]


def render_frame(elements: list[Element], W: int, H: int, t: float, seg_dur: float,
                 base: QImage | None = None, bar_total: float | None = None) -> QImage:
    """Frame RGBA con tutti gli elementi visibili al tempo `t` (locale al segmento).
    Identica per anteprima e per i PNG dell'export."""
    img = base.copy() if base is not None else new_image(W, H)
    p = QPainter(img)
    for el in elements:
        if not el.visible:
            continue
        st = state_at(el, t, seg_dur)
        if st is None:
            continue
        if el.kind == "bar":
            a = el.start
            b = seg_dur if el.end is None else min(el.end, seg_dur)
            bar = render_bar(el, W, H)
            x = bar_x(a, b, W, t)
            p.setOpacity(el.opacity * st.alpha)
            p.drawImage(round(x), bar_y(el, W, H), bar)
            continue
        layer = render_element(el, W, H, st)
        p.setOpacity(max(0.0, min(1.0, el.opacity * st.alpha)))
        p.drawImage(0, 0, layer)
    p.end()
    return img


# ---- barra di avanzamento: un PNG, scorre con overlay x=expr(t)

def render_bar(el: Element, W: int, H: int) -> QImage:
    th = max(2, round(el.thickness * H))
    img = new_image(W, th)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtCore import QRectF
    r = QRectF(0, 0, W, th)
    p.setPen(Qt.NoPen)
    p.setBrush(make_brush_gradient(_h_fill(el), r) if el.fill.kind == "gradient" else qcolor(el.fill.color))
    rad = el.radius * H
    p.drawRoundedRect(r, rad, rad)
    p.end()
    return img


def _h_fill(el: Element):
    f = type(el.fill)(el.fill.kind, el.fill.color, el.fill.color2, 0.0)  # sfumatura orizzontale
    return f


def bar_y(el: Element, W: int, H: int) -> int:
    th = max(2, round(el.thickness * H))
    m = round(el.margin * H)
    return m if el.position == "top" else H - th - m


def bar_x(a: float, b: float, W: int, t: float) -> float:
    """Posizione x del PNG (largo W) al tempo t: da -W (a) a 0 (b). Stessa formula dell'overlay ffmpeg."""
    if b <= a:
        return 0.0
    return -W + W * min(1.0, max(0.0, (t - a) / (b - a)))


def bar_x_expr(a: float, b: float, W: int) -> str:
    return f"-{W}+{W}*min(1\\,max(0\\,(t-{a:.4f})/{max(b - a, 1e-3):.4f}))"


# ---- piano dei layer per ffmpeg

@dataclass
class Layer:
    kind: str            # static | sequence | bar
    path: str            # file PNG, oppure pattern con %05d
    a: float             # inizio sulla timeline del segmento (s)
    b: float             # fine (s)
    x_expr: str = "0"
    y_expr: str = "0"
    frames: int = 0
    fps: float = 0.0
    opacity: float = 1.0


def _write(img: QImage, path: Path) -> None:
    if not img.save(str(path), "PNG"):
        raise OSError(f"Impossibile scrivere {path}")


def plan_layers(elements: list[Element], W: int, H: int, seg_dur: float, fps: float,
                workdir: Path, prefix: str) -> list[Layer]:
    """Un PNG per le parti statiche, sequenze PNG solo per le parti animate, un PNG per la barra."""
    workdir.mkdir(parents=True, exist_ok=True)
    layers: list[Layer] = []
    for i, el in enumerate(elements):
        if not el.visible or el.kind == "clip":                 # i clip animati entrano nel filtergraph come video (graph.py)
            continue
        a = el.start
        b = seg_dur if el.end is None else min(el.end, seg_dur)
        if b <= a:
            continue
        tag = f"{prefix}{i}"
        if el.kind == "bar":
            path = workdir / f"{tag}_bar.png"
            _write(render_bar(el, W, H), path)
            layers.append(Layer("bar", str(path), a, b, bar_x_expr(a, b, W), str(bar_y(el, W, H)),
                                opacity=el.opacity))
            continue
        sa, sb = static_window(el, seg_dur)
        if sb > sa:
            path = workdir / f"{tag}_s.png"
            st = state_at(el, (sa + sb) / 2, seg_dur)
            layer_img = render_element(el, W, H, st)
            if el.opacity < 1.0:
                layer_img = _with_opacity(layer_img, el.opacity)
            _write(layer_img, path)
            layers.append(Layer("static", str(path), sa, sb))
        for (wa, wb, nm) in ((a, sa, "in"), (sb, b, "out")):
            if wb - wa <= 1e-3:
                continue
            n = max(1, int(round((wb - wa) * fps)))
            for k in range(n):
                t = wa + (k + 0.5) / fps
                st = state_at(el, min(t, wb - 1e-4), seg_dur) or state_at(el, wa + 1e-4, seg_dur)
                img = render_element(el, W, H, st)
                op = el.opacity * (st.alpha if st else 1.0)
                _write(_with_opacity(img, op) if op < 0.999 else img, workdir / f"{tag}_{nm}_{k:05d}.png")
            layers.append(Layer("sequence", str(workdir / f"{tag}_{nm}_%05d.png"), wa, wb, frames=n, fps=fps))
    return layers


def _with_opacity(img: QImage, op: float) -> QImage:
    out = new_image(img.width(), img.height())
    p = QPainter(out)
    p.setOpacity(max(0.0, min(1.0, op)))
    p.drawImage(0, 0, img)
    p.end()
    return out


def render_scene_background(scene: Scene, W: int, H: int) -> QImage:
    img = new_image(W, H)
    paint_background(img, scene.background)
    return img
