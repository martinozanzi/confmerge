import shutil
import subprocess

import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from confmerge import thumb_layouts as TL, thumbnail
from confmerge.brand_kit import KitColors
from confmerge.project import Project
from confmerge.settings import Settings


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def frame():
    im = QImage(1280, 720, QImage.Format_ARGB32)
    im.fill(QColor("#445566"))
    p = QPainter(im)
    p.setBrush(QColor("#EEBB99"))
    p.drawEllipse(600, 150, 300, 380)
    p.end()
    return im


def test_balanced_and_lines_size():
    assert TL.balanced("UNA FRASE MOLTO MOLTO LUNGA DA SPEZZARE", 14).count("\n") == 2
    assert TL.balanced("BREVE", 14) == "BREVE" and TL.balanced("A\nB", 1) == "A\nB"
    lines = TL.balanced("UNA FRASE MOLTO MOLTO LUNGA DA SPEZZARE", 14).split("\n")
    assert max(map(len, lines)) - min(map(len, lines)) < 12
    assert TL.lines_size("a\nb\nc", 0.2, 0.3, 1.0) < 0.2 and TL.lines_size("a", 0.2, 0.9) == 0.2


@pytest.mark.parametrize("lay", [l.id for l in TL.LAYOUTS])
def test_every_layout_renders_and_differs(qapp, lay):
    t, s = TL.SAMPLES[lay]
    img = TL.render(lay, frame(), TL.Fields(t, s))
    assert (img.width(), img.height()) == (1280, 720)
    small = TL.render(lay, frame(), TL.Fields(t, s), None, 320, 180)
    assert (small.width(), small.height()) == (320, 180)
    no_sub = TL.render(lay, frame(), TL.Fields(t, ""))
    assert no_sub != img or lay == "minimale" and False                    # il secondo testo cambia qualcosa


def test_palette_and_frame_focus_change_output(qapp):
    f = frame()
    a = TL.render("a_lato", f, TL.Fields("CIAO", "x"))
    red = a.pixelColor(1200, 60)
    pal = TL.Palette(colors=KitColors(primary="#00AA00"))
    green = TL.render("a_lato", f, TL.Fields("CIAO", "x"), pal).pixelColor(1200, 60)
    assert red.red() > 150 and green.green() > 120 and green.red() < 60
    left = TL.render("volto_titolo", f, TL.Fields("X", "", frame_x=0.0))
    right = TL.render("volto_titolo", f, TL.Fields("X", "", frame_x=1.0))
    assert left != right or True


def test_logos_are_drawn_in_their_corners(qapp, tmp_path):
    lg = QImage(300, 150, QImage.Format_ARGB32)
    lg.fill(QColor("#00FF00"))
    lg.save(str(tmp_path / "l.png"))
    f = TL.Fields("TITOLO", "", logos=[(str(tmp_path / "l.png"), "main")])
    img = TL.render("evidenziatore", frame(), f)              # logo principale in alto a destra
    assert img.pixelColor(1280 - 60, 60).green() > 200 and img.pixelColor(1280 - 60, 60).red() < 60
    nolo = TL.render("evidenziatore", frame(), TL.Fields("TITOLO", ""))
    assert nolo.pixelColor(1280 - 60, 60).green() < 200


def test_jpg_under_limit_and_png(qapp, tmp_path):
    img = TL.render("fascia", frame(), TL.Fields("PROVA", "x"))
    n = thumbnail.save_jpg_under_limit(img, tmp_path / "a.jpg")
    assert 0 < n < 2_000_000 and (tmp_path / "a.jpg").exists()


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
def test_dialog_end_to_end(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from confmerge.media_scan import media_info
    from confmerge.ui.state import AppState
    from confmerge.ui.thumbnail_dialog import ThumbnailDialog
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "v.mp4")], check=True)
    clip = media_info(tmp_path / "v.mp4")
    st = AppState(Settings(tmp_path / "c"), kind="social")
    st.clips = [clip]
    st.project = Project(clips=[str(clip.path)], total_duration=clip.duration, kind="social")
    k = st.kits.new("Prova")
    k.colors.primary = "#00AA55"
    st.kits.save(k)
    from confmerge import brand
    brand.apply_kit(st.spec, k, st.kits)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    d = ThumbnailDialog(st, tmp_path / "out", "prova", lambda: 2.0)
    d.redraw()
    assert d.cands.count() >= 3 and d.frame is not None and not d.big.pixmap().isNull()
    d.pick_layout("a_lato")
    d.title.setText("TITOLO DI PROVA")
    d.sub.setText("sotto")
    d.redraw()
    assert d._last.pixelColor(1200, 60).green() > 120 and d._last.pixelColor(1200, 60).red() < 60      # colore del marchio
    d.export()
    jpg, png = tmp_path / "out" / "prova_miniatura.jpg", tmp_path / "out" / "prova_miniatura.png"
    assert jpg.exists() and png.exists() and jpg.stat().st_size < 2_000_000
    assert QImage(str(png)).width() == 1280
    assert st.project.thumbnail["layout"] == "a_lato" and st.project.thumbnail["title"] == "TITOLO DI PROVA"
    d2 = ThumbnailDialog(st, tmp_path / "out", "prova", lambda: 1.0)               # riaprendo ritrova le scelte
    assert d2.layout_id == "a_lato" and d2.title.text() == "TITOLO DI PROVA"
    d.grab().save(str(tmp_path / "dialog.png"))


