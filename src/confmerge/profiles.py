"""Profili: sottoinsieme della RenderSpec (grafica, credito, export, audio, immagine) richiamabile per canale/evento."""
from __future__ import annotations

from .serde import from_dict, to_dict
from .spec import (AudioSettings, BrandSettings, CreditSettings, ExportSettings, Graphics, ImageSettings, RenderSpec,
                   SocialSettings, SubtitleSettings)


def profile_from_spec(spec: RenderSpec, font: str = "Segoe UI") -> dict:
    return {
        "graphics": to_dict(spec.graphics),
        "credit": to_dict(spec.credit),
        "export": {k: v for k, v in to_dict(spec.export).items() if k not in ("name",)},
        "social": to_dict(spec.social),
        "brand": to_dict(spec.brand),
        "audio": {k: v for k, v in to_dict(spec.audio).items() if k not in ("music_path",)},
        "subtitles": {k: v for k, v in to_dict(spec.subtitles).items()
                      if k not in ("lines", "range_start", "range_end")},
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
        music = spec.audio.music_path
        spec.audio = from_dict(AudioSettings, profile["audio"])
        spec.audio.music_path = music
    if profile.get("brand"):
        spec.brand = from_dict(BrandSettings, profile["brand"])
    if profile.get("social"):
        spec.social = from_dict(SocialSettings, profile["social"])
    if profile.get("subtitles"):
        old = spec.subtitles
        spec.subtitles = from_dict(SubtitleSettings, profile["subtitles"])
        spec.subtitles.lines, spec.subtitles.range_start, spec.subtitles.range_end = old.lines, old.range_start, old.range_end
    if profile.get("image"):
        spec.image = from_dict(ImageSettings, profile["image"])
    if profile.get("variables") is not None:
        spec.variables = dict(profile["variables"])


STARTER_NAME = "Conferenza (semplice)"


def starter_profile() -> dict:
    """Profilo di partenza per la modalità Semplice: titolo iniziale, lower third del relatore e credito."""
    from .render.model import LowerThird
    spec = RenderSpec()
    from . import templates
    spec.graphics.title = templates.get("title", "aurora").build()
    spec.graphics.title_template = "aurora"
    spec.graphics.transition_style = "fade"
    spec.graphics.lower_thirds = [LowerThird(name="{relatore}", role="{ruolo}", start=10.0, duration=6.0, style="pill")]
    return profile_from_spec(spec)
