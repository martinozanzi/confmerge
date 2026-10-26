import numpy as np
import pytest

from confmerge import sync
from conftest import FS, make_world


def _noisy(x, snr_amp=0.02, seed=5):
    rng = np.random.default_rng(seed)
    return x + rng.standard_normal(len(x)).astype(np.float32) * snr_amp


@pytest.mark.parametrize("d", [3.217, 0.0, -2.5, 41.003, -37.77])
def test_offset_known(world, d):
    """ext(t) = cam(t + d): errore < 10 ms, positivo e negativo."""
    cam = _noisy(world[: 200 * FS], seed=2)
    if d >= 0:
        ext = world[int(round(d * FS)):]
    else:
        pre = make_world(-d, seed=99)
        ext = np.concatenate([pre, world])
    ext = _noisy(ext, 0.03, seed=3)
    res = sync.analyze_sync(cam, ext, FS, check_drift=False)
    assert abs(res.offset_s - d) < 0.010
    assert not res.low_confidence


def test_unrelated_audio_is_low_confidence():
    a = make_world(120, seed=10)
    b = make_world(120, seed=11)
    res = sync.analyze_sync(a, b, FS, check_drift=False)
    assert res.low_confidence


def test_drift_detected_and_corrected():
    eps = 150e-6
    world = make_world(1300, seed=7)
    cam = _noisy(world[: 1200 * FS], seed=1)
    d = 4.0
    t = np.arange(int(1250 * FS)) / FS
    ext = np.interp(t * (1 + eps) + d, np.arange(len(world)) / FS, world).astype(np.float32)
    ext = _noisy(ext, 0.02, seed=4)
    res = sync.analyze_sync(cam, ext, FS)
    assert res.drift_significant
    assert res.atempo == pytest.approx(1 - eps, abs=20e-6)
    # con la correzione l'offset effettivo coincide con d a inizio file
    assert res.offset_corrected_s == pytest.approx(d, abs=0.010)


def test_no_drift_below_threshold(world):
    cam = world[: 280 * FS]
    ext = world[3 * FS: 290 * FS]
    res = sync.analyze_sync(cam, ext, FS)
    assert res.drift_s is None or not res.drift_significant


def test_place_on_timeline():
    ext = np.ones(100, dtype=np.float32)
    out = sync.place_on_timeline(ext, 0.5, 8000 * 1, FS)
    assert out[:4000].sum() == 0 and out[4000:4100].sum() == 100
    out = sync.place_on_timeline(ext, -0.005, 200, FS)  # scarta 40 campioni
    assert out[:60].sum() == 60 and out[60:].sum() == 0
