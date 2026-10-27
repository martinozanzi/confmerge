import pytest

from confmerge import templates as T, transitions as TR
from confmerge.render import compositor as C
from confmerge.render.model import Element, LowerThird, lower_third_elements, substitute
from confmerge.spec import RenderSpec


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def test_every_template_builds_and_renders(qapp):
    from confmerge.ui.template_gallery import render_template
    for kind, items in T.ALL.items():
        assert items
        for tpl in items:
            img = render_template(tpl, 320, 180)
            assert not img.isNull(), (kind, tpl.id)
    assert len({t.id for t in T.TITLES}) == len(T.TITLES)


def test_apply_title_keeps_transition(qapp):
    spec = RenderSpec()
    spec.graphics.title.transition, spec.graphics.title.fade = "zoomin", 0.9
    T.apply_title(spec, "yellow")
    assert spec.graphics.title.transition == "zoomin" and spec.graphics.title.fade == 0.9
    assert spec.graphics.title_template == "yellow" and spec.graphics.title.elements


def test_lower_third_style_applies_to_all(qapp):
    spec = RenderSpec()
    spec.graphics.lower_thirds = [LowerThird("A", "x"), LowerThird("B", "y")]
    T.apply_lower_third_style(spec, "pill")
    assert [lt.style for lt in spec.graphics.lower_thirds] == ["pill", "pill"]
    for style in T.LOWER_THIRD_STYLES if hasattr(T, "LOWER_THIRD_STYLES") else []:
        assert lower_third_elements(LowerThird("A", "x", style=style), 0, {})


def test_caption_adds_elements_with_fresh_ids(qapp):
    spec = RenderSpec()
    a = T.add_caption(spec, T.CAPTIONS[0].id)
    b = T.add_caption(spec, T.CAPTIONS[0].id)
    assert len(spec.graphics.elements) == len(a) + len(b)
    assert not ({e.id for e in a} & {e.id for e in b})


def test_fit_width_shrinks_long_text(qapp):
    W, H = 640, 360
    long = Element(id="a", kind="text", text="Una riga molto molto lunga che non entra mai nello schermo di certo",
                   size=0.12, x=0.5, y=0.5, align="center", fit_width=0.8)
    free = Element.from_dict({**long.to_dict(), "fit_width": 0.0})
    img = C.render_frame([long], W, H, 1.0, 5.0)
    img2 = C.render_frame([free], W, H, 1.0, 5.0)

    def extent(im):
        xs = [x for x in range(W) for y in range(0, H, 3) if im.pixelColor(x, y).alpha() > 40]
        return (max(xs) - min(xs)) if xs else 0
    assert extent(img) <= 0.82 * W
    assert extent(img2) > extent(img)


def test_uppercase(qapp):
    e = Element(id="u", kind="text", text="ciao", size=0.2, x=0.5, y=0.5, uppercase=True)
    assert not C.render_frame([e], 320, 180, 1.0, 5.0).isNull()


def test_transitions_registry():
    assert TR.get("nope").id == "fade"
    assert all(t.join for t in TR.join_options())
    assert TR.nearest_join("zoomin") == "fadewhite" and TR.nearest_join("slideleft") == "fadeblack"
    spec = RenderSpec()
    TR.apply_all(spec, "slideleft")
    assert spec.graphics.title.transition == "slideleft" and spec.graphics.outro.transition == "slideleft"
    assert spec.image.clip_transition == "fadeblack" and spec.graphics.transition_style == "slideleft"


def test_join_dips_filter():
    from confmerge.graph import _join_dips

    class S:
        def __init__(self, n):
            self.length = n
    assert _join_dips([S(10), S(10)], "cut", 0.6) == ""
    f = _join_dips([S(10), S(8), S(5)], "fadewhite", 0.6)
    assert f.count("fade=t=out") == 2 and "color=white" in f and "st=9.700" in f


def test_color_picker(qapp):
    from confmerge.ui.color_picker import ColorPicker
    seen = []
    cp = ColorPicker("#336699")
    cp.colorChanged.connect(seen.append)
    cp.hex.setText("#ff0000")
    cp._from_hex()
    assert cp.color == "#FF0000" and seen == ["#FF0000"]
    cp.hex.setText("zzz")
    cp._from_hex()
    assert cp.color == "#FF0000"
    cp.close()


def test_reveal_guard(monkeypatch, tmp_path):
    from confmerge.ui import platform_utils
    called = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: called.append(a))
    platform_utils.reveal_in_folder(str(tmp_path / "x.mp4"))
    assert not called            # CONFMERGE_NO_REVEAL è impostata nei test


def test_transition_previews_paint(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from confmerge.ui.transition_gallery import paint_transition
    for t in TR.TRANSITIONS:
        for k in (0.0, 0.5, 1.0):
            im = QImage(150, 84, QImage.Format_ARGB32_Premultiplied)
            p = QPainter(im)
            paint_transition(p, QRectF(0, 0, 150, 84), t.id, k)
            p.end()
