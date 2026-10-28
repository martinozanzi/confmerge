"""Trasformazione diretta stile CapCut: maniglie, ridimensionamento con aggancio, allinea, ripristina, tastiera, secondo video."""
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from confmerge.project import Project
from confmerge.render.model import Element, Fill
from confmerge.settings import Settings
from confmerge.spec import LogoPlacement
from confmerge.ui import placement
from confmerge.ui.state import AppState

W, H = 720, 1280


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def _png():
    import tempfile
    from PySide6.QtGui import QImage
    f = tempfile.mkstemp(suffix=".png")[1]
    img = QImage(40, 20, QImage.Format_ARGB32)
    img.fill(0xFFFF0000)
    img.save(f)
    return f


@pytest.fixture
def st(qapp):
    s = AppState(kind="social")
    s.project = Project(clips=["a.mp4"], total_duration=5.0, kind="social")
    s.spec.image.aspect = "9:16"
    s.spec.graphics.elements = [
        Element(id="t", kind="text", text="CIAO", size=0.06, x=0.5, y=0.4, fit_width=0.86, fill=Fill(color="#FFFFFF"),
                targets=["main"]),
        Element(id="i", kind="image", path=_png(), width=0.2, x=0.3, y=0.7, targets=["main"]),
        Element(id="s", kind="shape", shape="rect", x=0.5, y=0.2, w=0.3, h=0.1, targets=["main"])]
    return s


def rect(st, kind, idx):
    return {(k, i): r for k, i, r in placement.items(st, W, H)}[(kind, idx)]


def test_handles_are_eight_and_hit_tested():
    r = QRectF(100, 200, 80, 40)
    pts = placement.handle_points(r)
    assert set(pts) == set(placement.HANDLES) and pts["nw"] == (100, 200) and pts["se"] == (180, 240) and pts["e"] == (180, 220)
    assert placement.handle_at(r, 181, 241, 9) == "se" and placement.handle_at(r, 140, 201, 9) == "n"
    assert placement.handle_at(r, 140, 220, 9) == ""                                   # in mezzo: nessuna maniglia


def test_resize_rect_corner_keeps_ratio_and_opposite_corner_fixed():
    r0 = QRectF(100, 100, 100, 50)
    r, fx, fy, g = placement.resize_rect(r0, "se", 300, 200, W, H, None, snap_on=False)
    assert (r.left(), r.top()) == (100, 100) and fx == fy == pytest.approx(2.0) and r.width() == 200 and r.height() == 100
    r, fx, fy, g = placement.resize_rect(r0, "nw", 50, 75, W, H, None, snap_on=False)          # dal lato opposto
    assert (r.right(), r.bottom()) == (200, 150) and fx == fy == pytest.approx(1.5)
    r, fx, fy, g = placement.resize_rect(r0, "e", 400, 0, W, H, None, snap_on=False, keep_ratio=False)
    assert fx == pytest.approx(3.0) and fy == pytest.approx(1.0) and r.height() == 50          # lato: solo la larghezza
    r, *_ = placement.resize_rect(r0, "se", 101, 101, W, H, None, snap_on=False)
    assert r.width() >= 6                                                                      # mai a zero, mai capovolto


def test_resize_snaps_edge_to_centre_safe_area_and_alt_disables(st):
    r0 = QRectF(100, 100, 100, 50)
    _, _, _, g = placement.resize_rect(r0, "e", 0.503 * W, 0, W, H, None)
    assert ("x", 0.5) in g                                                                     # bordo destro al centro
    r, *_ = placement.resize_rect(r0, "e", 0.503 * W, 0, W, H, None, snap_on=False)
    assert r.right() == pytest.approx(0.503 * W)
    _, _, _, g = placement.resize_rect(r0, "s", 0, (1 - 0.25 - 0.03 * W / H) * H + 3, W, H, (0.1, 0.25, 0.0, 0.0))
    assert any(a == "y" for a, _ in g)                                                         # bordo basso sopra la zona coperta


