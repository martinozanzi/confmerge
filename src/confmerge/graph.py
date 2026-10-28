"""Costruzione del filtergraph ffmpeg unico: clip → crop/zoom → slide/PiP → grafica → scene → audio → encode."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QImage

from .brand import brand_elements
from .render import anchors
from . import audio_fx, credit, edl, encoders, paths, slides as sl, subtitles, transitions
from .ffmpeg_wrapper import FFmpegError
from .media_scan import MediaInfo
from .pipeline import audio_filter, plan_segments
from .project import Project
from .render import compositor
from .render.model import Element, Scene, lower_third_elements, substitute
from .spec import RenderSpec, audio_bitrate_bps, output_size, split_heights, video_bitrate_bps

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
        self.second_audio = False

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


def _main_chain_for_clip(c: MediaInfo, spec: RenderSpec, W: int, H: int, fps: float, tag: str = "0",
                         social: bool = False) -> str:
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
    mode = im.reframe if social else ("fill" if im.vertical_mode == "crop" else "bars")
    tail = f"fps={fps:.5f},setsar=1,format=yuv420p"
    if abs(ar_src - ar_out) < 0.01:
        ch.append(f"scale={W}:{H}")
    elif mode == "fill":
        rx, ry = max(0.0, min(1.0, im.reframe_x)), max(0.0, min(1.0, im.reframe_y))
        ch.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H}:x='(iw-ow)*{rx:.4f}':y='(ih-oh)*{ry:.4f}'")
    elif mode == "blur":
        sw_, sh_ = max(2, W // 6 // 2 * 2), max(2, H // 6 // 2 * 2)
        pre = ",".join(ch + ["split=2[bg%s][fg%s]" % (tag, tag)])
        bg = (f"[bg{tag}]scale={sw_}:{sh_}:force_original_aspect_ratio=increase,crop={sw_}:{sh_},gblur=sigma=5,"
              f"scale={W}:{H},eq=brightness=-0.12[bgb{tag}]")
        fg = f"[fg{tag}]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs{tag}]"
        return f"{pre};{bg};{fg};[bgb{tag}][fgs{tag}]overlay=(W-w)/2:(H-h)/2,{tail}"
    else:
        ch.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black")
    ch.append(tail)
    return ",".join(ch)


def _clip_audio(k: int, seg) -> str:
    """Audio di un pezzo di clip, lungo esattamente quanto il suo video, con microdissolvenze che evitano i «click» ai tagli."""
    L, f = seg.length, 0.008
    if seg.clip.has_audio:
        src = f"[{k}:a:0]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS"
    else:
        src = "anullsrc=r=48000:cl=stereo"
    return (f"{src},apad=whole_dur={L:.4f},atrim=end={L:.4f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={f},afade=t=out:st={max(0.0, L - f):.4f}:d={f}")


def _stack_second(g: "_G", sp, W: int, top_h: int, gap_h: int, bot_h: int, D: float, fps: float, notes: list[str]) -> None:
    """Secondo video nel suo riquadro (riempie, con inquadratura regolabile) e i due riquadri uno sopra l'altro → [vc]."""
    from .media_scan import media_info
    h2 = bot_h if sp.main_on_top else top_h
    rx = max(0.0, min(1.0, sp.second_x))
    k = g.inp("-stream_loop", "-1", "-ss", f"{max(0.0, sp.second_start):.3f}", "-i", str(sp.path))
    g.f.append(f"[{k}:v:0]scale={W}:{h2}:force_original_aspect_ratio=increase,crop={W}:{h2}:x='(iw-ow)*{rx:.4f}':y='(ih-oh)*0.5',"
               f"fps={fps:.5f},setsar=1,format=yuv420p,trim=duration={D:.4f},setpts=PTS-STARTPTS[v2]")
    parts = ["[vcm]", "[v2]"] if sp.main_on_top else ["[v2]", "[vcm]"]
    if gap_h:
        c = g.inp("-f", "lavfi", "-i", f"color=c=black:s={W}x{gap_h}:r={fps:.5f}:d={D + 1:.3f}")
        parts.insert(1, f"[{c}:v:0]")
    g.f.append("".join(parts) + f"vstack=inputs={len(parts)}[vc]")
    g.second_audio = False
    if sp.second_audio:
        try:
            has = media_info(sp.path).has_audio
        except Exception:  # noqa: BLE001 - se non si riesce a leggere, il secondo video resta muto
            has = False
        if has:
            g.f.append(f"[{k}:a:0]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume={sp.second_db:.1f}dB,"
                       f"atrim=end={D:.4f},asetpts=PTS-STARTPTS[a2]")
            g.f.append("[acat][a2]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[acat2]")
            g.second_audio = True
        else:
            notes.append("Il secondo video non ha audio: si sente solo il tuo.")


