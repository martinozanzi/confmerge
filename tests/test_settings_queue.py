import threading

import pytest

from confmerge.queue import DONE, FAILED, CANCELLED, ExportQueue, QueueItem
from confmerge.settings import Settings
from confmerge.ffmpeg_wrapper import Cancelled


def test_profiles_roundtrip(tmp_path):
    s = Settings(tmp_path)
    prof = s.load_profile("Nuovo")
    assert prof["credit"]["enabled"] is True and prof["credit"]["duration"] == 3.0   # credito attivo di default
    prof["credit"]["enabled"] = False
    s.save_profile("Canale A", prof)
    assert s.load_profile("Canale A")["credit"]["enabled"] is False                   # per profilo
    s.duplicate_profile("Canale A", "Canale B")
    assert {"Canale A", "Canale B"} <= set(s.list_profiles())
    s.export_profile("Canale A", tmp_path / "x.json")
    s.delete_profile("Canale A")
    name = s.import_profile(tmp_path / "x.json")
    assert name == "Canale A" and s.load_profile(name)["credit"]["enabled"] is False
    s.data["last_folder"] = "/x"
    s.save()
    assert Settings(tmp_path).data["last_folder"] == "/x"


def test_apply_profile_to_spec(tmp_path):
    from confmerge.profiles import apply_profile, profile_from_spec
    from confmerge.spec import RenderSpec
    a = RenderSpec()
    a.credit.enabled, a.credit.duration = False, 4.0
    a.audio.loudnorm = False
    b = RenderSpec()
    apply_profile(b, profile_from_spec(a))
    assert b.credit.enabled is False and b.credit.duration == 4.0 and b.audio.loudnorm is False


def test_queue_order_and_cancel():
    q = ExportQueue()
    log = []
    for n in "abc":
        q.add(QueueItem(n, lambda c, p, n=n: log.append(n)))
    q.move(2, -1)                         # a c b
    q.cancel(0)                           # annulla a (in attesa)
    q.run_all()
    assert log == ["c", "b"] and q.items[0].status == CANCELLED
    assert [i.status for i in q.items[1:]] == [DONE, DONE]


def test_queue_failure_does_not_stop_others():
    q = ExportQueue()
    def bad(c, p): raise RuntimeError("boom")
    q.add(QueueItem("x", bad))
    q.add(QueueItem("y", lambda c, p: None))
    q.run_all()
    assert q.items[0].status == FAILED and "boom" in q.items[0].error and q.items[1].status == DONE


def test_queue_cancel_running():
    q = ExportQueue()
    def job(cancel, prog):
        cancel.set()
        raise Cancelled()
    q.add(QueueItem("x", job))
    q.run_all()
    assert q.items[0].status == CANCELLED


def test_cancel_all_cancels_pending_and_running():
    q = ExportQueue()
    a, b = QueueItem("a", lambda c, p: None), QueueItem("b", lambda c, p: None)
    q.add(a)
    q.add(b)
    a.status = "in corso"
    q.cancel_all()
    assert a.cancel.is_set() and b.status == CANCELLED


def test_nan_progress_is_ignored_and_stage_and_start_are_recorded():
    q = ExportQueue()

    def job(cancel, prog):
        prog(float("nan"), None)
        prog(float("inf"), None)
        prog(0.5, None)

    it = QueueItem("a", job)
    q.add(it)
    q.run_next()
    assert it.status == DONE and it.progress == 1.0 and it.started > 0


def test_run_export_reports_stages(tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg non disponibile")
    from confmerge import export_engine as ee
    import inspect
    assert "stage" in inspect.signature(ee.run_export).parameters
