import shutil
import subprocess

import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from confmerge import brand
from confmerge.brand_kit import BrandKit, KitStore, contrast_color, logo_size
from confmerge.profiles import apply_profile, profile_from_spec
from confmerge.settings import Settings
from confmerge.spec import RenderSpec


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def make_logo(path, w=400, h=200, color="#FFFFFF"):
    im = QImage(w, h, QImage.Format_ARGB32)
    im.fill(QColor(0, 0, 0, 0))
    p = QPainter(im)
    p.setBrush(QColor(color))
    p.setPen(QColor(0, 0, 0, 0))
    p.drawRect(0, 0, w, h)
    p.end()
    im.save(str(path))


@pytest.fixture
def store(qapp, tmp_path):
    return KitStore(tmp_path / "cfg")


@pytest.fixture
def kit(store, tmp_path):
    k = store.new("Associazione Prova")
    k.slogan, k.social = "Insieme", "@prova"
    k.colors.primary = "#CC0000"
    store.save(k)
    make_logo(tmp_path / "logo.png", 400, 200, "#FFFFFF")
    make_logo(tmp_path / "sym.png", 300, 300, "#00FF00")
    store.add_logo(k, tmp_path / "logo.png", "Logo", "main")
    store.add_logo(k, tmp_path / "sym.png", "Partito", "symbol")
    return store.get(k.id)


def test_store_crud_and_many_kits(store):
    a, b = store.new("Zeta"), store.new("Alfa")
    assert [k.name for k in store.list()] == ["Alfa", "Zeta"]
    d = store.duplicate(a.id)
    assert d.name == "Zeta (copia)" and d.id != a.id and len(store.list()) == 3
    store.delete(b.id)
    assert store.get(b.id) is None and len(store.list()) == 2
    a.colors.accent = "#123456"
    store.save(a)
    assert store.get(a.id).colors.accent == "#123456"


def test_logos_are_copied_and_survive_original_removal(store, kit, tmp_path):
    (tmp_path / "logo.png").unlink()
    path = store.logo_path(kit, kit.logo("main"))
    assert path and logo_size(path) == (400, 200)
    store.remove_logo(kit, kit.logo("symbol"))
    assert store.get(kit.id).logo("symbol") is None
    with pytest.raises(ValueError):
        store.add_logo(kit, tmp_path / "x.exe")


def test_export_import_roundtrip(store, kit, tmp_path):
    store.export_zip(kit.id, tmp_path / "k.zip")
    other = KitStore(tmp_path / "altro")
    imp = other.import_zip(tmp_path / "k.zip")
    assert imp.name == kit.name and imp.slogan == "Insieme" and len(imp.logos) == 2
    assert other.logo_path(imp, imp.logo("main"))
    (tmp_path / "bad.zip").write_bytes(b"")
    with pytest.raises(Exception):
        other.import_zip(tmp_path / "bad.zip")


def test_apply_kit_sets_logos_subtitles_and_names(store, kit):
    spec = RenderSpec()
    from confmerge.render.model import LowerThird
    spec.graphics.lower_thirds = [LowerThird("A", "x")]
    brand.apply_kit(spec, kit, store)
    assert spec.brand.kit_id == kit.id and [lg.role for lg in spec.brand.logos] == ["main", "symbol"]
    assert [lg.corner for lg in spec.brand.logos] == ["tr", "tl"]
    s = spec.subtitles
    assert s.box and s.box_color == "#CC0000" and s.color == "#FFFFFF" and s.font == "Inter"
    assert spec.graphics.lower_thirds[0].accent == kit.colors.accent and spec.variables["social"] == "@prova"
    kit.caption_style = "outline"
    brand.apply_kit(spec, kit, store)
    assert not spec.subtitles.box and spec.subtitles.outline > 0
    brand.clear_kit(spec)
    assert not spec.brand.logos and spec.brand.kit_id == ""
    assert contrast_color("#FACC15") == "#111111" and contrast_color("#0B1220") == "#FFFFFF"


def test_brand_elements_corners_and_safe_zone(store, kit):
    spec = RenderSpec()
    brand.apply_kit(spec, kit, store)
    els = {e.id: e for e in brand.brand_elements(spec, 1000, 500)}
    main, sym = els["__logo0"], els["__logo1"]
    assert main.x > 0.5 and main.y < 0.5 and sym.x < 0.5 and sym.y < 0.5            # in alto: destra e sinistra
    assert abs(main.width - kit.logo_size) < 1e-9
    spec.brand.logos[0].enabled = False
    assert [e.id for e in brand.brand_elements(spec, 1000, 500)] == ["__logo1"]
    spec.brand.logos[0].enabled = True
    spec.brand.safe = [0.12, 0.2, 0.04, 0.14]
    moved = {e.id: e for e in brand.brand_elements(spec, 1000, 500)}
    assert moved["__logo0"].y > main.y and moved["__logo0"].x < main.x             # spostato dentro la zona sicura
    spec.brand.logos[1].corner = "bl"
    assert {e.id: e for e in brand.brand_elements(spec, 1000, 500)}["__logo1"].y > 0.5


def test_profile_keeps_brand(store, kit):
    spec = RenderSpec()
    brand.apply_kit(spec, kit, store)
    prof = profile_from_spec(spec)
    other = RenderSpec()
    apply_profile(other, prof)
    assert other.brand.kit_id == kit.id and len(other.brand.logos) == 2


