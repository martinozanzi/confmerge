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
    kind: str = "text"            # text | image | clip (video/GIF con sfondo trasparente) | shape | bar
    x: float = 0.5                # centro, frazione della larghezza
    y: float = 0.5                # centro, frazione dell'altezza
    rotation: float = 0.0
    opacity: float = 1.0
    start: float = 0.0            # secondi nel segmento di destinazione
    end: float | None = None      # None = fino alla fine del segmento
    targets: list[str] = field(default_factory=lambda: ["main"])
    visible: bool = True          # «occhio» del pannello livelli
    locked: bool = False          # «lucchetto»: non si sposta col mouse
    anchor: str = ""              # angolo/lato dove sta («tl», «tc», «mr», «bc»…): si ricalcola per ogni formato; vuoto = x, y liberi
    anim_in: Anim = field(default_factory=Anim)
    anim_out: Anim = field(default_factory=Anim)
    # testo
    text: str = ""
    font: str = "Segoe UI"
    size: float = 0.06            # frazione dell'altezza
    bold: bool = False
    italic: bool = False
    align: str = "center"
    uppercase: bool = False        # TUTTO MAIUSCOLO (titoli stile YouTube)
    fit_width: float = 0.0         # 0 = nessun limite; altrimenti il testo si rimpicciolisce per stare in questa frazione della larghezza
    line_spacing: float = 1.0
    letter_spacing: float = 0.0   # frazione dell'altezza
    loop: bool = True             # clip: si ripete finché l'elemento è visibile
    hl_word: int = -1             # sottotitoli: indice della parola evidenziata (-1 = nessuna)
    hl_color: str = "#FFE600"
    hl_scale: float = 1.0
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
    fade: float = 0.5             # durata della transizione verso/dal video
    transition: str = "fade"      # effetto della transizione (vedi transitions.py)

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
    style: str = "bar"           # bar | pill | line | card | gradient | tag | underline | social
    anim_in: Anim = field(default_factory=lambda: Anim("slide_left", 0.6, "expo"))
    anim_out: Anim = field(default_factory=lambda: Anim("fade", 0.4, "ease_in_out"))


VARIABLES = {"titolo": "Titolo", "sottotitolo": "Sottotitolo", "data": "Data", "relatore": "Nome del relatore",
             "ruolo": "Ruolo del relatore", "social": "Canale o social (es. @nomecanale)"}


def resolve_text(text: str, variables: dict[str, str] | None) -> str:
    """Sostituisce i segnaposto {titolo}, {relatore}, {ruolo}, {data}; quelli senza valore diventano vuoti."""
    if "{" not in text:
        return text
    v = variables or {}
    for k in VARIABLES:
        text = text.replace("{" + k + "}", v.get(k, ""))
    return text


def substitute(elements: list[Element], variables: dict[str, str] | None) -> list[Element]:
    """Copie degli elementi con i segnaposto risolti (gli originali non si toccano)."""
    out = []
    for e in elements:
        if e.kind == "text" and "{" in e.text:
            d = e.to_dict()
            d["text"] = resolve_text(e.text, variables)
            out.append(Element.from_dict(d))
        else:
            out.append(e)
    return out


LOWER_THIRD_STYLES = {
    "bar": "Barra", "pill": "Pillola", "line": "Linea", "card": "Scheda bianca", "gradient": "Sfumatura",
    "tag": "Etichetta gialla", "underline": "Sottolineato", "social": "Social",
}


