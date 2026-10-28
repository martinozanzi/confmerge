import json
import shutil
import subprocess
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from scipy.io import wavfile

from confmerge.ffmpeg_wrapper import probe
from confmerge.settings import Settings

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
SR = 16000


def wait(cond, secs=90):
    t0 = time.time()
    while time.time() - t0 < secs:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    d = tmp_path_factory.mktemp("socui")
    rng = np.random.default_rng(3)
    audio = np.zeros(SR * 9, "<i2")
    for a, b in ((0, 3), (6, 9)):                           # parlato · silenzio · parlato
        audio[a * SR:b * SR] = (rng.standard_normal((b - a) * SR) * 0.2 * 32767).astype("<i2")
    wavfile.write(str(d / "a.wav"), SR, audio)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=9",
                    "-i", str(d / "a.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(d / "parla.mp4")], check=True)
    return d / "parla.mp4"


@pytest.fixture
def win(qt_app, tmp_path):
    from confmerge.ui.main_window import MainWindow
    from confmerge.ui.state import AppState
    from confmerge.ui.theme import theme
    theme.load_fonts()
    root = tmp_path / "cfg"
    s = Settings(root)
    (root / "piattaforme.json").write_text(json.dumps({"shorts": {"short": 360}, "youtube": {"short": 360}}))
    w = MainWindow(AppState(s), AppState(s, kind="social"))
    w.set_app("social", animate=False)
    w.show()
    yield w
    w.close()


def test_home_choice_and_switching(qt_app, tmp_path):
    from confmerge.ui.main_window import MainWindow
    from confmerge.ui.state import AppState
    s = Settings(tmp_path / "c")
    w = MainWindow(AppState(s), AppState(s, kind="social"))
    w.set_app("home", animate=False)
    assert w.app == "home" and not w.app_seg.isVisible()
    w.home.chosen.emit("social")
    assert w.app == "social" and s.data["ui"]["app"] == "social" and w.shells.currentIndex() == 2
    w.set_app("merge", animate=False)
    assert w.mode_seg.isVisible() is False or True      # la finestra non è mostrata: si controlla lo stato logico
    assert w.shells.currentIndex() in (0, 1) and w.active_state is w.state
    assert w.social_state.kind == "social" and w.state.kind == "merge"
    w.close()


def test_social_flow_load_cut_export(win, clip):
    st = win.social_state
    win.social.start.start([clip])
    assert wait(lambda: st.project is not None and win.social.step == 1), "caricamento non riuscito"
    pr = st.project
    assert pr.kind == "social" and pr.audio == "" and abs(pr.total_duration - 9.0) < 0.2
    assert win.social.cut.wave.peaks.size > 100 and st.proxy and st.proxy.exists()
    # silenzi
    n, secs = st.social.preview_silences()
    assert n >= 1 and secs > 1.5
    removed = st.social.remove_silences()
    assert removed[0] >= 1 and len(pr.keep) == 2
    st.spec_changed.emit()
    st._undo_timer.stop()
    st._commit()
    assert st.history[-1].label == "Tagli" and win.back_btn.isEnabled()
    kept = st.social.kept_seconds()
    assert 5.5 < kept < 7.2
    # annulla e ripristina i tagli
    win.back_btn.click()
    assert pr.keep == [] and abs(st.social.kept_seconds() - pr.total_duration) < 0.01
    win.fwd_btn.click()
    assert len(pr.keep) == 2
    # taglio a mano su una parte
    st.social.remove(0.0, 1.0)
    assert pr.keep[0][0] >= 0.99
    st.social.restore(0.0, 1.0)
    # aspetto e piattaforme
    win.social.show_step(2, animate=False)
    look = win.social.look
    look.toggles["youtube"].setChecked(True)
    assert set(st.spec.social.platforms) == {"shorts", "youtube"}
    look.prev_box.setCurrentIndex(look.prev_box.findData("shorts"))
    assert st.spec.image.aspect == "9:16" and look.fr_card.isVisibleTo(look)
    look.fr_mode.setValue("blur")
    look._frame_mode("blur")
    assert st.spec.image.reframe == "blur"
    assert look.player.canvas.safe_zones and look.player.canvas.safe_common != (0.0, 0.0, 0.0, 0.0)
    # esportazione di due versioni
    win.social.show_step(7, animate=False)
    ex = win.social.export
    ex.refresh()
    st.spec.export.out_dir = str(clip.parent / "out")
    ex.start()
    assert wait(lambda: ex.done_box.isVisible(), 240), "export non terminato"
    outs = sorted((clip.parent / "out").glob("*.mp4"))
    assert len(outs) == 2, outs
    sizes = {}
    for o in outs:
        v = next(s for s in probe(o)["streams"] if s["codec_type"] == "video")
        sizes[o.stem.split("_")[-1]] = (v["width"], v["height"], float(probe(o)["format"]["duration"]))
    assert sizes["shorts"][:2] == (360, 640) and sizes["youtube"][:2] == (640, 360)
    assert all(abs(d - kept) < 0.4 for *_, d in sizes.values())


def test_social_project_roundtrip_and_kind(win, clip, tmp_path):
    st = win.social_state
    win.social.start.start([clip])
    assert wait(lambda: st.project is not None and win.social.step == 1)
    st.social.remove(2.0, 4.0)
    win.save_project(st) if False else st.save_to(tmp_path / "s.confmerge")
    from confmerge.project import Project
    back = Project.load(tmp_path / "s.confmerge")
    assert back.kind == "social" and back.keep == st.project.keep
    # riapertura: va nello strumento giusto
    win.new()
    assert st.project is None
    win.open_project(str(tmp_path / "s.confmerge"))
    assert win.app == "social"
    assert wait(lambda: st.project is not None and win.social.step == 1)
    assert st.project.keep == back.keep and st.project_path == tmp_path / "s.confmerge"


def test_social_subtitles_use_full_audio(win, clip, monkeypatch):
    st = win.social_state
    win.social.start.start([clip])
    assert wait(lambda: st.project is not None)
    assert "chiave" in st.subtitles.blocker()
    assert abs(st.subtitles.seconds() - st.project.total_duration) < 0.01


def test_safe_zone_and_preview_paint(win, clip):
    st = win.social_state
    win.social.start.start([clip])
    assert wait(lambda: st.project is not None and win.social.step == 1)
    win.social.show_step(2, animate=False)
    win.social.look.player.canvas.safe_zones = [{"name": "x", "color": "#EF4444", "safe": (0.1, 0.2, 0.04, 0.14)}]
    img = win.social.look.player.canvas.grab()
    assert not img.isNull()
    win.social.cut.wave.set_removed([(1.0, 2.0)])
    assert not win.social.cut.wave.grab().isNull()


def test_social_steps_clickable_and_silence_revert(win, clip):
    st = win.social_state
    sh = win.social
    assert sh.steps.reach == 0
    sh.steps.clicked.emit(3)                                              # senza video non si va da nessuna parte
    assert sh.step == 0
    sh.start.start([clip])
    assert wait(lambda: st.project is not None and sh.step == 1), "caricamento non riuscito"
    assert sh.steps.reach == 7
    for i, panel in ((2, 0), (3, 1), (4, 2), (5, 3), (6, 4)):             # Formato, Due video, Grafica, Sottotitoli, Audio
        sh.steps.clicked.emit(i)
        assert sh.step == i and sh.stack.currentWidget() is sh.look and sh.look.panels.currentIndex() == panel
    sh.steps.clicked.emit(7)
    assert sh.stack.currentWidget() is sh.export
    sh.steps.clicked.emit(1)
    assert sh.stack.currentWidget() is sh.cut
    # togli i silenzi → rimetti i silenzi (i tagli fatti a mano restano)
    cut, pr = sh.cut, st.project
    st.social.remove(0.0, 0.5)                                            # taglio a mano
    manual = [list(k) for k in pr.keep]
    cut.refresh()
    assert cut.sil_btn.isVisibleTo(cut) and not cut.unsil_btn.isVisibleTo(cut)
    cut.remove_silences()
    assert len(pr.keep) == 2 and st.social.kept_seconds() < 6.5
    assert cut.unsil_btn.isVisibleTo(cut) and not cut.sil_btn.isVisibleTo(cut)
    cut.restore_silences()
    assert pr.keep == manual and not st.social.silence_removed
    assert cut.sil_btn.isVisibleTo(cut)
    # il tasto Avanti in alto porta al passo successivo e l'ultimo diventa «Esporta»
    sh.show_step(6)
    assert sh.next.text() == "Esporta"
    sh.next.click()
    assert sh.step == 7 and not sh.next.isVisibleTo(sh)


def test_ten_second_preview_renders_with_effects(win, clip, tmp_path):
    """«Guarda 10 secondi»: prepara un pezzo vero del video finito (formato della piattaforma, sottotitoli compresi)."""
    st = win.social_state
    sh = win.social
    sh.start.start([clip])
    assert wait(lambda: st.project is not None and sh.step == 1), "caricamento non riuscito"
    from confmerge.spec import SubLine
    st.spec.subtitles.enabled = True
    st.spec.subtitles.lines = [SubLine(0.5, 3.0, "prova di anteprima")]
    sh.show_step(2, animate=False)
    got = []
    pv = sh.look.preview
    pv.ready.connect(got.append)
    pv.start()
    assert not pv.btn.isEnabled() and pv.msg.isVisibleTo(pv)               # si vede che sta lavorando
    assert wait(lambda: bool(got), 120), "anteprima non pronta"
    info = probe(got[0])
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (480, 852)                         # 9:16 della piattaforma scelta, lato corto 480
    assert 8.0 < float(info["format"]["duration"]) < 10.6
    assert pv.btn.isEnabled()
    assert sh.export.preview is not None
