import numpy as np
import pytest

from confmerge import trim_detect
from conftest import FS


@pytest.fixture(autouse=True)
def no_vad(monkeypatch):
    monkeypatch.setattr(trim_detect, "_vad_ratio", lambda a, sr: None)


def _signal(total=300):
    rng = np.random.default_rng(0)
    x = rng.standard_normal(total * FS).astype(np.float32) * 0.002
    x[10 * FS:11 * FS] += rng.standard_normal(FS).astype(np.float32) * 0.2  # colpo di tosse: non sostenuto
    for s in range(60, 200):
        if s % 20 == 19:  # piccola pausa
            continue
        x[s * FS:(s + 1) * FS] += rng.standard_normal(FS).astype(np.float32) * 0.1
    return x


def test_start_end_with_padding():
    sug = trim_detect.suggest_trim(_signal(), FS, 300)
    assert sug.found
    assert sug.start_s == pytest.approx(55, abs=1.5)
    assert sug.end_s == pytest.approx(200 - 1 + 5 - 0, abs=2.5)  # ultimo secondo attivo è 198, +5


def test_silence_only_finds_nothing():
    x = np.random.default_rng(1).standard_normal(120 * FS).astype(np.float32) * 0.002
    sug = trim_detect.suggest_trim(x, FS, 120)
    assert not sug.found and sug.start_s == 0 and sug.end_s == 120


def test_clamped_to_bounds():
    x = np.random.default_rng(2).standard_normal(60 * FS).astype(np.float32) * 0.002
    x[2 * FS:58 * FS] += np.random.default_rng(3).standard_normal(56 * FS).astype(np.float32) * 0.1
    sug = trim_detect.suggest_trim(x, FS, 60)
    assert sug.start_s == 0 and sug.end_s == 60
