"""Profili: sottoinsieme della RenderSpec (grafica, credito, export, audio, immagine) richiamabile per canale/evento."""
from __future__ import annotations

from .serde import from_dict, to_dict
from .spec import AudioSettings, CreditSettings, ExportSettings, Graphics, ImageSettings, RenderSpec


def profile_from_spec(spec: RenderSpec, font: str = "Segoe UI") -> dict:
    return {
        "graphics": to_dict(spec.graphics),
        "credit": to_dict(spec.credit),
        "export": {k: v for k, v in to_dict(spec.export).items() if k not in ("name",)},
        "audio": to_dict(spec.audio),
        "image": to_dict(spec.image),
        "variables": dict(spec.variables),
        "font": font,
    }


def apply_profile(spec: RenderSpec, profile: dict) -> None:
    """Applica il profilo alla spec (non tocca slide e tempi del lavoro corrente)."""
    g = profile.get("graphics")
    if g:
        spec.graphics = from_dict(Graphics, {k: v for k, v in g.items() if v is not None})
    if profile.get("credit"):
        spec.credit = from_dict(CreditSettings, profile["credit"])
    if profile.get("export"):
        name, out_dir = spec.export.name, spec.export.out_dir
        spec.export = from_dict(ExportSettings, profile["export"])
        spec.export.name = name
        if not spec.export.out_dir:
            spec.export.out_dir = out_dir
    if profile.get("audio"):
        spec.audio = from_dict(AudioSettings, profile["audio"])
    if profile.get("image"):
        spec.image = from_dict(ImageSettings, profile["image"])
    if profile.get("variables") is not None:
        spec.variables = dict(profile["variables"])


STARTER_NAME = "Conferenza (semplice)"


def starter_profile() -> dict:
    """Profilo di partenza per la modalità Semplice: titolo iniziale, lower third del relatore e credito."""
    from .render.model import Anim, Background, Element, Fill, LowerThird, Scene, Shadow
    spec = RenderSpec()
    spec.graphics.title = Scene(
        enabled=True, duration=4.0, fade=0.6,
        background=Background("gradient", "#0F1B3D", "#3A1C71", 120.0),
        elements=[
            Element(id="t_titolo", kind="text", text="{titolo}", size=0.085, bold=True, x=0.5, y=0.44,
                    shadow=Shadow(True), anim_in=Anim("blur", 0.9, "ease_in_out"), anim_out=Anim("fade", 0.5)),
            Element(id="t_data", kind="text", text="{data}", size=0.04, x=0.5, y=0.6, fill=Fill(color="#C9D3FF"),
                    start=0.5, anim_in=Anim("fade", 0.8), anim_out=Anim("fade", 0.5)),
        ])
    spec.graphics.lower_thirds = [LowerThird(name="{relatore}", role="{ruolo}", start=10.0, duration=6.0)]
    return profile_from_spec(spec)
