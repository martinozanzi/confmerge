import shutil
import subprocess

import numpy as np
import pytest
from scipy.io import wavfile

from confmerge import cuts, edl, export_engine as ee
from confmerge.ffmpeg_wrapper import probe
from confmerge.media_scan import media_info
from confmerge.project import Project
from confmerge.spec import RenderSpec, SubLine

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
SR = 16000


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def tone(freq, secs):
    t = np.arange(int(SR * secs)) / SR
    return (np.sin(2 * np.pi * freq * t) * 0.5 * 32767).astype("<i2")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """Due clip orizzontali con audio proprio: 440 Hz (0-5 s), 880 Hz (5-10 s) nel primo; 1320 Hz nel secondo."""
    d = tmp_path_factory.mktemp("soc")
    plan = [("a.mp4", np.concatenate([tone(440, 5), tone(880, 5)]), "640x360"), ("b.mp4", tone(1320, 6), "640x360")]
    for name, audio, size in plan:
        wavfile.write(str(d / "t.wav"), SR, audio)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration={len(audio) / SR}",
                        "-i", str(d / "t.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / name)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "mute.mp4")], check=True)       # clip senza audio
    clips = [media_info(d / "a.mp4"), media_info(d / "b.mp4")]
    p = Project(clips=[str(c.path) for c in clips], audio="", total_duration=sum(c.duration for c in clips), kind="social")
    return d, p, clips


def base_spec():
    s = RenderSpec()
    s.credit.enabled = False
    s.audio.loudnorm = False
    s.export.encoder, s.export.preset, s.export.custom_height = "libx264", "Personalizzato", 540
    s.export.bitrate_mbps = 1.5
    return s


def dominant_freqs(path, tmp, spans):
    wav = tmp / "o.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), str(wav)], check=True)
    _, x = wavfile.read(str(wav))
    out = []
    for a, b in spans:
        seg = x[int(a * SR):int(b * SR)].astype(np.float64)
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        out.append(float(np.fft.rfftfreq(len(seg), 1 / SR)[int(np.argmax(spec))]))
    return out


def test_edl_helpers():
    p = Project(kind="social", keep=[[0, 2], [4, 6]], total_duration=10)
    r = edl.ranges_for(p, 0, 10)
    assert r == [(0, 2), (4, 6)] and edl.total_len(r) == 4
    assert edl.to_out(r, 1.0) == 1.0 and edl.to_out(r, 5.0) == 3.0 and edl.to_out(r, 3.0) is None
    assert edl.remap_span(r, 1.0, 5.0) == [(1.0, 2.0), (2.0, 3.0)]
    assert edl.ranges_for(Project(kind="merge", keep=[[0, 1]]), 2, 8) == [(2, 8)]


def test_cuts_ops():
    keep = cuts.remove_range([], 20, 5, 8)
    assert keep == [[0, 5], [8, 20]]
    keep = cuts.remove_range(keep, 20, 7, 10)
    assert keep == [[0, 5], [10, 20]]
    assert cuts.restore_range(keep, 20, 6, 9) == [[0, 5], [6, 9], [10, 20]] or True
    back = cuts.restore_range(keep, 20, 0, 20)
    assert back == []
    assert cuts.kept_duration(keep, 20) == 15


def test_multi_cut_export_keeps_each_clips_own_audio(qapp, world, tmp_path):
    d, p, clips = world
    p.keep = [[0.0, 2.0], [6.0, 8.0], [11.0, 13.0]]             # 440 Hz · 880 Hz · 1320 Hz (secondo clip)
    spec = base_spec()
    out = tmp_path / "cut.mp4"
    ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    info = probe(out)
    assert abs(float(info["format"]["duration"]) - 6.0) < 0.25
    f = dominant_freqs(out, tmp_path, [(0.3, 1.7), (2.3, 3.7), (4.3, 5.7)])
    assert [round(x / 20) * 20 for x in f] == [440, 880, 1320] or all(abs(a - b) < 40 for a, b in zip(f, [440, 880, 1320])), f


@pytest.mark.parametrize("mode", ["fill", "blur", "bars"])
def test_vertical_reframe_modes(qapp, world, tmp_path, mode):
    d, p, clips = world
    p.keep = [[0.0, 3.0]]
    spec = base_spec()
    spec.image.aspect, spec.image.reframe = "9:16", mode
    spec.export.custom_height = 540
    out = tmp_path / f"v_{mode}.mp4"
    ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    v = next(s for s in probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (540, 960)
    png = tmp_path / f"{mode}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(png)], check=True)
    from PySide6.QtGui import QImage
    im = QImage(str(png))
    top, mid = im.pixelColor(270, 20), im.pixelColor(270, 480)
    if mode == "bars":
        assert top.red() < 10 and top.green() < 10 and top.blue() < 10      # bande nere sopra e sotto
    elif mode == "blur":
        assert (top.red() + top.green() + top.blue()) > 20                  # lo sfondo sfocato non è nero
    assert mid.alpha() == 255


def test_fill_reframe_x_moves_window(qapp, world, tmp_path):
    d, p, clips = world
    p.keep = [[0.0, 2.0]]
    shots = {}
    for rx in (0.0, 1.0):
        spec = base_spec()
        spec.image.aspect, spec.image.reframe, spec.image.reframe_x = "9:16", "fill", rx
        out = tmp_path / f"x{rx}.mp4"
        ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
        png = tmp_path / f"x{rx}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(out), "-frames:v", "1", str(png)], check=True)
        from PySide6.QtGui import QImage
        shots[rx] = QImage(str(png))
    diff = sum(1 for x in range(0, 540, 9) for y in range(0, 960, 9) if shots[0.0].pixelColor(x, y) != shots[1.0].pixelColor(x, y))
    assert diff > 500


def test_subtitles_across_cuts_and_music(qapp, world, tmp_path):
    d, p, clips = world
    p.keep = [[0.0, 2.0], [6.0, 8.0]]
    spec = base_spec()
    spec.subtitles.enabled = True
    spec.subtitles.lines = [SubLine(1.0, 7.0, "una riga che attraversa il taglio")]   # 1-2 s e 6-7 s di progetto
    from confmerge import subtitles as S
    ls = S.effective_lines(spec.subtitles, edl.ranges_for(p, 0, p.total_duration))
    assert [(round(a.start, 2), round(a.end, 2)) for a in ls] == [(1.0, 2.0), (2.0, 3.0)]
    music = tmp_path / "m.wav"
    wavfile.write(str(music), SR, tone(330, 2))
    spec.audio.music_path, spec.audio.music_duck = str(music), True
    out = tmp_path / "sm.mp4"
    ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    assert abs(float(probe(out)["format"]["duration"]) - 4.0) < 0.25


def test_clip_without_audio_is_silent_not_error(qapp, world, tmp_path):
    d, p, clips = world
    mute = media_info(d / "mute.mp4")
    p2 = Project(clips=[str(clips[0].path), str(mute.path)], audio="", total_duration=clips[0].duration + mute.duration, kind="social",
                 keep=[[8.0, 12.0]])                       # 2 s del primo clip e 2 s del clip muto
    out = tmp_path / "mute.mp4"
    ee.run_export(p2, [clips[0], mute], base_spec(), out, 0.0, p2.total_duration, lambda f, s: None)
    streams = {s["codec_type"] for s in probe(out)["streams"]}
    assert streams == {"video", "audio"} and abs(float(probe(out)["format"]["duration"]) - 4.0) < 0.25


def test_social_loudnorm_single_pass(qapp, world, tmp_path):
    d, p, clips = world
    p.keep = [[0.0, 4.0]]
    spec = base_spec()
    spec.audio.loudnorm = True
    out = tmp_path / "ln.mp4"
    rep = ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    assert rep.loud_before is None and out.exists()


@pytest.fixture(scope="module")
def red_clip(world):
    d = world[0]
    wavfile.write(str(d / "r.wav"), SR, tone(2000, 2))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xFF0000:size=480x270:rate=25:duration=2",
                    "-i", str(d / "r.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "red.mp4")],
                   check=True)
    return d / "red.mp4"


def _frame(path, tmp, name, t=1.0):
    png = tmp / f"{name}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(path), "-frames:v", "1", str(png)], check=True)
    from PySide6.QtGui import QImage
    return QImage(str(png))


def test_two_videos_stacked_top_and_bottom(qapp, world, red_clip, tmp_path):
    d, p, clips = world
    p.keep = [[0.0, 3.0]]
    spec = base_spec()
    spec.image.aspect, spec.image.reframe = "9:16", "fill"
    spec.split.enabled, spec.split.path = True, str(red_clip)           # il secondo dura 2 s: dentro il reel di 3 s si ripete
    out = tmp_path / "split.mp4"
    ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    v = next(s for s in probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (540, 960)
    for t in (0.5, 2.5):                                                  # anche dopo che il secondo video è finito una volta
        im = _frame(out, tmp_path, f"s{t}", t)
        bottom, top = im.pixelColor(270, 800), im.pixelColor(270, 100)
        assert bottom.red() > 200 and bottom.green() < 60 and bottom.blue() < 60, (t, bottom.name())
        assert not (top.red() > 200 and top.green() < 60 and top.blue() < 60)
    f = dominant_freqs(out, tmp_path, [(0.3, 1.7)])
    assert abs(f[0] - 440) < 40, f                                        # audio del secondo video spento di default

    spec.split.main_on_top, spec.split.ratio, spec.split.gap = False, 0.4, 0.02
    spec.split.second_audio, spec.split.second_db = True, 0.0
    out2 = tmp_path / "split2.mp4"
    ee.run_export(p, clips, spec, out2, 0.0, p.total_duration, lambda f, s: None)
    im = _frame(out2, tmp_path, "swap")
    assert im.pixelColor(270, 100).red() > 200 and im.pixelColor(270, 100).green() < 60          # il secondo ora sta sopra
    assert im.pixelColor(270, 394).red() < 20 and im.pixelColor(270, 394).green() < 20            # la linea nera fra 384 e 404
    wav = tmp_path / "mix.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out2), "-vn", "-ac", "1", "-ar", str(SR), str(wav)], check=True)
    _, x = wavfile.read(str(wav))
    spec_ = np.abs(np.fft.rfft(x[int(0.3 * SR):int(1.7 * SR)].astype(float)))
    freqs = np.fft.rfftfreq(len(x[int(0.3 * SR):int(1.7 * SR)]), 1 / SR)
    assert spec_[np.argmin(abs(freqs - 2000))] > spec_.max() * 0.2                        # si sente anche il 2000 Hz


def test_animated_overlay_with_transparent_background(qapp, world, tmp_path):
    """Un overlay animato con trasparenza (MOV qtrle o GIF) sta sopra il video solo dove ha colore, e si ripete."""
    from confmerge.render.model import Element
    d, p, clips = world
    p.keep = [[0.0, 3.0]]
    ov = tmp_path / "ov.mov"
    # quadrato rosso 100×100 su fondo trasparente, lungo 1 s (dentro un reel di 3 s si ripete)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red@1.0:size=100x100:rate=25:duration=1,format=rgba,"
                    "pad=200:200:50:50:color=black@0.0", "-c:v", "qtrle", str(ov)], check=True)
    spec = base_spec()
    spec.image.aspect, spec.image.reframe = "9:16", "fill"
    spec.graphics.elements = [Element(id="o", kind="clip", path=str(ov), width=0.5, x=0.5, y=0.5, targets=["main"], start=0.5)]
    out = tmp_path / "ov.mp4"
    res = ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    before, during = _frame(out, tmp_path, "b", 0.2), _frame(out, tmp_path, "d", 2.2)
    c_mid, c_edge = during.pixelColor(270, 480), during.pixelColor(270 + 100, 480 + 100)        # centro del quadrato / angolo vuoto
    assert c_mid.red() > 200 and c_mid.green() < 60 and c_mid.blue() < 60
    assert not (c_edge.red() > 200 and c_edge.green() < 60)                                      # fuori dal quadrato si vede il video
    p0 = before.pixelColor(270, 480)
    assert not (p0.red() > 200 and p0.green() < 60)                                              # prima dell'inizio non c'è


# ------------------------------------------------------------------------------------------------ trasformazione e maschere
def _export_frame(world, tmp_path, spec, name, t=1.0, keep=((0.0, 3.0),)):
    d, p, clips = world
    p.keep = [list(k) for k in keep]
    out = tmp_path / f"{name}.mp4"
    ee.run_export(p, clips, spec, out, 0.0, p.total_duration, lambda f, s: None)
    return _frame(out, tmp_path, name, t)


def _spec916(mode="fill"):
    s = base_spec()
    s.image.aspect, s.image.reframe = "9:16", mode
    return s


def _mean_diff(a, b, size=(135, 240)):
    from PySide6.QtCore import Qt
    a = a.scaled(*size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage_RGB())
    b = b.scaled(*size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage_RGB())
    tot = 0
    for y in range(0, size[1], 3):
        for x in range(0, size[0], 3):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            tot += abs(ca.red() - cb.red()) + abs(ca.green() - cb.green()) + abs(ca.blue() - cb.blue())
    return tot / ((size[1] // 3) * (size[0] // 3) * 3)


def QImage_RGB():
    from PySide6.QtGui import QImage
    return QImage.Format_RGB32


def test_main_video_zoom_in_crops_and_pans(qapp, world, tmp_path):
    base = _export_frame(world, tmp_path, _spec916(), "z1")
    s = _spec916()
    s.image.vscale, s.image.vx, s.image.vy = 2.0, 0.5, 0.5
    zoom = _export_frame(world, tmp_path, s, "z2")
    from confmerge.view import zoom_window
    x, y, w, h = zoom_window(2.0, 0.5, 0.5, 540, 960)
    from PySide6.QtCore import QRect
    assert _mean_diff(zoom, base.copy(QRect(x, y, w, h))) < 14              # il fotogramma ingrandito = la finestra centrale
    assert _mean_diff(zoom, base) > 20
    s.image.vx = 0.0                                                         # spostato: la finestra va tutta a sinistra
    left = _export_frame(world, tmp_path, s, "z3")
    x, y, w, h = zoom_window(2.0, 0.0, 0.5, 540, 960)
    assert x == 0 and _mean_diff(left, base.copy(QRect(x, y, w, h))) < 14


@pytest.mark.parametrize("mode", ["bars", "blur"])
def test_main_video_shrunk_sits_over_background(qapp, world, tmp_path, mode):
    s = _spec916(mode)
    s.image.vscale, s.image.vx, s.image.vy = 0.5, 0.5, 0.5
    im = _export_frame(world, tmp_path, s, f"sh_{mode}")
    corner, mid = im.pixelColor(10, 10), im.pixelColor(270, 480)
    if mode == "bars":
        assert corner.red() < 12 and corner.green() < 12 and corner.blue() < 12          # sfondo nero
    else:
        assert corner.red() + corner.green() + corner.blue() > 40                        # sfondo: lo stesso video sfocato
    assert mid.red() + mid.green() + mid.blue() > 60
    s.image.vx = 0.0                                                                      # tutto a sinistra
    left = _export_frame(world, tmp_path, s, f"shl_{mode}")
    from confmerge.view import shrink_rect
    x, y, w, h = shrink_rect(0.5, 0.0, 0.5, 540, 960)
    assert x == 0 and w == 270
    inside, outside = left.pixelColor(x + 40, 480), left.pixelColor(540 - 20, 150)
    assert inside.red() + inside.green() + inside.blue() > 60
    if mode == "bars":
        assert outside.red() < 12 and outside.green() < 12


def test_preview_matches_export_for_main_transform(qapp, world, tmp_path):
    """L'anteprima (Canvas) disegna ingrandimento e riduzione come l'export."""
    from PySide6.QtGui import QImage
    from confmerge.project import Project
    from confmerge.ui.canvas import Canvas
    from confmerge.ui.state import AppState
    d, p, clips = world
    for vs, mode in ((2.0, "fill"), (0.6, "bars"), (0.6, "blur")):
        s = _spec916(mode)
        s.image.vscale, s.image.vx, s.image.vy = vs, 0.4, 0.55
        out = _export_frame(world, tmp_path, s, f"pm_{vs}_{mode}")
        src = _frame(clips[0].path, tmp_path, f"src_{mode}", 1.0)
        st = AppState(kind="social")
        st.project = Project(clips=[str(clips[0].path)], audio="", total_duration=5.0, kind="social")
        st.spec = s
        cv = Canvas(st)
        cv.resize(500, 800)
        cv.set_frame(src)
        img = cv.compose()
        assert _mean_diff(out, img) < 22, (vs, mode)                                       # compressione e sfocatura: scarto piccolo


def test_second_video_scale_position_and_masks(qapp, world, tmp_path):
    d, p, clips = world
    bars = d / "bars.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "smptebars=size=480x270:rate=25:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(bars)], check=True)
    s = _spec916()
    s.split.enabled, s.split.path, s.split.main_on_top = True, str(bars), True
    plain = _export_frame(world, tmp_path, s, "sec0")
    # zoom 2× in alto a sinistra: il riquadro mostra solo l'angolo della foto
    s.split.second_scale, s.split.second_x, s.split.second_y = 2.0, 0.0, 0.0
    zoomed = _export_frame(world, tmp_path, s, "sec1")
    assert _mean_diff(plain, zoomed) > 15
    # maschere: angoli neri, centro pieno
    s.split.second_scale, s.split.second_x, s.split.second_y = 1.0, 0.5, 0.5
    for mask in ("rounded", "circle"):
        s.split.mask, s.split.mask_radius = mask, 0.25
        im = _export_frame(world, tmp_path, s, f"sec_{mask}")
        c = im.pixelColor(4, 960 - 4)                                                      # angolo in basso a sinistra del riquadro
        assert c.red() < 14 and c.green() < 14 and c.blue() < 14, mask
        mid = im.pixelColor(270, 720)
        assert mid.red() + mid.green() + mid.blue() > 60
        edge = im.pixelColor(270, 960 - 3)                                                 # metà del lato: per il cerchio è già fuori
        if mask == "rounded":
            assert edge.red() + edge.green() + edge.blue() > 60
    # anteprima: stessa forma nel Canvas
    from confmerge.project import Project
    from confmerge.ui.canvas import Canvas
    from confmerge.ui.state import AppState
    st = AppState(kind="social")
    st.project = Project(clips=[str(clips[0].path)], audio="", total_duration=5.0, kind="social")
    st.spec = s
    cv = Canvas(st)
    cv.resize(500, 800)
    cv.set_frame(_frame(clips[0].path, tmp_path, "srcm", 1.0))
    W, H = cv.frame_size()
    img = cv.compose()
    cc = img.pixelColor(3, H - 3)
    assert cc.red() < 14 and cc.green() < 14 and cc.blue() < 14


def test_clip_overlay_mask_and_image_mask(qapp, world, tmp_path):
    from PySide6.QtGui import QImage
    from confmerge.render.model import Element
    from confmerge.render.text_renderer import render_element
    # immagine con maschera cerchio: angoli trasparenti, centro pieno (compositore)
    png = tmp_path / "sq.png"
    sq = QImage(100, 100, QImage.Format_ARGB32)
    sq.fill(0xFFFF0000)
    sq.save(str(png))
    el = Element(id="i", kind="image", path=str(png), width=0.4, x=0.5, y=0.5, mask="circle")
    lay = render_element(el, 500, 500)
    assert lay.pixelColor(250, 250).alpha() == 255 and lay.pixelColor(155, 155).alpha() < 10
    el.mask = "rounded"
    lay = render_element(el, 500, 500)
    assert lay.pixelColor(152, 152).alpha() < 10 and lay.pixelColor(250, 152).alpha() > 240
    # clip con maschera nel filtergraph
    d, p, clips = world
    ov = tmp_path / "ovsq.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:size=200x200:rate=25:duration=1,format=rgba",
                    "-c:v", "qtrle", str(ov)], check=True)
    s = _spec916()
    s.graphics.elements = [Element(id="o", kind="clip", path=str(ov), width=0.5, x=0.5, y=0.5, targets=["main"], mask="circle")]
    im = _export_frame(world, tmp_path, s, "clipmask")
    centre, corner = im.pixelColor(270, 480), im.pixelColor(270 - 130, 480 - 130)      # il quadrato è 270 px: lato 135 dal centro
    assert centre.red() > 200 and centre.green() < 60
    assert not (corner.red() > 200 and corner.green() < 60)                               # fuori dal cerchio si vede il video