def test_resize_text_image_logo_subtitle_and_shape(st):
    # testo: il corpo cresce, l'angolo opposto resta, si spegne il «fit_width»
    r0 = rect(st, "el", 0)
    orig = placement.sizes(st, "el", 0)
    placement.resize_item(st, "el", 0, orig, r0, "se", r0.right() + 80, r0.bottom() + 80, W, H, None, snap_on=False)
    e = st.spec.graphics.elements[0]
    r1 = rect(st, "el", 0)
    assert e.size > 0.06 and e.fit_width == 0.0 and e.anchor == ""
    assert (r1.left(), r1.top()) == (pytest.approx(r0.left(), abs=2), pytest.approx(r0.top(), abs=2)) and r1.width() > r0.width()
    # immagine: larghezza
    r0 = rect(st, "el", 1)
    placement.resize_item(st, "el", 1, placement.sizes(st, "el", 1), r0, "ne", r0.right() + 60, r0.top() - 60, W, H, None, False)
    assert st.spec.graphics.elements[1].width > 0.2
    # logo
    st.spec.brand.logos = [LogoPlacement(path=_png(), name="l", corner="tr", size=0.15)]
    r0 = rect(st, "logo", 0)
    placement.resize_item(st, "logo", 0, placement.sizes(st, "logo", 0), r0, "sw", r0.left() - 40, r0.bottom() + 40, W, H, None, False)
    lg = st.spec.brand.logos[0]
    assert lg.size > 0.15 and lg.corner == "free"
    # sottotitoli
    st.spec.subtitles.enabled = True
    r0 = rect(st, "sub", 0)
    placement.resize_item(st, "sub", 0, placement.sizes(st, "sub", 0), r0, "e", r0.right() + 50, r0.center().y(), W, H, None, False)
    assert st.spec.subtitles.size > 0.048
    # forma: i lati cambiano una dimensione sola, gli angoli (con Maiusc) due indipendenti
    r0 = rect(st, "el", 2)
    placement.resize_item(st, "el", 2, placement.sizes(st, "el", 2), r0, "e", r0.right() + 100, r0.center().y(), W, H, None, False)
    sh = st.spec.graphics.elements[2]
    assert sh.w > 0.3 and sh.h == pytest.approx(0.1)
    r0 = rect(st, "el", 2)
    placement.resize_item(st, "el", 2, placement.sizes(st, "el", 2), r0, "se", r0.right() + 10, r0.bottom() + 90, W, H, None,
                          False, free=True)
    assert sh.h > 0.1


def test_align_to_safe_area_and_whole_video(st):
    safe = (0.1, 0.3, 0.05, 0.1)
    placement.align(st, "el", 0, W, H, "l", "t", safe)
    r = rect(st, "el", 0)
    assert r.left() / W == pytest.approx(0.05 + 0.03, abs=0.002) and r.top() / H == pytest.approx(0.1 + 0.03 * W / H, abs=0.002)
    placement.align(st, "el", 0, W, H, "r", "b", safe)
    r = rect(st, "el", 0)
    assert r.right() / W == pytest.approx(1 - 0.1 - 0.03, abs=0.002) and r.bottom() / H == pytest.approx(1 - 0.3 - 0.03 * W / H, abs=0.002)
    placement.align(st, "el", 0, W, H, "c", "m", None)
    r = rect(st, "el", 0)
    assert r.center().x() / W == pytest.approx(0.5, abs=0.002) and r.center().y() / H == pytest.approx(0.5, abs=0.002)


def test_snapshot_restore_defaults_nudge_and_remove(st):
    snap = placement.snapshot(st, "el", 0)
    placement.align(st, "el", 0, W, H, "l", "t", None)
    placement.scale_values(st, "el", 0, placement.sizes(st, "el", 0), 2.0, 2.0)
    assert st.spec.graphics.elements[0].size > 0.1
    placement.restore(st, "el", 0, snap)
    e = st.spec.graphics.elements[0]
    assert (e.x, e.y, e.size, e.fit_width, e.anchor) == (0.5, 0.4, 0.06, 0.86, "")
    d = placement.defaults(st, "el", 0)
    assert d["anchor"] == "tc" and d["size"] == 0.055
    before = rect(st, "el", 0).center()
    placement.nudge(st, "el", 0, 10, -1, W, H)
    after = rect(st, "el", 0).center()
    assert after.x() - before.x() == pytest.approx(10, abs=0.5) and after.y() - before.y() == pytest.approx(-1, abs=0.5)
    assert placement.remove(st, "el", 0) and len(st.spec.graphics.elements) == 2
    assert not placement.remove(st, "sub", 0) and not placement.remove(st, "logo", 0)


