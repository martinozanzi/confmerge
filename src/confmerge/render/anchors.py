"""Elementi «ancorati»: un testo o un logo che sta sempre in un angolo o su un lato, qualunque sia il formato del video.

Si usa in Studio Social: lo stesso testo («@canale» in basso al centro, un titolo in alto…) finisce al posto giusto sia
nel 16:9 sia nel 9:16, e dentro la zona non coperta dall'interfaccia della piattaforma."""
from __future__ import annotations

from dataclasses import replace

from .model import Element

ANCHORS = {"tl": "In alto a sinistra", "tc": "In alto al centro", "tr": "In alto a destra",
           "ml": "A sinistra", "mc": "Al centro", "mr": "A destra",
           "bl": "In basso a sinistra", "bc": "In basso al centro", "br": "In basso a destra"}
MARGIN = 0.03                 # distanza dal bordo, frazione della larghezza


def resolve(elements: list[Element], W: int, H: int, safe: list[float] | tuple | None = None) -> list[Element]:
    """Copie degli elementi con x, y calcolati dall'ancora (gli altri restano uguali). `safe`: sopra, sotto, sinistra, destra."""
    from .text_renderer import element_bbox
    top, bottom, left, right = (list(safe or []) + [0.0] * 4)[:4]
    out = []
    m = MARGIN * W
    for el in elements:
        if el.anchor not in ANCHORS:
            out.append(el)
            continue
        b = element_bbox(replace(el, x=0.5, y=0.5, rotation=0.0), W, H)
        x = {"l": m + left * W + b.width() / 2, "c": W / 2, "r": W - m - right * W - b.width() / 2}[el.anchor[1]]
        y = {"t": m + top * H + b.height() / 2, "m": H / 2, "b": H - m - bottom * H - b.height() / 2}[el.anchor[0]]
        out.append(replace(el, x=x / W, y=y / H))
    return out