def lower_third_elements(lt: LowerThird, idx: int = 0, variables: dict[str, str] | None = None) -> list[Element]:
    """Espande un lower third negli elementi dello stile scelto (barre, box, nome, ruolo)."""
    lt = LowerThird(**{**lt.__dict__, "name": resolve_text(lt.name, variables), "role": resolve_text(lt.role, variables)})
    if not lt.name.strip() and not lt.role.strip():
        return []                      # nessun relatore indicato: niente lower third
    end = lt.start + lt.duration
    common = dict(start=lt.start, end=end, targets=["main"], anim_in=lt.anim_in, anim_out=lt.anim_out)
    x, y = lt.x, lt.y
    F = lt.font if lt.font not in ("", "Segoe UI") else "Poppins"
    uid = f"lt{idx}"

    def shape(n, cx, cy, w, h, color, radius=0.0, shape_="rect", **kw):
        fill = kw.pop("fill", Fill(color=color))
        return Element(id=f"{uid}_{n}", kind="shape", shape=shape_, x=cx, y=cy, w=w, h=h, fill=fill, radius=radius, **kw, **common)

    def text(n, t_, cx, cy, size, color="#FFFFFF", bold=False, font=F, align="left", **kw):
        kw.setdefault("fit_width", 0.31)          # un nome lungo si rimpicciolisce e resta nel box
        return Element(id=f"{uid}_{n}", kind="text", text=t_, font=font, size=size, bold=bold, fill=Fill(color=color),
                       x=cx, y=cy, align=align, **kw, **common)

    st = lt.style
    if st == "pill":
        return [shape("bg", x + 0.19, y, 0.38, 0.115, "#12151C", 0.0575, opacity=0.88, shadow=Shadow(True, "#000000", 0.012, 0.006, 90, 0.5)),
                shape("dot", x + 0.032, y, 0.012, 0.0213, lt.accent, shape_="ellipse"),
                text("name", lt.name, x + 0.055, y - 0.019, 0.04, bold=True),
                text("role", lt.role, x + 0.055, y + 0.026, 0.027, "#B6BDC9")]
    if st == "line":
        sh = Shadow(True, "#000000", 0.008, 0.003, 90, 0.9)
        return [shape("bar", x + 0.002, y, 0.004, 0.11, lt.accent),
                text("name", lt.name, x + 0.016, y - 0.024, 0.048, bold=True, shadow=sh),
                text("role", lt.role, x + 0.016, y + 0.028, 0.03, "#FFFFFF", shadow=sh)]
    if st == "card":
        return [shape("bg", x + 0.19, y, 0.38, 0.125, "#FFFFFF", 0.006, shadow=Shadow(True, "#000000", 0.016, 0.006, 90, 0.35)),
                shape("top", x + 0.19, y - 0.0585, 0.38, 0.008, lt.accent),
                text("name", lt.name, x + 0.02, y - 0.012, 0.042, "#12151C", True),
                text("role", lt.role, x + 0.02, y + 0.03, 0.027, "#5B6575")]
    if st == "gradient":
        g = Fill("gradient", lt.accent, "#00000000", 0.0)
        return [shape("bg", x + 0.25, y, 0.5, 0.115, "", 0.0, fill=g),
                text("name", lt.name, x + 0.018, y - 0.021, 0.044, bold=True),
                text("role", lt.role, x + 0.018, y + 0.027, 0.028, "#FFFFFF")]
    if st == "tag":
        return [shape("bg", x + 0.17, y - 0.02, 0.34, 0.07, "#FACC15", 0.0, rotation=-1.5),
                text("name", lt.name, x + 0.015, y - 0.02, 0.062, "#000000", False, "Anton", uppercase=True, rotation=-1.5),
                shape("rbg", x + 0.13, y + 0.045, 0.26, 0.046, "#000000", 0.0, rotation=-1.5),
                text("role", lt.role, x + 0.012, y + 0.045, 0.027, "#FFFFFF", False, "Poppins", rotation=-1.5)]
    if st == "underline":
        sh = Shadow(True, "#000000", 0.008, 0.003, 90, 0.8)
        return [text("name", lt.name, x, y - 0.02, 0.05, bold=True, shadow=sh),
                shape("ul", x + 0.09, y + 0.012, 0.18, 0.0045, lt.accent),
                text("role", lt.role, x, y + 0.04, 0.03, "#FFFFFF", shadow=sh)]
    if st == "social":
        return [shape("bg", x + 0.17, y, 0.34, 0.1, "#FFFFFF", 0.05, shadow=Shadow(True, "#000000", 0.014, 0.005, 90, 0.35)),
                text("name", lt.name, x + 0.03, y - 0.017, 0.037, "#12151C", True),
                text("role", lt.role, x + 0.03, y + 0.025, 0.026, lt.accent, True)]
    # bar (predefinito)
    return [
        Element(id=f"{uid}_bg", kind="shape", shape="rect", x=x + 0.17, y=y, w=0.34, h=0.115,
                fill=Fill(color="#101820"), radius=0.004, opacity=0.8, **common),
        Element(id=f"{uid}_bar", kind="shape", shape="rect", x=x + 0.003, y=y, w=0.006, h=0.115,
                fill=Fill(color=lt.accent), **common),
        Element(id=f"{uid}_name", kind="text", text=lt.name, font=F, size=0.042, bold=True, fit_width=0.31,
                x=x + 0.017, y=y - 0.021, align="left", **common),
        Element(id=f"{uid}_role", kind="text", text=lt.role, font=F, size=0.028, fit_width=0.31,
                fill=Fill(color="#D0D6DD"), x=x + 0.017, y=y + 0.025, align="left", **common),
    ]


def _build(cls, d: dict):
    from ..serde import from_dict
    return from_dict(cls, d)
