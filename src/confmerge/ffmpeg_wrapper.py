"""Accesso a ffmpeg/ffprobe: ricerca binari, probe, decodifica audio, esecuzione con progresso."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from . import paths

log = logging.getLogger(__name__)

_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class FFmpegError(RuntimeError):
    """Errore ffmpeg/ffprobe con messaggio leggibile."""


class Cancelled(Exception):
    """Operazione annullata dall'utente."""


def _find(name: str) -> str:
    exe = name + (".exe" if sys.platform == "win32" else "")
    candidate = paths.bin_dir() / exe
    if candidate.exists():
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise FFmpegError(
        f"{exe} non trovato. Copia ffmpeg.exe e ffprobe.exe nella cartella 'bin' accanto all'applicazione."
    )


def ffmpeg_path() -> str:
    return _find("ffmpeg")


def ffprobe_path() -> str:
    return _find("ffprobe")


def probe(path: str | Path) -> dict:
    cmd = [ffprobe_path(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    res = subprocess.run(cmd, capture_output=True, creationflags=_CREATIONFLAGS)
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", "replace").strip()
        raise FFmpegError(f"Impossibile leggere «{Path(path).name}»: {err or 'file non valido'}")
    return json.loads(res.stdout.decode("utf-8", "replace"))


def keyframe_times(path: str | Path) -> list[float]:
    """Tempi (s) dei fotogrammi chiave del primo stream video, ordinati."""
    cmd = [
        ffprobe_path(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, creationflags=_CREATIONFLAGS)
    if res.returncode != 0:
        raise FFmpegError(f"Impossibile leggere i keyframe di «{Path(path).name}»")
    times = []
    for line in res.stdout.decode().splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 2 and "K" in parts[1] and parts[0] not in ("", "N/A"):
            times.append(float(parts[0]))
    return sorted(times)


def decode_audio_mono(path: str | Path, sr: int = 8000, expected_s: float | None = None) -> np.ndarray:
    """Decodifica l'audio in mono float32 a `sr` Hz. Se `expected_s` è dato, pad/taglia a quella durata."""
    cmd = [
        ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(path),
        "-vn", "-map", "0:a:0?", "-ac", "1", "-ar", str(sr), "-f", "s16le", "pipe:1",
    ]
    res = subprocess.run(cmd, capture_output=True, creationflags=_CREATIONFLAGS)
    if res.returncode != 0:
        raise FFmpegError(f"Impossibile estrarre l'audio da «{Path(path).name}»: {res.stderr.decode('utf-8', 'replace').strip()}")
    data = np.frombuffer(res.stdout, dtype="<i2").astype(np.float32) / 32768.0
    if expected_s is not None:
        n = int(round(expected_s * sr))
        if len(data) < n:
            data = np.concatenate([data, np.zeros(n - len(data), dtype=np.float32)])
        else:
            data = data[:n]
    return data


def run_ffmpeg(
    args: Sequence[str],
    total_duration: float | None = None,
    on_progress: Callable[[float, float | None], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Esegue ffmpeg. `on_progress(frazione, velocità_x)`; solleva Cancelled/FFmpegError."""
    cmd = [ffmpeg_path(), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *map(str, args)]
    log.info("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", creationflags=_CREATIONFLAGS,
    )
    tail: deque[str] = deque(maxlen=40)

    def drain():
        for line in proc.stderr:  # type: ignore[union-attr]
            tail.append(line.rstrip())

    t = threading.Thread(target=drain, daemon=True)
    t.start()
    speed: float | None = None
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if cancel is not None and cancel.is_set():
                proc.terminate()
                proc.wait()
                raise Cancelled()
            key, _, val = line.strip().partition("=")
            if key == "speed":
                try:
                    speed = float(val.rstrip("x"))
                except ValueError:
                    pass
            elif key == "out_time_us" and on_progress and total_duration:
                try:
                    frac = min(1.0, max(0.0, int(val) / 1e6 / total_duration))
                except ValueError:
                    continue
                on_progress(frac, speed)
        proc.wait()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        raise
    finally:
        t.join(timeout=2)
    if proc.returncode != 0:
        msg = "\n".join(tail)
        log.error("ffmpeg fallito (%s):\n%s", proc.returncode, msg)
        raise FFmpegError("ffmpeg ha terminato con errore:\n" + "\n".join(list(tail)[-8:]))
    if on_progress:
        on_progress(1.0, speed)
