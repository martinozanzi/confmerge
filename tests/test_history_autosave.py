import json

import pytest
from PySide6.QtWidgets import QMessageBox

from confmerge import autosave as AS
from confmerge.project import Project
from confmerge.settings import Settings
from confmerge.spec import SubLine


@pytest.fixture
def st(qt_app, tmp_path):
    from confmerge.ui.state import AppState
    s = AppState(Settings(tmp_path / "cfg"))
    s.project = Project(clips=[str(tmp_path / "a.mp4")], audio=str(tmp_path / "a.wav"), total_duration=100.0)
    s.reset_history()
    s.mark_clean()
    return s


def change(s, fn):
    fn()
    s.touch()
    s._undo_timer.stop()
    s._commit()


def test_history_labels_and_jump(st):
    change(st, lambda: setattr(st.spec.image, "zoom", 1.5))
    change(st, lambda: setattr(st.spec.audio, "music_path", "m.mp3"))
    change(st, lambda: st.spec.subtitles.lines.append(SubLine(0, 1, "x")))
    change(st, lambda: setattr(st.project, "trim_start", 7.0))
    labels = [e.label for e in st.history]
    assert labels == ["Inizio", "Formato e ritaglio", "Musica", "Testo dei sottotitoli", "Inizio e fine del video"]
    assert st.history_index == 4 and st.can_undo and not st.can_redo
    assert st.jump(1)
    assert st.spec.image.zoom == 1.5 and st.spec.audio.music_path == "" and st.project.trim_start is None
    assert st.can_redo and not st.jump(1)
    assert st.jump(4) and st.project.trim_start == 7.0 and st.spec.subtitles.lines[0].text == "x"
    # una modifica dopo un ritorno indietro cancella il «futuro»
    st.jump(2)
    change(st, lambda: setattr(st.spec.credit, "duration", 4.5))
    assert [e.label for e in st.history][-1] == "Credito" and len(st.history) == 4 and not st.can_redo


def test_multi_change_label(st):
    def both():
        st.spec.image.zoom = 2.0
        st.spec.audio.highpass = True
    change(st, both)
    assert st.history[-1].label.startswith("Più modifiche")


def test_undo_redo_keep_trim_signal(st):
    seen = []
    st.review.trimChanged.connect(lambda: seen.append(1))
    change(st, lambda: setattr(st.project, "trim_end", 50.0))
    st.undo()
    assert st.project.trim_end is None and seen
    st.redo()
    assert st.project.trim_end == 50.0


def test_history_limit(st):
    for i in range(130):
        change(st, lambda i=i: setattr(st.spec.image, "zoom", 1.0 + i / 1000))
    assert len(st.history) == 100 and st.history_index == 99


def test_dirty_and_clean(st, tmp_path):
    assert not st.is_dirty()
    change(st, lambda: setattr(st.project, "trim_start", 3.0))
    assert st.is_dirty()
    st.save_to(tmp_path / "p.confmerge")
    assert not st.is_dirty() and st.project_path == tmp_path / "p.confmerge"
    assert Project.load(tmp_path / "p.confmerge").trim_start == 3.0
    change(st, lambda: setattr(st.spec.credit, "duration", 4.0))
    assert st.is_dirty()
    st.project.offset_s = 1.0                                           # anche la sincronia conta
    st.mark_clean()
    st.project.offset_s = 2.0
    assert st.is_dirty()


def test_autosave_unnamed_goes_to_recovery(st):
    assert st.autosave() == ""
    change(st, lambda: setattr(st.spec.image, "zoom", 1.7))
    assert st.autosave() == "recupero"
    assert AS.has_recovery(st.settings.root)
    assert json.loads(AS.recovery_file(st.settings.root).read_text())["spec"]["image"]["zoom"] == 1.7
    assert st.autosave() == ""                                           # niente di nuovo: non riscrive
    assert st.is_dirty()                                                 # la copia di sicurezza non è un salvataggio


