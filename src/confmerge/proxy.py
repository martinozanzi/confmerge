"""Proxy 480p H.264 con audio esterno già allineato; anteprima di sincronia."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from . import paths
from .ffmpeg_wrapper import run_ffmpeg
from .media_scan import MediaInfo
from .pipeline import audio_filter, plan_segments
from .project import Project

PROXY_H = 480


def proxy_size(clips: list[MediaInfo]) -> tuple[int, int]:
    ref = clips[0]
    w = round(PROXY_H * ref.width / max(ref.height, 1) / 2) * 2
    return max(2, w), PROXY_H


def build_proxy(p: Project, clips: list[MediaInfo], out: Path,
                on_progress: Callable[[float, float | None], None] | None = None,
                cancel: threading.Event | None = None) -> Path:
    """Video intero (linea temporale completa) a bassa risoluzione, con l'audio esterno allineato (offset in uso)."""
    w, h = proxy_size(clips)
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c.path)]
    args += ["-i", p.audio]
    n = len(clips)
    ch = [f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
          f"fps=25,setsar=1,format=yuv420p[v{i}]" for i in range(n)]
    ch.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
    ch.append(f"[{n}:a:0]{audio_filter(p, 0.0)},atrim=end={p.total_duration:.3f},aformat=channel_layouts=stereo[a]")
    args += ["-filter_complex", ";".join(ch), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
             "-crf", "28", "-pix_fmt", "yuv420p", "-g", "25", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
             str(out)]
    run_ffmpeg(args, p.total_duration, on_progress, cancel)
    return out


def sync_preview(p: Project, clips: list[MediaInfo], center: float, out: Path, span: float = 10.0) -> Path:
    """Audio camera + audio esterno sovrapposti (centro/centro): se non sono allineati si sente l'eco."""
    t0 = max(0.0, min(center - span / 2, p.total_duration - span))
    seg = plan_segments(clips, t0, t0 + span)[0]
    t_in = seg.ss
    length = min(span, seg.length)
    args = ["-ss", f"{t_in:.3f}", "-t", f"{length:.3f}", "-i", str(seg.clip.path), "-i", p.audio]
    start = t0
    fc = (f"[0:a:0]aformat=channel_layouts=mono,aresample=44100,volume=0.8[c];"
          f"[1:a:0]{audio_filter(p, start)},atrim=end={length:.3f},aformat=channel_layouts=mono,aresample=44100,volume=0.8[e];"
          f"[c][e]amix=inputs=2:normalize=0,atrim=end={length:.3f}[o]")
    run_ffmpeg([*args, "-filter_complex", fc, "-map", "[o]", "-c:a", "pcm_s16le", str(out)], length)
    return out


def rebuild_audio(p: Project, proxy_in: Path, out: Path, cancel: threading.Event | None = None) -> Path:
    """Dopo un cambio di offset: rifà solo l'audio del proxy (il video viene copiato: operazione rapida)."""
    args = ["-i", str(proxy_in), "-i", p.audio, "-filter_complex",
            f"[1:a:0]{audio_filter(p, 0.0)},atrim=end={p.total_duration:.3f},aformat=channel_layouts=stereo[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    run_ffmpeg(args, p.total_duration, None, cancel)
    return out
