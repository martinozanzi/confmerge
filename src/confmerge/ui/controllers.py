"""Logica dell'interfaccia, senza widget: sorgenti, analisi, revisione, export.

Le due modalità (Semplice e Avanzata) sono viste diverse sugli stessi controller e sullo stesso AppState.
"""
from __future__ import annotations

import copy
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .. import estimator, export_engine as ee, paths, pipeline, proxy
from ..ffmpeg_wrapper import FFmpegError
from ..media_scan import (AUDIO_EXT, SLIDE_EXT, VIDEO_EXT, MediaInfo, _natural_key, find_gaps, media_info, order_clips,
                          pick_external_audio, scan_folder)
from ..queue import DONE, FAILED, QueueItem
from ..spec import RenderSpec, output_size
from ..worker import Worker

log = logging.getLogger(__name__)

def theme_prefs():
    from .theme import theme
    return theme.prefs


ORDER_MODES = ("date", "name", "manual")


def friendly_message(msg: str) -> str:
    """Messaggi di avanzamento in italiano semplice (senza termini tecnici)."""
    m = msg.lower()
    for key, text in (("lettura dei metadati", "Guardo i video…"), ("audio camera", "Unisco i video…"),
                      ("audio esterno", "Ascolto la registrazione…"), ("offset", "Sincronizzo l'audio…"),
                      ("tagli", "Cerco inizio e fine…"), ("anteprima", "Preparo l'anteprima…"),
                      ("completata", "Fatto!")):
        if key in m:
            return text
    return msg


