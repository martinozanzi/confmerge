"""Easing e stato di animazione di entrata/uscita."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Anim, Element


def ease(name: str, t: float) -> float:
    t = min(1.0, max(0.0, t))
    if name == "linear":
        return t
    if name == "cubic":
        return 1 - (1 - t) ** 3
    if name == "back":  # overshoot
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    if name == "expo":
        return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)
    # ease_in_out (sinusoidale)
    return -(math.cos(math.pi * t) - 1) / 2


@dataclass
class AnimState:
    alpha: float = 1.0        # moltiplicatore opacità
    dx: float = 0.0           # spostamento in frazione della larghezza
    dy: float = 0.0           # in frazione dell'altezza
    scale: float = 1.0
    reveal: float = 1.0       # 0..1 maschera orizzontale
    blur: float = 0.0         # frazione dell'altezza
    chars: float = 1.0        # 0..1 quota di caratteri (macchina da scrivere)
    unit_progress: float | None = None   # per lettera/parola: progresso globale 0..1 con cascata


def _phase(a: Anim, u: float, entering: bool) -> AnimState:
    """u = progresso lineare 0..1 della fase; entering: True entrata, False uscita (u=0 inizio uscita)."""
    p = ease(a.easing, u)
    s = 1.0 - p if not entering else p   # s: 0 = nascosto, 1 = pienamente visibile
    st = AnimState()
    k = a.kind
    if k == "fade":
        st.alpha = s
    elif k.startswith("slide_"):
        off = (1.0 - s) * 0.12
        st.alpha = min(1.0, s * 2.5)
        st.dx = {"slide_left": -off, "slide_right": off}.get(k, 0.0)
        st.dy = {"slide_up": -off, "slide_down": off}.get(k, 0.0)
        # per entrata da sinistra: l'elemento arriva da sinistra (dx negativo → 0)
    elif k == "pop":
        st.scale = max(0.0, s)
        st.alpha = min(1.0, s * 3)
    elif k == "reveal":
        st.reveal = s
    elif k == "blur":
        st.alpha = min(1.0, s * 1.5)
        st.blur = (1.0 - s) * 0.02
    elif k == "typewriter":
        st.chars = u if entering else 1.0 - u
    elif k in ("by_word", "by_letter"):
        st.unit_progress = u if entering else 1.0 - u
    return st


def state_at(el: Element, t: float, seg_dur: float) -> AnimState | None:
    """Stato dell'elemento al tempo t (locale al segmento) o None se non visibile."""
    a = el.start
    b = seg_dur if el.end is None else min(el.end, seg_dur)
    if t < a or t > b:
        return None
    ai, ao = el.anim_in, el.anim_out
    if ai.kind != "none" and ai.duration > 0 and t < a + ai.duration:
        return _phase(ai, (t - a) / ai.duration, True)
    if ao.kind != "none" and ao.duration > 0 and t > b - ao.duration:
        return _phase(ao, (t - (b - ao.duration)) / ao.duration, False)
    return AnimState()


def static_window(el: Element, seg_dur: float) -> tuple[float, float]:
    """Intervallo in cui l'elemento è fermo (nessuna animazione)."""
    a = el.start
    b = seg_dur if el.end is None else min(el.end, seg_dur)
    if el.anim_in.kind != "none":
        a += el.anim_in.duration
    if el.anim_out.kind != "none":
        b -= el.anim_out.duration
    return a, max(a, b)
