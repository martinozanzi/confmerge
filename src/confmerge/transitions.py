"""Transizioni (stile YouTube / vlog): tra titolo e video, tra una clip e l'altra, tra video e schermata finale.

Ogni transizione ha un nome semplice e corrisponde a un effetto `xfade` di ffmpeg. Tra una clip e l'altra l'audio è
quello della registrazione esterna, continuo: per non perdere la sincronia si usano solo effetti che NON accorciano il
video (taglio netto, dissolvenza al nero, flash bianco)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transition:
    id: str
    label: str
    xfade: str            # nome dell'effetto in ffmpeg ("" = taglio netto)
    duration: float       # durata consigliata, in secondi
    description: str
    join: bool = False    # utilizzabile anche tra due clip (non cambia la durata)
    color: str = ""       # per le transizioni "attraverso un colore" tra clip


TRANSITIONS = [
    Transition("cut", "Taglio netto", "", 0.0, "Nessun effetto: si passa subito all'immagine successiva.", True),
    Transition("fade", "Dissolvenza", "fade", 0.8, "Il classico: un'immagine sfuma nell'altra."),
    Transition("fadeblack", "Dissolvenza al nero", "fadeblack", 0.8, "Si spegne al nero e riparte: elegante e sobria.", True, "black"),
    Transition("fadewhite", "Flash bianco", "fadewhite", 0.5, "Un lampo bianco: molto usato nei vlog.", True, "white"),
    Transition("slideleft", "Scorri", "slideleft", 0.6, "L'immagine nuova entra da destra spingendo via la vecchia."),
    Transition("slideup", "Scorri in alto", "slideup", 0.6, "L'immagine nuova sale dal basso."),
    Transition("wipeleft", "Tendina", "wipeleft", 0.7, "Una tendina scopre l'immagine nuova."),
    Transition("circleopen", "Cerchio", "circleopen", 0.8, "L'immagine nuova si apre da un cerchio al centro."),
    Transition("zoomin", "Zoom", "zoomin", 0.8, "Zoom avanti verso la scena successiva."),
    Transition("pixelize", "Pixel", "pixelize", 0.7, "L'immagine si trasforma in grossi pixel e cambia."),
    Transition("hblur", "Sfocatura", "hblur", 0.6, "Sfocatura veloce in orizzontale: effetto «whip»."),
    Transition("radial", "Radiale", "radial", 0.8, "Uno scatto circolare, come la lancetta di un orologio."),
]
BY_ID = {t.id: t for t in TRANSITIONS}


def get(tid: str) -> Transition:
    return BY_ID.get(tid, BY_ID["fade"])


def join_options() -> list[Transition]:
    return [t for t in TRANSITIONS if t.join]


def nearest_join(tid: str) -> str:
    """Stile da usare tra due clip quando l'utente sceglie un solo stile per tutto."""
    t = get(tid)
    if t.join:
        return t.id
    return "fadewhite" if tid in ("zoomin", "hblur", "pixelize") else "fadeblack"


def apply_all(spec, tid: str) -> None:
    """Un solo stile per tutto: titolo → video, clip → clip, video → finale (modalità Semplice)."""
    t = get(tid)
    gr = spec.graphics
    for sc in (gr.title, gr.outro):
        sc.transition = t.id
        if t.duration:
            sc.fade = t.duration
    spec.image.clip_transition = nearest_join(tid)
    spec.image.clip_transition_dur = 0.6
    gr.transition_style = t.id
