import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from confmerge.project import Project
from confmerge.settings import Settings


@pytest.fixture
def shell(qt_app, tmp_path):
    from confmerge.ui.advanced import PHASES, AdvancedShell
    from confmerge.ui.state import AppState
    from confmerge.ui.theme import theme
    theme.load_fonts()
    st = AppState(Settings(tmp_path / "cfg"))
    sh = AdvancedShell(st)
    sh.resize(1280, 700)
    sh.show()
    yield st, sh, PHASES
    sh.close()


def test_top_bar_shows_phase_and_back_next_skip_locked(shell):
    st, sh, PHASES = shell
    assert sh.phase_lbl.text() == f"Fase 1 di {len(PHASES)} · Sorgenti"
    assert not sh.back.isVisibleTo(sh) and sh.next.isVisibleTo(sh) and not sh.next.isEnabled()      # senza progetto: tutto bloccato
    sh.step(1)
    assert sh.stack.currentIndex() == 0
    st.project = Project(clips=[], audio="", total_duration=60.0)
    sh.refresh_nav()
    assert sh.next.isEnabled()
    sh.next.click()
    assert sh.phase_lbl.text() == f"Fase 2 di {len(PHASES)} · {PHASES[1][1]}" and sh.back.isVisibleTo(sh)
    sh.goto(2)
    assert sh.phase_lbl.text().startswith("Fase 3 di 8")
    sh.goto(len(PHASES) - 2)
    assert sh.next.text() == "Esporta"
    sh.next.click()
    assert sh.stack.currentIndex() == len(PHASES) - 1 and not sh.next.isVisibleTo(sh)
    sh.back.click()
    assert sh.stack.currentIndex() == len(PHASES) - 2


def test_drop_goes_through_single_entry_point_and_view_follows_model(shell, tmp_path):
    st, sh, _ = shell
    got = []
    sh.picked.connect(got.append)
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(f))])
    sh.select.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    assert got == [[f]]
    assert not st.sources.videos                                   # lo smista la finestra, non la pagina
    # la vista mostra ciò che è stato caricato altrove (Semplice / Social), anche a pagina nascosta
    sh.goto(0)
    st.sources.videos = [f]
    st.sources.infos = []
    sh.select.render()
    sh.hide()
    sh.show()
    assert "1" in sh.select.summary.text()


def test_main_window_wires_advanced_drop(qt_app, tmp_path):
    from confmerge.ui.main_window import MainWindow
    from confmerge.ui.state import AppState
    s = Settings(tmp_path / "c")
    w = MainWindow(AppState(s), AppState(s, kind="social"))
    w.set_app("merge", animate=False)
    note = tmp_path / "nota.txt"
    note.write_text("x")
    w.adv.picked.emit([note])                                      # nessun video: messaggio, non un caricamento muto
    assert "Non ho trovato video" in w.simple.start.problem.text()
    w.close()


def test_titles_page_pills_modern_first_and_sample_note(shell):
    st, sh, _ = shell
    page = sh.titles
    assert not page.tabs.tabBar().isVisibleTo(page) and page.pills.isVisibleTo(page)
    assert [b.text() for b in page.pills.buttons] == [page.tabs.tabText(i) for i in range(page.tabs.count())]
    page.pills.buttons[1].click()
    assert page.tabs.currentIndex() == 1 and page.pills.buttons[1].isChecked() and not page.pills.buttons[0].isChecked()
    from confmerge.ui.titles_tabs import TemplateTab
    tab = page.tabs.widget(0).widget()
    assert isinstance(tab, TemplateTab)
    first = tab.gallery._cards[0]
    assert "moderni" in first.tpl.tags
    assert tab.sample_note.isVisibleTo(tab) == bool(tab._keys)
