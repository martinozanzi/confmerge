import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


@pytest.fixture(scope="module")
def qapp(qt_app):
    return qt_app


def test_splash_is_small_and_on_the_cursor_screen(qapp):
    from confmerge.ui import splash as S
    sp = S.make_splash("1.2.0")
    scr = S.cursor_screen()
    assert sp.width() <= 400 and sp.height() <= 160                          # piccola: non nasconde lo schermo
    assert scr.geometry().contains(sp.frameGeometry().center())
    assert not (sp.windowFlags() & Qt.WindowStaysOnTopHint)                  # altre finestre possono stare sopra
    sp.close()


def test_window_is_centered_and_fits_the_screen(qapp):
    from confmerge.ui import splash as S
    w = QWidget()
    w.resize(5000, 4000)                                                     # più grande dello schermo
    S.center_on_screen(w, S.cursor_screen())
    avail = S.cursor_screen().availableGeometry()
    assert w.width() <= avail.width() and w.height() <= avail.height()
    assert avail.contains(w.frameGeometry().center())
