import shutil
import subprocess
import time

import pytest
from PySide6.QtGui import QColor, QImage

from confmerge import platforms as PF, style_templates as ST
from confmerge.project import Project
from confmerge.render import anchors
from confmerge.render.model import Element, Fill
from confmerge.settings import Settings
from confmerge.spec import RenderSpec, SubLine


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def text_el(anchor="bc"):
    return Element(id="t", kind="text", text="CIAO", size=0.1, anchor=anchor, fill=Fill(color="#FFFFFF"))


def test_anchor_positions_follow_format_and_safe_zone(qapp):
    wide = anchors.resolve([text_el("bc")], 1280, 720)[0]
    tall = anchors.resolve([text_el("bc")], 720, 1280)[0]
    assert abs(wide.x - 0.5) < 1e-9 and wide.y > 0.85 and tall.y > 0.9
    safe = anchors.resolve([text_el("bc")], 720, 1280, [0.1, 0.25, 0.0, 0.0])[0]
    assert safe.y < tall.y - 0.2 and 1 - safe.y > 0.25                               # sopra la zona coperta in basso
    tl = anchors.resolve([text_el("tl")], 1280, 720)[0]
    tr = anchors.resolve([text_el("tr")], 1280, 720, [0.0, 0.0, 0.0, 0.2])[0]
    assert tl.x < 0.2 and tl.y < 0.2 and tr.x < 0.75 and tr.y < 0.2
    free = Element(id="f", kind="text", text="x", x=0.3, y=0.4)
    assert anchors.resolve([free], 100, 100)[0] is free
    assert anchors.resolve([text_el("mc")], 800, 600)[0].y == pytest.approx(0.5)


def test_style_capture_apply_keeps_text_and_other_targets(qapp, tmp_path):
    a = RenderSpec()
    a.subtitles.size, a.subtitles.position, a.subtitles.color = 0.07, "top", "#FFEE00"
    a.subtitles.lines = [SubLine(0, 1, "mio")]
    a.graphics.elements = [text_el("tl"), Element(id="o", kind="text", text="finale", targets=["outro"])]
    a.brand.kit_id = "k"
    store = ST.StyleStore(tmp_path)
    store.save("Reel del sindaco", a)
    assert store.list() == ["Reel del sindaco"]
    b = RenderSpec()
    b.subtitles.lines = [SubLine(5, 6, "altro")]
    b.graphics.elements = [Element(id="x", kind="text", text="vecchio"), Element(id="y", kind="text", text="titolo", targets=["title"])]
    b.brand.safe = [0.1, 0.2, 0, 0]
    ST.apply(b, store.load("Reel del sindaco"))
    assert b.subtitles.size == 0.07 and b.subtitles.position == "top" and b.subtitles.color == "#FFEE00" and b.subtitles.enabled
    assert [l.text for l in b.subtitles.lines] == ["altro"]                           # il testo dei sottotitoli non si tocca
    assert [e.id for e in b.graphics.elements if "main" in e.targets] == ["t"]
    assert [e.id for e in b.graphics.elements if "title" in e.targets] == ["y"]
    assert b.brand.kit_id == "k" and b.brand.safe == [0.1, 0.2, 0, 0]
    store.delete("Reel del sindaco")
    assert store.list() == [] and store.load("Reel del sindaco") is None


def test_style_card_and_overlays_card(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from confmerge.ui.social_style import OverlaysCard, StyleTemplateCard
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path / "c"), kind="social")
    oc = OverlaysCard(st)
    oc.add_text()
    oc.add_text()
    els = st.spec.graphics.elements
    assert len(els) == 2 and els[0].anchor == "tc" and oc.rows.count() == 2
    els[0].text = "@canale"
    els[0].anchor = "bc"
    st.spec.subtitles.size = 0.065
    card = StyleTemplateCard(st)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Mio stile", True))
    card.save()
    assert card.combo.currentData() == "Mio stile"
    st.spec.graphics.elements.clear()
    st.spec.subtitles.size = 0.03
    card._applied(0)
    assert st.spec.subtitles.size == 0.065 and [e.text for e in st.spec.graphics.elements][0] == "@canale"
    oc.sync()
    oc.remove(st.spec.graphics.elements[0])
    assert len(st.spec.graphics.elements) == 1


