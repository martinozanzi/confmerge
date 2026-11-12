import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CONFMERGE_NO_CONFIRM", "1")

from confmerge.queue import PENDING, QueueItem


def test_progress_widgets_ignore_nan(qtbot=None):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from confmerge.ui.widgets.progress import ProgressBarThin, ProgressRing
    for w in (ProgressBarThin(), ProgressRing(80)):
        w.setValue(float("nan"))
        w.setValue(float("inf"))
        w.setValue(0.4)
        w.grab()
        assert 0.0 <= w.value() <= 1.0


def test_status_line_shows_stage_and_position():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from confmerge.ui.controllers import ExportController
    from confmerge.queue import ExportQueue

    class St:
        queue = ExportQueue()
    ctl = ExportController(St())
    a, b = QueueItem("uno.mp4", lambda c, p: None), QueueItem("due.mp4", lambda c, p: None)
    St.queue.add(a)
    St.queue.add(b)
    a.status, a.started, a.stage = "in corso", time.time() - 65, "Misuro il volume…"
    line = ctl.status_line(a)
    assert "1 di 2" in line and "uno.mp4" in line and "Misuro il volume" in line and "1:05" in line
    assert ctl.pending_count() == 1 and b.status == PENDING
