from confmerge import detect


def touch(d, *names):
    out = []
    for n in names:
        p = d / n
        p.write_bytes(b"x")
        out.append(p)
    return out


def test_audio_present_means_conference(tmp_path):
    touch(tmp_path, "cam1.mp4", "cam2.MOV", "registrazione.wav", "slide.pdf", "note.txt")
    d = detect.classify([tmp_path])
    assert d.kind == "merge" and len(d.videos) == 2 and d.audio.name == "registrazione.wav" and d.folder == tmp_path
    assert [s.name for s in d.slides] == ["slide.pdf"] and "conferenza" in d.reason


def test_videos_only_means_social(tmp_path):
    v = touch(tmp_path, "a.mp4", "b.mp4")
    d = detect.classify(v)
    assert d.kind == "social" and len(d.videos) == 2 and d.audio is None and d.sources == v
    assert detect.classify([tmp_path]).kind == "social"


def test_loose_files_with_audio_and_nothing_usable(tmp_path):
    f = touch(tmp_path, "a.mp4", "voce.m4a")
    assert detect.classify(f).kind == "merge"
    assert detect.classify(touch(tmp_path, "x.txt")).kind == ""
    assert detect.classify([tmp_path / "missing"]).kind == ""