# ---------------------------------------------------------------------------------------------------------------- sorgenti
class SourcesModel(QObject):
    """Video, audio esterno e slide scelti dall'utente, con ordine di montaggio."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.videos: list[Path] = []
        self.audio: Path | None = None
        self.slides: list[Path] = []
        self.infos: list[MediaInfo] = []
        self.order_mode = "date"
        self.notes: list[str] = []
        self.folder: Path | None = None
        self._cache: dict[Path, MediaInfo] = {}

    @property
    def ready(self) -> bool:
        return bool(self.videos and self.audio)

    def clear(self) -> None:
        self.videos, self.audio, self.slides, self.infos, self.notes, self.folder = [], None, [], [], [], None
        self.changed.emit()

    def load_folder(self, folder: Path) -> None:
        scan = scan_folder(folder)
        self.folder = Path(folder)
        self.videos = list(scan.videos)
        self.audio = pick_external_audio(scan.audios)
        self.slides = list(scan.slides)
        self.order_mode = "date"
        self.refresh(reorder=True)

    def accept_paths(self, items: list[Path]) -> Path | None:
        """Trascinamento di file/cartelle: una cartella carica tutto; altrimenti ogni file va al suo posto."""
        for p in items:
            if p.is_dir():
                self.load_folder(p)
                return p
        for p in items:
            ext = p.suffix.lower()
            if ext in VIDEO_EXT and p not in self.videos:
                self.videos.append(p)
            elif ext in AUDIO_EXT:
                self.audio = p
            elif ext in SLIDE_EXT:
                self.slides.append(p)
        self.refresh(reorder=True)
        return None

    def add_videos(self, paths_: list[Path]) -> None:
        self.videos += [p for p in paths_ if p not in self.videos]
        self.refresh(reorder=True)

    def set_audio(self, p: Path) -> None:
        self.audio = p
        self.changed.emit()

    def add_slides(self, paths_: list[Path]) -> None:
        self.slides += list(paths_)
        self.changed.emit()

    def remove(self, i: int) -> None:
        if 0 <= i < len(self.videos):
            del self.videos[i]
            self.refresh(reorder=True)

    def move(self, i: int, d: int) -> None:
        j = i + d
        if 0 <= i < len(self.videos) and 0 <= j < len(self.videos):
            self.videos[i], self.videos[j] = self.videos[j], self.videos[i]
            self.infos[i], self.infos[j] = self.infos[j], self.infos[i]
            self.order_mode = "manual"
            self.refresh()

    def set_order(self, mode: str) -> None:
        self.order_mode = mode if mode in ORDER_MODES else "date"
        if self.order_mode != "manual":
            self.refresh(reorder=True)
        else:
            self.changed.emit()

    def _info(self, p: Path) -> MediaInfo | None:
        if p not in self._cache:
            try:
                self._cache[p] = media_info(p)
            except FFmpegError as e:
                self.notes.append(str(e))
                return None
        return self._cache[p]

    def _sorted(self, infos: list[MediaInfo]) -> list[MediaInfo]:
        by_name = sorted(infos, key=lambda c: _natural_key(c.path))
        by_date, how = order_clips(infos)
        if self.order_mode == "manual":
            known = {c.path: c for c in infos}
            kept = [known[v] for v in self.videos if v in known]
            seen = {k.path for k in kept}
            return kept + [c for c in by_name if c.path not in seen]
        if self.order_mode == "name":
            return by_name
        if how != "creation_time":
            self.notes.append("Le date di registrazione mancano o sono uguali: ho usato l'ordine dei nomi.")
        elif [c.path for c in by_date] != [c.path for c in by_name]:
            self.notes.append("L'ordine per data è diverso da quello per nome file: controlla che il primo dell'elenco "
                              "sia davvero l'inizio (puoi cambiare criterio).")
        return by_date

    def refresh(self, reorder: bool = False) -> None:
        if reorder or len(self.infos) != len(self.videos):
            self.notes = []
            infos = [i for i in (self._info(v) for v in self.videos) if i]
            self.infos = self._sorted(infos) if infos else []
            self.videos = [c.path for c in self.infos]
        self.changed.emit()

    def warnings(self) -> list[str]:
        return list(self.notes) + [g.message() for g in find_gaps(self.infos)]


# ---------------------------------------------------------------------------------------------------------------- analisi
class AnalysisRunner(QObject):
    """Unione logica, sincronizzazione, suggerimento dei tagli e prima anteprima, in un thread."""
    progress = Signal(float, str)        # 0..1, messaggio semplice
    finished = Signal()
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.worker: Worker | None = None

    @property
    def running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def start(self, videos: list[Path], audio: Path, slides: list[Path]) -> None:
        paths.temp_dir()

        def job(cancel, report):
            rep = pipeline.analyze(videos, audio, lambda m, f: report(f * 0.5, friendly_message(m)), cancel, keep_order=True)
            out = paths.temp_dir() / "proxy.mp4"
            a, b = proxy.initial_window(rep.project)
            msg = "Preparo l'anteprima…"
            report(0.5, msg)
            proxy.build_window(rep.project, rep.clips, a, b, out, lambda f, s: report(0.5 + f * 0.5, msg), cancel)
            return rep, out, (a, b)

        self.worker = Worker(job)
        self.worker.progress.connect(self.progress)
        self.worker.finished_ok.connect(lambda r: self._ok(r, slides))
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.start()

    def open_project(self, proj) -> None:
        """Riapre un progetto salvato: legge i metadati e l'audio per la forma d'onda e prepara l'anteprima."""
        import numpy as np
        from ..ffmpeg_wrapper import decode_audio_mono

        def job(cancel, report):
            clips = [media_info(c) for c in proj.clips]
            report(0.2, "Leggo l'audio…")
            cam = [decode_audio_mono(c.path, 8000, c.duration) if c.has_audio else np.zeros(int(c.duration * 8000), np.float32)
                   for c in clips]
            ext = decode_audio_mono(proj.audio, 8000)
            report(0.5, "Preparo l'anteprima…")
            out = paths.temp_dir() / "proxy.mp4"
            a, b = proxy.initial_window(proj)
            proxy.build_window(proj, clips, a, b, out, lambda fr, s: report(0.5 + fr * 0.5, "Preparo l'anteprima…"), cancel)
            return clips, np.concatenate(cam), ext, out, (a, b)

        def ok(res):
            st = self.state
            st.clips, st.cam, st.ext, st.proxy, st.proxy_range = res
            st.load_project(proj)
            self.finished.emit()

        self.worker = Worker(job)
        self.worker.progress.connect(self.progress)
        self.worker.finished_ok.connect(ok)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.start()

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel()

    def _ok(self, res, slides: list[Path]) -> None:
        rep, out, rng = res
        st = self.state
        st.project, st.clips, st.cam, st.ext = rep.project, rep.clips, rep.cam, rep.ext
        st.proxy, st.proxy_stale, st.warnings, st.proxy_range = out, False, rep.warnings, rng
        if slides:
            st.spec.slides.files = [str(s) for s in slides]
            st.spec.slides.enabled = True
        st.spec.image.kb_t1 = min(st.spec.image.kb_t1, rep.project.total_duration)
        st.project_changed.emit()
        self.finished.emit()


