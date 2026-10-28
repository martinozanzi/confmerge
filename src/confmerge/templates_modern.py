"""Modelli moderni, nello stile dei video dei vlogger: titoli sopra il video, parole che «saltano», pennarello, vetro, bordi.

Stanno qui, separati dai modelli classici, e compaiono per primi nella galleria. Come gli altri, usano solo segnaposto e i
caratteri inclusi nel programma."""
from __future__ import annotations

from .render.model import Anim, Background, Box, Element, Fill, LowerThird, Outline, Shadow
from .templates import Template, _s, _scene, _t

ACCENT = "#FFD60A"
NO_FILL = "#00000000"


def _scrim(alpha_hex: str = "B3", angle: float = 90.0, start: float = 0.0):
    """Sfumatura scura (trasparente in alto, scura in basso) che rende leggibile il testo su qualsiasi video."""
    return _s("scrim", 0.5, 0.5, 1.0, 1.0, "", ai=Anim("fade", 0.7), ao=Anim("fade", 0.5), start=start,
              fill=Fill("gradient", NO_FILL, f"#{alpha_hex}000000", angle))


def _shadow(blur=0.02, dist=0.006, op=0.6):
    return Shadow(True, "#000000", blur, dist, 90, op)


# ------------------------------------------------------------------------------------------------ titoli
def vlog():
    return _scene(4.6, Background("transparent"), [
        _scrim("C4"),
        _s("bar", 0.074, 0.755, 0.007, 0.2, ACCENT, ai=Anim("reveal", 0.6, "expo"), start=0.15),
        _t("t", "{titolo}", 0.095, 0.73, 0.1, "Poppins Black", False, "#FFFFFF", Anim("by_word", 0.9, "back", 0.09), align="left",
           uppercase=True, fit_width=0.72, shadow=_shadow(), start=0.2, line_spacing=0.95),
        _t("s", "{sottotitolo}", 0.095, 0.865, 0.034, "Poppins", True, "#0B0B0B", Anim("slide_up", 0.6, "expo"), align="left",
           box=Box(True, ACCENT, 1.0, 0.012, 0.012), fit_width=0.6, start=0.7),
        _t("d", "{data}", 0.94, 0.93, 0.026, "Poppins", False, "#FFFFFF", Anim("fade", 0.8), align="right", start=1.0, opacity=0.75)],
                  over_video=True, fade=0.0)


def kinetic():
    return _scene(4.4, Background("transparent"), [
        _s("dim", 0.5, 0.5, 1.0, 1.0, "#000000", ai=Anim("fade", 0.5), ao=Anim("fade", 0.5), opacity=0.38),
        _t("t", "{titolo}", 0.5, 0.45, 0.17, "Anton", False, "#FFFFFF", Anim("by_word", 1.0, "back", 0.12), uppercase=True,
           fit_width=0.9, shadow=_shadow(0.0, 0.012, 0.9), line_spacing=0.95, start=0.1),
        _s("mk", 0.5, 0.64, 0.46, 0.085, ACCENT, ai=Anim("reveal", 0.6, "expo"), start=0.7, rotation=-2),
        _t("s", "{sottotitolo}", 0.5, 0.64, 0.036, "Poppins", True, "#0B0B0B", Anim("fade", 0.5), uppercase=True,
           letter_spacing=0.006, rotation=-2, fit_width=0.42, start=0.9)],
                  over_video=True, fade=0.0)


def glass():
    edge = Outline(0.0016, "#FFFFFF")
    return _scene(4.6, Background("transparent"), [
        _s("card", 0.5, 0.77, 0.74, 0.26, "#FFFFFF", 0.04, ai=Anim("pop", 0.6, "back"), ao=Anim("fade", 0.5), opacity=0.17,
           outline=edge, shadow=Shadow(True, "#000000", 0.04, 0.012, 90, 0.35)),
        _s("dot", 0.18, 0.7, 0.012, 0.0213, ACCENT, shape="ellipse", ai=Anim("pop", 0.5, "back"), start=0.4),
        _t("t", "{titolo}", 0.5, 0.775, 0.064, "Poppins", True, "#FFFFFF", Anim("slide_up", 0.7, "expo"), fit_width=0.66,
           shadow=_shadow(0.012, 0.004, 0.55), start=0.2),
        _t("s", "{sottotitolo}", 0.5, 0.855, 0.032, "Poppins", False, "#FFFFFF", Anim("fade", 0.7), fit_width=0.6, start=0.6,
           opacity=0.85)],
                  over_video=True, fade=0.0)


