from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from confmerge import detect


@pytest.fixture(scope="module")
def qapp(qt_app):
    from confmerge.ui.theme import theme
    theme.load_fonts()
    return qt_app


def make(tmp_path):
    for n in ("a.mp4", "b.mp4", "rec_1.wav", "rec_2.wav", "sigla.mp3", "slide.pdf", "note.txt"):
        (tmp_path / n).write_bytes(b"x" * 2048)
    return detect.classify([tmp_path])


def names(paths):
    return sorted(p.name for p in paths)


def test_dialog_lists_everything_and_pre_checks_what_belongs(qapp, tmp_path):
    from confmerge.ui.confirm_files import ConfirmFilesDialog
    det = make(tmp_path)
    d = ConfirmFilesDialog(det, det.kind)
    assert det.kind == "merge" and set(d.groups) == {"video", "audio", "slides"}
    assert names(d.selected_paths()) == ["a.mp4", "b.mp4", "rec_1.wav", "rec_2.wav", "slide.pdf"]          # la sigla non è una parte
    assert names(d._checked("audio")) == ["rec_1.wav", "rec_2.wav"] and d.groups["audio"].childCount() == 3   # ma si vede, deselezionata
    assert "2 video, 2 file audio, 1 slide" in d.summary.text()


def test_unchecking_a_file_removes_it_and_group_toggles_all(qapp, tmp_path):
    from confmerge.ui.confirm_files import ConfirmFilesDialog
    det = make(tmp_path)
    d = ConfirmFilesDialog(det, "merge")
    d.groups["video"].child(1).setCheckState(0, Qt.Unchecked)                                                 # b.mp4 non c'entra
    assert names(d._checked("video")) == ["a.mp4"]
    d.groups["slides"].setCheckState(0, Qt.Unchecked)                                                         # tutte le slide
    assert "slide.pdf" not in names(d.selected_paths())
    d.groups["video"].setCheckState(0, Qt.Unchecked)
    assert not d.ok.isEnabled()                                                                               # senza video non si va avanti


def test_social_kind_uses_only_videos(qapp, tmp_path):
    from confmerge.ui.confirm_files import ConfirmFilesDialog
    det = make(tmp_path)
    d = ConfirmFilesDialog(det, "merge")
    d.seg.setValue("social")
    d._kind_changed("social")
    assert d.kind() == "social" and names(d.selected_paths()) == ["a.mp4", "b.mp4"]
    assert d.groups["audio"].isDisabled() and "file audio" not in d.summary.text()
