import shutil
import subprocess
import time

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


def wait(app, cond, timeout=180):
    t = time.time()
    while not cond():
        app.processEvents()
        time.sleep(0.02)
        assert time.time() - t < timeout, "timeout"


@pytest.fixture
def app_window(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    from confmerge.settings import Settings
    from confmerge.ui.main_window import MainWindow
    from confmerge.ui.state import AppState
    from confmerge.ui.theme import theme
    theme.reduce_motion = True
    st = AppState(Settings(tmp_path / "cfg"))
    theme.apply(qt_app)
    w = MainWindow(st)
    w.show()
    yield qt_app, st, w
    w.close()


def test_first_launch_is_simple_with_starter_profile(app_window):
    app, st, w = app_window
    assert w.mode == "simple" and w.simple.step == 0
    assert st.profile_name == "Conferenza (semplice)" and st.spec.graphics.title.enabled
    assert st.spec.credit.enabled                                          # credito attivo di default


def test_simple_flow_to_exported_video(app_window, media, tmp_path):
    app, st, w = app_window
    s = w.simple
    s.start.use_folder(media)
    wait(app, lambda: st.project is not None and s.step == 1)
    pr = st.project
    assert pr.offset_s == pytest.approx(1.5, abs=0.01)
    assert not s.next.isEnabled() and "conferma" in s.hint.text()           # il taglio va confermato in modo esplicito
    assert pr.trim_start is None
    st.review.apply_suggestion()
    assert pr.trim_confirmed and s.next.isEnabled()
    # testi variabili del profilo
    st.spec.variables.update({"titolo": "Convegno di prova", "relatore": "Mario Rossi", "ruolo": "Sindaco"})
    s.go_next()
    assert s.step == 2
    s.export._choose("fast")                                                 # «Più veloce»
    st.spec.graphics.title.duration = 1.5
    st.spec.credit.duration = 2.0
    st.spec.export.out_dir, st.spec.export.name = str(tmp_path / "out"), "prova"
    st.spec.export.encoder = "libx264"
    wait(app, lambda: st.export.est is not None)
    assert "MB" in s.export.est_big.text()                                   # tempo E dimensione sempre visibili
    s.go_next()                                                              # «Esporta il video»
    wait(app, lambda: st.queue.items and st.queue.items[0].status in ("completato", "errore"), 400)
    assert st.queue.items[0].status == "completato", st.queue.items[0].error
    assert (tmp_path / "out" / "prova.mp4").stat().st_size > 10_000
    wait(app, lambda: s.export.stack.currentIndex() == 2)                    # schermata «Il video è pronto!»
    assert "pronto" in s.export.done_title.text()


def test_switch_modes_without_losing_anything(app_window, media):
    app, st, w = app_window
    w.simple.start.use_folder(media)
    wait(app, lambda: st.project is not None)
    st.review.apply_suggestion()
    st.spec.variables["titolo"] = "Titolo di prova"
    st.spec.credit.duration = 4.0
    proj, trim = st.project, (st.project.trim_start, st.project.trim_end)
    w.set_mode("advanced", animate=False)
    assert w.mode == "advanced" and st.project is proj and w.adv.current() == 1
    assert (proj.trim_start, proj.trim_end) == trim and st.spec.variables["titolo"] == "Titolo di prova"
    assert not w.adv.nav.buttons[2]._state == "locked"                       # fasi sbloccate col progetto
    w.adv.goto(3, animate=False)
    w.adv.graphics.tabs.setCurrentIndex(0)
    w.set_mode("simple", animate=False)
    assert w.mode == "simple" and st.spec.credit.duration == 4.0 and st.project is proj
    assert w.simple.step == 1 and w.simple.check._fields["titolo"].text() == "Titolo di prova"


def test_advanced_flow_layers_undo_and_export(app_window, media, tmp_path):
    app, st, w = app_window
    w.set_mode("advanced", animate=False)
    adv = w.adv
    adv.select.load_folder(media)
    assert st.sources.ready
    adv.start_analysis()
    wait(app, lambda: st.project is not None and adv.current() == 1)
    w.review.apply_suggestion()
    adv.goto(3, animate=False)
    from confmerge.ui.graphics_page import new_element
    el = new_element("text")
    el.text = "Evento"
    st.spec.graphics.elements.append(el)
    st.touch()
    adv.graphics.ov_main.refresh()
    adv.graphics.ov_main.list.setCurrentRow(0)
    # occhio e lucchetto nel pannello livelli
    row = adv.graphics.ov_main.list.itemWidget(adv.graphics.ov_main.list.item(0))
    row.eye.setChecked(False)
    assert el.visible is False
    row.eye.setChecked(True)
    # annulla / ripristina
    n = len(st.spec.graphics.elements)
    st._undo_timer.stop()
    st._commit()
    st.spec.graphics.elements.append(new_element("shape"))
    st.touch()
    st._undo_timer.stop()
    st._commit()
    assert len(st.spec.graphics.elements) == n + 1
    assert st.undo() and len(st.spec.graphics.elements) == n
    assert st.redo() and len(st.spec.graphics.elements) == n + 1
    st.spec.graphics.elements.pop()
    st.spec.graphics.title.enabled = False
    st.spec.credit.duration = 2.0
    st.spec.export.preset, st.spec.export.custom_height = "Personalizzato", 360
    st.spec.export.out_dir, st.spec.export.name = str(tmp_path / "out2"), "avanzato"
    st.spec.export.encoder = "libx264"
    adv.goto(6, animate=False)
    wait(app, lambda: st.export.est is not None)
    adv.export.enqueue(True)
    wait(app, lambda: st.queue.items and st.queue.items[0].status in ("completato", "errore"), 400)
    assert st.queue.items[0].status == "completato", st.queue.items[0].error
    assert (tmp_path / "out2" / "avanzato.mp4").exists()
    # progetto salvato e ricaricato
    st.sync_spec_to_project()
    st.project.save(tmp_path / "p.confmerge")
    from confmerge.project import Project
    assert Project.load(tmp_path / "p.confmerge").spec["graphics"]["elements"][0]["text"] == "Evento"
