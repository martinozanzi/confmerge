import shutil
import subprocess
from pathlib import Path

import pytest
from scipy.io import wavfile

from conftest import make_world
from confmerge import audio_parts as AP, detect, paths, pipeline
from confmerge.ffmpeg_wrapper import probe
from confmerge.media_scan import scan_folder

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
SR = 16000


def touch(d, *names):
    out = []
    for n in names:
        p = d / n
        p.write_bytes(b"x" * 10)
        out.append(p)
    return out


def test_parts_recognised_by_name_and_ordered(tmp_path):
    files = touch(tmp_path, "REC_010.wav", "REC_002.wav", "REC_001.wav")
    assert [p.name for p in AP.audio_parts(files)] == ["REC_001.wav", "REC_002.wav", "REC_010.wav"]        # ordine numerico, non alfabetico
    dates = touch(tmp_path, "20260501_113000.m4a", "20260501_101500.m4a")
    assert [p.name for p in AP.audio_parts(dates)] == ["20260501_101500.m4a", "20260501_113000.m4a"]       # per data e ora


def test_same_recording_in_two_formats_is_not_two_parts(tmp_path):
    files = touch(tmp_path, "voce.mp3", "voce.wav")
    assert [p.name for p in AP.audio_parts(files)] == ["voce.wav"]                                          # si tiene il formato migliore
    assert len(AP.audio_parts(touch(tmp_path, "solo.wav"))) == 1


def test_unrelated_audio_files_pick_one(tmp_path):
    wav = tmp_path / "intervento.wav"
    wavfile.write(str(wav), SR, make_world(3, 1).astype("float32"))
    jingle = tmp_path / "sigla.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=1", str(jingle)], check=True)
    assert [p.name for p in AP.audio_parts([wav, jingle])] == ["intervento.wav"]                            # nomi diversi: non sono parti


def test_detect_reports_parts(tmp_path):
    touch(tmp_path, "cam.mp4", "rec_1.wav", "rec_2.wav")
    d = detect.classify([tmp_path])
    assert d.kind == "merge" and [p.name for p in d.audios] == ["rec_1.wav", "rec_2.wav"] and d.audio.name == "rec_1.wav"
    assert "2 file" in d.reason


def test_split_audio_is_chained_and_synced_on_the_first_part(tmp_path):
    """La registrazione è in due file: si sincronizza l'inizio del primo e il secondo segue, come se fosse un file solo."""
    world = make_world(60, seed=8, fs=SR)
    world[:15 * SR] *= 0.02
    clips = []
    for i in range(2):
        wavfile.write(str(tmp_path / f"c{i}.wav"), SR, (world[i * 30 * SR:(i + 1) * 30 * SR] * 32767).astype("<i2"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=30",
                        "-i", str(tmp_path / f"c{i}.wav"), "-t", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-metadata", f"creation_time=2026-05-01T10:00:{i * 30:02d}Z", str(tmp_path / f"v{i}.mp4")], check=True)
        clips.append(tmp_path / f"v{i}.mp4")
        (tmp_path / f"c{i}.wav").unlink()
    rec = world[int(1.5 * SR):]
    cut = 20 * SR
    p1, p2 = tmp_path / "rec_001.wav", tmp_path / "rec_002.wav"
    wavfile.write(str(p1), SR, (rec[:cut] * 32767).astype("<i2"))
    wavfile.write(str(p2), SR, (rec[cut:] * 32767).astype("<i2"))
    scan = scan_folder(tmp_path)
    parts = AP.audio_parts(scan.audios)
    assert [p.name for p in parts] == ["rec_001.wav", "rec_002.wav"]
    paths.temp_dir()
    rep = pipeline.analyze(clips, parts, keep_order=True)
    pr = rep.project
    assert pr.offset_s == pytest.approx(1.5, abs=0.01)                           # l'inizio del primo file decide la sincronia
    assert [Path(a).name for a in pr.audios] == ["rec_001.wav", "rec_002.wav"]
    assert pr.drift_s is None and pr.atempo == 1.0 and not pr.use_drift_correction     # con più file non si corregge la deriva
    merged = probe(pr.audio)
    assert abs(float(merged["format"]["duration"]) - len(rec) / SR) < 0.2        # i due file sono uno in fila all'altro
    assert Path(pr.audio).suffix == ".flac"
    # riaprendo il progetto, se il file unito non c'è più si rifà
    Path(pr.audio).unlink()
    again = AP.ensure_merged([Path(a) for a in pr.audios], Path(pr.audio))
    assert again.exists() and abs(float(probe(again)["format"]["duration"]) - len(rec) / SR) < 0.2


def test_other_audio_files_in_the_folder_are_not_parts(tmp_path):
    a, b = tmp_path / "rec_1.wav", tmp_path / "rec_2.wav"
    for p in (a, b):
        wavfile.write(str(p), SR, make_world(4, 1).astype("float32"))
    jingle = tmp_path / "sigla.wav"
    wavfile.write(str(jingle), SR, make_world(1, 2).astype("float32"))
    assert [p.name for p in AP.audio_parts([jingle, b, a])] == ["rec_1.wav", "rec_2.wav"]


def test_export_rebuilds_missing_merged_audio(tmp_path):
    from confmerge.project import Project
    a, b = tmp_path / "rec_1.wav", tmp_path / "rec_2.wav"
    for p in (a, b):
        wavfile.write(str(p), SR, make_world(2, 1, fs=SR).astype("float32"))
    pr = Project(audio=str(tmp_path / "sparito.flac"), audios=[str(a), str(b)])
    paths.temp_dir()
    AP.ensure_project_audio(pr)
    assert Path(pr.audio).exists() and abs(float(probe(pr.audio)["format"]["duration"]) - 4.0) < 0.1
