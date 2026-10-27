import pytest

from confmerge import subtitles as S
from confmerge.spec import RenderSpec, SubLine, SubtitleSettings
from confmerge.profiles import apply_profile, profile_from_spec


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def sample():
    st = SubtitleSettings(enabled=True)
    st.lines = [SubLine(10.0, 12.5, "Buongiorno a tutti"), SubLine(14.0, 16.0, "e benvenuti"), SubLine(100.0, 101.0, "fuori")]
    return st


def test_effective_lines_clip_and_shift():
    st = sample()
    ls = S.effective_lines(st, 11.0, 15.0)
    assert [(round(a.start, 2), round(a.end, 2), a.text) for a in ls] == [(0.0, 1.5, "Buongiorno a tutti"), (3.0, 4.0, "e benvenuti")]


def test_srt_format():
    srt = S.to_srt(sample(), 10.0, 20.0)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,500\nBuongiorno a tutti\n")
    assert "2\n00:00:04,000 --> 00:00:06,000\ne benvenuti" in srt and "fuori" not in srt


def test_ass_contents(qapp):
    st = sample()
    st.uppercase = True
    ass = S.to_ass(st, 10.0, 20.0, 1280, 720)
    assert "PlayResX: 1280" in ass and "PlayResY: 720" in ass and "WrapStyle: 2" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,BUONGIORNO A TUTTI" in ass
    st.position, st.box = "top", True
    ass = S.to_ass(st, 10.0, 20.0, 1280, 720)
    assert ",3," in ass.split("Style: Default,")[1].split("\n")[0]        # BorderStyle 3 = sfondo pieno
    assert S._ass_color("#FF8000") == "&H000080FF" and S._ass_color("#000000", 0.5) == "&H80000000"


def test_ass_escapes_braces(qapp):
    st = SubtitleSettings(enabled=True, lines=[SubLine(0, 2, "testo {con} graffe \\ strane")])
    assert "{con}" not in S.to_ass(st, 0, 5, 1280, 720)


def test_wrap_keeps_lines_inside(qapp):
    st = SubtitleSettings()
    txt = "una frase decisamente molto lunga che non può stare tutta su una sola riga del video verticale"
    out = S.wrap_text(st, txt, 540, 960).split("\n")
    assert len(out) >= 2 and " ".join(out) == txt


def test_preview_element_positions(qapp):
    st = SubtitleSettings()
    el = S.preview_element(st, "ciao", 1280, 720)
    assert el.y > 0.8 and el.align == "center"
    st.position = "top"
    assert S.preview_element(st, "ciao", 1280, 720).y < 0.2
    st.position = "middle"
    assert abs(S.preview_element(st, "ciao", 1280, 720).y - 0.5) < 1e-6


def test_profile_keeps_style_not_lines(qapp):
    spec = RenderSpec()
    spec.subtitles = sample()
    spec.subtitles.size = 0.07
    spec.audio.music_path = "/x/y.mp3"
    prof = profile_from_spec(spec)
    assert "lines" not in prof["subtitles"] and "music_path" not in prof["audio"]
    other = RenderSpec()
    other.subtitles.lines = [SubLine(1, 2, "mio")]
    other.audio.music_path = "/mia.mp3"
    apply_profile(other, prof)
    assert other.subtitles.size == 0.07 and [l.text for l in other.subtitles.lines] == ["mio"]
    assert other.audio.music_path == "/mia.mp3"


def test_spec_roundtrip(qapp):
    spec = RenderSpec()
    spec.subtitles = sample()
    back = RenderSpec.from_dict(spec.to_dict())
    assert [l.text for l in back.subtitles.lines] == ["Buongiorno a tutti", "e benvenuti", "fuori"]


def test_presets_apply(qapp):
    st = SubtitleSettings()
    for name in S.PRESETS:
        S.apply_preset(st, name)
    assert st.font == "Inter"


def test_controller_blockers(qapp, tmp_path, monkeypatch):
    from confmerge.settings import Settings
    from confmerge.ui.state import AppState
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    st = AppState(Settings(tmp_path))
    ctl = st.subtitles
    assert "cartella" in ctl.blocker()
    st.project = object()
    assert "chiave" in ctl.blocker()
    st.settings.keys.set("groq", "gsk_x")
    assert ctl.blocker() == ""


def test_subtitle_tab_builds_and_edits(qapp, tmp_path, monkeypatch):
    from confmerge.settings import Settings
    from confmerge.ui.graphics_page import GraphicsPage
    from confmerge.ui.state import AppState
    from confmerge.ui.review_page import ReviewPage
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    st = AppState(Settings(tmp_path))
    st.spec.subtitles = sample()
    page = GraphicsPage(st, ReviewPage(st), ("subs",), "Sottotitoli")
    tab = page._inner(page.tabs.currentWidget())
    tab.refresh()
    assert tab.table.rowCount() == 3
    tab.table.item(0, 2).setText("Ciao")
    assert st.spec.subtitles.lines[0].text == "Ciao"
    tab.table.setCurrentCell(1, 0)
    tab.delete_row()
    assert len(st.spec.subtitles.lines) == 2
    from confmerge.ui.subtitles_tab import fmt_t, parse_t
    assert parse_t("1:23,5") == 83.5 and parse_t("83") == 83.0 and parse_t("x") is None and fmt_t(83.5) == "1:23,5"
