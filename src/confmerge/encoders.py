"""Encoder video (x264 e accelerazione hardware con fallback) e parametri YouTube."""
from __future__ import annotations

import subprocess
from functools import lru_cache

from .ffmpeg_wrapper import _CREATIONFLAGS, ffmpeg_path
from .spec import ExportSettings, audio_bitrate_bps, video_bitrate_bps

HW_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf"]


@lru_cache(maxsize=1)
def detect_hw() -> list[str]:
    """Encoder hardware realmente utilizzabili (prova una codifica di 1 fotogramma)."""
    found = []
    try:
        listing = subprocess.run([ffmpeg_path(), "-hide_banner", "-encoders"], capture_output=True, text=True,
                                 errors="replace", creationflags=_CREATIONFLAGS).stdout
    except OSError:
        return []
    for enc in HW_ENCODERS:
        if enc not in listing:
            continue
        r = subprocess.run([ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x144:d=0.2",
                            "-frames:v", "1", "-c:v", enc, "-f", "null", "-"],
                           capture_output=True, creationflags=_CREATIONFLAGS)
        if r.returncode == 0:
            found.append(enc)
    return found


def resolve_encoder(choice: str) -> str:
    if choice == "auto":
        hw = detect_hw()
        return hw[0] if hw else "libx264"
    return choice


def video_args(encoder: str, ex: ExportSettings, h_short: int, fps: float) -> list[str]:
    b = video_bitrate_bps(ex, h_short, fps)
    kb = f"{b / 1000:.0f}k"
    maxr, buf = f"{b * 1.1 / 1000:.0f}k", f"{b * 2 / 1000:.0f}k"
    gop = str(max(1, round(fps * 2)))
    tag = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-pix_fmt", "yuv420p"]
    if encoder == "h264_nvenc":
        rate = ["-rc", "vbr", "-cq", str(ex.crf), "-b:v", "0"] if ex.crf_mode else \
               ["-rc", "vbr", "-b:v", kb, "-maxrate", maxr, "-bufsize", buf]
        return ["-c:v", encoder, "-preset", "p5", "-profile:v", "high", *rate, "-g", gop, "-bf", "2", *tag]
    if encoder == "h264_qsv":
        rate = ["-global_quality", str(ex.crf)] if ex.crf_mode else ["-b:v", kb, "-maxrate", maxr]
        return ["-c:v", encoder, "-preset", "medium", "-profile:v", "high", *rate, "-g", gop, *tag]
    if encoder == "h264_amf":
        rate = ["-rc", "cqp", "-qp_i", str(ex.crf), "-qp_p", str(ex.crf + 2)] if ex.crf_mode else \
               ["-rc", "vbr_peak", "-b:v", kb, "-maxrate", maxr]
        return ["-c:v", encoder, "-quality", "quality", "-profile:v", "high", *rate, "-g", gop, *tag]
    rate = ["-crf", str(ex.crf)] if ex.crf_mode else ["-b:v", kb, "-maxrate", maxr, "-bufsize", buf]
    return ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high", *rate, "-g", gop, "-bf", "2", *tag]


def audio_args(ex: ExportSettings, h_short: int) -> list[str]:
    kbps = round(audio_bitrate_bps(ex, h_short) / 1000)
    return ["-c:a", "aac", "-b:a", f"{kbps}k", "-ar", "48000", "-ac", "2"]
