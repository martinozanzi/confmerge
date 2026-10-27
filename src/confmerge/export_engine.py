"""Driver dell'export: scelta copia/ricodifica, loudnorm a due passate, esecuzione, campioni e stima."""
from __future__ import annotations

import logging
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import audio_fx, encoders, estimator, graph, paths
from .ffmpeg_wrapper import Cancelled, FFmpegError, run_ffmpeg
from .media_scan import MediaInfo
from .pipeline import audio_filter, build_plan, copy_compatible
from .project import Project
from .slides import load_slides
from .spec import RenderSpec, audio_bitrate_bps, output_size, video_bitrate_bps

log = logging.getLogger(__name__)
Progress = Callable[[float, float | None], None]
SAMPLE_S = 10.0


@dataclass
class Decision:
    mode: str                                   # 'copy' | 'encode'
    reasons: list[str] = field(default_factory=list)   # perché serve ricodificare
    credit_conflict: bool = False               # copia stream richiesta ma il credito è attivo
    warnings: list[str] = field(default_factory=list)


def visual_changes(spec: RenderSpec) -> list[str]:
    """Elenco delle modifiche visive: se vuoto è possibile la copia stream."""
    r, im, gr = [], spec.image, spec.graphics
    if im.crop_l or im.crop_t or im.crop_r or im.crop_b:
        r.append("ritaglio")
    if im.zoom != 1.0 or im.kenburns:
        r.append("zoom")
    if im.fade_in > 0 or im.fade_out > 0:
        r.append("dissolvenze")
    if im.fps:
        r.append("fps")
    if im.aspect != "16:9" or im.resolution != "1080p" and spec.export.preset == "Personalizzato":
        r.append("formato/risoluzione")
    if gr.elements or gr.lower_thirds:
        r.append("grafica")
    if gr.title.enabled or gr.outro.enabled:
        r.append("titolo/schermata finale")
    if spec.slides.enabled:
        r.append("slide")
    return r


def decide(spec: RenderSpec, clips: list[MediaInfo]) -> Decision:
    """Copia stream solo con preset «Veloce» (o nessuna modifica) e clip compatibili."""
    changes = visual_changes(spec)
    ok, why = copy_compatible(clips)
    wants_copy = spec.export.preset.startswith("Veloce")
    d = Decision("encode")
    if wants_copy and not changes and ok:
        d.mode = "copy"
        if spec.credit.enabled:
            d.credit_conflict = True
            d.warnings.append("Con la copia stream il credito finale non può essere aggiunto: "
                              "disattivalo oppure ricodifica.")
        return d
    if wants_copy:
        d.reasons = changes or [why]
        d.warnings.append("Ricodifica necessaria (" + ", ".join(d.reasons) + "): la copia stream non è possibile.")
    elif changes:
        d.reasons = changes
    if not changes and not wants_copy:
        d.reasons = ["preset di export"]
    return d


@dataclass
class ExportReport:
    mode: str
    out: str
    wall_s: float
    size_bytes: int
    encoder: str
    duration: float
    loud_before: dict | None = None
    loud_after: dict | None = None
    notes: list[str] = field(default_factory=list)


def _voice(spec: RenderSpec) -> audio_fx.VoiceOptions:
    return audio_fx.VoiceOptions(spec.audio.highpass, spec.audio.denoise, spec.audio.compressor)


def measure_loudness(p: Project, spec: RenderSpec, t0: float, t1: float) -> dict:
    pre = [audio_filter(p, t0)] + audio_fx.voice_chain(_voice(spec))
    return audio_fx.measure(["-i", p.audio], [",".join(pre)], duration=t1 - t0)


