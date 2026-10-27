"""Studio Social, parte di calcolo: progetto senza audio esterno, forma d'onda, anteprima e ricerca dei silenzi.

Si lavora su uno o più video con il loro audio. Il montaggio è l'elenco `Project.keep` degli intervalli da tenere
(vuoto = tutto). Il file finale si costruisce con lo stesso motore di Merge Conferenze (graph.build)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import numpy as np

from . import cuts
from .ffmpeg_wrapper import decode_audio_mono, run_ffmpeg
from .media_scan import MediaInfo, _natural_key, media_info
from .project import Project

CAM_SR = 8000
PROXY_H = 360


def load_clips(paths: list[str | Path], cancel: threading.Event | None = None) -> list[MediaInfo]:
    """Legge i metadati. L'ordine è quello scelto dall'utente; se arriva da una cartella si ordina per nome."""
    clips = []
    for p in paths:
        if cancel is not None and cancel.is_set():
            break
        info = media_info(p)
        if not info.has_video:
            raise ValueError(f"«{Path(p).name}» non contiene video.")
        clips.append(info)
    return clips


def sort_by_name(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=_natural_key)


def new_project(clips: list[MediaInfo]) -> Project:
    return Project(clips=[str(c.path) for c in clips], audio="", total_duration=sum(c.duration for c in clips),
                   kind="social", trim_confirmed=True)


def decode_waveform(clips: list[MediaInfo], sr: int = CAM_SR) -> np.ndarray:
    """Audio di tutte le clip, una dopo l'altra (mono). Le clip senza audio contano come silenzio."""
    parts = []
    for c in clips:
        if c.has_audio:
            parts.append(decode_audio_mono(c.path, sr, c.duration))
        else:
            parts.append(np.zeros(int(c.duration * sr), np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, np.float32)


def proxy_size(clips: list[MediaInfo]) -> tuple[int, int]:
    ref = clips[0]
    w = round(PROXY_H * ref.width / max(ref.height, 1) / 2) * 2
    return max(2, w), PROXY_H


def build_preview(clips: list[MediaInfo], out: Path, on_progress: Callable[[float, float | None], None] | None = None,
                  cancel: threading.Event | None = None) -> Path:
    """Anteprima 360p di tutto il materiale, con l'audio delle clip (nessun taglio: i tagli si saltano in riproduzione)."""
    w, h = proxy_size(clips)
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c.path)]
    ch = []
    for i, c in enumerate(clips):
        ch.append(f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                  f"fps=25,setsar=1,format=yuv420p,trim=duration={c.duration:.3f},setpts=PTS-STARTPTS[v{i}]")
        if c.has_audio:
            ch.append(f"[{i}:a:0]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,apad=whole_dur={c.duration:.3f},"
                      f"atrim=end={c.duration:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            ch.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={c.duration:.3f},asetpts=PTS-STARTPTS[a{i}]")
    n = len(clips)
    ch.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
    total = sum(c.duration for c in clips)
    args += ["-filter_complex", ";".join(ch), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
             "-tune", "fastdecode", "-crf", "30", "-pix_fmt", "yuv420p", "-g", "25", "-c:a", "aac", "-b:a", "96k",
             "-movflags", "+faststart", str(out)]
    run_ffmpeg(args, total, on_progress, cancel)
    return out


def find_silences(cam: np.ndarray, total: float, rel_db: float, min_len: float, pad: float) -> list[tuple[float, float]]:
    return cuts.silence_ranges(cam, CAM_SR, rel_db, min_len, pad)
