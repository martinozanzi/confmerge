"""Modello dati degli elementi grafici (serializzabile in JSON)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

TARGETS = ("main", "title", "outro")
ANIM_KINDS = ["none", "fade", "slide_left", "slide_right", "slide_up", "slide_down", "pop",
              "reveal", "blur", "typewriter", "by_word", "by_letter"]
EASINGS = ["linear", "ease_in_out", "cubic", "back", "expo"]


@dataclass
class Anim:
    kind: str = "none"
    duration: float = 0.6
    easing: str = "ease_in_out"
    stagger: float = 0.05   # ritardo a cascata per lettera/parola (s)


@dataclass
class Fill:
    kind: str = "solid"      # solid | gradient
    color: str = "#FFFFFF"
    color2: str = "#4A90E2"
    angle: float = 90.0      # gradi (90 = dall'alto al basso)


@dataclass
class Outline:
    width: float = 0.0       # frazione dell'altezza del frame
    color: str = "#000000"


@dataclass
class Shadow:
    enabled: bool = False
    color: str = "#000000"
    blur: float = 0.006      # frazione dell'altezza
    distance: float = 0.004
    angle: float = 45.0
    opacity: float = 0.6


@dataclass
class Box:
    enabled: bool = False
    color: str = "#000000"
    opacity: float = 0.6
    padding: float = 0.012
    radius: float = 0.01


@dataclass
class Element:
    id: str = ""
    kind: str = "text"            # text | image | shape | bar
    x: float = 0.5                # centro, frazione della larghezza
    y: float = 0.5                # centro, frazione dell'altezza
    rotation: float = 0.0
    opacity: float = 1.0
    start: float = 0.0            # secondi nel segmento di destinazione
    end: float | None = None      # None = fino alla fine del segmento
    targets: list[str] = field(default_factory=lambda: ["main"])
    anim_in: Anim = field(default_factory=Anim)
    anim_out: Anim = field(default_factory=Anim)
    # testo
    text: str = ""
    font: str = "Segoe UI"
    size: float = 0.06            # frazione dell'altezza
    bold: bool = False
    italic: bool = False
    align: str = "center"
    line_spacing: float = 1.0
    letter_spacing: float = 0.0   # frazione dell'altezza
    fill: Fill = field(default_factory=Fill)
    outline: Outline = field(default_factory=Outline)
    shadow: Shadow = field(default_factory=Shadow)
    box: Box = field(default_factory=Box)
    # immagine (PNG/SVG/JPG)
    path: str = ""
    width: float = 0.15           # frazione della larghezza del frame
    # forma
    shape: str = "rect"           # rect | ellipse | line
    w: float = 0.2
    h: float = 0.1
    radius: float = 0.0
    # barra di avanzamento
    position: str = "bottom"      # top | bottom
    thickness: float = 0.008
    margin: float = 0.0
    fill2: Fill = field(default_factory=lambda: Fill(color="#FFFFFF"))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Element":
        return _build(cls, d)


@dataclass
class Background:
    kind: str = "black"           # black | solid | gradient | image | transparent
    color: str = "#000000"
    color2: str = "#1B2A49"
    angle: float = 90.0
    path: str = ""


@dataclass
class Scene:
    """Titolo iniziale o schermata finale."""
    enabled: bool = False
    duration: float = 4.0
    background: Background = field(default_factory=Background)
    elements: list[Element] = field(default_factory=list)
    over_video: bool = False      # solo titolo: sulle prime immagini del video (sfondo trasparente)
    fade: float = 0.5             # dissolvenza verso/dal video

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return _build(cls, d)


@dataclass
class LowerThird:
    name: str = ""
    role: str = ""
    start: float = 10.0
    duration: float = 6.0
    x: float = 0.06               # bordo sinistro (frazione)
    y: float = 0.82               # centro verticale
    accent: str = "#E94F37"
    font: str = "Segoe UI"
    anim_in: Anim = field(default_factory=lambda: Anim("slide_left", 0.6, "expo"))
    anim_out: Anim = field(default_factory=lambda: Anim("fade", 0.4, "ease_in_out"))


def lower_third_elements(lt: LowerThird, idx: int = 0) -> list[Element]:
    """Espande un lower third in elementi (barra accento + box + nome + ruolo)."""
    end = lt.start + lt.duration
    common = dict(start=lt.start, end=end, targets=["main"], anim_in=lt.anim_in, anim_out=lt.anim_out)
    cx = lt.x
    return [
        Element(id=f"lt{idx}_bg", kind="shape", shape="rect", x=cx + 0.17, y=lt.y, w=0.34, h=0.115,
                fill=Fill(color="#101820"), radius=0.004, opacity=0.8, **common),
        Element(id=f"lt{idx}_bar", kind="shape", shape="rect", x=cx + 0.003, y=lt.y, w=0.006, h=0.115,
                fill=Fill(color=lt.accent), **common),
        Element(id=f"lt{idx}_name", kind="text", text=lt.name, font=lt.font, size=0.042, bold=True,
                x=cx + 0.017, y=lt.y - 0.021, align="left", **common),
        Element(id=f"lt{idx}_role", kind="text", text=lt.role, font=lt.font, size=0.028,
                fill=Fill(color="#D0D6DD"), x=cx + 0.017, y=lt.y + 0.025, align="left", **common),
    ]


def _build(cls, d: dict):
    from ..serde import from_dict
    return from_dict(cls, d)
