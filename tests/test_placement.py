import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from confmerge import brand
from confmerge.render.model import Element, Fill
from confmerge.spec import LogoPlacement
from confmerge.ui import placement
from confmerge.ui.state import AppState


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


@pytest.fixture
def st(qapp):
    s = AppState(kind="social")
    s.spec.graphics.elements = [Element(id="t", kind="text", text="CIAO", size=0.08, anchor="bc", fit_width=0.0,
                                        fill=Fill(color="#FFFFFF"), targets=["main"])]
    return s


def test_snap_to_centre_thirds_and_safe_edges():
    cx, cy, g = placement.snap(0.503, 0.2, 0.1, 0.05, 1000, 1000, [0, 0, 0, 0])
    assert cx == 0.5 and ("x", 0.5) in g and cy == 0.2 and not [x for x in g if x[0] == "y"]
    cx, _, g = placement.snap(0.137, 0.2, 0.1, 0.05, 1000, 1000, [0, 0, 0, 0])
    assert cx == pytest.approx(0.03 + 0.1)                                    # bordo sinistro sul margine
    _, cy, _ = placement.snap(0.5, 0.61, 0.1, 0.05, 1000, 1000, [0, 0.3, 0, 0])
    assert cy == pytest.approx(1 - 0.3 - 0.03 - 0.05)                         # bordo basso sopra la zona coperta
    cx, cy, g = placement.snap(0.3, 0.4, 0.05, 0.05, 1000, 1000, [0, 0, 0, 0])
    assert (cx, cy, g) == (0.3, 0.4, [])


def test_center_buttons_element_logo_and_subtitle(st):
    W, H = 720, 1280
    placement.center(st, "el", 0, W, H, True, False)
    e = st.spec.graphics.elements[0]
    assert e.anchor == "" and e.x == pytest.approx(0.5) and e.y > 0.8             # resta in basso, si centra a lato
    placement.center(st, "el", 0, W, H, False, True)
    assert e.y == pytest.approx(0.5, abs=1e-3)
    st.spec.brand.logos = [LogoPlacement(path=__file__, name="l", corner="tr", size=0.2)]
    st.spec.brand.logos[0].path = _png()
    placement.center(st, "logo", 0, W, H, True, False)
    lg = st.spec.brand.logos[0]
    assert lg.corner == "free" and lg.x == pytest.approx(0.5)
    el = [b for b in brand.brand_elements(st.spec, W, H)][0]
    assert el.x == pytest.approx(0.5, abs=1e-3)
    st.spec.subtitles.enabled = True
    placement.center(st, "sub", 0, W, H, False, True)
    assert st.spec.subtitles.y == pytest.approx(0.5, abs=1e-3) and st.spec.subtitles.x == pytest.approx(0.5, abs=1e-3)
    placement.center(st, "sub", 0, W, H, True, True, (0.1, 0.3, 0.0, 0.0))                 # area sicura: più in alto
    assert st.spec.subtitles.y == pytest.approx(0.4)


def test_subtitle_drag_is_free_in_both_directions(st):
    from confmerge import subtitles as S
    st.spec.subtitles.enabled = True
    placement.place(st, "sub", 0, 0.3, 0.38, 0.8, 0.1, 720, 1280)
    sb = st.spec.subtitles
    assert (sb.x, sb.y) == (0.3, 0.38)
    el = S.preview_element(sb, "ciao", 720, 1280)
    assert (el.x, el.y) == (0.3, 0.38)
    sb.lines = [__import__("confmerge.spec", fromlist=["SubLine"]).SubLine(0, 2, "ciao")]
    assert "\\an5\\pos(216.0,486.4)" in S.to_ass(sb, 0.0, 10.0, 720, 1280)
    sb.x, sb.y = 0.5, -1.0
    assert "\\pos" not in S.to_ass(sb, 0.0, 10.0, 720, 1280)


def test_canvas_repaints_when_spec_changes(st):
    from confmerge.ui.canvas import Canvas
    hits = []

    class Spy(Canvas):
        def update(self, *a):
            hits.append(1)

    cv = Spy(st)
    hits.clear()
    st.spec_changed.emit()
    assert hits


def test_palettes_and_free_subtitle_in_landscape(qapp):
    from confmerge.ui.color_picker import PALETTES
    assert len(PALETTES) >= 5 and all(len(v) == 6 for v in PALETTES.values())
    s = AppState(kind="social")
    s.spec.image.aspect = "16:9"
    s.spec.subtitles.enabled = True
    from confmerge.ui.canvas import Canvas
    cv = Canvas(s)
    cv.resize(500, 320)
    W, H = cv.frame_size()
    assert W > H
    cx, cy, _ = placement.snap(0.6, 0.5, 0.2, 0.05, W, H, (0, 0, 0, 0))
    placement.place(s, "sub", 0, cx, cy, 0.4, 0.1, W, H)
    assert s.spec.subtitles.x == 0.6


def test_mouse_drag_on_canvas(st):
    from confmerge.ui.canvas import Canvas
    cv = Canvas(st)
    cv.resize(400, 300)
    cv.social_edit = True
    cv.show()
    W, H = cv.frame_size()
    r = {(k, i): rr for k, i, rr in placement.items(st, W, H)}[("el", 0)]
    tr = cv._target_rect()
    sc = tr.width() / W

    def at(x, y):
        return QPointF(tr.x() + x * sc, tr.y() + y * sc)

    def ev(t, p):
        return QMouseEvent(t, p, p, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    picked, changed = [], []
    cv.itemSelected.connect(lambda k, i: picked.append((k, i)))
    cv.itemsChanged.connect(lambda: changed.append(1))
    c = r.center()
    cv.mousePressEvent(ev(QMouseEvent.MouseButtonPress, at(c.x(), c.y())))
    assert picked[-1] == ("el", 0)
    cv.mouseMoveEvent(ev(QMouseEvent.MouseMove, at(W * 0.326, H * 0.34)))
    cv.mouseReleaseEvent(ev(QMouseEvent.MouseButtonRelease, at(W * 0.326, H * 0.34)))
    e = st.spec.graphics.elements[0]
    assert changed and e.anchor == "" and e.x == pytest.approx(1 / 3, abs=0.02) and e.y == pytest.approx(1 / 3, abs=0.02)
    cv.mousePressEvent(ev(QMouseEvent.MouseButtonPress, at(5, 5)))
    assert picked[-1] == ("", -1)


def _png():
    import tempfile
    from PySide6.QtGui import QImage
    f = tempfile.mkstemp(suffix=".png")[1]
    img = QImage(40, 20, QImage.Format_ARGB32)
    img.fill(0xFFFF0000)
    img.save(f)
    return f
