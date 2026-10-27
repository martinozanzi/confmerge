"""Applicare un kit del marchio a un lavoro e disegnare i suoi loghi sul video."""
from __future__ import annotations

import os

from .brand_kit import BrandKit, KitStore, contrast_color, logo_size
from .render.model import Element
from .spec import LogoPlacement, RenderSpec


def apply_kit(spec: RenderSpec, kit: BrandKit, store: KitStore) -> None:
    """Copia nel lavoro quello che il kit decide: loghi sul video, stile dei sottotitoli, colore dei nomi, @canale."""
    placements = []
    main, symbol = kit.logo("main") or kit.logo("wide") or kit.logo("square"), kit.logo("symbol")
    for logo, role, corner in ((main, "main", kit.main_corner), (symbol, "symbol", kit.symbol_corner)):
        path = store.logo_path(kit, logo) if logo else ""
        if path:
            placements.append(LogoPlacement(path=path, role=role, name=logo.name, corner=corner, size=kit.logo_size))
    spec.brand.kit_id, spec.brand.name, spec.brand.logos = kit.id, kit.name, placements
    sub, c = spec.subtitles, kit.colors
    sub.font, sub.bold = kit.font_body, True
    if kit.caption_style == "box":
        sub.box, sub.box_color, sub.box_opacity = True, c.primary, 0.92
        sub.color, sub.shadow, sub.outline = contrast_color(c.primary), False, 0.0
    else:
        sub.box, sub.color, sub.outline, sub.outline_color, sub.shadow = False, c.text, 0.0045, c.secondary, True
    for lt in spec.graphics.lower_thirds:
        lt.accent, lt.font = c.accent, kit.font_title
    if kit.social:
        spec.variables["social"] = kit.social


def clear_kit(spec: RenderSpec) -> None:
    spec.brand.kit_id, spec.brand.name, spec.brand.logos = "", "", []


def brand_elements(spec: RenderSpec, W: int, H: int) -> list[Element]:
    """Elementi immagine dei loghi attivi, negli angoli scelti e dentro le zone di sicurezza (se la piattaforma le ha)."""
    out = []
    top, bottom, left, right = (list(spec.brand.safe) + [0.0] * 4)[:4]
    m = 0.03 * W
    for i, lg in enumerate(spec.brand.logos):
        if not lg.enabled or not lg.path or not os.path.exists(lg.path):
            continue
        iw, ih = logo_size(lg.path)
        if not iw:
            continue
        w = lg.size * W
        h = w * ih / iw
        if lg.corner == "free":
            x, y = lg.x * W, lg.y * H                            # messo a mano trascinandolo
        else:
            x = (m + left * W + w / 2) if lg.corner in ("tl", "bl") else (W - m - right * W - w / 2)
            y = (m + top * H + h / 2) if lg.corner in ("tl", "tr") else (H - m - bottom * H - h / 2)
        out.append(Element(id=f"__logo{i}", kind="image", path=lg.path, width=lg.size, x=x / W, y=y / H, opacity=lg.opacity))
    return out


# ------------------------------------------------------------------------------------------------ titolo e finale del marchio
def _logo_el(kit: BrandKit, store: KitStore, role: str, x: float, y: float, width: float, id_: str) -> Element | None:
    logo = kit.logo(role)
    path = store.logo_path(kit, logo) if logo else ""
    if not path:
        return None
    from .render.model import Anim
    return Element(id=id_, kind="image", path=path, width=width, x=x, y=y, anim_in=Anim("fade", 0.7), anim_out=Anim("fade", 0.4))


def brand_title_scene(kit: BrandKit, store: KitStore):
    """Titolo iniziale con i colori, i caratteri e il logo del marchio."""
    from .render.model import Anim, Background, Element as E, Fill, Scene
    c = kit.colors
    els = []
    main = _logo_el(kit, store, "main", 0.5, 0.2, 0.16, "bt_logo") or _logo_el(kit, store, "wide", 0.5, 0.2, 0.26, "bt_logo")
    if main:
        els.append(main)
    sym = _logo_el(kit, store, "symbol", 0.92, 0.88, 0.09, "bt_sym")
    if sym:
        els.append(sym)
    els += [
        E(id="bt_bar", kind="shape", shape="rect", x=0.5, y=0.6, w=0.12, h=0.006, fill=Fill(color=c.accent),
          anim_in=Anim("reveal", 0.8, "expo"), start=0.3),
        E(id="bt_t", kind="text", text="{titolo}", x=0.5, y=0.46, size=0.075, font=kit.font_title, bold=True, fill=Fill(color=c.text),
          fit_width=0.86, anim_in=Anim("slide_up", 0.8, "expo")),
        E(id="bt_s", kind="text", text="{sottotitolo}", x=0.5, y=0.69, size=0.036, font=kit.font_body, fill=Fill(color=c.accent),
          fit_width=0.8, start=0.5, anim_in=Anim("fade", 0.8)),
        E(id="bt_d", kind="text", text="{data}", x=0.5, y=0.77, size=0.028, font=kit.font_body, fill=Fill(color=c.text),
          opacity=0.75, fit_width=0.8, start=0.7, anim_in=Anim("fade", 0.8)),
    ]
    if kit.slogan:
        els.append(E(id="bt_slogan", kind="text", text=kit.slogan, x=0.5, y=0.93, size=0.026, font=kit.font_body, italic=True,
                     fill=Fill(color=c.text), opacity=0.7, fit_width=0.8, start=0.9, anim_in=Anim("fade", 0.8)))
    return Scene(enabled=True, duration=4.0, fade=0.6, background=Background("solid", c.background), elements=els)


def brand_outro_scene(kit: BrandKit, store: KitStore):
    """Schermata finale: logo, slogan e @canale sul colore principale."""
    from .render.model import Anim, Background, Element as E, Fill, Scene
    c = kit.colors
    ink = contrast_color(c.primary)
    els = []
    main = _logo_el(kit, store, "main", 0.5, 0.34, 0.2, "bo_logo") or _logo_el(kit, store, "wide", 0.5, 0.34, 0.3, "bo_logo")
    if main:
        els.append(main)
    sym = _logo_el(kit, store, "symbol", 0.5, 0.7, 0.1, "bo_sym")
    if sym:
        els.append(sym)
    els.append(E(id="bo_t", kind="text", text=kit.slogan or "Grazie per averci seguito", x=0.5, y=0.56 if not sym else 0.52, size=0.058,
                 font=kit.font_title, bold=True, fill=Fill(color=ink), fit_width=0.86, start=0.3, anim_in=Anim("slide_up", 0.7, "expo")))
    if kit.social:
        els.append(E(id="bo_h", kind="text", text=kit.social, x=0.5, y=0.9, size=0.036, font=kit.font_body, bold=True,
                     fill=Fill(color=c.accent if ink != "#111111" else c.secondary), fit_width=0.7, start=0.6, anim_in=Anim("fade", 0.7)))
    return Scene(enabled=True, duration=5.0, fade=0.6, background=Background("solid", c.primary), elements=els)


def apply_brand_scene(spec: RenderSpec, kit: BrandKit, store: KitStore, which: str) -> None:
    """Imposta titolo iniziale o schermata finale con il marchio (la transizione scelta resta)."""
    scene = brand_title_scene(kit, store) if which == "title" else brand_outro_scene(kit, store)
    old = spec.graphics.title if which == "title" else spec.graphics.outro
    scene.transition, scene.fade = old.transition, old.fade
    if which == "title":
        spec.graphics.title, spec.graphics.title_template = scene, "brand"
    else:
        spec.graphics.outro, spec.graphics.outro_template = scene, "brand"