def run_export(p: Project, clips: list[MediaInfo], spec: RenderSpec, out: Path, t0: float, t1: float,
               on_progress: Progress | None = None, cancel: threading.Event | None = None,
               force_mode: str | None = None) -> ExportReport:
    out = Path(out)
    inputs = {Path(c).resolve() for c in p.clips} | ({Path(p.audio).resolve()} if p.audio else set())
    if out.resolve() in inputs:
        raise FFmpegError("Il file di uscita coincide con un file di input: gli originali non vengono mai modificati")
    out.parent.mkdir(parents=True, exist_ok=True)
    dec = decide(spec, clips)
    mode = "encode" if p.kind == "social" else (force_mode or dec.mode)     # il social è sempre ricodificato (tagli, formato)
    started = time.time()
    notes = list(dec.warnings)
    loud = None
    if spec.audio.loudnorm and p.kind != "social":
        loud = measure_loudness(p, spec, t0, t1)
    workdir = paths.temp_dir() / f"job_{int(started * 1000)}"
    try:
        if mode == "copy":
            post = ",".join(audio_fx.voice_chain(_voice(spec)) + ([audio_fx.loudnorm_apply_filter(loud)] if loud else []))
            plan = build_plan(p, clips, out, "copy", t0, t1, audio_post=post)
            run_ffmpeg(plan.args, plan.duration, on_progress, cancel)
            notes += plan.notes
            enc, dur = "copy", plan.duration
        else:
            slides_imgs = load_slides(spec.slides.files) if (spec.slides.enabled and spec.slides.files) else []
            enc = encoders.resolve_encoder(spec.export.encoder)
            while True:
                res = graph.build(p, clips, spec, out, t0, t1, workdir, loud=loud, encoder=enc, slide_images=slides_imgs)
                try:
                    run_ffmpeg(res.args, res.duration, on_progress, cancel)
                    break
                except FFmpegError as e:
                    if enc == "libx264":
                        raise
                    log.warning("Encoder %s fallito (%s): ripiego su CPU", enc, e)
                    notes.append(f"Accelerazione hardware non riuscita ({enc}): ricodificato su CPU.")
                    enc = "libx264"
            dur = res.duration
        after = audio_fx.measure(["-i", str(out)], []) if spec.audio.loudnorm else None
        return ExportReport(mode, str(out), time.time() - started, out.stat().st_size, enc, dur, loud, after, notes)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def render_sample(p: Project, clips: list[MediaInfo], spec: RenderSpec, start: float, dur: float, out: Path,
                  cancel: threading.Event | None = None) -> tuple[float, float, int]:
    """Codifica un campione con gli STESSI filtri/encoder dell'export. Restituisce (secondi reali, velocità×, byte).
    Serve sia alla stima sia all'anteprima di 10 s."""
    t0 = max(0.0, min(start, p.total_duration - dur))
    t1 = min(p.total_duration, t0 + dur)
    slides_imgs = load_slides(spec.slides.files) if (spec.slides.enabled and spec.slides.files) else []
    workdir = paths.temp_dir() / f"sample_{int(time.time() * 1000)}"
    try:
        enc = encoders.resolve_encoder(spec.export.encoder)
        s2 = RenderSpec.from_dict(spec.to_dict())
        s2.audio.loudnorm = False
        s2.credit.enabled = False
        s2.graphics.title.enabled = False
        s2.graphics.outro.enabled = False
        t_start = time.time()
        rng = [(t0, t1)] if p.kind == "social" else None
        res = graph.build(p, clips, s2, out, t0, t1, workdir, with_scenes=False, encoder=enc, slide_images=slides_imgs,
                          ranges=rng)
        try:
            run_ffmpeg(res.args, res.duration, None, cancel)
        except FFmpegError:
            if enc == "libx264":
                raise
            res = graph.build(p, clips, s2, out, t0, t1, workdir, with_scenes=False, encoder="libx264",
                              slide_images=slides_imgs, ranges=rng)
            run_ffmpeg(res.args, res.duration, None, cancel)
        wall = max(time.time() - t_start, 1e-3)
        return wall, (t1 - t0) / wall, out.stat().st_size
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@dataclass
class Estimate:
    time_lo: float
    time_hi: float
    time_text: str
    size: estimator.SizeEstimate
    size_text: str
    approximate: bool
    speed_x: float
    notes: list[str]