# ---------------------------------------------------------------------------------------------------------------- revisione
def sync_quality(confidence: float) -> tuple[str, str, str]:
    """(parola, tipo di badge, spiegazione): il numero grezzo non si mostra, solo nel tooltip."""
    if confidence >= 15:
        return "Ottima", "ok", "Il programma è molto sicuro che voce e video coincidano."
    if confidence >= 7:
        return "Buona", "info", "Probabilmente è a posto: controlla guardando le labbra."
    return "Da controllare", "warn", "Il programma non è sicuro: guarda e ascolta con attenzione e correggi a mano."


def seconds_text(v: float) -> str:
    return f"{abs(v):.1f}".replace(".", ",") + (" secondi" if abs(v) != 1.0 else " secondo")


class ReviewController(QObject):
    """Sincronia, finestre di anteprima e tagli: usato sia dalla schermata Avanzata sia da quella Semplice."""
    windowReady = Signal(object, float, float, object)   # file, origine, fine, posizione da raggiungere
    message = Signal(str)                                  # stato per l'utente (es. «Preparo l'anteprima…»)
    syncChanged = Signal()
    trimChanged = Signal()
    STEP_S, BIG_STEP_S = 0.1, 0.5

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.worker: Worker | None = None
        self._queued: tuple | None = None
        self._n = 0
        self.auto_offset = 0.0
        self._offset_timer = QTimer(self)
        self._offset_timer.setSingleShot(True)
        self._offset_timer.setInterval(1200)
        self._offset_timer.timeout.connect(lambda: self.apply_offset(self._last_pos))
        self._last_pos = 0.0
        state.project_changed.connect(self._on_project)

    def _on_project(self):
        pr = self.state.project
        if pr:
            self.auto_offset = pr.effective_offset

    @property
    def project(self):
        return self.state.project

    # --- finestre di anteprima
    def need_window(self, t: float) -> None:
        a, b = proxy.window_around(self.project, t)
        self.message.emit("Sto preparando l'anteprima di questo punto: ci vuole qualche secondo…")
        self._queue(("window", a, b, t))

    def apply_offset(self, pos: float) -> None:
        st = self.state
        if not st.proxy or not st.project:
            return
        a, b = st.proxy_range
        self.message.emit("Aggiorno l'audio dell'anteprima…")
        self._queue(("audio", a, b, pos))

    def _queue(self, job: tuple) -> None:
        if self.worker and self.worker.isRunning():
            self._queued = job
            return
        self._start(job)

    def _start(self, job: tuple) -> None:
        st = self.state
        pr = st.project
        self._n += 1
        out = paths.temp_dir() / f"win_{self._n}.mp4"
        kind, a, b, seek = job
        if kind == "window":
            fn = lambda c, r: proxy.build_window(pr, st.clips, a, b, out, lambda f, s: None, c)  # noqa: E731
        else:
            src = st.proxy
            fn = lambda c, r: proxy.rebuild_audio(pr, src, out, a, b - a, c)  # noqa: E731
        self.worker = Worker(fn)
        self.worker.finished_ok.connect(lambda p, a=a, b=b, seek=seek, kind=kind: self._done(p, a, b, seek, kind))
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._next)
        self.worker.start()

    def _done(self, path, a, b, seek, kind) -> None:
        st = self.state
        old = st.proxy
        st.proxy, st.proxy_range, st.proxy_stale = path, (a, b), False
        self.windowReady.emit(path, a, b, seek)
        self.message.emit("Audio aggiornato: premi «Guarda e ascolta» per controllare." if kind == "audio" else "")
        try:
            if old and old != path:
                Path(old).unlink(missing_ok=True)
        except OSError:
            pass

    def _failed(self, msg: str) -> None:
        log.error("Anteprima non riuscita: %s", msg)
        self.message.emit("Non sono riuscito a preparare l'anteprima di questo punto. Riprova o scegli un altro punto.")

    def _next(self) -> None:
        if self._queued:
            job, self._queued = self._queued, None
            self._start(job)

    # --- sincronia
    def nudge(self, sign: int, big: bool, pos: float) -> None:
        self.set_offset(self.project.effective_offset + sign * (self.BIG_STEP_S if big else self.STEP_S), pos)

    def set_offset(self, v: float, pos: float = 0.0) -> None:
        pr = self.project
        if pr.use_drift_correction:
            pr.offset_corrected_s = v
        else:
            pr.offset_s = v
        self.state.proxy_stale = True
        self._last_pos = pos
        self.syncChanged.emit()
        self.message.emit("Sto aggiornando l'audio dell'anteprima: tra un attimo potrai riascoltare.")
        self._offset_timer.start()

    def reset_offset(self, pos: float = 0.0) -> None:
        self.set_offset(self.auto_offset, pos)

    def set_drift(self, on: bool, pos: float = 0.0) -> None:
        pr = self.project
        pr.use_drift_correction = on
        self.auto_offset = pr.effective_offset
        self.state.proxy_stale = True
        self._last_pos = pos
        self.syncChanged.emit()
        self._offset_timer.start()

    def offset_is_manual(self) -> bool:
        return abs(self.project.effective_offset - self.auto_offset) > 0.0005

    def has_drift(self) -> bool:
        pr = self.project
        return pr.offset_corrected_s is not None and pr.drift_s is not None and abs(pr.drift_s) > 0.05

    # --- tagli
    def set_trim(self, start: float | None, end: float | None) -> None:
        pr = self.project
        pr.trim_start, pr.trim_end = start, end
        pr.trim_confirmed = True
        self.trimChanged.emit()
        self.state.spec_changed.emit()

    def apply_suggestion(self) -> None:
        pr = self.project
        if pr and pr.suggested_start is not None:
            self.set_trim(pr.suggested_start, pr.suggested_end)

    def keep_all(self) -> None:
        self.set_trim(None, None)

    def trim_confirmed(self) -> bool:
        pr = self.project
        return bool(pr and pr.trim_confirmed)


