"""Registrazione audio divisa in più file (il registratore spezza i file lunghi): si riconosce dal nome e si mettono a seguire.

Basta sincronizzare l'inizio del primo file con il video: gli altri seguono nell'ordine, come i video. Se i file sono solo alternative
della stessa registrazione (stesso nome, formato diverso) se ne usa uno."""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Callable

from . import ffmpeg_wrapper as fw
from .media_scan import _natural_key, pick_external_audio

PREFERRED_EXT = (".wav", ".flac", ".m4a", ".mp3", ".ogg")           # a parità di nome si tiene il formato migliore


def _skeleton(p: Path) -> str:
    """Il nome senza i numeri: «REC_001» e «REC_002», o due date, hanno lo stesso scheletro."""
    return re.sub(r"\d+", "#", p.stem.lower()).strip()


def audio_parts(audios: list[Path]) -> list[Path]:
    """Le parti della registrazione, in ordine. Con un solo file, o con file che non sembrano parti, restituisce [il più lungo]."""
    uniq: dict[str, Path] = {}
    for p in audios:                                                    # stesso nome, formati diversi: uno solo
        best = uniq.get(p.stem.lower())
        rank = lambda q: PREFERRED_EXT.index(q.suffix.lower()) if q.suffix.lower() in PREFERRED_EXT else 99   # noqa: E731
        if best is None or rank(p) < rank(best):
            uniq[p.stem.lower()] = p
    files = list(uniq.values())
    if len(files) <= 1:
        return files
    groups: dict[str, list[Path]] = {}
    for p in files:
        groups.setdefault(_skeleton(p), []).append(p)
    series = [g for g in groups.values() if len(g) > 1]                 # REC_001, REC_002… oppure 20260501_101500, 20260501_113000…
    if series:
        biggest = max(series, key=lambda g: sum(q.stat().st_size for q in g))      # un altro file (sigla, jingle) non è una parte
        return sorted(biggest, key=_natural_key)
    best = pick_external_audio(files)
    return [best] if best else files[:1]


def merged_path(parts: list[Path], workdir: Path) -> Path:
    """Dove sta il file unito: dipende da quali file sono (nome, dimensione, data), così si riusa se non cambia nulla."""
    h = hashlib.sha1()
    for p in parts:
        st = p.stat()
        h.update(f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode())
    return workdir / f"audio_unito_{h.hexdigest()[:12]}.flac"


def ensure_project_audio(p, cancel: threading.Event | None = None) -> None:
    """Un progetto con la registrazione divisa in più file: se il file unito non c'è più (cartella temporanea pulita) lo rifà."""
    from . import paths
    audios = [Path(a) for a in getattr(p, "audios", []) or []]
    if len(audios) > 1 and (not p.audio or not Path(p.audio).exists()):
        p.audio = str(ensure_merged(audios, merged_path(audios, paths.temp_dir()), cancel))


def _channels(p: Path) -> int:
    try:
        for s in fw.probe(p).get("streams", []):
            if s.get("codec_type") == "audio":
                return int(s.get("channels") or 1)
    except Exception:  # noqa: BLE001 - se non si legge, si lavora in stereo
        return 2
    return 1


def ensure_merged(parts: list[Path], out: Path, cancel: threading.Event | None = None,
                  progress: Callable[[float, float | None], None] | None = None) -> Path:
    """Mette le parti una dopo l'altra in un solo file FLAC (senza perdite). Se esiste già non rifà nulla."""
    if out.exists() and out.stat().st_size > 1000:
        return out
    from .media_scan import media_info
    total = sum(media_info(p).duration for p in parts)
    ch = 2 if any(_channels(p) > 1 for p in parts) else 1
    layout = "stereo" if ch == 2 else "mono"
    args: list[str] = []
    for p in parts:
        args += ["-i", str(p)]
    chain = ";".join(f"[{i}:a:0]aresample=48000,aformat=sample_fmts=s16:channel_layouts={layout}[a{i}]" for i in range(len(parts)))
    chain += ";" + "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]"
    tmp = out.with_suffix(".part.flac")
    args += ["-filter_complex", chain, "-map", "[out]", "-c:a", "flac", "-compression_level", "2", str(tmp)]
    out.parent.mkdir(parents=True, exist_ok=True)
    fw.run_ffmpeg(args, total, progress, cancel)
    tmp.replace(out)
    return out
