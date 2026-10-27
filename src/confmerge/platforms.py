"""Piattaforme per Studio Social: formato, durata massima e zone coperte dall'interfaccia (safe zone).

Le misure sono approssimative e cambiano nel tempo: vanno verificate sulle indicazioni ufficiali di ogni piattaforma.
Si possono correggere senza toccare il codice: basta un file `piattaforme.json` nella cartella delle impostazioni, per
esempio {"tiktok": {"max_s": 600, "safe": [0.12, 0.25, 0.04, 0.14]}} (margini sopra, sotto, sinistra, destra: frazioni)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from .spec import RenderSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    aspect: str                              # "16:9" | "9:16" | "1:1"
    short: int = 1080                        # lato corto in pixel
    max_s: float | None = None               # durata massima consigliata (None = nessun limite pratico)
    safe: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)   # sopra, sotto, sinistra, destra (frazioni)
    note: str = ""


PLATFORMS: list[Platform] = [
    Platform("youtube", "YouTube", "16:9", 1080, None, note="Video orizzontale completo."),
    Platform("shorts", "YouTube Shorts", "9:16", 1080, 180, (0.10, 0.20, 0.04, 0.14), "Verticale, fino a 3 minuti."),
    Platform("reels", "Instagram Reel", "9:16", 1080, 180, (0.12, 0.22, 0.04, 0.12), "Verticale, fino a 3 minuti."),
    Platform("tiktok", "TikTok", "9:16", 1080, 600, (0.12, 0.25, 0.04, 0.14), "Verticale, la didascalia copre il basso."),
    Platform("threads", "Threads", "9:16", 1080, 300, (0.10, 0.16, 0.04, 0.10), "Verticale, fino a 5 minuti."),
    Platform("instagram", "Instagram quadrato", "1:1", 1080, 60, (0.04, 0.08, 0.04, 0.04), "Quadrato per il feed."),
    Platform("x", "X", "16:9", 720, 140, note="Orizzontale, 2 min 20 s per gli account normali."),
]
BY_ID = {p.id: p for p in PLATFORMS}


def _user_overrides(root: Path | None) -> dict:
    if root is None:
        return {}
    try:
        return json.loads((Path(root) / "piattaforme.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def all_platforms(root: Path | None = None) -> list[Platform]:
    """Elenco con le eventuali correzioni dell'utente (file `piattaforme.json`)."""
    over = _user_overrides(root)
    out = []
    for p in PLATFORMS:
        o = over.get(p.id)
        if isinstance(o, dict):
            try:
                kw = {k: (tuple(v) if k == "safe" else v) for k, v in o.items() if k in ("name", "aspect", "short", "max_s", "safe", "note")}
                p = replace(p, **kw)
            except (TypeError, ValueError):
                log.warning("Correzione non valida per la piattaforma %s", p.id)
        out.append(p)
    return out


def get(pid: str, root: Path | None = None) -> Platform:
    return next((p for p in all_platforms(root) if p.id == pid), BY_ID["youtube"])


def common_safe(selected: list[Platform]) -> tuple[float, float, float, float]:
    """Zona sicura comune: per ogni lato il margine più grande tra le piattaforme scelte con lo stesso formato."""
    if not selected:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(max(p.safe[i] for p in selected) for i in range(4))   # type: ignore[return-value]


def variant_spec(base: RenderSpec, p: Platform) -> RenderSpec:
    """Copia della spec con formato e posizione dei sottotitoli adatti alla piattaforma."""
    s = RenderSpec.from_dict(base.to_dict())
    s.image.aspect = p.aspect
    s.image.kenburns = False
    s.export.preset, s.export.custom_height = "Personalizzato", p.short
    top, bottom = p.safe[0], p.safe[1]
    sub = s.subtitles
    if sub.position == "bottom":
        sub.margin = max(sub.margin, bottom + 0.02)
    elif sub.position == "top":
        sub.margin = max(sub.margin, top + 0.02)
    return s


def duration_warning(p: Platform, seconds: float) -> str:
    if p.max_s and seconds > p.max_s + 0.5:
        return (f"{p.name}: il video dura {_mmss(seconds)} ma il limite indicativo è {_mmss(p.max_s)}. "
                "Accorcialo oppure pubblicalo comunque se il tuo account lo permette.")
    return ""


def _mmss(t: float) -> str:
    t = int(round(t))
    return f"{t // 60}:{t % 60:02d}"