def outline():
    return _scene(4.4, Background("solid", "#0A0A0C"), [
        _t("t", "{titolo}", 0.5, 0.44, 0.15, "Anton", False, NO_FILL, Anim("slide_up", 0.9, "expo"), uppercase=True,
           outline=Outline(0.0035, "#FFFFFF"), fit_width=0.9, line_spacing=0.95),
        _s("ul", 0.5, 0.6, 0.12, 0.006, ACCENT, ai=Anim("reveal", 0.7, "expo"), start=0.6),
        _t("s", "{sottotitolo}", 0.5, 0.69, 0.034, "Poppins", False, "#E5E7EB", Anim("fade", 0.8), uppercase=True,
           letter_spacing=0.01, fit_width=0.8, start=0.8)], fade=0.4)


def editorial():
    return _scene(4.6, Background("transparent"), [
        _s("dim", 0.5, 0.5, 1.0, 1.0, "#000000", ai=Anim("fade", 0.6), ao=Anim("fade", 0.5), opacity=0.3),
        _s("l1", 0.5, 0.36, 0.76, 0.0035, "#FFFFFF", ai=Anim("reveal", 0.9, "expo")),
        _t("t", "{titolo}", 0.5, 0.5, 0.16, "Bebas Neue", False, "#FFFFFF", Anim("fade", 1.0), uppercase=True,
           letter_spacing=0.01, fit_width=0.8, shadow=_shadow(0.015, 0.004, 0.5), start=0.3),
        _s("l2", 0.5, 0.64, 0.76, 0.0035, "#FFFFFF", ai=Anim("reveal", 0.9, "expo"), start=0.3),
        _t("s", "{sottotitolo}", 0.5, 0.71, 0.03, "Poppins", False, "#FFFFFF", Anim("fade", 0.9), uppercase=True,
           letter_spacing=0.012, fit_width=0.7, start=0.8),
        _t("d", "{data}", 0.5, 0.29, 0.024, "Space Mono", False, ACCENT, Anim("fade", 0.9), start=0.7)],
                  over_video=True, fade=0.0)


def punch():
    """Colore pieno acceso: titolo enorme nero e striscia con il canale."""
    return _scene(3.8, Background("solid", "#FF5A36"), [
        _t("t", "{titolo}", 0.5, 0.45, 0.17, "Poppins Black", False, "#0B0B0B", Anim("pop", 0.55, "back"), uppercase=True,
           fit_width=0.88, line_spacing=0.92),
        _s("pill", 0.5, 0.72, 0.3, 0.085, "#0B0B0B", 0.04, ai=Anim("slide_up", 0.6, "back"), start=0.45),
        _t("h", "{social}", 0.5, 0.72, 0.034, "Poppins", True, "#FFFFFF", Anim("fade", 0.5), fit_width=0.26, start=0.6)],
                  fade=0.3)


TITLES = [
    Template("vlog", "Vlog", "title", "Titolo grande sul video, parole che saltano e striscia gialla", ("moderni", "vlogger", "sul video"), vlog),
    Template("kinetic", "Parole in movimento", "title", "Maiuscole enormi sul video e pennarello giallo", ("moderni", "vlogger", "sul video"), kinetic),
    Template("glass", "Vetro", "title", "Scheda trasparente a vetro, in basso sul video", ("moderni", "sul video"), glass),
    Template("editorial", "Editoriale", "title", "Filetti e lettere alte, come un documentario", ("moderni", "sul video"), editorial),
    Template("outline", "Contorno", "title", "Scritta vuota con il solo contorno su fondo nero", ("moderni", "vlogger"), outline),
    Template("punch", "Colpo di colore", "title", "Arancione acceso e titolo nero enorme", ("moderni", "vlogger"), punch),
]