def _canvas(st):
    from confmerge.ui.canvas import Canvas
    cv = Canvas(st)
    cv.resize(420, 760)
    cv.social_edit = True
    cv.show()
    return cv


def _widget_point(cv, x, y):
    Wc, Hc = cv.frame_size()
    tr = cv._target_rect()
    s = tr.width() / Wc
    return QPointF(tr.x() + x * s, tr.y() + y * s)


def _ev(t, p, mods=Qt.NoModifier):
    return QMouseEvent(t, p, p, Qt.LeftButton, Qt.LeftButton, mods)


def test_canvas_drag_handle_resizes_with_snap_and_alt(st):
    cv = _canvas(st)
    Wc, Hc = cv.frame_size()
    sel, changed = [], []
    cv.itemSelected.connect(lambda k, i: sel.append((k, i)))
    cv.itemsChanged.connect(lambda: changed.append(1))
    r = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 1)]               # l'immagine
    c = r.center()
    cv.mousePressEvent(_ev(QMouseEvent.MouseButtonPress, _widget_point(cv, c.x(), c.y())))
    assert sel[-1] == ("el", 1) and cv._item_drag is not None
    cv.mouseReleaseEvent(_ev(QMouseEvent.MouseButtonRelease, _widget_point(cv, c.x(), c.y())))
    changed.clear()
    r = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 1)]
    se = _widget_point(cv, r.right(), r.bottom())
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, se))                                      # sopra la maniglia: cursore di ridimensionamento
    assert cv.cursor().shape() == Qt.SizeFDiagCursor
    cv.mousePressEvent(_ev(QMouseEvent.MouseButtonPress, se))
    assert cv._resize is not None and cv._resize[2] == "se"
    target = _widget_point(cv, r.right() + 40, r.bottom() + 40)
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, target))
    cv.mouseReleaseEvent(_ev(QMouseEvent.MouseButtonRelease, target))
    img = st.spec.graphics.elements[1]
    assert img.width > 0.2 and changed and img.anchor == "" and cv._resize is None
    # Alt: nessun aggancio, quindi il bordo destro arriva esattamente dove si porta il mouse
    r = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 1)]
    cv.mousePressEvent(_ev(QMouseEvent.MouseButtonPress, _widget_point(cv, r.right(), r.center().y())))
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, _widget_point(cv, 0.503 * Wc, r.center().y()), Qt.AltModifier))
    assert not cv._guides
    r2 = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 1)]
    assert r2.right() / Wc == pytest.approx(0.503, abs=0.004)
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, _widget_point(cv, 0.503 * Wc, r.center().y())))
    assert ("x", 0.5) in cv._guides                                                        # senza Alt si aggancia al centro
    cv.mouseReleaseEvent(_ev(QMouseEvent.MouseButtonRelease, _widget_point(cv, 0.5 * Wc, r.center().y())))


def test_canvas_keyboard_nudge_delete_and_reset(st):
    cv = _canvas(st)
    Wc, Hc = cv.frame_size()
    changed = []
    cv.itemsChanged.connect(lambda: changed.append(1))
    r = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 0)]
    cv.mousePressEvent(_ev(QMouseEvent.MouseButtonPress, _widget_point(cv, r.center().x(), r.center().y())))
    cv.mouseReleaseEvent(_ev(QMouseEvent.MouseButtonRelease, _widget_point(cv, r.center().x(), r.center().y())))
    c0 = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 0)].center()
    cv.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    c1 = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 0)].center()
    assert c1.x() - c0.x() == pytest.approx(1.0, abs=0.2)
    cv.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier))
    c2 = {(k, i): rr for k, i, rr in placement.items(st, Wc, Hc)}[("el", 0)].center()
    assert c2.y() - c1.y() == pytest.approx(10.0, abs=0.2) and changed
    # «Ripristina» riporta alla posizione di partenza
    cv.reset_selected()
    e = st.spec.graphics.elements[0]
    assert (e.x, e.y, e.anchor, e.size, e.fit_width) == (0.5, 0.4, "", 0.06, 0.86)
    # Canc toglie il testo
    assert cv.delete_selected() and len(st.spec.graphics.elements) == 2 and cv.sel_item is None
    # i sottotitoli non si cancellano con Canc
    st.spec.subtitles.enabled = True
    cv.sel_item = ("sub", 0)
    cv.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert st.spec.subtitles.enabled and cv.sel_item == ("sub", 0)


