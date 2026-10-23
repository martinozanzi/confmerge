"""Sincronizzazione audio camera / audio esterno con GCC-PHAT e stima della deriva dei clock.

Convenzione: `offset_s` = d tale che  esterno(t) ≈ camera(t + d).
  d > 0  → l'audio esterno parte DOPO l'inizio del video (si riempie l'inizio con silenzio)
  d < 0  → l'audio esterno parte PRIMA (si scarta la parte iniziale)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft

SR = 8000
BAND_HZ = (100.0, 3400.0)
LOW_CONFIDENCE_Z = 7.0       # sotto questa soglia l'offset è inaffidabile
DRIFT_WARN_S = 0.050         # deriva totale oltre la quale si propone atempo
DRIFT_WINDOW_S = 120.0
DRIFT_MARGIN_S = 10.0
DRIFT_MIN_SPAN_S = 4 * DRIFT_WINDOW_S


@dataclass
class SyncResult:
    offset_s: float
    confidence: float
    drift_s: float | None = None          # d_fine - d_inizio
    drift_span_s: float | None = None
    atempo: float = 1.0                   # fattore suggerito per l'audio esterno
    offset_corrected_s: float | None = None  # offset effettivo se si applica atempo

    @property
    def low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_Z

    @property
    def drift_significant(self) -> bool:
        return self.drift_s is not None and abs(self.drift_s) > DRIFT_WARN_S


def gcc_phat(cam: np.ndarray, ext: np.ndarray, fs: int = SR) -> tuple[float, float]:
    """Ritardo d (s) che massimizza la correlazione cam[n+d] ~ ext[n], e confidenza (z-score del picco)."""
    na, nb = len(cam), len(ext)
    if na < fs or nb < fs:
        raise ValueError("Audio troppo corto per la sincronizzazione")
    nfft = sfft.next_fast_len(na + nb, real=True)
    A = sfft.rfft(cam.astype(np.float32), nfft)
    B = sfft.rfft(ext.astype(np.float32), nfft)
    R = A * np.conj(B)
    mag = np.abs(R)
    R = R / (mag + 1e-3 * float(mag.mean()) + 1e-20)
    freqs = sfft.rfftfreq(nfft, 1.0 / fs)
    R[(freqs < BAND_HZ[0]) | (freqs > BAND_HZ[1])] = 0
    cc = sfft.irfft(R, nfft)
    # lag validi: da -(nb-1) a +(na-1)
    full = np.concatenate([cc[nfft - (nb - 1):], cc[:na]])
    k0 = -(nb - 1)
    i = int(np.argmax(full))
    std = float(full.std())
    z = (float(full[i]) - float(full.mean())) / std if std > 0 else 0.0
    frac = 0.0
    if 0 < i < len(full) - 1:  # interpolazione parabolica sub-campione
        y0, y1, y2 = full[i - 1], full[i], full[i + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            frac = float(0.5 * (y0 - y2) / den)
    return (k0 + i + frac) / fs, z


def _local_offset(cam, ext, a_s, win_s, d0, margin_s, fs=SR) -> tuple[float, float]:
    """Offset misurato su una finestra di camera [a_s, a_s+win_s] contro la porzione attesa di esterno."""
    a, w = int(a_s * fs), int(win_s * fs)
    seg = cam[a:a + w]
    e0 = max(0, int((a_s - d0 - margin_s) * fs))
    e1 = min(len(ext), int((a_s - d0 + win_s + margin_s) * fs))
    sl = ext[e0:e1]
    k, z = gcc_phat(seg, sl, fs)
    return k + a_s - e0 / fs, z


def estimate_drift(cam, ext, d0, fs=SR, window_s=DRIFT_WINDOW_S, margin_s=DRIFT_MARGIN_S,
                   min_span_s=DRIFT_MIN_SPAN_S):
    """Restituisce (drift_s, span_s, atempo, offset_corretto, z_min) oppure None se non misurabile."""
    lo = max(0.0, d0)
    hi = min(len(cam) / fs, d0 + len(ext) / fs)
    if hi - lo < max(min_span_s, 2 * window_s):
        return None
    a1, a2 = lo, hi - window_s
    d1, z1 = _local_offset(cam, ext, a1, window_s, d0, margin_s, fs)
    d2, z2 = _local_offset(cam, ext, a2, window_s, d0, margin_s, fs)
    if min(z1, z2) < LOW_CONFIDENCE_Z:
        return None
    span = a2 - a1
    drift = d2 - d1
    s = 1.0 - drift / span
    c = d1 - drift * a1 / span
    return drift, span, s, c / s, min(z1, z2)


def analyze_sync(cam: np.ndarray, ext: np.ndarray, fs: int = SR, check_drift: bool = True) -> SyncResult:
    d0, z = gcc_phat(cam, ext, fs)
    res = SyncResult(offset_s=d0, confidence=z)
    if check_drift:
        # la deriva spalma il picco globale: la misura sulle due finestre ne conferma l'affidabilità
        dr = estimate_drift(cam, ext, d0, fs)
        if dr is not None:
            res.drift_s, res.drift_span_s, res.atempo, res.offset_corrected_s, zw = dr
            res.confidence = max(res.confidence, zw)
    return res


def place_on_timeline(ext: np.ndarray, d: float, n_out: int, fs: int = SR) -> np.ndarray:
    """Posiziona l'audio esterno sulla linea temporale della camera (silenzio dove manca)."""
    out = np.zeros(n_out, dtype=np.float32)
    start = int(round(d * fs))
    src0 = max(0, -start)
    dst0 = max(0, start)
    n = min(len(ext) - src0, n_out - dst0)
    if n > 0:
        out[dst0:dst0 + n] = ext[src0:src0 + n]
    return out
