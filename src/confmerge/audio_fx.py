"""Audio per YouTube: loudnorm a due passate (-14 LUFS, -1 dBTP) e filtri voce."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from .ffmpeg_wrapper import _CREATIONFLAGS, FFmpegError, ffmpeg_path

TARGET_I = -14.0
TARGET_TP = -1.0
TARGET_LRA = 11.0


@dataclass
class VoiceOptions:
    highpass: bool = False
    denoise: bool = False
    compressor: bool = False


def voice_chain(o: VoiceOptions) -> list[str]:
    f = []
    if o.highpass:
        f.append("highpass=f=80")
    if o.denoise:
        f.append("afftdn=nr=12:nf=-30")
    if o.compressor:
        f.append("acompressor=threshold=-21dB:ratio=2.5:attack=20:release=250:makeup=2")
    return f


def loudnorm_measure_filter() -> str:
    return f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"


def parse_loudnorm(stderr: str) -> dict:
    m = list(re.finditer(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S))
    if not m:
        raise FFmpegError("Misura loudnorm non riuscita")
    d = json.loads(m[-1].group(0))
    return {k: float(v) for k, v in d.items() if k != "normalization_type"}


def loudnorm_apply_filter(m: dict) -> str:
    return (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
            f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def measure(args_in: list[str], pre_filters: list[str], duration: float | None = None) -> dict:
    """Prima passata: misura il loudness del segnale dopo i filtri `pre_filters`."""
    chain = ",".join([*pre_filters, loudnorm_measure_filter()])
    cmd = [ffmpeg_path(), "-hide_banner", "-nostdin", *args_in, "-vn", "-af", chain]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", creationflags=_CREATIONFLAGS)
    if res.returncode != 0:
        raise FFmpegError("Analisi loudness fallita:\n" + res.stderr[-400:])
    return parse_loudnorm(res.stderr)
