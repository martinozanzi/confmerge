import pytest

from confmerge.render import compositor
from confmerge.render.model import Element, LowerThird, lower_third_elements, resolve_text, substitute
from confmerge.settings import Settings


def test_placeholders_and_empty_lower_third():
    v = {"titolo": "Convegno", "relatore": "Anna"}
    assert resolve_text("{titolo} – {data}", v) == "Convegno – "
    els = substitute([Element(text="{relatore}"), Element(text="fisso"), Element(kind="shape")], v)
    assert [e.text for e in els[:2]] == ["Anna", "fisso"]
    assert lower_third_elements(LowerThird(name="{relatore}", role="{ruolo}"), 0, {}) == []      # nessun relatore → nessuna barra
    assert len(lower_third_elements(LowerThird(name="{relatore}", role="{ruolo}"), 0, v)) == 4


def test_hidden_layers_are_not_rendered(qt_app, tmp_path):
    el = Element(text="CIAO", size=0.2)
    on = compositor.render_frame([el], 320, 180, 0.0, 5.0)
    el.visible = False
    off = compositor.render_frame([el], 320, 180, 0.0, 5.0)
    assert any(on.pixelColor(x, 90).alpha() for x in range(0, 320, 4))
    assert not any(off.pixelColor(x, y).alpha() for x in range(0, 320, 4) for y in range(0, 180, 6))
    assert compositor.plan_layers([el], 320, 180, 5.0, 25, tmp_path, "x") == []


def test_starter_profile_created_once(tmp_path):
    s = Settings(tmp_path)
    assert s.ensure_starter_profile() is True
    assert "Conferenza (semplice)" in s.list_profiles() and s.data["current_profile"] == "Conferenza (semplice)"
    assert s.ensure_starter_profile() is False


def test_undo_keeps_object_identity(qt_app, tmp_path):
    from confmerge.ui.state import AppState
    st = AppState(Settings(tmp_path))
    audio_obj, img_obj = st.spec.audio, st.spec.image
    st.spec.image.zoom = 1.0
    st._undo_timer.stop()
    st._commit()
    st.spec.image.zoom = 2.0
    st.spec.audio.highpass = True
    st.touch()
    st._undo_timer.stop()
    st._commit()
    assert st.undo()
    assert st.spec.image.zoom == 1.0 and st.spec.audio.highpass is False
    assert st.spec.audio is audio_obj and st.spec.image is img_obj          # i widget legati agli oggetti restano validi
    assert st.redo() and st.spec.image.zoom == 2.0
    assert not st.redo()


def test_sources_model_modes(qt_app, tmp_path):
    from confmerge.ui.controllers import SourcesModel, friendly_message
    m = SourcesModel()
    assert not m.ready
    assert friendly_message("Calcolo dell'offset di sincronizzazione…") == "Sincronizzo l'audio…"
    assert friendly_message("Suggerimento dei tagli…") == "Cerco inizio e fine…"
    assert friendly_message("Estrazione audio camera (1/2)…") == "Unisco i video…"
