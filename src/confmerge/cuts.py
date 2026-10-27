"""Tagli per Studio Social: ricerca dei silenzi e operazioni sugli intervalli tenuti."""
from __future__ import annotations

import numpy as np

HOP_S = 0.02


def envelope_db(x: np.ndarray, sr: int, hop_s: float = HOP_S) -> np.ndarray:
    """Livello (dB, rispetto al fondo scala) a finestre di `hop_s` secondi."""
    n = max(1, int(sr * hop_s))
    m = len(x) // n
    if m == 0:
        return np.full(1, -100.0, dtype=np.float32)
    r = np.sqrt(np.mean(np.square(x[:m * n].reshape(m, n).astype(np.float32)), axis=1) + 1e-12)
    return (20 * np.log10(r + 1e-9)).astype(np.float32)


def silence_ranges(x: np.ndarray, sr: int, rel_db: float = 35.0, min_len: float = 0.7, pad: float = 0.15,
                   hop_s: float = HOP_S) -> list[tuple[float, float]]:
    """Pause da togliere. Silenzio = più di `rel_db` dB sotto il livello tipico del parlato (95° percentile);
    si toglie solo se dura almeno `min_len` s, e si lasciano `pad` s di margine su entrambi i lati."""
    env = envelope_db(x, sr, hop_s)
    if len(env) < 3:
        return []
    ref = float(np.percentile(env, 95))
    quiet = env < max(ref - rel_db, -80.0)
    out, i, n = [], 0, len(quiet)
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        a, b = i * hop_s + pad, j * hop_s - pad
        if b - a >= max(min_len - 2 * pad, 0.05):
            out.append((a, b))
        i = j
    return out


def keep_from_removed(total: float, removed: list[tuple[float, float]], min_keep: float = 0.15) -> list[list[float]]:
    """Intervalli tenuti = tutto meno i tolti (ordinati, senza pezzi troppo corti)."""
    keep, pos = [], 0.0
    for a, b in sorted(removed):
        a, b = max(0.0, a), min(total, b)
        if a > pos:
            keep.append([pos, a])
        pos = max(pos, b)
    if pos < total:
        keep.append([pos, total])
    return [[round(a, 3), round(b, 3)] for a, b in keep if b - a >= min_keep]


def removed_from_keep(total: float, keep: list[list[float]]) -> list[tuple[float, float]]:
    if not keep:
        return []
    out, pos = [], 0.0
    for a, b in sorted(keep):
        if a > pos + 1e-6:
            out.append((pos, a))
        pos = max(pos, b)
    if pos < total - 1e-6:
        out.append((pos, total))
    return out


def remove_range(keep: list[list[float]], total: float, a: float, b: float) -> list[list[float]]:
    """Toglie [a, b] dal montaggio (`keep` vuoto = tutto tenuto)."""
    cur = keep or [[0.0, total]]
    removed = removed_from_keep(total, cur) + [(min(a, b), max(a, b))]
    return keep_from_removed(total, _merge(removed))


def restore_range(keep: list[list[float]], total: float, a: float, b: float) -> list[list[float]]:
    """Rimette [a, b]: toglie quell'intervallo dai pezzi rimossi."""
    cur = keep or [[0.0, total]]
    lo, hi = min(a, b), max(a, b)
    removed = []
    for x, y in removed_from_keep(total, cur):
        if y <= lo or x >= hi:
            removed.append((x, y))
        else:
            if x < lo:
                removed.append((x, lo))
            if y > hi:
                removed.append((hi, y))
    return [] if not removed else keep_from_removed(total, removed)


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def kept_duration(keep: list[list[float]], total: float) -> float:
    return sum(b - a for a, b in keep) if keep else total
