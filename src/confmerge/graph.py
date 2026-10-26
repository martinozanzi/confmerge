"""Costruzione del filtergraph ffmpeg unico: clip → crop/zoom → slide/PiP → grafica → scene → audio → encode."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QImage

from . import audio_fx, credit, encoders, paths, slides as sl
from .ffmpeg_wrapper import FFmpegError
from .media_scan import MediaInfo
from .pipeline import audio_filter, plan_segments
from .project import Project
from .render import compositor
from .render.model import Element, Scene, lower_third_elements, substitute
from .spec import RenderSpec, audio_bitrate_bps, output_size, video_bitrate_bps

MAX_SAMPLE_FADE = 0.0


def esc(expr: str) -> str:
    """Virgole escape per espressioni non fra apici."""
    return expr.replace(",", "\\,")


@dataclass
class BuildResult:
    args: list[str]
    duration: float                  # durata del file finale
    main_duration: float
    W: int
    H: int
    fps: float
    encoder: str
    notes: list[str] = field(default_factory=list)
    extra_s: float = 0.0             # durata dei segmenti titolo/outro/credito (per la stima)
    animated_frames: int = 0         # fotogrammi PNG generati per le parti animate
    loudness: dict | None = None


class _G:
    def __init__(self, fps: float):
        self.fps = fps
        self.inputs: list[str] = []
        self.n = 0
        self.f: list[str] = []
        self.uses: dict[str, list[str]] = {}

    def inp(self, *args: str) -> int:
        self.inputs += list(args)
        self.n += 1
        return self.n - 1

    def img_input(self, path: str, t_end: float) -> int:
        return self.inp("-loop", "1", "-framerate", f"{self.fps:.5f}", "-t", f"{t_end:.4f}", "-i", path)

    def take(self, src: str) -> str:
        """Etichetta unica derivata da `src` (verrà creato uno split)."""
        lst = self.uses.setdefault(src, [])
        lab = f"{src}_u{len(lst)}"
        lst.append(lab)
        return lab

    def finalize_splits(self) -> None:
        for src, labs in self.uses.items():
            if len(labs) == 1:
                self.f.append(f"[{src}]null[{labs[0]}]")
            else:
                self.f.append(f"[{src}]split={len(labs)}" + "".join(f"[{l}]" for l in labs))


_counter = 0


def _lab(prefix: str) -> str:
    global _counter
    _counter += 1
    return f"{prefix}{_counter}"


def add_layers(g: _G, cur: str, layers: list[compositor.Layer], fmt: str = "yuv420p") -> str:
    for ly in layers:
        out = _lab("o")
        if ly.kind == "sequence":
            k = g.inp("-framerate", f"{g.fps:.5f}", "-start_number", "0", "-i", ly.path)
            lab = _lab("q")
            g.f.append(f"[{k}:v]format=rgba,setpts=PTS-STARTPTS+{ly.a:.4f}/TB[{lab}]")
            g.f.append(f"[{cur}][{lab}]overlay=0:0:enable='between(t,{ly.a:.4f},{ly.b:.4f})':eof_action=pass:format=auto[{out}]")
        else:
            k = g.img_input(ly.path, ly.b + 0.5)
            lab = _lab("s")
            pre = "format=rgba" + (f",colorchannelmixer=aa={ly.opacity:.3f}" if ly.opacity < 1 and ly.kind == "bar" else "")
            g.f.append(f"[{k}:v]{pre}[{lab}]")
            x = ly.x_expr if ly.kind == "bar" else "0"
            y = ly.y_expr if ly.kind == "bar" else "0"
            g.f.append(f"[{cur}][{lab}]overlay=x={x}:y={y}:enable='between(t,{ly.a:.4f},{ly.b:.4f})':format=auto[{out}]")
        cur = out
    return cur


def _main_chain_for_clip(c: MediaInfo, spec: RenderSpec, W: int, H: int, fps: float) -> str:
    im = spec.image
    ch = []
    l, t, r, b = im.crop_l, im.crop_t, im.crop_r, im.crop_b
    sw, sh = c.width, c.height
    if l or t or r or b:
        cw, chh = max(0.05, 1 - l - r), max(0.05, 1 - t - b)
        ch.append(f"crop=w='trunc(iw*{cw:.6f}/2)*2':h='trunc(ih*{chh:.6f}/2)*2':x='iw*{l:.6f}':y='ih*{t:.6f}'")
        sw, sh = sw * cw, sh * chh
    if not im.kenburns and im.zoom > 1.001:
        z = im.zoom
        ch.append(f"crop=w='trunc(iw/{z:.5f}/2)*2':h='trunc(ih/{z:.5f}/2)*2':"
                  f"x='max(0,min(iw-ow,{im.cx:.5f}*iw-ow/2))':y='max(0,min(ih-oh,{im.cy:.5f}*ih-oh/2))'")
        sw, sh = sw / z, sh / z
    ar_src, ar_out = sw / max(sh, 1), W / H
    if abs(ar_src - ar_out) < 0.01:
        ch.append(f"scale={W}:{H}")
    elif im.vertical_mode == "crop":
        ch.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    else:
        ch.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black")
    ch += [f"fps={fps:.5f}", "setsar=1", "format=yuv420p"]
    return ",".join(ch)


def kenburns_filter(spec: RenderSpec, W: int, H: int, t0: float) -> str:
    im = spec.image
    a, b = im.kb_t0, max(im.kb_t1, im.kb_t0 + 1e-3)
    P = f"min(1,max(0,(t-{a:.4f})/{b - a:.4f}))"
    S = f"({P}*{P}*(3-2*{P}))"

    def lerp(v1, v2):
        return f"({v1:.5f}+({v2:.5f}-{v1:.5f})*{S})"
    z, cx, cy = lerp(im.zoom, im.zoom2), lerp(im.cx, im.cx2), lerp(im.cy, im.cy2)
    return (f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,"
            f"crop={W}:{H}:x='max(0,min(iw-{W},{cx}*iw-{W}/2))':y='max(0,min(ih-{H},{cy}*ih-{H}/2))'")


def _graphics_elements(spec: RenderSpec, D: float) -> list[Element]:
    gr = spec.graphics
    els = substitute([e for e in gr.elements if "main" in e.targets], spec.variables)
    for i, lt in enumerate(gr.lower_thirds):
        els += lower_third_elements(lt, i, spec.variables)
    if gr.title.enabled and gr.title.over_video:
        for e in substitute(gr.title.elements, spec.variables):
            d = e.to_dict()
            d["end"] = min(d["end"], gr.title.duration) if d.get("end") is not None else gr.title.duration
            els.append(Element.from_dict(d))
    return els


def build(p: Project, clips: list[MediaInfo], spec: RenderSpec, out: Path, t0: float, t1: float,
          workdir: Path, *, with_scenes: bool = True, loud: dict | None = None,
          encoder: str | None = None, slide_images: list[QImage] | None = None) -> BuildResult:
    global _counter
    _counter = 0
    workdir.mkdir(parents=True, exist_ok=True)
    im, gr = spec.image, spec.graphics
    W, H = output_size(im, spec.export)
    ref = clips[0]
    fps = im.fps or ref.fps or 30.0
    h_short = min(W, H)
    D = t1 - t0
    if D < 1.0:
        raise FFmpegError("L'intervallo di taglio è vuoto o troppo corto")
    enc = encoder or encoders.resolve_encoder(spec.export.encoder)
    g = _G(fps)
    notes: list[str] = []
    frames = 0

    # --- 1. clip → [vc]
    segs = plan_segments(clips, t0, t1)
    for s in segs:
        k = g.inp("-ss", f"{s.ss:.6f}", "-t", f"{s.length:.6f}", "-i", str(s.clip.path))
        g.f.append(f"[{k}:v:0]{_main_chain_for_clip(s.clip, spec, W, H, fps)}[v{k}]")
    n = len(segs)
    if n == 1:
        g.f.append("[v0]null[vc]")
    else:
        g.f.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    cur = "vc"
    if im.kenburns:
        g.f.append(f"[{cur}]{kenburns_filter(spec, W, H, t0)}[vk]")
        cur = "vk"

    # --- 2. slide / PiP
    sls = spec.slides
    if sls.enabled and (sls.files or sls.video):
        cur = _add_slides(g, cur, sls, slide_images or [], W, H, fps, D, workdir, t0, p)

    # --- 3. grafica sul video principale
    els = _graphics_elements(spec, D)
    layers = compositor.plan_layers(els, W, H, D, fps, workdir, "m")
    frames += sum(l.frames for l in layers)
    cur = add_layers(g, cur, layers)

    # --- 4. fade del video principale
    chain = []
    if im.fade_in > 0:
        chain.append(f"fade=t=in:st=0:d={im.fade_in:.3f}")
    if im.fade_out > 0:
        chain.append(f"fade=t=out:st={max(0, D - im.fade_out):.3f}:d={im.fade_out:.3f}")
    chain += [f"trim=duration={D:.4f}", "setpts=PTS-STARTPTS", f"fps={fps:.5f}", "format=yuv420p"]
    g.f.append(f"[{cur}]{','.join(chain)}[vmain]")

    # --- 5. audio principale
    voice = audio_fx.VoiceOptions(spec.audio.highpass, spec.audio.denoise, spec.audio.compressor)
    a_in = g.inp("-i", p.audio)
    achain = [audio_filter(p, t0)] + audio_fx.voice_chain(voice)
    if spec.audio.loudnorm and loud:
        achain.append(audio_fx.loudnorm_apply_filter(loud))
    achain += [f"atrim=end={D:.4f}", "asetpts=PTS-STARTPTS", "aformat=sample_rates=48000:channel_layouts=stereo"]
    if im.fade_in > 0:
        achain.append(f"afade=t=in:st=0:d={im.fade_in:.3f}")
    if im.fade_out > 0:
        achain.append(f"afade=t=out:st={max(0, D - im.fade_out):.3f}:d={im.fade_out:.3f}")
    g.f.append(f"[{a_in}:a:0]{','.join(achain)}[amain]")

    # --- 6. scene (titolo, outro, credito)
    seq: list[tuple[str, str, float, float]] = []   # (video, audio, durata, dissolvenza verso la precedente)
    extra = 0.0
    if with_scenes:
        if gr.title.enabled and not gr.title.over_video:
            v, a, d, fr = _scene(g, gr.title, "title", W, H, fps, workdir, "t", extra=substitute([e for e in gr.elements if "title" in e.targets], spec.variables), variables=spec.variables)
            seq.append((v, a, d, 0.0))
            frames += fr
            extra += d
    seq.append(("vmain", "amain", D, gr.title.fade if (with_scenes and gr.title.enabled and not gr.title.over_video) else 0.0))
    if with_scenes:
        if gr.outro.enabled:
            v, a, d, fr = _scene(g, gr.outro, "outro", W, H, fps, workdir, "u", extra=substitute([e for e in gr.elements if "outro" in e.targets], spec.variables), variables=spec.variables)
            seq.append((v, a, d, gr.outro.fade))
            frames += fr
            extra += d
        if spec.credit.enabled:
            qr = credit.qr_png(workdir / "qr.png") if spec.credit.qr else None
            cs = credit.credit_scene(spec.credit.duration, qr)
            v, a, d, fr = _scene(g, cs, "outro", W, H, fps, workdir, "c", fade_inout=credit.FADE)
            seq.append((v, a, d, 0.0))
            frames += fr
            extra += d

    cv, ca, clen, _ = seq[0]
    for i, (nv, na, nl, f) in enumerate(seq[1:], 1):
        ov, oa = f"xv{i}", f"xa{i}"
        if f > 0:
            f = min(f, clen / 2, nl / 2)
            g.f.append(f"[{cv}][{nv}]xfade=transition=fade:duration={f:.3f}:offset={clen - f:.4f}[{ov}]")
            g.f.append(f"[{ca}][{na}]acrossfade=d={f:.3f}[{oa}]")
            clen += nl - f
        else:
            g.f.append(f"[{cv}][{ca}][{nv}][{na}]concat=n=2:v=1:a=1[{ov}][{oa}]")
            clen += nl
        cv, ca = ov, oa

    g.finalize_splits()
    total = clen
    args = list(g.inputs)
    args += ["-filter_complex", ";".join(g.f), "-map", f"[{cv}]", "-map", f"[{ca}]"]
    args += encoders.video_args(enc, spec.export, h_short, fps)
    args += encoders.audio_args(spec.export, h_short)
    args += ["-movflags", "+faststart", str(out)]
    return BuildResult(args, total, D, W, H, fps, enc, notes, extra, frames, loud)


def _scene(g: _G, scene: Scene, target: str, W: int, H: int, fps: float, workdir: Path, pre: str,
           fade_inout: float = 0.0, extra: list[Element] | None = None,
           variables: dict[str, str] | None = None) -> tuple[str, str, float, int]:
    d = scene.duration
    bg = workdir / f"{pre}_bg.png"
    compositor.render_scene_background(scene, W, H).save(str(bg), "PNG")
    k = g.img_input(str(bg), d)
    cur = _lab("sb")
    g.f.append(f"[{k}:v]format=yuv420p,setsar=1[{cur}]")
    els = substitute(list(scene.elements), variables) + list(extra or [])
    layers = compositor.plan_layers(els, W, H, d, fps, workdir, pre)
    cur = add_layers(g, cur, layers)
    ch = []
    if fade_inout > 0:
        ch += [f"fade=t=in:st=0:d={fade_inout:.3f}", f"fade=t=out:st={max(0, d - fade_inout):.3f}:d={fade_inout:.3f}"]
    ch += [f"trim=duration={d:.4f}", "setpts=PTS-STARTPTS", f"fps={fps:.5f}", "format=yuv420p"]
    v, a = _lab("sv"), _lab("sa")
    g.f.append(f"[{cur}]{','.join(ch)}[{v}]")
    g.f.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.4f},asetpts=PTS-STARTPTS[{a}]")
    return v, a, d, sum(l.frames for l in layers)


def _add_slides(g: _G, cur: str, sls, images: list[QImage], W: int, H: int, fps: float, D: float,
                workdir: Path, t0: float, p: Project) -> str:
    """Compone slide a schermo intero / PiP / affiancati secondo la timeline dei layout."""
    ivs = sl.intervals(sls, D, len(images) if images else 1)
    pip = sls.pip
    use_video = bool(sls.video) and not images
    aux = None
    if use_video:
        x = t0 - sls.video_offset
        if x >= 0:
            k = g.inp("-ss", f"{x:.4f}", "-t", f"{D:.4f}", "-i", sls.video)
            pre = ""
        else:
            k = g.inp("-t", f"{D + x:.4f}", "-i", sls.video)
            pre = f",tpad=start_duration={-x:.4f}"
        g.f.append(f"[{k}:v:0]fps={fps:.5f},setsar=1{pre},format=yuv420p[aux]")
        aux = "aux"
    g.f.append(f"[{cur}]null[spk]")
    spk = "spk"
    cur = g.take(spk)   # il relatore di base resta sotto; ogni intervallo aggiunge strati sopra
    for iv in ivs:
        if iv.layout == "speaker":
            continue
        en = f"enable='between(t,{iv.a:.4f},{iv.b:.4f})'"
        img = images[iv.slide] if images else None
        if iv.layout == "slide_full":
            if img is not None:
                f = workdir / f"sl_full_{iv.slide}.png"
                if not f.exists():
                    sl.full_slide_png(img, W, H).save(str(f), "PNG")
                cur = _overlay_png(g, cur, str(f), iv, 0, 0)
            elif aux:
                cur = _overlay_video(g, cur, g.take(aux), iv, 0, 0, W, H, None, fit=True)
            rect = sl.pip_rect(pip, W, H)
            cur = _pip_video(g, cur, g.take(spk), iv, rect, pip, W, H, workdir)
        elif iv.layout == "speaker_full":
            if img is not None:
                f = workdir / f"sl_small_{iv.slide}.png"
                if not f.exists():
                    sl.small_slide_png(img, pip, W, H).save(str(f), "PNG")
                cur = _overlay_png(g, cur, str(f), iv, 0, 0)
            elif aux:
                rect = sl.pip_rect(pip, W, H)
                cur = _pip_video(g, cur, g.take(aux), iv, rect, pip, W, H, workdir)
        elif iv.layout == "side_by_side":
            left, right = sl.side_rects(pip, W, H)
            if img is not None:
                f = workdir / f"sl_side_{iv.slide}.png"
                if not f.exists():
                    sl.side_by_side_png(img, pip, W, H).save(str(f), "PNG")
                cur = _overlay_png(g, cur, str(f), iv, 0, 0)
            else:
                f = workdir / "sl_black.png"
                bk = QImage(W, H, QImage.Format_RGB32)
                bk.fill(0)
                bk.save(str(f), "PNG")
                cur = _overlay_png(g, cur, str(f), iv, 0, 0)
                if aux:
                    cur = _pip_video(g, cur, g.take(aux), iv, right, pip, W, H, workdir)
            cur = _pip_video(g, cur, g.take(spk), iv, left, pip, W, H, workdir)
    return cur


def _overlay_png(g: _G, cur: str, path: str, iv: sl.Interval, x, y) -> str:
    k = g.img_input(path, iv.b + 0.5)
    lab, out = _lab("sl"), _lab("o")
    g.f.append(f"[{k}:v]format=rgba[{lab}]")
    g.f.append(f"[{cur}][{lab}]overlay={x}:{y}:enable='between(t,{iv.a:.4f},{iv.b:.4f})':format=auto[{out}]")
    return out


def _overlay_video(g: _G, cur: str, src: str, iv, x, y, w, h, mask_idx, fit=True) -> str:
    lab, out = _lab("av"), _lab("o")
    g.f.append(f"[{src}]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
               f"format=yuv420p[{lab}]")
    g.f.append(f"[{cur}][{lab}]overlay={x}:{y}:enable='between(t,{iv.a:.4f},{iv.b:.4f})'[{out}]")
    return out


def _pip_video(g: _G, cur: str, src: str, iv, rect, pip, W: int, H: int, workdir: Path) -> str:
    """Video in un riquadro con angoli arrotondati, bordo e ombra (maschera e decorazioni da QPainter)."""
    w, h = int(rect.width()) // 2 * 2, int(rect.height()) // 2 * 2
    x, y = int(rect.x()), int(rect.y())
    dec = workdir / f"dec_{x}_{y}_{w}_{h}.png"
    if not dec.exists():
        sl.decor_png(rect, pip, W, H).save(str(dec), "PNG")
    cur = _overlay_png(g, cur, str(dec), iv, 0, 0)
    mp = workdir / f"mask_{w}_{h}.png"
    if not mp.exists():
        sl.mask_png(w, h, pip.radius * H).save(str(mp), "PNG")
    km = g.img_input(str(mp), iv.b + 0.5)
    ml, vl, out = _lab("mk"), _lab("pv"), _lab("o")
    g.f.append(f"[{km}:v]format=gray[{ml}]")
    g.f.append(f"[{src}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuva420p[{vl}a]")
    g.f.append(f"[{vl}a][{ml}]alphamerge[{vl}]")
    g.f.append(f"[{cur}][{vl}]overlay={x}:{y}:enable='between(t,{iv.a:.4f},{iv.b:.4f})':format=auto[{out}]")
    return out
