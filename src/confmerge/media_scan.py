"""Scansione dei file: metadati, ordinamento per creation_time, buchi temporali, cartella."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .ffmpeg_wrapper import FFmpegError, probe

VIDEO_EXT = {".mp4", ".mov", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
SLIDE_EXT = {".pdf", ".png", ".jpg", ".jpeg"}

GAP_WARN_S = 5.0      # buco tra la fine di un file e l'inizio del successivo
OVERLAP_WARN_S = 2.0  # sovrapposizione sospetta


@dataclass
class MediaInfo:
    path: Path
    duration: float
    creation_time: datetime | None = None
    width: int = 0          # dimensioni DOPO la rotazione
    height: int = 0
    rotation: int = 0
    fps: float = 0.0
    vcodec: str = ""
    pix_fmt: str = ""
    has_video: bool = False
    has_audio: bool = False

    @property
    def name(self) -> str:
        return self.path.name


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_fps(s: str | None) -> float:
    if not s or s == "0/0":
        return 0.0
    num, _, den = s.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def media_info(path: str | Path) -> MediaInfo:
    path = Path(path)
    data = probe(path)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    info = MediaInfo(path=path, duration=float(fmt.get("duration") or (v or a or {}).get("duration") or 0.0))
    info.has_audio = a is not None
    ctime = (fmt.get("tags") or {}).get("creation_time") or ((v or {}).get("tags") or {}).get("creation_time")
    info.creation_time = _parse_time(ctime)
    if v:
        info.has_video = True
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(round(float(sd["rotation"])))
        if not rot:
            try:
                rot = int(float((v.get("tags") or {}).get("rotate", 0)))
            except ValueError:
                rot = 0
        rot %= 360
        info.rotation = rot
        info.width, info.height = (h, w) if rot in (90, 270) else (w, h)
        info.fps = _parse_fps(v.get("avg_frame_rate")) or _parse_fps(v.get("r_frame_rate"))
        info.vcodec = v.get("codec_name", "")
        info.pix_fmt = v.get("pix_fmt", "")
    return info


def _natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def order_clips(clips: list[MediaInfo]) -> tuple[list[MediaInfo], str]:
    """Ordina per creation_time; ripiega sul nome file se mancano o sono tutti uguali.
    Restituisce (clip ordinate, metodo: 'creation_time' | 'nome')."""
    times = [c.creation_time for c in clips]
    if clips and all(t is not None for t in times) and len(set(times)) == len(times):
        return sorted(clips, key=lambda c: c.creation_time), "creation_time"
    return sorted(clips, key=lambda c: _natural_key(c.path)), "nome"


@dataclass
class GapWarning:
    before: MediaInfo
    after: MediaInfo
    gap_s: float  # negativo = sovrapposizione

    def message(self) -> str:
        if self.gap_s >= 0:
            return f"Buco di {self.gap_s:.0f} s tra «{self.before.name}» e «{self.after.name}»: manca una parte?"
        return f"«{self.after.name}» inizia {-self.gap_s:.0f} s prima della fine di «{self.before.name}»: ordine o file sospetti."


def find_gaps(ordered: list[MediaInfo]) -> list[GapWarning]:
    out = []
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev.creation_time is None or nxt.creation_time is None:
            continue
        gap = (nxt.creation_time - prev.creation_time).total_seconds() - prev.duration
        if gap > GAP_WARN_S or gap < -OVERLAP_WARN_S:
            out.append(GapWarning(prev, nxt, gap))
    return out


@dataclass
class FolderScan:
    videos: list[Path]
    audios: list[Path]
    slides: list[Path]


def scan_folder(folder: str | Path) -> FolderScan:
    folder = Path(folder)
    if not folder.is_dir():
        raise FFmpegError(f"«{folder}» non è una cartella")
    files = [p for p in folder.iterdir() if p.is_file()]
    return FolderScan(
        videos=sorted((p for p in files if p.suffix.lower() in VIDEO_EXT), key=_natural_key),
        audios=sorted((p for p in files if p.suffix.lower() in AUDIO_EXT), key=_natural_key),
        slides=sorted((p for p in files if p.suffix.lower() in SLIDE_EXT), key=_natural_key),
    )


def pick_external_audio(audios: list[Path]) -> Path | None:
    """Il file audio più lungo della cartella."""
    best, best_d = None, -1.0
    for p in audios:
        try:
            d = media_info(p).duration
        except FFmpegError:
            continue
        if d > best_d:
            best, best_d = p, d
    return best
