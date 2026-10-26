"""File di progetto (.confmerge, JSON): clip, audio, offset, trim."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT_VERSION = 1


@dataclass
class Project:
    clips: list[str] = field(default_factory=list)       # in ordine di montaggio
    audio: str = ""
    total_duration: float = 0.0                          # durata del video unito
    offset_s: float = 0.0                                # esterno(t) ≈ camera(t + offset)
    sync_confidence: float = 0.0
    drift_s: float | None = None
    atempo: float = 1.0
    offset_corrected_s: float | None = None
    use_drift_correction: bool = False
    suggested_start: float | None = None                 # suggerimenti: MAI applicati senza conferma
    suggested_end: float | None = None
    trim_start: float | None = None                      # confermati dall'utente
    trim_end: float | None = None
    trim_confirmed: bool = False                         # l'utente ha confermato esplicitamente il taglio (o «tengo tutto»)
    spec: dict = field(default_factory=dict)             # RenderSpec serializzata (grafica, slide, immagine…)
    thumbnail: dict = field(default_factory=dict)
    profile_name: str = ""
    version: int = FORMAT_VERSION

    @property
    def effective_offset(self) -> float:
        if self.use_drift_correction and self.offset_corrected_s is not None:
            return self.offset_corrected_s
        return self.offset_s

    @property
    def effective_atempo(self) -> float:
        return self.atempo if self.use_drift_correction else 1.0

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