def test_variant_spec_adds_platform_safe(store, kit):
    from confmerge import platforms as PF
    spec = RenderSpec()
    brand.apply_kit(spec, kit, store)
    v = PF.variant_spec(spec, PF.BY_ID["tiktok"])
    assert v.brand.safe == list(PF.BY_ID["tiktok"].safe) and spec.brand.safe == []


def test_brand_scenes_render(store, kit):
    from confmerge.render import compositor as C
    from confmerge.render.model import substitute
    for fn in (brand.brand_title_scene, brand.brand_outro_scene):
        sc = fn(kit, store)
        base = C.render_scene_background(sc, 320, 180)
        img = C.render_frame(substitute(sc.elements, {"titolo": "Prova"}), 320, 180, 3.0, 5.0, base)
        assert not img.isNull() and img.pixelColor(2, 2).isValid()
    spec = RenderSpec()
    spec.graphics.title.transition, spec.graphics.title.fade = "zoomin", 0.9
    brand.apply_brand_scene(spec, kit, store, "title")
    assert spec.graphics.title.enabled and spec.graphics.title.transition == "zoomin" and spec.graphics.title_template == "brand"
    brand.apply_brand_scene(spec, kit, store, "outro")
    assert spec.graphics.outro.enabled and spec.graphics.outro.background.color == "#CC0000"


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg assente")
def test_logos_in_exported_video(qapp, store, kit, tmp_path):
    from confmerge import export_engine as ee
    from confmerge.media_scan import media_info
    from confmerge.project import Project
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x303040:size=640x360:rate=25:duration=3",
                    "-f", "lavfi", "-i", "sine=f=300:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(tmp_path / "bg.mp4")], check=True)
    clip = media_info(tmp_path / "bg.mp4")
    p = Project(clips=[str(clip.path)], audio="", total_duration=clip.duration, kind="social")
    spec = RenderSpec()
    spec.credit.enabled = False
    spec.export.encoder, spec.export.preset, spec.export.custom_height = "libx264", "Personalizzato", 360
    spec.export.bitrate_mbps = 2.0
    brand.apply_kit(spec, kit, store)
    out = tmp_path / "o.mp4"
    ee.run_export(p, [clip], spec, out, 0.0, p.total_duration, lambda f, s: None)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(tmp_path / "f.png")], check=True)
    im = QImage(str(tmp_path / "f.png"))
    tr = im.pixelColor(int(im.width() * 0.90), int(im.height() * 0.07))             # logo bianco in alto a destra
    tl = im.pixelColor(int(im.width() * 0.07), int(im.height() * 0.08))             # simbolo verde in alto a sinistra
    mid = im.pixelColor(im.width() // 2, im.height() // 2)
    assert tr.red() > 200 and tr.green() > 200 and tl.green() > 200 and tl.red() < 80 and mid.red() < 90


def test_brand_card_and_dialog(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from confmerge.ui.brand_card import BrandCard
    from confmerge.ui.brand_dialog import BrandDialog
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path / "c"), kind="social")
    k = st.kits.new("Uno")
    make_logo(tmp_path / "l.png")
    st.kits.add_logo(k, tmp_path / "l.png", "L", "main")
    card = BrandCard(st, scenes=True)
    assert card.combo.count() == 2 and not card.t_btn.isEnabled()
    card.combo.setCurrentIndex(1)
    assert st.spec.brand.kit_id == k.id and len(st.spec.brand.logos) == 1 and card.t_btn.isEnabled()
    card._scene("title")
    assert st.spec.graphics.title_template == "brand"
    card.logos_box.lay.itemAt(0).widget().setChecked(False)
    assert st.spec.brand.logos[0].enabled is False
    dlg = BrandDialog(st)
    assert dlg.list.count() == 1 and dlg.kit.name == "Uno"
    monkeypatch.setattr("PySide6.QtWidgets.QInputDialog.getText", lambda *a, **k: ("Due", True))
    dlg.new()
    assert dlg.list.count() == 2 and dlg.kit.name == "Due"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "l.png"), ""))
    dlg.add_logo()
    assert len(st.kits.get(dlg.kit.id).logos) == 1
    dlg.kit.colors.primary = "#00AA00"
    dlg._changed()
    assert st.kits.get(dlg.kit.id).colors.primary == "#00AA00"
    got = []
    dlg.chosen.connect(got.append)
    dlg._use()
    assert got == [dlg.kit.id]


def test_social_preview_applies_safe_zone_to_logos(qapp, tmp_path):
    from confmerge.project import Project
    from confmerge.ui.state import AppState
    from confmerge.ui.social_shell import SocialLook
    st = AppState(Settings(tmp_path / "c"), kind="social")
    st.project = Project(clips=["a.mp4"], total_duration=5, kind="social")
    look = SocialLook(st)
    st.spec.social.platforms = ["tiktok"]
    look.sync()
    assert st.spec.brand.safe and st.spec.brand.safe[1] == 0.25          # in basso lascia la zona di TikTok
    st.spec.social.platforms = ["youtube"]
    look.sync()
    assert st.spec.brand.safe == [0.0, 0.0, 0.0, 0.0]
