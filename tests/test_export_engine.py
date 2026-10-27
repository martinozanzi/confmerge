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


def test_transitions_all_export(qapp, project, tmp_path):
    """Ogni transizione produce un file valido; la durata resta quella attesa (titolo + video + finale - sovrapposizioni)."""
    from confmerge import transitions
    d, rep = project
    base = None
    for t in transitions.TRANSITIONS:
        spec = RenderSpec()
        spec.graphics.title = Scene(True, 2.0, Background("solid", "#102040"), [Element(id="t", text="Titolo", size=0.1)],
                                    fade=t.duration or 0.5, transition=t.id)
        spec.graphics.outro = Scene(True, 2.0, Background("black"), [Element(id="o", text="Fine", size=0.1)],
                                    fade=t.duration or 0.5, transition=t.id)
        spec.credit.enabled = False
        spec.image.clip_transition = transitions.nearest_join(t.id)
        spec.export.encoder, spec.export.preset, spec.export.custom_height = "libx264", "Personalizzato", 360
        spec.export.bitrate_mbps = 1.0
        out = tmp_path / f"t_{t.id}.mp4"
        r = ee.run_export(rep.project, rep.clips, spec, out, 5.0, 33.0, lambda f, s: None)
        dur = float(probe(out)["format"]["duration"])
        f = 0.0 if t.id == "cut" else min(t.duration, 1.0)
        assert abs(dur - (2.0 + 28.0 + 2.0 - 2 * f)) < 0.6, (t.id, dur)
        if base is None:
            base = dur


def test_subtitles_burned_in(qapp, project, tmp_path):
    """Le righe finiscono nel video: il fotogramma con il sottotitolo ha pixel chiari in basso che senza non ci sono."""
    from confmerge.spec import SubLine
    d, rep = project
    base = RenderSpec()
    base.credit.enabled = False
    base.export.encoder, base.export.preset, base.export.custom_height = "libx264", "Personalizzato", 360
    base.export.bitrate_mbps = 1.0
    spec = RenderSpec.from_dict(base.to_dict())
    spec.subtitles.enabled = True
    spec.subtitles.lines = [SubLine(7.0, 9.0, "Questo è un sottotitolo di prova abbastanza lungo da andare a capo sul video"),
                            SubLine(500.0, 502.0, "fuori intervallo")]
    outs = {}
    for name, sp in (("no", base), ("si", spec)):
        out = tmp_path / f"{name}.mp4"
        ee.run_export(rep.project, rep.clips, sp, out, 5.0, 15.0, lambda f, s: None)
        png = tmp_path / f"{name}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "3", "-i", str(out), "-frames:v", "1", str(png)], check=True)
        outs[name] = png
    from PySide6.QtGui import QImage
    a, b = QImage(str(outs["no"])), QImage(str(outs["si"]))
    assert a.size() == b.size()
    diff = sum(1 for y in range(int(b.height() * 0.7), b.height()) for x in range(0, b.width(), 2)
               if a.pixelColor(x, y) != b.pixelColor(x, y))
    top = sum(1 for y in range(0, int(b.height() * 0.5)) for x in range(0, b.width(), 2)
              if a.pixelColor(x, y) != b.pixelColor(x, y))
    assert diff > 1000 and top < diff / 10, (diff, top)      # il resto cambia solo per il rumore di codifica


def test_background_music_with_ducking(qapp, project, tmp_path):
    d, rep = project
    music = tmp_path / "m.wav"
    sr = 22050
    t = np.arange(sr * 3) / sr
    wavfile.write(str(music), sr, (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype("<i2"))   # più corta del video: va in loop
    rms = {}
    for name, (use, duck) in {"no": (False, False), "mix": (True, False), "duck": (True, True)}.items():
        spec = RenderSpec()
        spec.credit.enabled = False
        spec.export.encoder, spec.export.preset, spec.export.custom_height = "libx264", "Personalizzato", 360
        spec.export.bitrate_mbps = 1.0
        spec.audio.loudnorm = False
        if use:
            spec.audio.music_path, spec.audio.music_duck, spec.audio.music_db = str(music), duck, -6.0
        out = tmp_path / f"{name}.mp4"
        ee.run_export(rep.project, rep.clips, spec, out, 5.0, 17.0, lambda f, s: None)
        assert abs(float(probe(out)["format"]["duration"]) - 12.0) < 0.5
        wav = tmp_path / f"{name}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
        _, x = wavfile.read(str(wav))
        rms[name] = float(np.sqrt(np.mean((x.astype(np.float64) / 32768) ** 2)))
    assert rms["mix"] > rms["no"] * 1.05              # la musica si sente
    assert rms["duck"] < rms["mix"]                   # e con l'abbassamento è più bassa del mix semplice


def test_subtitle_controller_end_to_end(qapp, project, tmp_path, monkeypatch):
    """Cartella → audio del video finale → (finto) Groq → righe nello spec, con i tempi sulla linea del progetto."""
    import threading, time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import json as _json
    from PySide6.QtWidgets import QApplication
    from confmerge.settings import Settings
    from confmerge.ui.state import AppState

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            raw = _json.dumps({"segments": [{"start": 1.0, "end": 3.0, "text": " ciao a tutti", "no_speech_prob": 0}],
                               "words": [{"word": "ciao", "start": 1.0, "end": 1.5}, {"word": "a", "start": 1.5, "end": 1.7},
                                         {"word": "tutti", "start": 1.7, "end": 3.0}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("CONFMERGE_GROQ_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    d, rep = project
    st = AppState(Settings(tmp_path / "cfg"))
    st.project, st.clips = rep.project, rep.clips
    st.project.trim_start, st.project.trim_end = 5.0, 25.0
    ctl = st.subtitles
    assert "chiave" in ctl.blocker()
    st.settings.keys.set("groq", "good")
    done = []
    ctl.finished.connect(done.append)
    ctl.failed.connect(lambda m: done.append(m))
    ctl.start()
    t0 = time.time()
    while not done and time.time() - t0 < 60:
        QApplication.processEvents()
        time.sleep(0.02)
    srv.shutdown()
    assert done and isinstance(done[0], int), done
    sub = st.spec.subtitles
    assert sub.enabled and sub.lines and sub.lines[0].text.startswith("ciao a tutti")
    assert abs(sub.lines[0].start - 6.0) < 0.1 and sub.range_start == 5.0 and sub.range_end == 25.0   # 1 s del video + 5 s di inizio