# ---------------------------------------------------------------------------------------------------------------- export
def fmt_dur(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


@dataclass
class Prepared:
    spec: RenderSpec
    proj: object
    dec: ee.Decision
    out: Path
    t0: float
    t1: float
    space_warnings: list[str] = field(default_factory=list)


class ExportController(QObject):
    estimateStarted = Signal()
    estimateReady = Signal(object)
    estimateFailed = Signal(str)
    queueChanged = Signal()
    progress = Signal(object, float, object, int)      # elemento, frazione, secondi residui | None, byte attuali
    finished = Signal(list)                            # [(elemento, rapporto | None)]
    previewReady = Signal(object)
    previewFailed = Signal(str)
    powerRequested = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.active = False                  # le viste lo attivano quando sono visibili
        self.est: ee.Estimate | None = None
        self.est_worker: Worker | None = None
        self.run_worker: Worker | None = None
        self.prev_worker: Worker | None = None
        self.after_action = "none"           # none | shutdown | sleep
        self._dirty = False
        self._reports: dict[int, ee.ExportReport] = {}
        self._est_mid: dict[int, float] = {}
        self._current: QueueItem | None = None
        self.speed = estimator.MovingSpeed()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(1500)
        self._debounce.timeout.connect(self.run_estimate)
        self._poll = QTimer(self)
        self._poll.setInterval(500)
        self._poll.timeout.connect(self._tick)

    # --- stima
    def request_estimate(self) -> None:
        self.estimateStarted.emit()
        self._debounce.start()

    def trim_range(self) -> tuple[float, float]:
        return self.state.trim_start, self.state.trim_end

    def run_estimate(self) -> None:
        st = self.state
        if not st.project or not st.clips or not self.active:
            return
        if self.est_worker and self.est_worker.isRunning():
            self._dirty = True
            self.est_worker.cancel()
            return
        t0, t1 = self.trim_range()
        spec = RenderSpec.from_dict(st.spec.to_dict())
        proj = copy.deepcopy(st.project)
        corr = st.settings.data.get("estimator_corr", {})
        self._dirty = False
        self.estimateStarted.emit()
        self.est_worker = Worker(lambda c, r: ee.estimate(proj, st.clips, spec, t0, t1, corr, st.sample_cache, c))
        self.est_worker.finished_ok.connect(self._est_done)
        self.est_worker.failed.connect(lambda m: (log.error("Stima non riuscita: %s", m), self.estimateFailed.emit(m)))
        self.est_worker.finished.connect(lambda: self.run_estimate() if self._dirty else None)
        self.est_worker.start()

    def _est_done(self, est: ee.Estimate) -> None:
        self.est = est
        self.estimateReady.emit(est)

    def quick_size(self) -> str | None:
        """Dimensione stimata subito, senza benchmark, quando si usa un bitrate fisso (stima precisa)."""
        from .. import estimator as est
        from ..spec import audio_bitrate_bps, video_bitrate_bps
        st = self.state
        if not st.project or not st.clips:
            return None
        ex = st.spec.export
        if ex.crf_mode or ee.decide(st.spec, st.clips).mode == "copy":
            return None
        W, H = output_size(st.spec.image, ex)
        fps = st.spec.image.fps or st.clips[0].fps or 30.0
        t0, t1 = self.trim_range()
        extra = 0.0
        gr = st.spec.graphics
        if gr.title.enabled and not gr.title.over_video:
            extra += gr.title.duration
        if gr.outro.enabled:
            extra += gr.outro.duration
        if st.spec.credit.enabled:
            extra += st.spec.credit.duration
        sz = est.size_from_bitrate(video_bitrate_bps(ex, min(W, H), fps), audio_bitrate_bps(ex, min(W, H)), (t1 - t0) + extra)
        return est.format_size(sz.mid)

    def warnings(self) -> list[str]:
        st = self.state
        if not st.project:
            return []
        warns = list(ee.decide(st.spec, st.clips).warnings) + (self.est.notes if self.est else [])
        if self.est:
            W, H = output_size(st.spec.image, st.spec.export)
            try:
                warns += ee.check_space(Path(st.spec.export.out_dir or "."), self.est.size.high, st.spec, 0, W, H)
            except OSError:
                pass
        return warns

    # --- anteprima 10 s
    def make_preview(self, out_start: float) -> None:
        st = self.state
        spec = RenderSpec.from_dict(st.spec.to_dict())
        proj = copy.deepcopy(st.project)
        out = paths.temp_dir() / f"preview_{int(time.time())}.mp4"
        start = st.from_out(out_start)
        self.prev_worker = Worker(lambda c, r: (ee.render_sample(proj, st.clips, spec, start, 10.0, out, c), out)[1])
        self.prev_worker.finished_ok.connect(self.previewReady)
        self.prev_worker.failed.connect(lambda m: (log.error("Anteprima 10 s: %s", m), self.previewFailed.emit(m)))
        self.prev_worker.start()

    # --- coda
    def prepare(self) -> Prepared | None:
        st = self.state
        if not st.project:
            return None
        spec = RenderSpec.from_dict(st.spec.to_dict())
        proj = copy.deepcopy(st.project)
        dec = ee.decide(spec, st.clips)
        out_dir = Path(spec.export.out_dir or Path(proj.clips[0]).parent)
        name = (spec.export.name or "conferenza").strip() or "conferenza"
        out = out_dir / f"{name}.mp4"
        n = 1
        while out.exists() or any(it.name == out.name for it in st.queue.items if it.status not in (DONE, FAILED)):
            n += 1
            out = out_dir / f"{name}_{n}.mp4"
        t0, t1 = self.trim_range()
        return Prepared(spec, proj, dec, out, t0, t1)

    def space_warnings(self, prep: Prepared) -> list[str]:
        W, H = output_size(prep.spec.image, prep.spec.export)
        est = self.est
        return ee.check_space(prep.out.parent, est.size.high if est else 0, prep.spec, 0, W, H)

    def enqueue(self, prep: Prepared) -> QueueItem:
        st = self.state
        clips = list(st.clips)
        est = self.est
        key = id(prep.spec)
        self._est_mid[key] = (est.time_lo + est.time_hi) / 2 if est else 0.0

        def job(cancel, prog, prep=prep, key=key):
            rep = ee.run_export(prep.proj, clips, prep.spec, prep.out, prep.t0, prep.t1, prog, cancel)
            self._reports[key] = rep

        item = QueueItem(prep.out.name, job, (est.time_text + " · " + est.size_text) if est else "")
        item.key = key  # type: ignore[attr-defined]
        item.path = prep.out  # type: ignore[attr-defined]
        st.queue.add(item)
        self.queueChanged.emit()
        return item

    def move(self, i: int, d: int) -> None:
        self.state.queue.move(i, d)
        self.queueChanged.emit()

    def cancel(self, i: int) -> None:
        if 0 <= i < len(self.state.queue.items):
            self.state.queue.cancel(i)
            self.queueChanged.emit()

    @property
    def running(self) -> bool:
        return bool(self.run_worker and self.run_worker.isRunning())

    def start_queue(self) -> None:
        if self.running:
            return
        q = self.state.queue

        def job(cancel, report):
            while True:
                it = q.next_pending()
                if it is None:
                    break
                self._current = it
                self.speed = estimator.MovingSpeed()
                q.run_next()
                self._after_item(it)

        self.run_worker = Worker(job)
        self.run_worker.finished.connect(self._done)
        self._poll.start()
        self.run_worker.start()

    def _after_item(self, it: QueueItem) -> None:
        key = getattr(it, "key", None)
        rep = self._reports.get(key)
        if rep and rep.mode != "copy" and self._est_mid.get(key):
            estimator.update_correction(self.state.settings.data.setdefault("estimator_corr", {}), rep.encoder,
                                        self._est_mid[key], rep.wall_s)
            self.state.settings.save()

    def report_for(self, item: QueueItem) -> ee.ExportReport | None:
        return self._reports.get(getattr(item, "key", None))

    def _tick(self) -> None:
        cur = self._current
        self.queueChanged.emit()
        if cur and cur.status == "in corso":
            self.speed.add(time.time(), cur.progress)
            path = getattr(cur, "path", None)
            size = path.stat().st_size if path and Path(path).exists() else 0
            self.progress.emit(cur, cur.progress, self.speed.remaining(cur.progress), size)

    def _done(self) -> None:
        self._poll.stop()
        self.queueChanged.emit()
        results = [(it, self.report_for(it)) for it in self.state.queue.items if it.status in (DONE, FAILED)]
        for it, rep in results:
            if it.status == FAILED:
                log.error("Export fallito (%s): %s", it.name, it.error)
        self.finished.emit(results)
        ok = [it for it, _ in results if it.status == DONE and getattr(it, "path", None)]
        if ok and theme_prefs().get("reveal_after_export", True):
            from .platform_utils import reveal_in_folder
            reveal_in_folder(ok[-1].path)                 # apre la cartella e seleziona il video appena creato
        if self.after_action != "none" and sys.platform == "win32" and all(it.status != FAILED for it, _ in results):
            self.powerRequested.emit(self.after_action)

    @staticmethod
    def do_power(action: str) -> None:
        if action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "30"])
        elif action == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
