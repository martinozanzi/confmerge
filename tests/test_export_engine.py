import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from confmerge import export_engine as ee, pipeline
from confmerge.ffmpeg_wrapper import probe
from confmerge.media_scan import media_info
from confmerge.render.model import Anim, Background, Element, Fill, LowerThird, Scene
from confmerge.spec import LayoutSpan, RenderSpec, SlideChange
from conftest import make_world

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
SR = 16000


@pytest.fixture(scope="module")
def qapp(qt_app):
    return qt_app


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    d = tmp_path_factory.mktemp("eng")
    world = make_world(40, seed=3, fs=SR)
    for i, (size, name) in enumerate([("640x360", "a.mp4"), ("360x640", "b.mp4")]):  # secondo clip verticale
        wavfile.write(str(d / f"c{i}.wav"), SR, (world[i * 20 * SR:(i + 1) * 20 * SR] * 32767).astype("<i2"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration=20",
                        "-i", str(d / f"c{i}.wav"), "-t", "20", "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-metadata", f"creation_time=2026-05-01T10:00:{i * 20:02d}Z", str(d / name)], check=True)
    wavfile.write(str(d / "rec.wav"), SR, (world * 32767).astype("<i2"))
    rep = pipeline.analyze([d / "a.mp4", d / "b.mp4"], d / "rec.wav")
    # slide
    from PySide6.QtGui import QColor, QImage
    for i, col in enumerate(["#cc3333", "#33aa55"]):
        im = QImage(800, 600, QImage.Format_RGB32)
        im.fill(QColor(col))
        im.save(str(d / f"s{i}.png"))
    return d, rep


def full_spec(d):
    s = RenderSpec()
    s.image.fade_in = s.image.fade_out = 0.5
    s.image.kenburns, s.image.kb_t0, s.image.kb_t1, s.image.zoom2 = True, 2, 8, 1.4
    s.image.vertical_mode = "bars"
    s.graphics.elements = [
        Element(id="ov", text="Evento 2026", size=0.05, x=0.85, y=0.06, anim_in=Anim("fade", 0.5)),
        Element(id="bar", kind="bar", thickness=0.01, fill=Fill("gradient", "#00c2ff", "#7b2ff7"), radius=0.005),
    ]
    s.graphics.lower_thirds = [LowerThird("Mario Rossi", "Relatore", start=3, duration=5)]
    s.graphics.title = Scene(True, 3.0, Background("solid", "#102040"),
                             [Element(id="t", text="Titolo", size=0.1, bold=True, anim_in=Anim("pop", 0.6, "back"))])
    s.graphics.outro = Scene(True, 2.0, Background("black"), [Element(id="o", text="Grazie", size=0.08)])
    s.credit.duration = 2.0
    s.slides.enabled = True
    s.slides.files = [str(d / "s0.png"), str(d / "s1.png")]
    s.slides.changes = [SlideChange(0, 0), SlideChange(12, 1)]
    s.slides.layouts = [LayoutSpan(0, "speaker"), LayoutSpan(4, "slide_full"), LayoutSpan(9, "speaker_full"),
                        LayoutSpan(14, "side_by_side")]
    s.audio.highpass = True
    s.export.bitrate_mbps = 2.0
    s.export.encoder = "libx264"
    s.export.preset, s.export.custom_height = "Personalizzato", 720
    return s


def test_full_pipeline(qapp, project, tmp_path):
    d, rep = project
    spec = full_spec(d)
    out = tmp_path / "full.mp4"
    prog = []
    r = ee.run_export(rep.project, rep.clips, spec, out, 2.0, 22.0, lambda f, s: prog.append(f))
    info = probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1280, 720)
    assert v["pix_fmt"] == "yuv420p" and v["profile"] == "High"
    dur = float(info["format"]["duration"])
    # 20 s main + titolo 3 (-0.5 dissolvenza) + outro 2 (-0.5) + credito 2
    assert dur == pytest.approx(20 + 3 - 0.5 + 2 - 0.5 + 2, abs=0.3)
    assert r.loud_before and r.loud_after
    assert r.loud_after["input_i"] == pytest.approx(-14.0, abs=1.5)
    assert prog and prog[-1] == 1.0


def test_estimate_size_exact_for_bitrate(qapp, project):
    d, rep = project
    spec = full_spec(d)
    est = ee.estimate(rep.project, rep.clips, spec, 0, 30)
    assert est.size.exact and not est.approximate
    assert est.time_lo < est.time_hi and est.speed_x > 0


def test_sample_matches_estimate_filters(qapp, project, tmp_path):
    d, rep = project
    spec = full_spec(d)
    wall, speed, size = ee.render_sample(rep.project, rep.clips, spec, 5, 6, tmp_path / "s.mp4")
    assert size > 0 and speed > 0
    assert float(probe(tmp_path / "s.mp4")["format"]["duration"]) == pytest.approx(6, abs=0.3)


def test_decide_copy_and_credit_conflict(project):
    d, rep = project
    s = RenderSpec()
    s.export.preset = "Veloce (copia stream)"
    s.audio.loudnorm = False
    dec = ee.decide(s, [rep.clips[0]])
    assert dec.mode == "copy" and dec.credit_conflict
    s.graphics.elements = [Element(id="x", text="a")]
    assert ee.decide(s, [rep.clips[0]]).mode == "encode"