def _add_clip_overlays(g: "_G", cur: str, els: list[Element], W: int, H: int, D: float, notes: list[str]) -> str:
    """Overlay animati (video o GIF, anche con sfondo trasparente): uno per elemento, per tutta la sua durata."""
    for el in els:
        if el.kind != "clip" or not el.visible:
            continue
        if not el.path or not Path(el.path).exists():
            notes.append(f"Overlay non trovato: {Path(el.path).name or 'senza nome'}.")
            continue
        a = max(0.0, el.start)
        b = D if el.end is None else min(el.end, D)
        if b - a < 0.05:
            continue
        ext = Path(el.path).suffix.lower()
        args = ["-c:v", "libvpx-vp9"] if ext == ".webm" else []                # il decoder predefinito perde la trasparenza
        if el.loop:
            args = ["-stream_loop", "-1", *args]
        k = g.inp(*args, "-i", el.path)
        lab, out = _lab("c"), _lab("o")
        w = max(2, round(el.width * W / 2) * 2)
        op = f",colorchannelmixer=aa={el.opacity:.3f}" if el.opacity < 0.999 else ""
        fade = ""
        if el.anim_in.kind != "none":
            fade += f",fade=t=in:st={a:.3f}:d={max(0.05, el.anim_in.duration):.3f}:alpha=1"
        if el.anim_out.kind != "none":
            fade += f",fade=t=out:st={max(a, b - el.anim_out.duration):.3f}:d={max(0.05, el.anim_out.duration):.3f}:alpha=1"
        g.f.append(f"[{k}:v:0]format=rgba,scale={w}:-2,fps={g.fps:.5f}{op},setpts=PTS-STARTPTS+{a:.4f}/TB{fade}[{lab}]")
        g.f.append(f"[{cur}][{lab}]overlay=x={el.x * W:.2f}-w/2:y={el.y * H:.2f}-h/2:enable='between(t,{a:.4f},{b:.4f})':"
                   f"eof_action={'repeat' if el.loop else 'pass'}:shortest=0:format=auto[{out}]")
        cur = out
    return cur


def _fpath(p: Path) -> str:
    """Percorso dentro un filtro ffmpeg: barre dritte e due punti protetti (C\\:/...)."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _mix_music(g, spec: RenderSpec, D: float, music: str) -> None:
    """Musica di sottofondo sotto il video principale, con abbassamento automatico quando c'è voce ([vox] → [amain])."""
    au = spec.audio
    m = g.inp("-stream_loop", "-1", "-i", music)
    fade = max(0.0, min(au.music_fade, D / 3))
    chain = [f"atrim=end={D + 1:.3f}", "asetpts=PTS-STARTPTS", "aformat=sample_rates=48000:channel_layouts=stereo",
             "loudnorm=I=-16:TP=-2:LRA=11", "aformat=sample_rates=48000:channel_layouts=stereo",
             f"volume={au.music_db:.1f}dB", f"atrim=end={D:.4f}", "asetpts=PTS-STARTPTS"]
    if fade > 0:
        chain += [f"afade=t=in:st=0:d={fade:.2f}", f"afade=t=out:st={max(0.0, D - fade):.3f}:d={fade:.2f}"]
    if au.music_duck:
        depth = max(1.0, abs(au.music_duck_db))                 # dB da togliere mentre si parla (stima: dipende dal volume della voce)
        ratio = min(20.0, max(1.5, 1.0 / max(0.05, 1.0 - depth / 20.0)))
        g.f.append("[vox]asplit=2[vmix][vsc]")
        g.f.append(f"[{m}:a:0]{','.join(chain)}[mus]")
        g.f.append(f"[mus][vsc]sidechaincompress=threshold=0.02:ratio={ratio:.2f}:attack=40:release=700:makeup=1[musd]")
        g.f.append("[vmix][musd]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[amain]")
    else:
        g.f.append(f"[{m}:a:0]{','.join(chain)}[mus]")
        g.f.append("[vox][mus]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[amain]")


