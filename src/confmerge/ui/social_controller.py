"""Studio Social: caricamento dei video, anteprima, tagli e ricerca dei silenzi."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .. import cuts, paths, social
from ..worker import Worker


class SocialController(QObject):
    progress = Signal(float, str)
    finished = Signal()
    failed = Signal(str)
    cancelled = Signal()
    silencesFound = Signal(int, float)          # quante pause, quanti secondi si toglierebbero

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.worker: Worker | None = None

    @property
    def running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    # --- caricamento
    def load(self, files: list[str | Path], project=None) -> None:
        """Nuovo lavoro dai video scelti, oppure (con `project`) riapertura di un lavoro salvato."""
        paths.temp_dir()
        names = [Path(f) for f in files]

        def job(cancel, report):
            report(0.02, "Leggo i video…")
            clips = social.load_clips(names, cancel)
            report(0.15, "Ascolto l'audio…")
            cam = social.decode_waveform(clips)
            out = paths.temp_dir() / "social_preview.mp4"
            report(0.3, "Preparo l'anteprima…")
            social.build_preview(clips, out, lambda f, s: report(0.3 + 0.7 * f, "Preparo l'anteprima…"), cancel)
            return clips, cam, out

        def ok(res):
            st = self.state
            clips, cam, out = res
            st.clips, st.cam, st.ext, st.proxy = clips, cam, None, out
            st.proxy_stale = False
            st.proxy_range = (0.0, sum(c.duration for c in clips))
            if project is not None:
                st.load_project(project)
            else:
                st.project = social.new_project(clips)
                st.project_path = None
                st.project_changed.emit()
                st.reset_history()
                st.mark_clean()
            self.finished.emit()

        self.worker = Worker(job)
        self.worker.progress.connect(self.progress)
        self.worker.finished_ok.connect(ok)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.start()

    def open_project(self, proj) -> None:
        self.load(proj.clips, proj)

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel()

    # --- tagli
    @property
    def total(self) -> float:
        pr = self.state.project
        return pr.total_duration if pr else 0.0

    def keep(self) -> list[list[float]]:
        pr = self.state.project
        return [list(k) for k in pr.keep] if pr and pr.keep else ([[0.0, pr.total_duration]] if pr else [])

    def removed(self) -> list[tuple[float, float]]:
        pr = self.state.project
        return cuts.removed_from_keep(pr.total_duration, pr.keep) if pr else []

    def kept_seconds(self) -> float:
        pr = self.state.project
        return cuts.kept_duration(pr.keep, pr.total_duration) if pr else 0.0

    def _set_keep(self, keep: list[list[float]]) -> None:
        self.state.project.keep = keep
        self.state.cuts_changed.emit()
        self.state.touch()                       # entra nella cronologia («Tagli»), nel «non salvato» e nell'autosave

    def remove(self, a: float, b: float) -> None:
        pr = self.state.project
        if pr and abs(b - a) >= 0.05:
            self._set_keep(cuts.remove_range(pr.keep, pr.total_duration, a, b))

    def restore(self, a: float, b: float) -> None:
        pr = self.state.project
        if pr:
            self._set_keep(cuts.restore_range(pr.keep, pr.total_duration, a, b))

    def reset(self) -> None:
        if self.state.project and self.state.project.keep:
            self._set_keep([])

    def silences(self) -> list[tuple[float, float]]:
        st, so = self.state, self.state.spec.social
        if st.cam is None or not st.project:
            return []
        return social.find_silences(st.cam, st.project.total_duration, so.skip_silence_db, so.skip_silence_min,
                                    so.skip_silence_pad)

    def preview_silences(self) -> tuple[int, float]:
        found = self.silences()
        return len(found), sum(b - a for a, b in found)

    def remove_silences(self) -> tuple[int, float]:
        """Toglie le pause trovate (si sommano ai tagli già fatti). Restituisce (quante, secondi tolti)."""
        pr = self.state.project
        found = self.silences()
        if not pr or not found:
            return 0, 0.0
        removed = cuts.removed_from_keep(pr.total_duration, pr.keep) + found
        self._set_keep(cuts.keep_from_removed(pr.total_duration, cuts._merge(removed)))
        n, secs = len(found), sum(b - a for a, b in found)
        self.silencesFound.emit(n, secs)
        return n, secs
