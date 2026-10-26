from datetime import datetime, timedelta, timezone
from pathlib import Path

from confmerge.media_scan import MediaInfo, find_gaps, order_clips

T0 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)


def clip(name, start_s=None, dur=600.0):
    ct = None if start_s is None else T0 + timedelta(seconds=start_s)
    return MediaInfo(Path(name), dur, ct)


def test_order_by_creation_time():
    cs = [clip("b.mp4", 600), clip("a.mp4", 1200), clip("c.mp4", 0)]
    ordered, how = order_clips(cs)
    assert how == "creation_time" and [c.name for c in ordered] == ["c.mp4", "b.mp4", "a.mp4"]


def test_fallback_on_name_natural_sort():
    cs = [clip("DJI_10.mp4"), clip("DJI_2.mp4"), clip("DJI_1.mp4")]
    ordered, how = order_clips(cs)
    assert how == "nome" and [c.name for c in ordered] == ["DJI_1.mp4", "DJI_2.mp4", "DJI_10.mp4"]


def test_identical_creation_times_fall_back_to_name():
    cs = [clip("b.mp4", 0), clip("a.mp4", 0)]
    _, how = order_clips(cs)
    assert how == "nome"


def test_gap_detection():
    ordered = [clip("a.mp4", 0), clip("b.mp4", 601), clip("c.mp4", 1260)]
    gaps = find_gaps(ordered)
    assert len(gaps) == 1 and gaps[0].after.name == "c.mp4" and 55 < gaps[0].gap_s < 65