def _fade_of(scene: Scene) -> float:
    """Durata della transizione di una scena; «taglio netto» = nessuna sovrapposizione."""
    return 0.0 if scene.transition == "cut" else scene.fade


def _join_dips(segs, tid: str, dur: float) -> str:
    """Stacco tra due clip senza accorciare il video (l'audio esterno resta in sincronia): dissolvenza al nero o flash."""
    tr = transitions.get(tid)
    if not tr.join or not tr.color or dur <= 0 or len(segs) < 2:
        return ""
    half, parts, pos = dur / 2, [], 0.0
    for s in segs[:-1]:
        pos += s.length
        parts.append(f"fade=t=out:st={max(0.0, pos - half):.3f}:d={half:.3f}:color={tr.color}")
        parts.append(f"fade=t=in:st={pos:.3f}:d={half:.3f}:color={tr.color}")
    return ",".join(parts)


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


def _graphics_elements(spec: RenderSpec, D: float, W: int = 1920, H: int = 1080) -> list[Element]:
    gr = spec.graphics
    els = anchors.resolve(substitute([e for e in gr.elements if "main" in e.targets], spec.variables), W, H, spec.brand.safe)
    els += brand_elements(spec, W, H)                       # loghi del kit del marchio
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
          encoder: str | None = None, slide_images: list[QImage] | None = None,
          ranges: list[tuple[float, float]] | None = None) -> BuildResult:
    global _counter
    _counter = 0
    workdir.mkdir(parents=True, exist_ok=True)
    im, gr = spec.image, spec.graphics
    W, H = output_size(im, spec.export)
    ref = clips[0]
    fps = im.fps or ref.fps or 30.0
    h_short = min(W, H)
    ranges = ranges or edl.ranges_for(p, t0, t1)
    social = p.kind == "social"
    D = edl.total_len(ranges)
    if D < 1.0:
        raise FFmpegError("L'intervallo di taglio è vuoto o troppo corto")
    enc = encoder or encoders.resolve_encoder(spec.export.encoder)
    g = _G(fps)
    notes: list[str] = []
    frames = 0

    # --- 1. clip → [vc]
    segs = [s for a, b in ranges for s in plan_segments(clips, a, b)]
    if not segs:
        raise FFmpegError("Nessuna parte del video da esportare")
    sp = spec.split
    split = social and sp.enabled and bool(sp.path) and Path(sp.path).exists()
    if social and sp.enabled and not split:
        notes.append("Secondo video non trovato: il reel esce con un solo video.")
    top_h, gap_h, bot_h = split_heights(sp, H) if split else (0, 0, 0)
    Hm = (top_h if sp.main_on_top else bot_h) if split else H            # altezza del riquadro del tuo video
    for s in segs:
        k = g.inp("-ss", f"{s.ss:.6f}", "-t", f"{s.length:.6f}", "-i", str(s.clip.path))
        g.f.append(f"[{k}:v:0]{_main_chain_for_clip(s.clip, spec, W, Hm, fps, str(k), social)}[v{k}]")
        if social:
            g.f.append(f"{_clip_audio(k, s)}[a{k}]")
    n = len(segs)
    dips = ""
    if social:
        vcat = "vcm" if split else "vc"
        g.f.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[{vcat}][acat]")
        if split:
            _stack_second(g, sp, W, top_h, gap_h, bot_h, D, fps, notes)
    elif n == 1:
        g.f.append("[v0]null[vc]")
    else:
        g.f.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
        dips = _join_dips(segs, im.clip_transition, im.clip_transition_dur)
        if dips:
            g.f.append(f"[vc]{dips}[vcd]")
    cur = "vcd" if dips else "vc"
    if im.kenburns and not split:
        g.f.append(f"[{cur}]{kenburns_filter(spec, W, H, t0)}[vk]")
        cur = "vk"

    # --- 2. slide / PiP
    sls = spec.slides
    if sls.enabled and (sls.files or sls.video):
        cur = _add_slides(g, cur, sls, slide_images or [], W, H, fps, D, workdir, t0, p)

    # --- 3. grafica sul video principale
    els = _graphics_elements(spec, D, W, H)
    layers = compositor.plan_layers(els, W, H, D, fps, workdir, "m")
    frames += sum(l.frames for l in layers)
    cur = add_layers(g, cur, layers)
    cur = _add_clip_overlays(g, cur, els, W, H, D, notes)

    # --- 3b. sottotitoli (libass), sopra tutto il resto del video principale
    sub = spec.subtitles
    fonts = Path(__file__).resolve().parent / "resources" / "fonts"
    if sub.enabled and subtitles.write_ass(sub, ranges, W, H, workdir / "subs.ass", fonts):
        g.f.append(f"[{cur}]ass=filename='{_fpath(workdir / 'subs.ass')}':fontsdir='{_fpath(fonts)}'[vsub]")
        cur = "vsub"
    elif sub.enabled:
        notes.append("Sottotitoli attivi ma nessuna riga nell'intervallo scelto: non vengono aggiunti.")

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
    if social:
        src = "[acat2]" if split and g.second_audio else "[acat]"   # audio delle stesse clip, già tagliato insieme al video
        achain = audio_fx.voice_chain(voice)
        if spec.audio.loudnorm:
            achain.append("loudnorm=I=-14:TP=-1.5:LRA=11")   # livello tipico dei social, in una sola passata
    else:
        a_in = g.inp("-i", p.audio)
        src = f"[{a_in}:a:0]"
        achain = [audio_filter(p, t0)] + audio_fx.voice_chain(voice)
        if spec.audio.loudnorm and loud:
            achain.append(audio_fx.loudnorm_apply_filter(loud))
    achain += [f"atrim=end={D:.4f}", "asetpts=PTS-STARTPTS", "aformat=sample_rates=48000:channel_layouts=stereo"]
    if im.fade_in > 0:
        achain.append(f"afade=t=in:st=0:d={im.fade_in:.3f}")
    if im.fade_out > 0:
        achain.append(f"afade=t=out:st={max(0, D - im.fade_out):.3f}:d={im.fade_out:.3f}")
    music = spec.audio.music_path
    if music and Path(music).exists():
        g.f.append(f"{src}{','.join(achain)}[vox]")
        _mix_music(g, spec, D, music)
    else:
        g.f.append(f"{src}{','.join(achain)}[amain]")

    # --- 6. scene (titolo, outro, credito)
    seq: list[tuple[str, str, float, float, str]] = []   # (video, audio, durata, durata transizione dalla precedente, effetto)
    extra = 0.0
    if with_scenes:
        if gr.title.enabled and not gr.title.over_video:
            v, a, d, fr = _scene(g, gr.title, "title", W, H, fps, workdir, "t", extra=substitute([e for e in gr.elements if "title" in e.targets], spec.variables), variables=spec.variables)
            seq.append((v, a, d, 0.0, "cut"))
            frames += fr
            extra += d
    seq.append(("vmain", "amain", D, _fade_of(gr.title) if (with_scenes and gr.title.enabled and not gr.title.over_video) else 0.0, gr.title.transition))
    if with_scenes:
        if gr.outro.enabled:
            v, a, d, fr = _scene(g, gr.outro, "outro", W, H, fps, workdir, "u", extra=substitute([e for e in gr.elements if "outro" in e.targets], spec.variables), variables=spec.variables)
            seq.append((v, a, d, _fade_of(gr.outro), gr.outro.transition))
            frames += fr
            extra += d
        if spec.credit.enabled:
            qr = credit.qr_png(workdir / "qr.png") if spec.credit.qr else None
            cs = credit.credit_scene(spec.credit.duration, qr)
            v, a, d, fr = _scene(g, cs, "outro", W, H, fps, workdir, "c", fade_inout=credit.FADE)
            seq.append((v, a, d, 0.0, "cut"))
            frames += fr
            extra += d

    cv, ca, clen = seq[0][:3]
    for i, (nv, na, nl, f, tr) in enumerate(seq[1:], 1):
        ov, oa = f"xv{i}", f"xa{i}"
        if f > 0:
            f = min(f, clen / 2, nl / 2)
            g.f.append(f"[{cv}][{nv}]xfade=transition={transitions.get(tr).xfade or 'fade'}:duration={f:.3f}:offset={clen - f:.4f}[{ov}]")
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