def test_second_video_edge_and_pan_with_mouse(st, tmp_path):
    import subprocess
    red = tmp_path / "r.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xFF0000:size=640x360:rate=25:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(red)], check=True)
    st.spec.split.enabled, st.spec.split.path = True, str(red)
    cv = _canvas(st)
    Wc, Hc = cv.frame_size()
    changed = []
    cv.itemsChanged.connect(lambda: changed.append(1))
    # bordo: trascinato verso l'alto cambia l'altezza dei riquadri, vicino al 50 % si aggancia
    edge = _widget_point(cv, 0.5 * Wc, 0.5 * Hc)
    cv.mousePressEvent(_ev(QMouseEvent.MouseButtonPress, edge))
    assert cv.sel_item == ("split", 0) and cv._split_drag == ("edge",)
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, _widget_point(cv, 0.5 * Wc, 0.4 * Hc)))
    assert st.spec.split.ratio == pytest.approx(0.4, abs=0.01)
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, _widget_point(cv, 0.5 * Wc, 0.505 * Hc)))
    assert st.spec.split.ratio == 0.5 and ("y", 0.5) in cv._guides
    cv.mouseReleaseEvent(_ev(QMouseEvent.MouseButtonRelease, edge))
    assert changed
    # dentro il secondo video: trascinare sposta l'inquadratura
    cv.mousePressEvent(_ev(QMouseEvent.MouseButtonPress, _widget_point(cv, 0.5 * Wc, 0.8 * Hc)))
    assert cv.sel_item == ("split", 0) and cv._split_drag[0] == "pan"
    cv.mouseMoveEvent(_ev(QMouseEvent.MouseMove, _widget_point(cv, 0.6 * Wc, 0.8 * Hc)))
    assert st.spec.split.second_x < 0.5                                                  # video verso destra: si vede più sinistra
    cv.mouseReleaseEvent(_ev(QMouseEvent.MouseButtonRelease, _widget_point(cv, 0.6 * Wc, 0.8 * Hc)))
    cv.reset_selected()
    assert (st.spec.split.ratio, st.spec.split.second_x) == (0.5, 0.5)


def test_look_toolbar_align_reset_and_split_selection(qapp, tmp_path):
    from confmerge.ui.social_shell import SocialLook
    s = AppState(Settings(tmp_path / "c"), kind="social")
    s.project = Project(clips=["a.mp4"], total_duration=5, kind="social")
    s.spec.social.platforms = ["shorts"]
    s.spec.graphics.elements = [Element(id="t", kind="text", text="CIAO", size=0.06, x=0.5, y=0.4, fill=Fill(color="#FFFFFF"),
                                        targets=["main"])]
    look = SocialLook(s)
    look.sync()
    assert not any(b.isEnabled() for b in look.align_btns) and not look.reset_item.isEnabled()
    cv = look.player.canvas
    cv.sel_item = ("el", 0)
    cv._remember("el", 0)                                   # come alla prima selezione con il mouse
    look._item_selected("el", 0)
    assert all(b.isEnabled() for b in look.align_btns) and look.reset_item.isEnabled()
    look.c_ref.setValue("video")
    look._align("l", "t")
    r = {(k, i): rr for k, i, rr in placement.items(s, *cv.frame_size())}[("el", 0)]
    assert r.left() < 0.1 * cv.frame_size()[0] and r.top() < 0.1 * cv.frame_size()[1]
    look._reset_item()
    e = s.spec.graphics.elements[0]
    assert (e.x, e.y, e.size) == (0.5, 0.4, 0.06)
    look._item_selected("split", 0)
    assert not any(b.isEnabled() for b in look.align_btns) and not look.c_h.isEnabled() and look.reset_item.isEnabled()