def estimate(p: Project, clips: list[MediaInfo], spec: RenderSpec, t0: float, t1: float,
             corrections: dict | None = None, sample_cache: dict | None = None,
             cancel: threading.Event | None = None, D: float | None = None) -> Estimate:
    """Stima tempo e dimensione: benchmark su un campione di ~10 s dal centro, esteso alla durata finale.
    `D`: durata del video finito se diversa da t1 - t0 (Studio Social, dopo i tagli)."""
    D = D if D is not None else t1 - t0
    W, H = output_size(spec.image, spec.export)
    h_short = min(W, H)
    fps = spec.image.fps or clips[0].fps or 30.0
    dec = decide(spec, clips)
    abps = audio_bitrate_bps(spec.export, h_short)
    notes: list[str] = []
    extra = 0.0
    if spec.graphics.title.enabled and not spec.graphics.title.over_video:
        extra += spec.graphics.title.duration
    if spec.graphics.outro.enabled:
        extra += spec.graphics.outro.duration
    if spec.credit.enabled and dec.mode != "copy":
        extra += spec.credit.duration
    total_s = D + extra

    if dec.mode == "copy":
        tot_bytes = sum(Path(c.path).stat().st_size for c in clips)
        sz = estimator.size_copy(tot_bytes, sum(c.duration for c in clips), D, abps)
        t = D / 60.0 + 2  # quasi solo I/O + riscrittura audio
        return Estimate(max(1, t * 0.6), t * 1.6, estimator.format_range(t * 0.6, t * 1.6), sz,
                        estimator.format_size(sz.mid), True, 0.0, ["Copia stream: stima approssimativa."])

    key = (encoders.resolve_encoder(spec.export.encoder), (W, H), round(fps, 2), repr(spec.image), repr(spec.graphics.elements),
           repr(spec.slides), spec.export.crf_mode, spec.export.crf)
    sample_s = min(SAMPLE_S, D)
    if sample_cache is not None and key in sample_cache:
        wall, speed, size_b = sample_cache[key]
    else:
        tmp = paths.temp_dir() / "bench.mp4"
        mid = t0 + ((t1 - t0) - sample_s) / 2
        wall, speed, size_b = render_sample(p, clips, spec, mid, sample_s, tmp, cancel)
        tmp.unlink(missing_ok=True)
        if sample_cache is not None:
            sample_cache[key] = (wall, speed, size_b)

    parts = estimator.TimeParts(main_s=D / speed)
    if spec.audio.loudnorm:
        parts.loudnorm_s = D / 60.0 + 3      # analisi della prima passata: molto più veloce del tempo reale
    parts.segments_s = extra / speed
    if spec.audio.loudnorm is False:
        parts.loudnorm_s = 0
    if abs(p.effective_atempo - 1.0) > 1e-6:
        parts.drift_s = D / 200.0
    enc = key[0]
    corr = (corrections or {}).get(enc, 1.0)
    lo, hi = estimator.estimate_time(D, speed, estimator.TimeParts(0, parts.loudnorm_s, parts.segments_s, 0, parts.drift_s),
                                     corr)
    if spec.export.crf_mode:
        sz = estimator.size_from_sample(size_b, sample_s, abps, total_s)
        notes.append("Stima approssimativa (CRF): la dimensione dipende dal contenuto.")
    else:
        vb = video_bitrate_bps(spec.export, h_short, fps)
        sz = estimator.size_from_bitrate(vb, abps, total_s)
    return Estimate(lo, hi, estimator.format_range(lo, hi), sz,
                    estimator.format_size(sz.mid) if sz.exact else f"{estimator.format_size(sz.low)} – {estimator.format_size(sz.high)}",
                    not sz.exact, speed, notes)


def check_space(out_dir: Path, est_bytes: float, spec: RenderSpec, anim_frames: int, W: int, H: int,
                proxy_bytes: float = 0) -> list[str]:
    """Avvisi se lo spazio libero è insufficiente (destinazione e cartella temporanea)."""
    warns = []
    out_dir.mkdir(parents=True, exist_ok=True)
    free_out = shutil.disk_usage(out_dir).free
    if free_out < est_bytes * 1.1:
        warns.append(f"Spazio insufficiente nella cartella di destinazione: servono ~{est_bytes / 1e9:.1f} GB, "
                     f"liberi {free_out / 1e9:.1f} GB.")
    tmp_need = anim_frames * W * H * 0.12 + proxy_bytes + 50e6   # PNG compressi ≈ 12% del raw RGBA
    free_tmp = shutil.disk_usage(paths.temp_dir()).free
    if free_tmp < tmp_need:
        warns.append(f"Spazio insufficiente nella cartella temporanea: servono ~{tmp_need / 1e9:.1f} GB, "
                     f"liberi {free_tmp / 1e9:.1f} GB.")
    return warns
