"""Orchestrazione: analisi (scan + sync + trim) ed export (copia stream o ricodifica)."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import paths, sync, trim_detect
from .ffmpeg_wrapper import Cancelled, FFmpegError, decode_audio_mono, keyframe_times, run_ffmpeg
from .media_scan import GapWarning, MediaInfo, find_gaps, media_info, order_clips
from .project import Project

log = logging.getLogger(__name__)

Progress = Callable[[str, float], None]  # (messaggio, frazione 0..1)


def _noop(msg: str, frac: float) -> None:
    pass


@dataclass
class AnalysisReport:
    project: Project
    clips: list[MediaInfo]
    order_method: str
    gaps: list[GapWarning]
    warnings: list[str] = field(default_factory=list)
    cam: np.ndarray | None = None   # audio camera 8 kHz mono (per forma d'onda)
    ext: np.ndarray | None = None   # audio esterno 8 kHz mono


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def analyze(video_paths: list[Path], audio_path: Path, progress: Progress = _noop,
            cancel: threading.Event | None = None, keep_order: bool = False) -> AnalysisReport:
    if not video_paths:
        raise FFmpegError("Nessun video selezionato")
    progress("Lettura dei metadati…", 0.0)
    infos = []
    for p in video_paths:
        info = media_info(p)
        if not info.has_video:
            raise FFmpegError(f"«{p.name}» non contiene un video")
        infos.append(info)
    ordered, method = (infos, "manuale") if keep_order else order_clips(infos)
    gaps = find_gaps(ordered)
    warnings = [g.message() for g in gaps]
    total = sum(c.duration for c in ordered)

    sr = sync.SR
    cam_parts = []
    for i, c in enumerate(ordered):
        _check_cancel(cancel)
        progress(f"Estrazione audio camera ({i + 1}/{len(ordered)})…", 0.05 + 0.3 * i / len(ordered))
        if c.has_audio:
            cam_parts.append(decode_audio_mono(c.path, sr, expected_s=c.duration))
        else:
            cam_parts.append(np.zeros(int(round(c.duration * sr)), dtype=np.float32))
    cam = np.concatenate(cam_parts)
    _check_cancel(cancel)
    progress("Estrazione audio esterno…", 0.4)
    ext = decode_audio_mono(audio_path, sr)
    _check_cancel(cancel)

    progress("Calcolo dell'offset di sincronizzazione…", 0.55)
    res = sync.analyze_sync(cam, ext, sr)
    if res.low_confidence:
        warnings.append(
            f"Confidenza di sincronizzazione bassa ({res.confidence:.1f}): controlla l'offset a orecchio."
        )
    if res.drift_significant:
        warnings.append(
            f"Deriva dei clock di {res.drift_s * 1000:+.0f} ms in {res.drift_span_s / 60:.0f} min: "
            f"consigliata la correzione (atempo={res.atempo:.6f})."
        )

    _check_cancel(cancel)
    progress("Suggerimento dei tagli…", 0.8)
    aligned = sync.place_on_timeline(ext, res.offset_s, len(cam), sr)
    sug = trim_detect.suggest_trim(aligned, sr, total)

    proj = Project(
        clips=[str(c.path.resolve()) for c in ordered], audio=str(Path(audio_path).resolve()), total_duration=total,
        offset_s=res.offset_s, sync_confidence=res.confidence, drift_s=res.drift_s,
        atempo=res.atempo, offset_corrected_s=res.offset_corrected_s,
        use_drift_correction=False,
    )
    if sug.found:
        proj.suggested_start, proj.suggested_end = sug.start_s, sug.end_s
    else:
        warnings.append("Nessun parlato sostenuto rilevato: nessun taglio suggerito.")
    progress("Analisi completata", 1.0)
    return AnalysisReport(proj, ordered, method, gaps, warnings, cam, ext)


# ----------------------------------------------------------------------------- export

@dataclass
class Segment:
    clip: MediaInfo
    ss: float
    length: float


@dataclass
class ExportPlan:
    mode: str                 # 'copy' | 'encode'
    args: list[str]
    duration: float
    start: float              # inizio effettivo sulla linea temporale (può differire in copia stream)
    notes: list[str]


def plan_segments(clips: list[MediaInfo], t0: float, t1: float) -> list[Segment]:
    segs, pos = [], 0.0
    for c in clips:
        c0, c1 = pos, pos + c.duration
        pos = c1
        lo, hi = max(t0, c0), min(t1, c1)
        if hi - lo > 1e-3:
            segs.append(Segment(c, lo - c0, hi - lo))
    return segs


def copy_compatible(clips: list[MediaInfo]) -> tuple[bool, str]:
    first = clips[0]
    for c in clips[1:]:
        for attr, label in (("vcodec", "codec"), ("width", "larghezza"), ("height", "altezza"),
                            ("pix_fmt", "pixel format"), ("rotation", "rotazione")):
            if getattr(c, attr) != getattr(first, attr):
                return False, f"«{c.name}» ha {label} diverso da «{first.name}»"
        if abs(c.fps - first.fps) > 0.01:
            return False, f"«{c.name}» ha fps diverso da «{first.name}»"
    return True, ""


def audio_filter(p: Project, t0: float) -> str:
    """Catena per l'audio esterno: atempo → 48 kHz → scarto/silenzio iniziale → padding finale."""
    parts = []
    s = p.effective_atempo
    if abs(s - 1.0) > 1e-6:
        parts.append(f"atempo={s:.8f}")
    parts.append("aresample=48000")
    x = t0 - p.effective_offset  # istante dell'audio esterno (già riscalato) da cui partire
    if x > 1e-4:
        parts.append(f"atrim=start={x:.6f}")
        parts.append("asetpts=PTS-STARTPTS")
    elif x < -1e-4:
        ms = int(round(-x * 1000))
        parts.append(f"adelay={ms}:all=1")
    parts.append("apad")
    return ",".join(parts)


