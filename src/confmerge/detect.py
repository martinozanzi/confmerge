"""Che lavoro è? Guarda i file scelti e decide se è una conferenza (video + registrazione audio a parte) o un video social.

Regola semplice e prevedibile: se fra i file c'è una registrazione audio (mp3, wav, m4a…) è una conferenza da unire e sincronizzare;
altrimenti sono clip con il loro audio da tagliare per i social. L'utente può sempre cambiare dall'alto."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .media_scan import AUDIO_EXT, SLIDE_EXT, VIDEO_EXT


@dataclass
class Detection:
    kind: str                                   # "merge" | "social" | "" (niente di utilizzabile)
    videos: list[Path] = field(default_factory=list)
    audio: Path | None = None
    slides: list[Path] = field(default_factory=list)
    folder: Path | None = None
    reason: str = ""                            # frase per l'utente: perché è stato scelto
    sources: list[Path] = field(default_factory=list)      # quello che l'utente aveva scelto (file o cartelle), da conservare


def expand(items) -> tuple[list[Path], Path | None]:
    """File singoli dalle voci scelte (le cartelle si leggono, non in profondità). Restituisce anche la prima cartella."""
    files: list[Path] = []
    folder: Path | None = None
    for it in items:
        p = Path(it)
        if p.is_dir():
            folder = folder or p
            files += sorted(f for f in p.iterdir() if f.is_file())
        elif p.is_file():
            files.append(p)
    return files, folder


def classify(items) -> Detection:
    items = [Path(i) for i in items]
    files, folder = expand(items)
    videos = [f for f in files if f.suffix.lower() in VIDEO_EXT]
    audios = [f for f in files if f.suffix.lower() in AUDIO_EXT]
    slides = [f for f in files if f.suffix.lower() in SLIDE_EXT]
    if not videos:
        return Detection("", audio=audios[0] if audios else None, slides=slides, folder=folder, sources=items,
                         reason="Non ho trovato video (file .mp4, .mov o .m4v).")
    n = len(videos)
    quanti = "un video" if n == 1 else f"{n} video"
    if audios:
        return Detection("merge", videos, audios[0], slides, folder, f"Ho trovato {quanti} e una registrazione audio: sembra una "
                         "conferenza da unire e sincronizzare.", items)
    return Detection("social", videos, None, slides, folder, f"Ho trovato {quanti} con {'il suo' if n == 1 else 'il loro'} audio: "
                     "li preparo per i social. (Se hai anche una registrazione audio a parte, trascinala insieme ai video.)", items)
