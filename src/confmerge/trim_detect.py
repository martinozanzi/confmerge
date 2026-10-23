"""Suggerimento di inizio/fine: energia RMS a finestre da 1 s + rilevamento del parlato."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SUSTAINED_S = 10      # durata minima del parlato "sostenuto"
MIN_ACTIVE_RATIO = 0.7  # quota minima di secondi attivi nella finestra (poche pause)
PAD_S = 5.0


@dataclass
class TrimSuggestion:
    start_s: float
    end_s: float
    found: bool
    method: str


def _rms_db(audio: np.ndarray, sr: int) -> np.ndarray:
    n = len(audio) // sr
    if n == 0:
        return np.zeros(0)
    x = audio[: n * sr].reshape(n, sr).astype(np.float64)
    rms = np.sqrt((x ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-7))


def _vad_ratio(audio: np.ndarray, sr: int) -> np.ndarray | None:
    """Quota di frame da 30 ms con parlato per ogni secondo, o None se webrtcvad non è disponibile."""
    try:
        import webrtcvad  # type: ignore
    except Exception:
        return None
    if sr not in (8000, 16000, 32000, 48000):
        return None
    vad = webrtcvad.Vad(2)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    fl = int(sr * 0.03)
    n = len(pcm) // sr
    out = np.zeros(n)
    for s in range(n):
        seg = pcm[s * sr:(s + 1) * sr]
        frames = [seg[i:i + fl] for i in range(0, len(seg) - fl + 1, fl)]
        out[s] = sum(vad.is_speech(f.tobytes(), sr) for f in frames) / max(1, len(frames))
    return out


def activity_per_second(audio: np.ndarray, sr: int) -> tuple[np.ndarray, str]:
    """Vettore booleano (1 valore/secondo): c'è parlato? e il metodo usato."""
    db = _rms_db(audio, sr)
    if len(db) == 0:
        return np.zeros(0, dtype=bool), "vuoto"
    floor, p90 = np.percentile(db, 10), np.percentile(db, 90)
    if p90 - floor < 6.0:  # dinamica troppo piatta: niente parlato distinguibile
        return np.zeros(len(db), dtype=bool), "soglia adattiva"
    thr = floor + max(6.0, 0.35 * (p90 - floor))
    energetic = db > thr
    ratio = _vad_ratio(audio, sr)
    if ratio is not None:
        return energetic & (ratio >= 0.3), "webrtcvad + RMS"
    return energetic, "soglia adattiva RMS"


def suggest_trim(audio: np.ndarray, sr: int, total_s: float | None = None) -> TrimSuggestion:
    """Inizio = primo parlato sostenuto − 5 s; fine = ultimo parlato sostenuto + 5 s."""
    total = total_s if total_s is not None else len(audio) / sr
    active, method = activity_per_second(audio, sr)
    n, w = len(active), SUSTAINED_S
    if n < w:
        return TrimSuggestion(0.0, total, False, method)
    csum = np.concatenate([[0], np.cumsum(active.astype(int))])
    win = csum[w:] - csum[:-w]  # win[i] = secondi attivi in [i, i+w)
    ok = np.flatnonzero(win >= MIN_ACTIVE_RATIO * w)
    if len(ok) == 0:
        return TrimSuggestion(0.0, total, False, method)
    first = int(ok[0])
    last = int(ok[-1]) + w
    # affina: il parlato inizia al primo secondo attivo della prima finestra, finisce all'ultimo dell'ultima
    first += int(np.argmax(active[first:first + w]))
    last = first + 1 if last <= first else last
    while last > first and not active[last - 1]:
        last -= 1
    return TrimSuggestion(max(0.0, first - PAD_S), min(total, last + PAD_S), True, method)