# ------------------------------------------------------------------------------------------------ nomi dei relatori
def _lt(style: str):
    def make() -> LowerThird:
        return LowerThird(name="{relatore}", role="{ruolo}", start=1.0, duration=6.0, style=style,
                          anim_in=Anim("slide_left", 0.6, "expo"), anim_out=Anim("fade", 0.4))
    return make


LOWER_THIRDS = [
    Template("glass", "Vetro", "lower_third", "Scheda trasparente a vetro con pallino colorato", ("moderni",), _lt("glass")),
    Template("block", "Blocco", "lower_third", "Blocco colorato con il nome in maiuscolo, stile vlogger", ("moderni", "vlogger"), _lt("block")),
]


# ------------------------------------------------------------------------------------------------ schermate finali
def end_screen():
    """Spazi pronti per gli elementi finali di YouTube: due video consigliati e il pulsante di iscrizione."""
    edge = Outline(0.002, "#FFFFFF")
    ghost = dict(radius=0.012, opacity=0.9, outline=edge)
    return _scene(12.0, Background("gradient", "#0B0D12", "#1B2230", 90.0), [
        _t("t", "{titolo}", 0.5, 0.12, 0.05, "Poppins", True, "#FFFFFF", Anim("fade", 0.6), fit_width=0.8),
        _s("v1", 0.27, 0.5, 0.36, 0.36 * 16 / 9 * 0.5625 * 1.0, "#FFFFFF", ai=Anim("pop", 0.5, "back"), start=0.3,
           fill=Fill(color="#FFFFFF1A"), **ghost),
        _s("v2", 0.73, 0.5, 0.36, 0.36 * 16 / 9 * 0.5625 * 1.0, "#FFFFFF", ai=Anim("pop", 0.5, "back"), start=0.5,
           fill=Fill(color="#FFFFFF1A"), **ghost),
        _t("l1", "Guarda anche", 0.27, 0.78, 0.028, "Poppins", False, "#CBD5E1", Anim("fade", 0.5), start=0.6),
        _t("l2", "Guarda anche", 0.73, 0.78, 0.028, "Poppins", False, "#CBD5E1", Anim("fade", 0.5), start=0.8),
        _s("sub", 0.5, 0.86, 0.12, 0.12 * 16 / 9, "#FF0033", shape="ellipse", ai=Anim("pop", 0.6, "back"), start=0.9),
        _t("h", "{social}", 0.5, 0.95, 0.03, "Poppins", True, "#FFFFFF", Anim("fade", 0.6), start=1.0, fit_width=0.4)])


def follow():
    return _scene(5.0, Background("solid", "#0A0A0C"), [
        _t("t", "Ti è piaciuto?", 0.5, 0.36, 0.1, "Anton", False, "#FFFFFF", Anim("by_word", 0.8, "back", 0.12), uppercase=True),
        _t("s", "Segui per altri video", 0.5, 0.52, 0.038, "Poppins", False, "#9CA3AF", Anim("fade", 0.7), start=0.6),
        _s("p", 0.5, 0.68, 0.3, 0.095, ACCENT, 0.047, ai=Anim("pop", 0.6, "back"), start=0.8),
        _t("h", "{social}", 0.5, 0.68, 0.038, "Poppins", True, "#0B0B0B", Anim("fade", 0.5), start=0.95, fit_width=0.26)])


OUTROS = [
    Template("endscreen", "Schermata finale YouTube", "outro", "Due spazi per i video consigliati e il pulsante di iscrizione",
             ("moderni", "youtube"), end_screen),
    Template("follow", "Segui", "outro", "Maiuscole che saltano e pillola con il tuo canale", ("moderni", "vlogger"), follow),
]
