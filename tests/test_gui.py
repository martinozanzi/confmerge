import shutil
import subprocess
import time
from pathlib import Path

import pytest
from scipy.io import wavfile

from conftest import make_world

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
SR = 16000


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("gui")
    world = make_world(60, seed=8, fs=SR)
    world[:15 * SR] *= 0.02
    world[50 * SR:] *= 0.02
    for i in range(2):
        wavfile.write(str(d / f"c{i}.wav"), SR, (world[i * 30 * SR:(i + 1) * 30 * SR] * 32767).astype("<i2"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=30",
                        "-i", str(d / f"c{i}.wav"), "-t", "30", "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-metadata", f"creation_time=2026-05-01T10:00:{i * 30:02d}Z",
                        str(d / f"v{i}.mp4")], check=True)
        (d / f"c{i}.wav").unlink()
    wavfile.write(str(d / "rec.wav"), SR, (world[int(1.5 * SR):] * 32767).astype("<i2"))
    return d


def wait(app, cond, timeout=120):
    t = time.time()
    while not cond():
        app.processEvents()
        time.sleep(0.02)
        assert time.time() - t < timeout, "timeout"


def test_wizard_flow(media, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    from confmerge.render.model import Anim
    from confmerge.settings import Settings
    from confmerge.ui.graphics_page import new_element
    from confmerge.ui.main_window import MainWindow
    from confmerge.ui.state import AppState

    st = AppState(Settings(tmp_path / "cfg"))
    w = MainWindow(st)
    w.show()
    w.select.load_folder(media)
    assert len(w.select.videos) == 2 and w.select.audio.name == "rec.wav"
    w.go_next()
    wait(app, lambda: w.stack.currentIndex() == 2)
    pr = st.project
    assert pr.offset_s == pytest.approx(1.5, abs=0.01)
    assert st.cam is not None and st.proxy.exists()
    # la revisione carica forma d'onda e suggerimento (non applicato)
    assert w.review.wave.suggest is not None and pr.trim_start is None
    w.review.apply_suggestion()
    assert pr.trim_start is not None and pr.trim_end > pr.trim_start
    w.go_next()
    assert w.stack.currentIndex() == 3
    # grafica: un overlay di testo, titolo, credito attivo di default
    el = new_element("text")
    el.text, el.anim_in = "Evento", Anim("fade", 0.4)
    st.spec.graphics.elements.append(el)
    st.spec.graphics.title.enabled = True
    st.spec.graphics.title.duration = 2.0
    st.spec.credit.duration = 2.0
    st.spec.export.preset, st.spec.export.custom_height = "Personalizzato", 360
    st.spec.export.out_dir = str(tmp_path / "out")
    st.spec.export.name = "prova"
    st.spec.export.encoder = "libx264"
    st.touch()
    w.graphics.canvas.grab()
    # profilo
    st.save_profile("Canale A")
    assert "Canale A" in st.settings.list_profiles()
    w.go_next()
    assert w.stack.currentIndex() == 4
    wait(app, lambda: w.export.est is not None)
    assert w.export.est.size.exact
    w.export.enqueue(True)
    wait(app, lambda: st.queue.items and st.queue.items[0].status in ("completato", "errore"), 300)
    assert st.queue.items[0].status == "completato", st.queue.items[0].error
    out = tmp_path / "out" / "prova.mp4"
    assert out.exists() and out.stat().st_size > 10_000
    # progetto salvato e ricaricato
    st.sync_spec_to_project()
    pr.save(tmp_path / "p.confmerge")
    from confmerge.project import Project
    p2 = Project.load(tmp_path / "p.confmerge")
    assert p2.spec["graphics"]["elements"][0]["text"] == "Evento"
    w.close()
