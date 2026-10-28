"""Modelli pronti (stile YouTube / Instagram / Canva): titoli iniziali, nomi dei relatori, schermate finali e scritte.

Tutti i testi usano segnaposto ({titolo}, {sottotitolo}, {data}, {social}, {relatore}, {ruolo}) che l'utente compila
in un campo semplice, senza aprire l'editor. I font sono quelli inclusi nel programma (Poppins, Bebas Neue, Anton,
DM Serif Display, Pacifico, Space Mono, Inter), quindi il risultato è uguale su qualsiasi computer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .render.model import (LOWER_THIRD_STYLES, Anim, Background, Box, Element, Fill, LowerThird, Outline, Scene, Shadow)

SAMPLE = {"titolo": "Il titolo del tuo video", "sottotitolo": "Una frase che lo racconta", "data": "12 maggio 2026",
          "social": "@iltuocanale", "relatore": "Mario Rossi", "ruolo": "Direttore"}


def preview_variables(variables: dict[str, str] | None) -> dict[str, str]:
    """Testi per le anteprime: quelli scritti dall'utente, e per gli altri un esempio. Così titoli, nomi e scritte si vedono subito,
    prima di scrivere qualcosa (nell'export un campo vuoto resta vuoto)."""
    return {**SAMPLE, **{k: v for k, v in (variables or {}).items() if v and v.strip()}}


@dataclass
class Template:
    id: str
    name: str
    kind: str                       # title | lower_third | outro | caption
    description: str
    tags: tuple[str, ...]
    build: Callable[[], object]     # Scene | list[Element] | LowerThird


# ------------------------------------------------------------------------------------------------ aiuti
def _t(id_, text, x, y, size, font="Poppins", bold=False, color="#FFFFFF", ai=None, ao=None, start=0.0, align="center", **kw) -> Element:
    kw.setdefault("fit_width", 0.88 if align == "center" else 0.8)       # titoli lunghi: si rimpiccioliscono da soli
    return Element(id=id_, kind="text", text=text, x=x, y=y, size=size, font=font, bold=bold, fill=Fill(color=color),
                   align=align, start=start, anim_in=ai or Anim("fade", 0.6), anim_out=ao or Anim("fade", 0.4), **kw)


def _s(id_, x, y, w, h, color, radius=0.0, shape="rect", ai=None, ao=None, start=0.0, **kw) -> Element:
    fill = kw.pop("fill", Fill(color=color))
    return Element(id=id_, kind="shape", shape=shape, x=x, y=y, w=w, h=h, fill=fill, radius=radius, start=start,
                   anim_in=ai or Anim("fade", 0.5), anim_out=ao or Anim("fade", 0.4), **kw)


def _scene(duration, bg: Background, elements, over_video=False, fade=0.5) -> Scene:
    return Scene(enabled=True, duration=duration, background=bg, elements=elements, over_video=over_video, fade=fade)


# ------------------------------------------------------------------------------------------------ titoli iniziali
def _minimal():
    return _scene(4.0, Background("solid", "#0E1014"), [
        _s("l", 0.5, 0.58, 0.1, 0.004, "#4C8DF6", ai=Anim("reveal", 0.8, "expo"), start=0.3),
        _t("t", "{titolo}", 0.5, 0.45, 0.075, "Poppins", True, ai=Anim("slide_up", 0.8, "expo")),
        _t("s", "{sottotitolo}", 0.5, 0.66, 0.034, color="#9CA3B0", ai=Anim("fade", 0.8), start=0.5),
        _t("d", "{data}", 0.5, 0.74, 0.026, color="#6B7280", ai=Anim("fade", 0.8), start=0.7)])


def _yellow():
    return _scene(3.6, Background("solid", "#FACC15"), [
        _t("t", "{titolo}", 0.5, 0.45, 0.19, "Anton", False, "#0B0B0B", Anim("pop", 0.55, "back"), uppercase=True,
           shadow=Shadow(True, "#000000", 0.0, 0.012, 45, 1.0), line_spacing=0.95),
        _t("s", "{sottotitolo}", 0.5, 0.78, 0.045, "Poppins", True, "#0B0B0B", Anim("slide_up", 0.5, "back"), start=0.4)],
                  fade=0.3)


def _neon():
    g = Fill("gradient", "#22D3EE", "#3B82F6", 0.0)
    return _scene(4.2, Background("gradient", "#04060C", "#0B1B3B", 90.0), [
        Element(id="t", kind="text", text="{titolo}", x=0.5, y=0.45, size=0.1, font="Poppins ExtraBold", fill=g, fit_width=0.88,
                shadow=Shadow(True, "#22D3EE", 0.03, 0.0, 0.0, 0.85), anim_in=Anim("blur", 1.0), anim_out=Anim("fade", 0.5)),
        _t("s", "{sottotitolo}", 0.5, 0.64, 0.034, "Poppins", False, "#BAE6FD", Anim("fade", 0.9), start=0.6),
        _t("d", "{data}", 0.5, 0.88, 0.024, "Space Mono", False, "#22D3EE", Anim("typewriter", 1.2, "linear"), start=0.8)])


def _cinema():
    bars = Fill(color="#000000")
    return _scene(4.5, Background("solid", "#08090B"), [
        _s("b1", 0.5, 0.09, 1.0, 0.18, "#000000", ai=Anim("slide_down", 0.8, "expo")),
        _s("b2", 0.5, 0.91, 1.0, 0.18, "#000000", ai=Anim("slide_up", 0.8, "expo")),
        _t("t", "{titolo}", 0.5, 0.47, 0.058, "Poppins", False, "#F5F0E6", Anim("fade", 1.4), uppercase=True,
           letter_spacing=0.012, start=0.4),
        _t("s", "{sottotitolo}", 0.5, 0.58, 0.026, "Poppins", False, "#A8A29E", Anim("fade", 1.2), uppercase=True,
           letter_spacing=0.008, start=1.0)], fade=0.8)


def _card():
    return _scene(4.0, Background("gradient", "#0EA5E9", "#2563EB", 120.0), [
        _s("card", 0.5, 0.5, 0.74, 0.38, "#FFFFFF", 0.03, ai=Anim("pop", 0.6, "back"),
           shadow=Shadow(True, "#0B1B3B", 0.04, 0.02, 90, 0.45)),
        _t("t", "{titolo}", 0.5, 0.46, 0.06, "Poppins", True, "#12151C", Anim("slide_up", 0.6, "expo"), start=0.25),
        _t("s", "{sottotitolo}", 0.5, 0.58, 0.03, "Poppins", False, "#5B6575", Anim("fade", 0.6), start=0.5)])


def _stripe():
    return _scene(3.8, Background("gradient", "#101216", "#1D2129", 90.0), [
        _s("band", 0.5, 0.5, 1.3, 0.24, "#FF4D4D", ai=Anim("slide_left", 0.7, "expo"), rotation=-6),
        _t("t", "{titolo}", 0.5, 0.5, 0.085, "Poppins ExtraBold", False, "#FFFFFF", Anim("slide_left", 0.8, "expo"),
           rotation=-6, start=0.15, shadow=Shadow(True, "#000000", 0.01, 0.006, 80, 0.4)),
        _t("s", "{sottotitolo}", 0.5, 0.74, 0.032, "Poppins", False, "#D1D5DB", Anim("fade", 0.6), start=0.6)])


def _sticker():
    return _scene(3.8, Background("solid", "#FDE68A"), [
        Element(id="t", kind="text", text="{titolo}", x=0.5, y=0.46, size=0.14, font="Bebas Neue", fill=Fill(color="#0B0B0B"), fit_width=0.8,
                rotation=-4, box=Box(True, "#FFFFFF", 1.0, 0.03, 0.014), outline=Outline(0.0, "#000000"),
                shadow=Shadow(True, "#000000", 0.0, 0.01, 45, 1.0), anim_in=Anim("by_word", 1.0, "back", 0.12),
                anim_out=Anim("fade", 0.4)),
        _t("s", "{sottotitolo}", 0.5, 0.74, 0.04, "Poppins", True, "#0B0B0B", Anim("fade", 0.6), start=0.9, rotation=-4)],
                  fade=0.3)


def _typewriter():
    return _scene(4.6, Background("solid", "#0B0F14"), [
        _t("t", "{titolo}", 0.09, 0.44, 0.06, "Space Mono", True, "#4ADE80", Anim("typewriter", 1.8, "linear"), align="left"),
        _t("s", "{sottotitolo}", 0.09, 0.56, 0.03, "Space Mono", False, "#94A3B8", Anim("typewriter", 1.2, "linear"),
           start=1.8, align="left"),
        _t("d", "{data}", 0.09, 0.64, 0.026, "Space Mono", False, "#475569", Anim("fade", 0.6), start=2.8, align="left")])


def _elegant():
    gold = "#C9A227"
    return _scene(4.6, Background("gradient", "#14161B", "#050608", 90.0), [
        _s("l1", 0.5, 0.33, 0.14, 0.003, gold, ai=Anim("reveal", 1.0, "expo"), start=0.2),
        _t("t", "{titolo}", 0.5, 0.48, 0.09, "DM Serif Display", False, "#F5F0E6", Anim("fade", 1.3), start=0.4),
        _s("l2", 0.5, 0.63, 0.14, 0.003, gold, ai=Anim("reveal", 1.0, "expo"), start=0.8),
        _t("s", "{sottotitolo}", 0.5, 0.72, 0.028, "Poppins", False, "#D6D3D1", Anim("fade", 1.2), uppercase=True,
           letter_spacing=0.01, start=1.0)], fade=0.8)


def _aurora():
    return _scene(4.2, Background("gradient", "#0F766E", "#1D4ED8", 135.0), [
        _t("t", "{titolo}", 0.5, 0.45, 0.085, "Poppins", True, "#FFFFFF", Anim("blur", 1.0),
           shadow=Shadow(True, "#052E2B", 0.025, 0.008, 90, 0.5)),
        _t("s", "{sottotitolo}", 0.5, 0.62, 0.034, "Poppins", False, "#E0F2FE", Anim("fade", 0.9), start=0.5),
        _t("d", "{data}", 0.5, 0.86, 0.025, "Poppins", False, "#BAE6FD", Anim("fade", 0.9), start=0.8)])


def _split():
    return _scene(4.0, Background("solid", "#0E1014"), [
        _s("blk", 0.3, 0.5, 0.6, 1.0, "#2563EB", ai=Anim("slide_left", 0.7, "expo")),
        _t("t", "{titolo}", 0.06, 0.45, 0.07, "Poppins ExtraBold", False, "#FFFFFF", Anim("slide_left", 0.8, "expo"), align="left",
           start=0.2),
        _t("s", "{sottotitolo}", 0.66, 0.46, 0.034, "Poppins", False, "#CBD5E1", Anim("fade", 0.8), start=0.7, align="left"),
        _t("d", "{data}", 0.66, 0.56, 0.026, "Space Mono", False, "#4C8DF6", Anim("fade", 0.8), start=0.9, align="left")])


def _social():
    return _scene(3.8, Background("gradient", "#FF6B4A", "#FF9F1C", 120.0), [
        _t("t", "{titolo}", 0.5, 0.44, 0.09, "Poppins ExtraBold", False, "#FFFFFF", Anim("pop", 0.6, "back"),
           shadow=Shadow(True, "#9A3412", 0.0, 0.01, 45, 0.6)),
        _t("h", "{social}", 0.5, 0.68, 0.034, "Poppins", True, "#12151C", Anim("slide_up", 0.6, "back"), start=0.5,
           box=Box(True, "#FFFFFF", 0.95, 0.018, 0.03))])


def _over_lower():
    return _scene(4.0, Background("transparent"), [
        _s("bg", 0.3, 0.84, 0.54, 0.2, "#0B0D12", 0.01, ai=Anim("slide_left", 0.6, "expo"), opacity=0.78),
        _s("ac", 0.032, 0.84, 0.006, 0.2, "#4C8DF6", ai=Anim("slide_left", 0.6, "expo")),
        _t("t", "{titolo}", 0.05, 0.815, 0.06, "Poppins", True, "#FFFFFF", Anim("slide_left", 0.7, "expo"), align="left", start=0.1),
        _t("s", "{sottotitolo}", 0.05, 0.885, 0.03, "Poppins", False, "#CBD5E1", Anim("fade", 0.6), align="left", start=0.4)],
                  over_video=True, fade=0.0)


def _over_center():
    scrim = Fill("gradient", "#00000000", "#CC000000", 90.0)
    return _scene(4.0, Background("transparent"), [
        _s("scrim", 0.5, 0.5, 1.0, 1.0, "", ai=Anim("fade", 0.8), fill=scrim),
        _t("t", "{titolo}", 0.5, 0.74, 0.085, "Poppins", True, "#FFFFFF", Anim("slide_up", 0.8, "expo"), start=0.2,
           shadow=Shadow(True, "#000000", 0.015, 0.005, 90, 0.6)),
        _t("s", "{sottotitolo}", 0.5, 0.86, 0.034, "Poppins", False, "#E5E7EB", Anim("fade", 0.8), start=0.6)],
                  over_video=True, fade=0.0)


TITLES = [
    Template("minimal", "Minimale", "title", "Pulito, testo bianco su fondo scuro", ("moderno", "sobrio"), _minimal),
    Template("yellow", "Giallo YouTuber", "title", "Testo enorme nero su giallo, ombra netta", ("youtube", "energico"), _yellow),
    Template("neon", "Neon", "title", "Testo luminoso azzurro su notte blu", ("moderno", "tech"), _neon),
    Template("cinema", "Cinema", "title", "Bande da film, lettere spaziate", ("elegante", "film"), _cinema),
    Template("card", "Scheda", "title", "Scheda bianca che compare su fondo blu", ("pulito", "instagram"), _card),
    Template("stripe", "Fascia", "title", "Fascia rossa inclinata con titolo", ("energico", "social"), _stripe),
    Template("sticker", "Sticker", "title", "Parole che «saltano» su un adesivo", ("divertente", "instagram"), _sticker),
    Template("typewriter", "Macchina da scrivere", "title", "Il titolo si scrive da solo", ("tech", "retro"), _typewriter),
    Template("elegant", "Elegante", "title", "Serif raffinato con filetti dorati", ("elegante", "evento"), _elegant),
    Template("aurora", "Aurora", "title", "Sfumatura verde-blu, titolo sfocato che si mette a fuoco", ("moderno", "morbido"), _aurora),
    Template("split", "Diviso", "title", "Blocco blu a sinistra, dettagli a destra", ("moderno", "evento"), _split),
    Template("social", "Social", "title", "Arancione vivo con il tuo @canale", ("instagram", "energico"), _social),
    Template("over_lower", "Sul video: in basso", "title", "Titolo trasparente sopra le prime immagini", ("sul video",), _over_lower),
    Template("over_center", "Sul video: sfumato", "title", "Titolo su sfumatura scura sopra il video", ("sul video",), _over_center),
]


# ------------------------------------------------------------------------------------------------ nomi dei relatori
def _lt(style: str):
    def make() -> LowerThird:
        return LowerThird(name="{relatore}", role="{ruolo}", start=1.0, duration=6.0, style=style,
                          anim_in=Anim("slide_left", 0.6, "expo"), anim_out=Anim("fade", 0.4))
    return make


LOWER_THIRDS = [
    Template("bar", "Barra", "lower_third", "Barra scura con filo colorato", ("classico",), _lt("bar")),
    Template("pill", "Pillola", "lower_third", "Capsula scura arrotondata con pallino", ("moderno",), _lt("pill")),
    Template("line", "Linea", "lower_third", "Solo testo con filo verticale, su qualsiasi video", ("minimale",), _lt("line")),
    Template("card", "Scheda bianca", "lower_third", "Scheda bianca con bordo colorato", ("pulito",), _lt("card")),
    Template("gradient", "Sfumatura", "lower_third", "Barra colorata che sfuma", ("moderno",), _lt("gradient")),
    Template("tag", "Etichetta gialla", "lower_third", "Stile YouTuber: nome in maiuscolo su giallo", ("youtube",), _lt("tag")),
    Template("underline", "Sottolineato", "lower_third", "Nome con sottolineatura colorata", ("minimale",), _lt("underline")),
    Template("social", "Social", "lower_third", "Pillola bianca con @profilo colorato", ("instagram",), _lt("social")),
]


# ------------------------------------------------------------------------------------------------ schermate finali
def _end_thanks():
    return _scene(5.0, Background("gradient", "#0B1B3B", "#0E6E8C", 120.0), [
        _t("t", "Grazie per la visione", 0.5, 0.45, 0.075, "Poppins", True, ai=Anim("slide_up", 0.8, "expo")),
        _t("h", "{social}", 0.5, 0.62, 0.036, "Poppins", False, "#BAE6FD", Anim("fade", 0.8), start=0.5)])


def _end_subscribe():
    return _scene(6.0, Background("solid", "#0E1014"), [
        _t("t", "Ti è piaciuto?", 0.5, 0.32, 0.07, "Poppins", True, ai=Anim("slide_down", 0.7, "expo")),
        _s("btn", 0.5, 0.52, 0.28, 0.1, "#FF0033", 0.02, ai=Anim("pop", 0.6, "back"), start=0.4),
        _t("bt", "ISCRIVITI", 0.5, 0.52, 0.045, "Poppins ExtraBold", False, "#FFFFFF", Anim("pop", 0.6, "back"), start=0.5),
        _t("h", "{social}", 0.5, 0.7, 0.034, "Poppins", False, "#9CA3B0", Anim("fade", 0.8), start=0.9)])


def _end_next():
    return _scene(5.0, Background("gradient", "#FF6B4A", "#FF9F1C", 120.0), [
        _t("t", "Alla prossima!", 0.5, 0.45, 0.11, "Poppins ExtraBold", False, "#FFFFFF", Anim("pop", 0.6, "back"),
           shadow=Shadow(True, "#9A3412", 0.0, 0.01, 45, 0.6)),
        _t("s", "{titolo}", 0.5, 0.65, 0.032, "Poppins", True, "#12151C", Anim("fade", 0.8), start=0.5)])


def _end_minimal():
    return _scene(4.0, Background("solid", "#000000"), [
        _s("l", 0.5, 0.52, 0.08, 0.003, "#FFFFFF", ai=Anim("reveal", 0.8, "expo")),
        _t("t", "Grazie", 0.5, 0.44, 0.06, "Poppins", False, "#FFFFFF", Anim("fade", 1.0), letter_spacing=0.01, uppercase=True),
        _t("h", "{social}", 0.5, 0.6, 0.026, "Space Mono", False, "#9CA3B0", Anim("fade", 1.0), start=0.5)], fade=0.8)


def _end_event():
    return _scene(5.0, Background("gradient", "#14161B", "#050608", 90.0), [
        _t("t", "{titolo}", 0.5, 0.44, 0.07, "DM Serif Display", False, "#F5F0E6", Anim("fade", 1.2)),
        _s("l", 0.5, 0.56, 0.12, 0.003, "#C9A227", ai=Anim("reveal", 1.0, "expo"), start=0.5),
        _t("s", "Grazie a tutti i partecipanti", 0.5, 0.65, 0.028, "Poppins", False, "#D6D3D1", Anim("fade", 1.0), start=0.8)],
                  fade=0.8)


OUTROS = [
    Template("thanks", "Grazie", "outro", "Ringraziamento con il tuo canale", ("classico",), _end_thanks),
    Template("subscribe", "Iscriviti", "outro", "Invito a iscriversi, con pulsante rosso", ("youtube",), _end_subscribe),
    Template("next", "Alla prossima", "outro", "Arancione vivo, saluto finale", ("instagram", "energico"), _end_next),
    Template("minimal", "Minimale", "outro", "Solo «Grazie» su nero", ("sobrio",), _end_minimal),
    Template("event", "Evento", "outro", "Titolo dell'evento e ringraziamento", ("elegante", "evento"), _end_event),
]


# ------------------------------------------------------------------------------------------------ scritte sul video
def _cap(id_, text, x, y, size, color="#FFFFFF", font="Poppins", bold=True, box=None, shadow=None, uppercase=False, **kw):
    return [Element(id=id_, kind="text", text=text, x=x, y=y, size=size, font=font, bold=bold, fill=Fill(color=color),
                    box=box or Box(), shadow=shadow or Shadow(), uppercase=uppercase, start=2.0, end=8.0, fit_width=0.6,
                    anim_in=Anim("fade", 0.5), anim_out=Anim("fade", 0.4), **kw)]


CAPTIONS = [
    Template("caption", "Didascalia", "caption", "Testo bianco su fascia scura, in basso", ("base",),
             lambda: _cap("c", "Scrivi qui la didascalia", 0.5, 0.9, 0.04, bold=False, box=Box(True, "#000000", 0.6, 0.014, 0.01))),
    Template("hashtag", "Hashtag", "caption", "Pillola colorata in alto a sinistra", ("social",),
             lambda: _cap("c", "#iltuohashtag", 0.12, 0.08, 0.034, "#FFFFFF", box=Box(True, "#2563EB", 1.0, 0.014, 0.03))),
    Template("big", "Titolo grande", "caption", "Testo enorme con contorno", ("youtube",),
             lambda: _cap("c", "Parola chiave", 0.5, 0.5, 0.14, "#FFFFFF", "Anton", False, uppercase=True,
                          outline=Outline(0.006, "#000000"), shadow=Shadow(True, "#000000", 0.0, 0.01, 45, 1.0))),
    Template("tag", "Etichetta gialla", "caption", "Adesivo giallo inclinato", ("youtube",),
             lambda: _cap("c", "Importante", 0.82, 0.14, 0.06, "#0B0B0B", "Anton", False, uppercase=True, rotation=-4,
                          box=Box(True, "#FACC15", 1.0, 0.016, 0.006))),
    Template("date", "Data", "caption", "Piccola data in un angolo", ("base",),
             lambda: _cap("c", "{data}", 0.9, 0.07, 0.03, "#FFFFFF", "Space Mono", True,
                          shadow=Shadow(True, "#000000", 0.008, 0.003, 90, 0.8))),
    Template("quote", "Citazione", "caption", "Frase in corsivo elegante con ombra", ("elegante",),
             lambda: _cap("c", "Una frase da ricordare", 0.5, 0.82, 0.06, "#FFFFFF", "DM Serif Display", False,
                          shadow=Shadow(True, "#000000", 0.012, 0.004, 90, 0.8))),
]

ALL = {"title": TITLES, "lower_third": LOWER_THIRDS, "outro": OUTROS, "caption": CAPTIONS}

# modelli moderni (stile vlogger): stanno in un file a parte e compaiono per primi nelle gallerie
from . import templates_modern as _modern  # noqa: E402

TITLES[:0] = _modern.TITLES
LOWER_THIRDS[:0] = _modern.LOWER_THIRDS
OUTROS[:0] = _modern.OUTROS


def get(kind: str, tid: str) -> Template:
    return next(t for t in ALL[kind] if t.id == tid)


# ------------------------------------------------------------------------------------------------ applicazione
def apply_title(spec, tid: str) -> None:
    sc = get("title", tid).build()
    old = spec.graphics.title
    sc.transition, sc.fade = old.transition, old.fade        # la transizione scelta resta, cambia solo l'aspetto
    spec.graphics.title = sc
    spec.graphics.title_template = tid


def apply_outro(spec, tid: str) -> None:
    sc = get("outro", tid).build()
    old = spec.graphics.outro
    sc.transition, sc.fade = old.transition, old.fade
    spec.graphics.outro = sc
    spec.graphics.outro_template = tid


def apply_lower_third_style(spec, style: str) -> None:
    """Applica lo stile a tutti i nomi già inseriti (nome, ruolo e tempi restano)."""
    for lt in spec.graphics.lower_thirds:
        lt.style = style


def new_lower_third(spec, style: str | None = None) -> LowerThird:
    base = get("lower_third", style or (spec.graphics.lower_thirds[-1].style if spec.graphics.lower_thirds else "bar")).build()
    return base


def add_caption(spec, tid: str) -> list[Element]:
    import uuid
    els = get("caption", tid).build()
    for e in els:
        e.id = uuid.uuid4().hex[:6]
        e.targets = ["main"]
    spec.graphics.elements.extend(els)
    return els


def used_text_variables(spec) -> list[str]:
    """Segnaposto davvero usati dal progetto: sono gli unici campi da far compilare."""
    from .render.model import VARIABLES
    gr = spec.graphics
    texts = [e.text for e in gr.elements + gr.title.elements + gr.outro.elements if e.kind == "text"]
    if gr.title.enabled is False:
        texts = [e.text for e in gr.elements + gr.outro.elements if e.kind == "text"]
    texts += [t for lt in gr.lower_thirds for t in (lt.name, lt.role)]
    return [k for k in VARIABLES if any("{" + k + "}" in t for t in texts)]