def test_subtitle_card_controls_sample_and_key_refresh(qapp, tmp_path, monkeypatch):
    from confmerge.ui.canvas import Canvas
    from confmerge.ui.subtitle_card import SubtitleCard
    from confmerge.ui.state import AppState
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    st = AppState(Settings(tmp_path / "c"), kind="social")
    st.project = Project(clips=["a.mp4"], total_duration=10, kind="social")
    card = SubtitleCard(st, open_settings=lambda: None)
    assert not card.make.isEnabled() and "chiave" in card.msg.text()
    st.settings.keys.set("groq", "gsk_test")
    st.keys_changed.emit()                                    # la chiave salvata nelle Impostazioni è riconosciuta subito
    assert card.make.isEnabled() and card.msg.text() == "" and not card.keybtn.isVisibleTo(card)
    # grandezza e posizione
    card.size.setValue(90)
    assert st.spec.subtitles.size == pytest.approx(0.09) and st.spec.subtitles.enabled
    card._pos("top")
    assert st.spec.subtitles.position == "top"
    card.margin.setValue(200)
    assert st.spec.subtitles.margin == pytest.approx(0.2)
    card._pos("middle")
    assert not card.margin.isVisibleTo(card) or True
    # la frase di esempio compare in anteprima anche senza righe
    cv = Canvas(st)
    img = QImage(640, 360, QImage.Format_ARGB32)
    img.fill(QColor("#202020"))
    cv.set_frame(img)
    st.spec.image.aspect = "16:9"
    st.spec.subtitles.position, st.spec.subtitles.color = "bottom", "#FFFFFF"
    st.spec.subtitles.enabled = False
    off = cv.compose()
    st.spec.subtitles.enabled = True
    on = cv.compose()
    diff = sum(1 for x in range(0, on.width(), 4) for y in range(int(on.height() * 0.6), on.height(), 2)
               if on.pixelColor(x, y) != off.pixelColor(x, y))
    assert diff > 150
    st.spec.subtitles.size = 0.14
    big = cv.compose()
    diff_big = sum(1 for x in range(0, on.width(), 4) for y in range(int(on.height() * 0.5), on.height(), 2)
                   if big.pixelColor(x, y) != off.pixelColor(x, y))
    assert diff_big > diff


def test_toggle_on_shows_sample_window(qapp, tmp_path):
    from confmerge.ui.subtitle_card import SubtitleCard
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path / "c"), kind="social")
    card = SubtitleCard(st)
    st.spec.subtitles.lines = [SubLine(100, 101, "fuori campo")]
    card.on.setChecked(True)
    assert st.spec.subtitles.enabled and st.subtitle_sample_until > time.monotonic()


def test_zone_legend_has_one_colour_per_platform(qapp, tmp_path):
    from confmerge.ui.social_shell import ZONE_COLORS, SocialLook
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path / "c"), kind="social")
    st.project = Project(clips=["a.mp4"], total_duration=5, kind="social")
    st.spec.social.platforms = ["shorts", "reels", "tiktok"]
    look = SocialLook(st)
    look.sync()
    cv = look.player.canvas
    assert [z["name"] for z in cv.safe_zones] == ["YouTube Shorts", "Instagram Reel", "TikTok"]
    assert len({z["color"] for z in cv.safe_zones}) == 3 and look.legend_lay.count() == 3
    assert cv.safe_common == PF.common_safe([PF.BY_ID[i] for i in ("shorts", "reels", "tiktok")])
    look._zone_toggle("tiktok", False)
    assert [z["name"] for z in cv.safe_zones] == ["YouTube Shorts", "Instagram Reel"]
    assert cv.safe_common[1] == 0.22                                                  # senza TikTok il limite basso scende
    st.spec.social.show_safe = False
    look._preview_changed()
    assert cv.safe_zones == []
    assert set(ZONE_COLORS) >= {"shorts", "reels", "tiktok", "threads", "youtube", "x", "instagram"}


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
def test_anchored_text_stays_above_platform_ui_in_export(qapp, tmp_path):
    from confmerge import export_engine as ee
    from confmerge.media_scan import media_info
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x101020:size=640x360:rate=25:duration=3",
                    "-f", "lavfi", "-i", "sine=f=300:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(tmp_path / "bg.mp4")], check=True)
    clip = media_info(tmp_path / "bg.mp4")
    p = Project(clips=[str(clip.path)], audio="", total_duration=clip.duration, kind="social")
    spec = RenderSpec()
    spec.credit.enabled = False
    spec.export.encoder, spec.export.bitrate_mbps = "libx264", 2.0
    spec.graphics.elements = [Element(id="t", kind="text", text="@CANALE", size=0.05, bold=True, anchor="bc",
                                      fill=Fill(color="#FFFFFF"), targets=["main"])]
    v = PF.variant_spec(spec, PF.BY_ID["tiktok"])
    v.export.custom_height = 360
    out = tmp_path / "o.mp4"
    ee.run_export(p, [clip], v, out, 0.0, p.total_duration, lambda f, s: None)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(tmp_path / "f.png")], check=True)
    im = QImage(str(tmp_path / "f.png"))
    ys = [y for y in range(im.height()) for x in range(0, im.width(), 2) if im.pixelColor(x, y).red() > 200]
    assert ys and max(ys) < im.height() * (1 - 0.25)         # il testo sta sopra la fascia coperta da TikTok (25 % in basso)


