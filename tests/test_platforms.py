import json

import pytest
from PySide6.QtGui import QColor, QImage

from confmerge import platforms as PF
from confmerge.project import Project
from confmerge.settings import Settings
from confmerge.spec import ExportSettings, ImageSettings, RenderSpec, output_size


def test_catalogue_and_sizes():
    ids = [p.id for p in PF.PLATFORMS]
    assert {"youtube", "shorts", "reels", "tiktok", "threads", "instagram", "x"} <= set(ids)
    sizes = {}
    for p in PF.PLATFORMS:
        sizes[p.id] = output_size(ImageSettings(aspect=p.aspect), ExportSettings(preset="Personalizzato", custom_height=p.short))
    assert sizes["shorts"] == (1080, 1920) and sizes["youtube"] == (1920, 1080) and sizes["instagram"] == (1080, 1080)
    assert sizes["x"] == (1280, 720)
    assert output_size(ImageSettings(aspect="4:5"), ExportSettings(preset="Personalizzato", custom_height=1080)) == (1080, 1350)


def test_variant_spec_moves_subtitles_above_safe_zone():
    base = RenderSpec()
    base.subtitles.position, base.subtitles.margin = "bottom", 0.08
    v = PF.variant_spec(base, PF.BY_ID["tiktok"])
    assert v.image.aspect == "9:16" and v.export.custom_height == 1080 and v.subtitles.margin >= 0.25 - 1e-9
    assert base.subtitles.margin == 0.08 and base.image.aspect == "16:9"              # la base non cambia
    base.subtitles.position = "top"
    assert PF.variant_spec(base, PF.BY_ID["tiktok"]).subtitles.margin >= PF.BY_ID["tiktok"].safe[0] + 0.02 - 1e-9


def test_common_safe_and_warnings():
    sel = [PF.BY_ID["shorts"], PF.BY_ID["tiktok"]]
    top, bottom, left, right = PF.common_safe(sel)
    assert bottom == 0.25 and right == 0.14 and top == 0.12 and PF.common_safe([]) == (0.0, 0.0, 0.0, 0.0)
    assert "limite" in PF.duration_warning(PF.BY_ID["x"], 200) and PF.duration_warning(PF.BY_ID["x"], 100) == ""
    assert PF.duration_warning(PF.BY_ID["youtube"], 99999) == ""


def test_user_overrides(tmp_path):
    (tmp_path / "piattaforme.json").write_text(json.dumps({"tiktok": {"max_s": 900, "safe": [0.1, 0.3, 0.0, 0.1]}, "x": "rotto"}))
    t = PF.get("tiktok", tmp_path)
    assert t.max_s == 900 and t.safe == (0.1, 0.3, 0.0, 0.1)
    assert PF.get("x", tmp_path).max_s == 140                                          # voce non valida: ignorata
    (tmp_path / "piattaforme.json").write_text("{non json")
    assert PF.get("tiktok", tmp_path).max_s == 600


@pytest.fixture
def canvas(qt_app, tmp_path):
    from confmerge.ui.canvas import Canvas
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path), kind="social")
    st.project = Project(clips=["a.mp4"], total_duration=10, kind="social")
    st.spec.image.aspect = "9:16"
    c = Canvas(st)
    img = QImage(640, 360, QImage.Format_ARGB32)
    img.fill(QColor(220, 30, 30))
    c.set_frame(img)
    return c, st


@pytest.mark.parametrize("mode,top_dark,mid_red", [("bars", True, True), ("blur", False, True), ("fill", False, True)])
def test_preview_matches_reframe_mode(canvas, mode, top_dark, mid_red):
    c, st = canvas
    st.spec.image.reframe = mode
    im = c.compose()
    top = im.pixelColor(im.width() // 2, 4)
    mid = im.pixelColor(im.width() // 2, im.height() // 2)
    assert (top.red() < 15 and top.green() < 15 and top.blue() < 15) == top_dark
    assert mid.red() > 150
    if mode == "blur":
        assert top.red() > 80            # lo sfondo sfocato prende il colore dell'immagine


def test_social_state_defaults(qt_app, tmp_path):
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path), kind="social")
    assert st.kind == "social" and not st.spec.credit.enabled and st.spec.audio.loudnorm and st.slot == "social"
    assert st.spec.social.platforms == ["shorts"]
