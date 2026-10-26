import pytest

from confmerge import estimator as e
from confmerge.spec import ExportSettings, audio_bitrate_bps, video_bitrate_bps


def test_size_from_known_bitrate_tight():
    # 8 Mbit/s video + 192 kbit/s audio per 1 h = 3.69 GB + 1,5% di contenitore
    s = e.size_from_bitrate(8e6, 192e3, 3600)
    expected = (8e6 + 192e3) * 3600 / 8 * 1.015
    assert s.exact and s.mid == pytest.approx(expected, rel=1e-6)
    assert (s.high - s.low) / s.mid < 0.011          # tolleranza stretta


def test_presets_bitrates():
    ex = ExportSettings()
    assert video_bitrate_bps(ex, 1080, 25) == 8e6
    assert video_bitrate_bps(ex, 1080, 60) == 12e6
    assert video_bitrate_bps(ex, 2160, 30) == 35e6
    assert audio_bitrate_bps(ex, 1080) == 192_000
    ex.bitrate_mbps = 5
    assert video_bitrate_bps(ex, 1080, 25) == 5e6


def test_crf_estimate_is_range():
    s = e.size_from_sample(2_500_000, 10, 192_000, 600)
    assert not s.exact and s.low < s.mid < s.high


def test_copy_size_proportional():
    s = e.size_copy(10e9, 3600, 1800)
    assert s.mid == pytest.approx(5e9, rel=0.01)


def test_time_range_and_format():
    lo, hi = e.estimate_time(1800, 2.0)       # 15 min stimati
    assert lo < 900 < hi
    assert e.format_range(lo, hi).startswith("circa ")
    lo2, hi2 = e.estimate_time(1800, 2.0, correction=2.0)
    assert lo2 == pytest.approx(2 * lo)


def test_time_includes_extra_parts():
    base, _ = e.estimate_time(600, 3.0, spread=0)
    extra, _ = e.estimate_time(600, 3.0, e.TimeParts(0, loudnorm_s=30, segments_s=10, animated_s=5, drift_s=5), spread=0)
    assert extra == pytest.approx(base + 50)


def test_moving_speed_remaining():
    m = e.MovingSpeed()
    for i in range(5):
        m.add(i * 10.0, i * 0.1)           # 10% ogni 10 s
    assert m.remaining(0.4) == pytest.approx(60, abs=1)


def test_correction_converges():
    c = {}
    for _ in range(10):
        e.update_correction(c, "libx264", 100, 150)
    assert c["libx264"] == pytest.approx(1.5, abs=0.05)