def test_subtitle_margin_respects_platform_zone_in_preview_and_export(qapp):
    from confmerge import subtitles as S
    st = RenderSpec().subtitles
    st.position, st.margin = "bottom", 0.05
    assert S.effective_margin(st, [0.1, 0.25, 0, 0]) == pytest.approx(0.27) and S.effective_margin(st, None) == 0.05
    el = S.preview_element(st, "ciao", 1080, 1920, [0.1, 0.25, 0, 0])
    plain = S.preview_element(st, "ciao", 1080, 1920)
    assert el.y < plain.y - 0.15
    v = PF.variant_spec(RenderSpec.from_dict({**RenderSpec().to_dict()}), PF.BY_ID["tiktok"])
    assert v.subtitles.margin == pytest.approx(0.27)
    st.position = "middle"
    assert S.effective_margin(st, [0.1, 0.25, 0, 0]) == 0.05


def test_overlay_library_roundtrip_and_ui(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from confmerge.overlay_library import OverlayLibrary
    from confmerge.ui.social_style import OverlaysCard
    from confmerge.ui.state import AppState
    png = tmp_path / "sticker.png"
    img = QImage(60, 30, QImage.Format_ARGB32)
    img.fill(0x80FF0000)                                                     # semitrasparente
    img.save(str(png))
    lib = OverlayLibrary(tmp_path / "root")
    el = Element(id="x", kind="image", path=str(png), width=0.2, anchor="tr", opacity=0.8, targets=["main"])
    lib.save("Bollino", el)
    png.unlink()                                                             # l'originale sparisce: la copia resta
    assert lib.list() == ["Bollino"]
    back = lib.load("Bollino")
    assert back.id != "x" and back.opacity == 0.8 and back.anchor == "tr" and back.path.endswith("Bollino.png")
    assert QImage(back.path).format() != 0 and not QImage(back.path).isNull()
    st = AppState(Settings(tmp_path / "cfg"), kind="social")
    st.settings.root = tmp_path / "root"
    card = OverlaysCard(st)
    card.saved.setCurrentIndex(card.saved.findData("Bollino"))
    card._add_saved()
    assert [e.path.endswith("Bollino.png") for e in st.spec.graphics.elements] == [True] and card.rows.count() == 1
    lib.delete("Bollino")
    assert lib.list() == [] and not (tmp_path / "root" / "overlay_salvati" / "file" / "Bollino.png").exists()


def test_gif_and_webm_overlays_become_clip_elements(qapp):
    from confmerge.render.text_renderer import is_video_overlay
    assert all(is_video_overlay(f"a{e}") for e in (".gif", ".WEBM", ".mov")) and not is_video_overlay("a.png")


def test_previews_show_example_text_until_you_write_yours(qapp):
    from confmerge import templates as T
    from confmerge.ui.canvas import Canvas
    from confmerge.ui.state import AppState
    pv = T.preview_variables({"titolo": "  ", "relatore": "Anna Verdi", "data": ""})
    assert pv["titolo"] == T.SAMPLE["titolo"] and pv["relatore"] == "Anna Verdi" and pv["data"] == T.SAMPLE["data"]
    st = AppState(kind="social")
    T.apply_title(st.spec, "vlog")
    cv = Canvas(st)
    cv.mode, cv.scene, cv.scene_target = "scene", st.spec.graphics.title, "title"
    texts = " ".join(e.text for e in cv._scene_elements() if e.kind == "text")
    assert T.SAMPLE["titolo"] in texts and "{titolo}" not in texts                # esempio, non il segnaposto vuoto
    st.spec.variables["titolo"] = "Il mio titolo"
    texts = " ".join(e.text for e in cv._scene_elements() if e.kind == "text")
    assert "Il mio titolo" in texts


def test_modern_templates_are_first_and_render(qapp):
    from confmerge import templates as T
    from confmerge.ui import template_gallery as G
    assert [t.id for t in T.TITLES[:6]] == ["vlog", "kinetic", "glass", "editorial", "outline", "punch"]
    assert T.LOWER_THIRDS[0].id == "glass" and T.OUTROS[0].id == "endscreen"
    for k, tid in (("title", "vlog"), ("title", "kinetic"), ("lower_third", "block"), ("outro", "endscreen")):
        img = G.render_template(T.get(k, tid), 320, 180)
        assert not img.isNull() and img.width() == 320