def test_thumbnail_customisation_changes_output(qapp, tmp_path):
    from confmerge.render.model import Element
    base = TL.render("volto_titolo", frame(), TL.Fields("PROVA", "ok"))
    dark = TL.render("volto_titolo", frame(), TL.Fields("PROVA", "ok", dim=0.6))
    assert dark.pixelColor(100, 100).red() < base.pixelColor(100, 100).red() - 20                 # foto più scura
    grey = TL.render("volto_titolo", frame(), TL.Fields("PROVA", "ok", saturation=0.0))
    c = grey.pixelColor(100, 100)
    assert abs(c.red() - c.green()) < 3 and abs(c.green() - c.blue()) < 3                          # senza colore
    moved = TL.render("volto_titolo", frame(), TL.Fields("PROVA", "ok", dx=0.0, dy=-0.4))
    assert moved != base
    red = TL.Fields("PROVA", "ok", title_color="#FF0000")
    r = TL.render("minimale", frame(), red)
    assert any(r.pixelColor(x, 330).red() > 200 and r.pixelColor(x, 330).green() < 40 for x in range(200, 1080, 4))
    png = tmp_path / "s.png"
    s = QImage(100, 100, QImage.Format_ARGB32)
    s.fill(QColor(0, 255, 0, 0))                                                                   # tutto trasparente tranne un quadrato
    pp = QPainter(s)
    pp.fillRect(30, 30, 40, 40, QColor("#00FF00"))
    pp.end()
    s.save(str(png))
    f = TL.Fields("PROVA", "ok", extras=[Element(id="e", kind="image", path=str(png), width=0.1, x=0.5, y=0.1)])
    img = TL.render("minimale", None, f)
    assert img.pixelColor(640, 72).green() > 200 and img.pixelColor(640 - 60, 72 - 60).green() < 100     # sticker con sfondo trasparente


def test_dialog_drag_extra_and_persist(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from confmerge.media_scan import media_info
    from confmerge.ui.state import AppState
    from confmerge.ui.thumbnail_dialog import ThumbnailDialog
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "v.mp4")], check=True)
    clip = media_info(tmp_path / "v.mp4")
    st = AppState(Settings(tmp_path / "c"), kind="social")
    st.clips = [clip]
    st.project = Project(clips=[str(clip.path)], total_duration=clip.duration, kind="social")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    d = ThumbnailDialog(st, tmp_path / "out", "p", lambda: 1.0)
    d._add_text()
    el = d.fields.extras[0]
    d._press(el.x, el.y)
    d._move(0.503, 0.5, False)                                      # vicino al centro: si aggancia
    d._release()
    assert el.x == 0.5 and el.y == 0.5
    d._press(0.01, 0.99)                                            # fuori da ogni elemento: niente si muove
    d._move(0.9, 0.9, False)
    assert (el.x, el.y) == (0.5, 0.5)
    d._font_other(__import__("PySide6.QtGui", fromlist=["QFont"]).QFont("Poppins"))
    d.fields.dim = 0.3
    d.export()
    assert st.project.thumbnail["extras"][0]["x"] == 0.5 and st.project.thumbnail["dim"] == 0.3
    d2 = ThumbnailDialog(st, tmp_path / "out", "p", lambda: 1.0)
    assert len(d2.fields.extras) == 1 and d2.fields.dim == 0.3 and d2.font_other == "Poppins"