def test_autosave_named_writes_file(st, tmp_path):
    st.save_to(tmp_path / "n.confmerge")
    change(st, lambda: setattr(st.spec.image, "zoom", 1.9))
    assert st.is_dirty()
    assert st.autosave() == "file"
    assert not st.is_dirty()
    assert Project.load(tmp_path / "n.confmerge").spec["image"]["zoom"] == 1.9
    assert not AS.has_recovery(st.settings.root)
    st.settings.data["autosave_named"] = False
    change(st, lambda: setattr(st.spec.image, "zoom", 2.2))
    assert st.autosave() == "recupero" and Project.load(tmp_path / "n.confmerge").spec["image"]["zoom"] == 1.9


def test_save_clears_recovery(st, tmp_path):
    change(st, lambda: setattr(st.spec.image, "zoom", 1.2))
    st.autosave()
    assert AS.has_recovery(st.settings.root)
    st.save_to(tmp_path / "s.confmerge")
    assert not AS.has_recovery(st.settings.root)


def test_atomic_save_leaves_no_tmp(tmp_path):
    Project().save(tmp_path / "x.confmerge")
    assert [f.name for f in tmp_path.iterdir()] == ["x.confmerge"]


def _window(qt_app, st):
    from confmerge.ui.main_window import MainWindow
    return MainWindow(st)


def test_confirm_discard_flows(st, qt_app, monkeypatch, tmp_path):
    monkeypatch.delenv("CONFMERGE_NO_CONFIRM")
    w = _window(qt_app, st)
    assert w.confirm_discard()                                           # pulito: nessuna domanda
    change(st, lambda: setattr(st.spec.image, "zoom", 1.3))
    asked = []

    def fake_exec(self):
        asked.append(self.text())
        btn = {"salva": None}
        for b in self.buttons():
            if b.text() == answer["text"]:
                self._chosen = b
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self._chosen)
    answer = {"text": "Annulla"}
    assert not w.confirm_discard() and asked
    answer["text"] = "Non salvare"
    st.autosave()
    assert AS.has_recovery(st.settings.root)
    assert w.confirm_discard() and not AS.has_recovery(st.settings.root)
    # con nome e autosave attivo: nessuna domanda, salva da solo
    st.save_to(tmp_path / "w.confmerge")
    change(st, lambda: setattr(st.spec.image, "zoom", 1.8))
    asked.clear()
    assert w.confirm_discard() and not asked and not st.is_dirty()
    # con nome ma autosave spento: chiede
    st.settings.data["autosave_named"] = False
    change(st, lambda: setattr(st.spec.image, "zoom", 2.0))
    answer["text"] = "Annulla"
    assert not w.confirm_discard() and asked
    # chiusura della finestra rispetta la scelta
    from PySide6.QtGui import QCloseEvent
    ev = QCloseEvent()
    w.closeEvent(ev)
    assert not ev.isAccepted()
    w.close()


def test_history_dialog_and_buttons(st, qt_app):
    from confmerge.ui.history_dialog import HistoryDialog
    w = _window(qt_app, st)
    assert not w.back_btn.isEnabled()
    change(st, lambda: setattr(st.spec.image, "zoom", 1.4))
    assert w.back_btn.isEnabled() and not w.fwd_btn.isEnabled()
    d = HistoryDialog(st)
    assert d.list.count() == 2 and "Formato e ritaglio" in d.list.item(0).text() and "adesso" in d.list.item(0).text()
    d._go(d.list.item(1))
    assert st.spec.image.zoom != 1.4 and w.fwd_btn.isEnabled()
    d._step(+1)
    assert st.spec.image.zoom == 1.4
    w.close()


def test_recovery_offer_and_restore(st, qt_app, monkeypatch):
    monkeypatch.delenv("CONFMERGE_NO_RECOVERY")
    change(st, lambda: setattr(st.spec.image, "zoom", 1.6))
    st.autosave()
    st.project = None
    w = _window(qt_app, st)
    opened = []
    monkeypatch.setattr(w, "open_project", lambda path, recovery=False: opened.append((path, recovery)))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: [setattr(self, "_c", b) for b in self.buttons() if b.text() == "Riprendi il lavoro"] and 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self._c)
    w._offer_recovery()
    assert opened and opened[0][1] is True and opened[0][0].endswith("recupero.confmerge")
    monkeypatch.setattr(QMessageBox, "exec", lambda self: [setattr(self, "_c", b) for b in self.buttons() if b.text() == "Scarta"] and 0)
    w._offer_recovery()
    assert not AS.has_recovery(st.settings.root)
    w.close()
