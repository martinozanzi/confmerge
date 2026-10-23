import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from confmerge import pipeline, sync
from confmerge.ffmpeg_wrapper import decode_audio_mono, probe
from confmerge.media_scan import media_info
from conftest import make_world

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")

SR = 16000
D = 3.0  # l'audio esterno parte 3 s dopo l'inizio del video


def _wav(path, x, sr=SR):
    wavfile.write(str(path), sr, (np.clip(x, -1, 1) * 32767).astype("<i2"))


def _clip(path, wav, start_iso):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=20",
         "-i", str(wav), "-t", "20", "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-metadata", f"creation_time={start_iso}", str(path)], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    world = make_world(40, seed=3, fs=SR)
    for i in range(2):
        _wav(d / f"c{i}.wav", world[i * 20 * SR:(i + 1) * 20 * SR])
    _clip(d / "DJI_0002.mp4", d / "c1.wav", "2026-05-01T10:00:20Z")  # nome/ordine invertiti
    _clip(d / "DJI_0001.mp4", d / "c0.wav", "2026-05-01T10:00:00Z")
    rng = np.random.default_rng(1)
    ext = world[int(D * SR):] + rng.standard_normal(len(world) - int(D * SR)).astype(np.float32) * 0.01
    _wav(d / "rec.wav", ext)
    return d, world


def _analyze(d):
    return pipeline.analyze([d / "DJI_0002.mp4", d / "DJI_0001.mp4"], d / "rec.wav")


def test_analyze(media):
    d, _ = media
    rep = _analyze(d)
    assert [c.name for c in rep.clips] == ["DJI_0001.mp4", "DJI_0002.mp4"]
    assert rep.order_method == "creation_time"
    assert rep.project.offset_s == pytest.approx(D, abs=0.010)
    assert not rep.gaps
    assert rep.project.trim_start is None  # i tagli non vengono mai applicati da soli


@pytest.mark.parametrize("mode", ["copy", "encode"])
def test_export_alignment(media, tmp_path, mode):
    d, world = media
    rep = _analyze(d)
    out = tmp_path / f"out_{mode}.mp4"
    plan = pipeline.export(rep.project, rep.clips, out, mode, t0=5.0, t1=32.0)
    assert plan.mode == mode
    info = probe(out)
    dur = float(info["format"]["duration"])
    assert dur == pytest.approx(plan.duration, abs=0.25)
    assert sum(1 for s in info["streams"] if s["codec_type"] == "audio") == 1
    # l'audio dell'output deve coincidere con world[plan.start : ...]
    got = decode_audio_mono(out, sync.SR)
    ref = world[:: SR // sync.SR][: 40 * sync.SR]
    d_meas, z = sync.gcc_phat(ref, got)
    assert z > 7
    assert d_meas == pytest.approx(plan.start, abs=0.010)


def test_export_never_overwrites_input(media):
    d, _ = media
    rep = _analyze(d)
    with pytest.raises(Exception, match="originali"):
        pipeline.export(rep.project, rep.clips, d / "DJI_0001.mp4")


def test_audio_filter_pad_or_discard(media):
    d, _ = media
    rep = _analyze(d)
    p = rep.project
    p.offset_s = 3.0   # l'esterno parte 3 s dopo il video: silenzio iniziale
    assert "adelay=3000:all=1" in pipeline.audio_filter(p, 0.0)
    assert "atrim=start=2.000000" in pipeline.audio_filter(p, 5.0)   # taglio a 5 s: scarta 2 s
    p.offset_s = -2.0  # l'esterno parte 2 s prima: si scarta l'inizio
    assert "atrim=start=2.000000" in pipeline.audio_filter(p, 0.0)
