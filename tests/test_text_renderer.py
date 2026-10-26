import pytest

from conftest import qt_app  # noqa: F401
from confmerge.render import compositor
from confmerge.render.animations import ease, state_at
from confmerge.render.model import Anim, Element, Fill, Outline, Shadow, Scene, Background
from confmerge.render.text_renderer import render_element

W, H = 640, 360


def alpha_bbox(img):
    xs, ys = [], []
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            if img.pixelColor(x, y).alpha() > 0:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def test_transparent_png_outside_text(qt_app):
    img = render_element(Element(text="Ciao", size=0.15), W, H)
    assert img.hasAlphaChannel()
    assert img.pixelColor(2, 2).alpha() == 0           # angolo trasparente
    bb = alpha_bbox(img)
    assert bb and bb[0] > 100 and bb[2] < 540          # solo il testo, centrato


def test_font_size_scales_with_height(qt_app):
    small = alpha_bbox(render_element(Element(text="Ciao", size=0.05), W, H))
    big = alpha_bbox(render_element(Element(text="Ciao", size=0.15), W, H))
    assert (big[3] - big[1]) > 2 * (small[3] - small[1])


def test_resolution_independent(qt_app):
    a = alpha_bbox(render_element(Element(text="Ciao", size=0.1), 640, 360))
    b = alpha_bbox(render_element(Element(text="Ciao", size=0.1), 1280, 720))
    assert abs((b[2] - b[0]) / 1280 - (a[2] - a[0]) / 640) < 0.02


def test_outline_grows_bbox(qt_app):
    plain = alpha_bbox(render_element(Element(text="Ciao", size=0.15), W, H))
    out = alpha_bbox(render_element(Element(text="Ciao", size=0.15, outline=Outline(0.02, "#ff0000")), W, H))
    assert out[0] < plain[0] and out[2] > plain[2]


def test_shadow_adds_offset_pixels(qt_app):
    plain = alpha_bbox(render_element(Element(text="Ciao", size=0.15), W, H))
    sh = alpha_bbox(render_element(Element(text="Ciao", size=0.15, shadow=Shadow(True, "#000000", 0.01, 0.03, 45, 0.8)), W, H))
    assert sh[2] > plain[2] and sh[3] > plain[3]


def test_partial_opacity_preserved(qt_app, tmp_path):
    scene = Scene(True, 1.0, Background("transparent"), [Element(text="Ciao", size=0.2, opacity=0.5)])
    layers = compositor.plan_layers(scene.elements, W, H, 1.0, 25, tmp_path, "x")
    from PySide6.QtGui import QImage
    img = QImage(layers[0].path)
    vals = {img.pixelColor(x, y).alpha() for x in range(200, 440, 3) for y in range(120, 240, 3)}
    assert any(100 < a < 160 for a in vals)             # ~50% di 255, non 0/255


def test_gradient_fill_has_two_colors(qt_app):
    el = Element(text="MMMM", size=0.3, fill=Fill("gradient", "#ff0000", "#0000ff", 90))
    img = render_element(el, W, H)
    bb = alpha_bbox(img)
    mid = (bb[1] + bb[3]) // 2
    top, bot = [], []
    for y in range(bb[1], bb[3], 2):
        for x in range(bb[0], bb[2], 2):
            c = img.pixelColor(x, y)
            if c.alpha() > 200:
                (top if y < mid else bot).append((c.red(), c.blue()))
    assert sum(r for r, _ in top) / len(top) > sum(b for _, b in top) / len(top)    # alto: rosso
    assert sum(b for _, b in bot) / len(bot) > sum(r for r, _ in bot) / len(bot)    # basso: blu


def test_easing_endpoints():
    for name in ("linear", "ease_in_out", "cubic", "back", "expo"):
        assert ease(name, 0) == pytest.approx(0, abs=1e-3)
        assert ease(name, 1) == pytest.approx(1, abs=1e-3)
    assert max(ease("back", t / 100) for t in range(101)) > 1.05      # overshoot


def test_animation_window():
    el = Element(start=2, end=6, anim_in=Anim("fade", 1.0), anim_out=Anim("fade", 1.0))
    assert state_at(el, 1.0, 10) is None
    assert state_at(el, 2.5, 10).alpha == pytest.approx(0.5, abs=0.1)
    assert state_at(el, 4.0, 10).alpha == 1.0
    assert state_at(el, 5.9, 10).alpha < 0.2


def test_typewriter_reveals_progressively(qt_app):
    el = Element(text="Macchina", size=0.15, anim_in=Anim("typewriter", 1.0, "linear"))
    a = alpha_bbox(render_element(el, W, H, state_at(el, 0.3, 5)))
    b = alpha_bbox(render_element(el, W, H, state_at(el, 0.9, 5)))
    assert (a[2] - a[0]) < (b[2] - b[0])


def test_bar_moves_with_time():
    assert compositor.bar_x(0, 10, 1000, 0) == -1000
    assert compositor.bar_x(0, 10, 1000, 5) == -500
    assert compositor.bar_x(0, 10, 1000, 20) == 0