def _esc(path: str) -> str:
    return path.replace("\\", "/").replace("'", r"'\''")


def build_plan(p: Project, clips: list[MediaInfo], out: Path, mode: str = "auto",
               t0: float | None = None, t1: float | None = None, audio_post: str = "") -> ExportPlan:
    """Costruisce gli argomenti ffmpeg. `mode`: auto | copy | encode."""
    t0 = 0.0 if t0 is None else max(0.0, t0)
    t1 = p.total_duration if t1 is None else min(p.total_duration, t1)
    if t1 - t0 < 1.0:
        raise FFmpegError("L'intervallo di taglio è vuoto o troppo corto")
    notes: list[str] = []
    ok, why = copy_compatible(clips)
    if mode == "auto":
        mode = "copy" if ok else "encode"
        if not ok:
            notes.append(f"Ricodifica automatica: {why}.")
    if mode == "copy" and not ok:
        raise FFmpegError(f"Copia stream impossibile: {why}. Usa la ricodifica.")

    if mode == "copy":
        # il taglio in copia può partire solo da un keyframe: arretra l'inizio
        segs0 = plan_segments(clips, t0, t1)
        first = segs0[0]
        kfs = [k for k in keyframe_times(first.clip.path) if k <= first.ss + 1e-3]
        if kfs and abs(kfs[-1] - first.ss) > 1e-3:
            shift = first.ss - kfs[-1]
            notes.append(f"Copia stream: inizio anticipato di {shift:.2f} s al keyframe precedente.")
            t0 -= shift
        segs = plan_segments(clips, t0, t1)
        lst = paths.temp_dir() / "concat.txt"
        lines = []
        for s in segs:
            lines.append(f"file '{_esc(str(s.clip.path.resolve()))}'")
            if s.ss > 1e-3:
                lines.append(f"inpoint {s.ss:.6f}")
            if s.length < s.clip.duration - s.ss - 1e-3:
                lines.append(f"outpoint {s.ss + s.length:.6f}")
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        dur = t1 - t0
        args = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", p.audio,
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-filter:a", ",".join(x for x in (audio_filter(p, t0), audio_post) if x), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", f"{dur:.6f}", "-movflags", "+faststart", str(out)]
        return ExportPlan("copy", args, dur, t0, notes)

    segs = plan_segments(clips, t0, t1)
    ref = clips[0]
    w, h = ref.width // 2 * 2, ref.height // 2 * 2
    fps = ref.fps or 30.0
    args: list[str] = []
    for s in segs:
        args += ["-ss", f"{s.ss:.6f}", "-t", f"{s.length:.6f}", "-i", str(s.clip.path)]
    args += ["-i", p.audio]
    n = len(segs)
    chains = [
        f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.5f},format=yuv420p[v{i}]"
        for i in range(n)
    ]
    vin = "".join(f"[v{i}]" for i in range(n))
    chains.append(f"{vin}concat=n={n}:v=1:a=0[v]")
    chains.append(f"[{n}:a:0]{audio_filter(p, t0)}[a]")
    dur = t1 - t0
    args += ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-t", f"{dur:.6f}", "-movflags", "+faststart", str(out)]
    return ExportPlan("encode", args, dur, t0, notes)


def export(p: Project, clips: list[MediaInfo], out: Path, mode: str = "auto",
           t0: float | None = None, t1: float | None = None,
           on_progress: Callable[[float, float | None], None] | None = None,
           cancel: threading.Event | None = None) -> ExportPlan:
    out = Path(out)
    inputs = {Path(c).resolve() for c in p.clips} | {Path(p.audio).resolve()}
    if out.resolve() in inputs:
        raise FFmpegError("Il file di uscita coincide con un file di input: i video originali non vengono mai modificati")
    plan = build_plan(p, clips, out, mode, t0, t1)
    run_ffmpeg(plan.args, plan.duration, on_progress, cancel)
    return plan
