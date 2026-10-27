import random
import shutil
import subprocess

import numpy as np
import pytest
from scipy.io import wavfile

from confmerge import pipeline, proxy, sync
from confmerge.ffmpeg_wrapper import decode_audio_mono, probe
from conftest import make_world

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
SR = 16000
D = 3.0


@pytest.fixture(scope="module")
def rep(tmp_path_factory):
    d = tmp_path_factory.mktemp("pw")
    world = make_world(40, seed=3, fs=SR)
    for i in range(2):
        wavfile.write(str(d / f"c{i}.wav"), SR, (world[i * 20 * SR:(i + 1) * 20 * SR] * 32767).astype("<i2"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=20",
                        "-i", str(d / f"c{i}.wav"), "-t", "20", "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-metadata", f"creation_time=2026-05-01T10:00:{i * 20:02d}Z", str(d / f"v{i}.mp4")],
                       check=True)
    wavfile.write(str(d / "rec.wav"), SR, (world[int(D * SR):] * 32767).astype("<i2"))
    return pipeline.analyze([d / "v0.mp4", d / "v1.mp4"], d / "rec.wav"), world, d


def test_initial_window_starts_at_audio_and_is_limited(rep):
    r, _, _ = rep
    a, b = proxy.initial_window(r.project)
    assert a == pytest.approx(D, abs=0.02)
    assert b == pytest.approx(r.project.total_duration)       # video più corto di 10 minuti: finisce col video
    r.project.total_duration = 3600.0
    a, b = proxy.initial_window(r.project)
    assert b - a == pytest.approx(600.0)                      # 10 minuti da quando inizia l'audio
    r.project.total_duration = 40.0


def test_build_window_duration_and_alignment(rep, tmp_path):
    r, world, _ = rep
    a, b = 8.0, 30.0                                          # a cavallo dei due file
    out = tmp_path / "w.mp4"
    proxy.build_window(r.project, r.clips, a, b, out)
    info = probe(out)
    assert float(info["format"]["duration"]) == pytest.approx(b - a, abs=0.3)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert v["height"] == 360
    got = decode_audio_mono(out, sync.SR)
    ref = world[:: SR // sync.SR][: 40 * sync.SR]
    d, z = sync.gcc_phat(ref, got)
    assert z > 7 and d == pytest.approx(a, abs=0.02)          # l'audio della finestra coincide con la timeline


def test_window_around(rep):
    r, _, _ = rep
    a, b = proxy.window_around(r.project, 35.0)
    assert 0 <= a <= 35.0 <= b <= r.project.total_duration


def test_player_coalesces_seeks_and_requests_windows(rep, qt_app, tmp_path, monkeypatch):
    from confmerge.settings import Settings
    from confmerge.ui.player import PlayerWidget
    from confmerge.ui.state import AppState
    r, _, _ = rep
    out = tmp_path / "w2.mp4"
    proxy.build_window(r.project, r.clips, 5.0, 20.0, out)
    st = AppState(Settings(tmp_path / "cfg"))
    st.project, st.clips = r.project, r.clips
    pl = PlayerWidget(st)
    pl.load(out, 5.0, 15.0, 40.0)
    needed, calls = [], []
    pl.windowNeeded.connect(needed.append)
    monkeypatch.setattr("confmerge.ui.player.NO_PLAYER", False)    # qui serve il percorso reale verso il lettore
    pl.player.setPosition = lambda ms: calls.append(ms)       # conta le richieste vere al backend
    for _ in range(300):                                      # molti click ravvicinati
        pl.set_position(random.uniform(5.0, 20.0))
    assert pl._seek_timer.isActive() and not calls            # non ancora eseguite: unite in una sola
    pl._apply_seek()
    assert len(calls) == 1
    pl.set_position(30.0)                                     # fuori dall'anteprima
    assert needed and needed[-1] == pytest.approx(30.0)
