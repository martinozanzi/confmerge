"""Montaggio per intervalli (Studio Social): quali parti del video si tengono e come si riportano i tempi.

Tutti i tempi «di progetto» sono sulla linea del video unito; i tempi «di uscita» sono quelli del video finito, dopo i
tagli. `ranges` è una lista ordinata di (inizio, fine) di progetto: l'uscita è la loro concatenazione."""
from __future__ import annotations

from .project import Project

MIN_RANGE = 0.1


def ranges_for(p: Project, t0: float, t1: float) -> list[tuple[float, float]]:
    """Intervalli da usare in export: nel social quelli tenuti (dentro t0..t1), altrimenti l'unico intervallo t0..t1."""
    if p.kind != "social" or not p.keep:
        return [(t0, t1)]
    out = []
    for a, b in p.keep:
        a, b = max(a, t0), min(b, t1)
        if b - a >= MIN_RANGE:
            out.append((a, b))
    return out or [(t0, t1)]


def total_len(ranges: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in ranges)


def to_out(ranges: list[tuple[float, float]], t: float) -> float | None:
    """Tempo di uscita di un istante di progetto (None se cade in una parte tolta)."""
    pos = 0.0
    for a, b in ranges:
        if a <= t < b:
            return pos + (t - a)
        pos += b - a
    return None


def remap_span(ranges: list[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    """Un intervallo di progetto diventa uno o più intervalli di uscita (se attraversa dei tagli si spezza)."""
    out, pos = [], 0.0
    for a, b in ranges:
        lo, hi = max(start, a), min(end, b)
        if hi - lo > 1e-3:
            out.append((pos + lo - a, pos + hi - a))
        pos += b - a
    return out
