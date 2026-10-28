import pytest

from confmerge.render.model import Element
from confmerge.spec import RenderSpec
from confmerge.ui.state import AppState


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def test_new_fields_have_defaults_and_roundtrip():
    s = RenderSpec()
    assert (s.image.vscale, s.image.vx, s.image.vy) == (1.0, 0.5, 0.5)
    assert (s.split.second_scale, s.split.second_y, s.split.mask) == (1.0, 0.5, "")
    s.image.vscale, s.split.mask, s.split.second_scale = 0.6, "circle", 2.0
    s2 = RenderSpec.from_dict(s.to_dict())
    assert (s2.image.vscale, s2.split.mask, s2.split.second_scale) == (0.6, "circle", 2.0)
    old = s.to_dict()
    for k in ("vscale", "vx", "vy"):
        old["image"].pop(k)
    assert RenderSpec.from_dict(old).image.vscale == 1.0                      # i progetti vecchi si aprono come prima
    e = Element.from_dict({"id": "x", "kind": "image"})
    assert e.mask == "" and e.mask_radius == 0.15


def test_geometry_helpers_stay_inside_and_are_even():
    from confmerge.view import shrink_rect, zoom_window
    for vx in (0.0, 0.5, 1.0):
        x, y, w, h = shrink_rect(0.5, vx, 0.9, 540, 960)
        assert 0 <= x and x + w <= 540 and 0 <= y and y + h <= 960 and w % 2 == 0 and h % 2 == 0
        x, y, w, h = zoom_window(2.0, vx, 0.1, 540, 960)
        assert 0 <= x and x + w <= 540 and 0 <= y and y + h <= 960 and (w, h) == (270, 480)
    assert shrink_rect(0.1, 0.5, 0.5, 100, 100)[2] == 40                       # non meno del 40 %
    assert zoom_window(9.0, 0.5, 0.5, 600, 600)[2] == 200                      # non oltre il 300 %


def test_split_card_shape_zoom_and_element_mask_controls(qapp):
    from PySide6.QtWidgets import QComboBox
    from confmerge.ui.element_editor import ElementEditor
    from confmerge.ui.split_card import SplitCard
    st = AppState(kind="social")
    card = SplitCard(st)
    card.shape.setCurrentIndex(card.shape.findData("circle"))
    assert st.spec.split.mask == "circle"
    card.zoom.setValue(250)
    assert st.spec.split.second_scale == 2.5 and "250" in card.zoom_lbl.text()
    card.second_y.setValue(20)
    assert st.spec.split.second_y == 0.2
    ed = ElementEditor(show_targets=False, show_timing=False)
    el = Element(id="m", kind="image", path="x.png")
    ed.set_element(el)
    combos = [w for w in ed.findChildren(QComboBox) if w.findData("circle") >= 0]
    assert combos
    combos[0].setCurrentIndex(combos[0].findData("rounded"))
    assert el.mask == "rounded"
