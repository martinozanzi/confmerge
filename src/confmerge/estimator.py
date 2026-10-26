"""Stima di tempo e dimensione dell'export."""
from __future__ import annotations

from dataclasses import dataclass

OVERHEAD = 0.015  # contenitore MP4 (~1-2%)


@dataclass
class SizeEstimate:
    low: float
    high: float
    exact: bool

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2


def size_from_bitrate(video_bps: float, audio_bps: float, duration_s: float, overhead: float = OVERHEAD) -> SizeEstimate:
    """Bitrate target: (video+audio) x durata + overhead. Stima precisa (±0,5%)."""
    b = (video_bps + audio_bps) * duration_s / 8 * (1 + overhead)
    return SizeEstimate(b * 0.995, b * 1.005, True)


def size_from_sample(sample_bytes: float, sample_s: float, audio_bps: float, duration_s: float) -> SizeEstimate:
    """CRF: estrapola dal bitrate misurato sul campione; intervallo largo (±25%)."""
    vbps = max(0.0, sample_bytes * 8 / max(sample_s, 1e-6) - audio_bps)
    mid = (vbps + audio_bps) * duration_s / 8 * (1 + OVERHEAD)
    return SizeEstimate(mid * 0.75, mid * 1.25, False)


def size_copy(total_bytes: float, total_s: float, kept_s: float, audio_bps: float = 192_000) -> SizeEstimate:
    """Copia stream: dimensione proporzionale alla parte tenuta (video originale; audio ricodificato)."""
    b = total_bytes * (kept_s / max(total_s, 1e-6))
    return SizeEstimate(b * 0.9, b * 1.1, False)


@dataclass
class TimeParts:
    main_s: float           # tempo di codifica del video principale
    loudnorm_s: float = 0.0
    segments_s: float = 0.0  # titolo / outro / credito
    animated_s: float = 0.0
    drift_s: float = 0.0

    @property
    def total(self) -> float:
        return self.main_s + self.loudnorm_s + self.segments_s + self.animated_s + self.drift_s


def estimate_time(duration_s: float, speed_x: float, parts_extra: TimeParts | None = None,
                  correction: float = 1.0, spread: float = 0.2) -> tuple[float, float]:
    """Intervallo (min, max) in secondi. `speed_x` = multiplo del tempo reale misurato sul campione."""
    if speed_x <= 0:
        raise ValueError("velocità non valida")
    main = duration_s / speed_x
    extra = 0.0
    if parts_extra:
        extra = parts_extra.loudnorm_s + parts_extra.segments_s + parts_extra.animated_s + parts_extra.drift_s
    mid = (main + extra) * correction
    return mid * (1 - spread), mid * (1 + spread)


def format_range(lo_s: float, hi_s: float) -> str:
    def m(s):
        return max(1, round(s / 60))
    a, b = m(lo_s), m(hi_s)
    if lo_s < 90 and hi_s < 90:
        return f"circa {round(lo_s)}-{round(hi_s)} s"
    return f"circa {a} min" if a == b else f"circa {a}-{b} min"


def format_size(b: float) -> str:
    return f"{b / 1e9:.2f} GB" if b >= 1e9 else f"{b / 1e6:.0f} MB"


class MovingSpeed:
    """Media mobile della velocità reale per il tempo residuo."""

    def __init__(self, n: int = 8):
        self.n = n
        self.samples: list[tuple[float, float]] = []  # (t_wall, frac)

    def add(self, t_wall: float, frac: float) -> None:
        self.samples.append((t_wall, frac))
        self.samples = self.samples[-self.n:]

    def remaining(self, frac: float) -> float | None:
        if len(self.samples) < 2:
            return None
        (t0, f0), (t1, f1) = self.samples[0], self.samples[-1]
        if f1 <= f0 or t1 <= t0:
            return None
        return (1 - frac) * (t1 - t0) / (f1 - f0)


def update_correction(corr: dict, encoder: str, estimated_s: float, actual_s: float, alpha: float = 0.4) -> None:
    """Salva lo scarto (reale/stimato) per-encoder con media esponenziale."""
    if estimated_s <= 0 or actual_s <= 0:
        return
    ratio = actual_s / estimated_s
    old = corr.get(encoder, 1.0)
    corr[encoder] = round((1 - alpha) * old + alpha * ratio, 4)
