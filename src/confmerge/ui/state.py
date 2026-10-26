"""Stato condiviso dell'applicazione: il modello di progetto usato da entrambe le modalità."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from ..media_scan import MediaInfo
from ..profiles import apply_profile, profile_from_spec
from ..project import Project
from ..queue import ExportQueue
from ..settings import Settings
from ..spec import RenderSpec
from .controllers import AnalysisRunner, ExportController, ReviewController, SourcesModel

UNDO_LIMIT = 100


def _assign(dst, src) -> None:
    """Copia src dentro dst campo per campo, ricorsivamente, mantenendo l'identità degli oggetti
    (i widget che tengono un riferimento a `spec.image`, `spec.audio`… restano validi)."""
    for f in dataclasses.fields(dst):
        new, old = getattr(src, f.name), getattr(dst, f.name)
        if dataclasses.is_dataclass(old) and not isinstance(old, type) and type(old) is type(new):
            _assign(old, new)
        else:
            setattr(dst, f.name, new)


class AppState(QObject):
    spec_changed = Signal()       # qualsiasi modifica a grafica/immagine/audio/export
    project_changed = Signal()    # nuovo progetto / offset / trim
    profile_changed = Signal()    # profilo applicato o annullamento: le viste si ricostruiscono

    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings()
        from .theme import theme
        theme.prefs.data = self.settings.data.setdefault("ui", {})
        theme.prefs.save = self.settings.save
        theme.mode = theme.prefs.get("theme", "dark")
        theme.reduce_motion = bool(theme.prefs.get("reduce_motion", False))
        self.project: Project | None = None
        self.clips: list[MediaInfo] = []
        self.spec = RenderSpec()
        self.cam: np.ndarray | None = None
        self.ext: np.ndarray | None = None
        self.proxy: Path | None = None
        self.proxy_stale = False
        self.proxy_range: tuple[float, float] = (0.0, 0.0)   # parte della linea temporale coperta dall'anteprima
        self.warnings: list[str] = []
        self.last_frame = None            # ultimo QImage del player (sfondo per l'editor grafico)
        self.queue = ExportQueue()
        self.sample_cache: dict = {}
        # controller condivisi dalle due modalità
        self.sources = SourcesModel()
        self.analysis = AnalysisRunner(self)
        self.review = ReviewController(self)
        self.export = ExportController(self)
        # profilo e annulla/ripristina
        self.settings.ensure_starter_profile()
        self.profile_name = self.settings.data.get("current_profile", "Predefinito")
        self.apply_profile(self.profile_name, emit=False)
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._cur = self._dump()
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(450)
        self._undo_timer.timeout.connect(self._commit)
        self._restoring = False
        self.spec_changed.connect(self._schedule_commit)

    @property
    def mode(self) -> str:
        return self.settings.data.get("ui", {}).get("mode", "simple")

    # --- tempi: la timeline del player è quella del video unito; grafica/slide usano il tempo di uscita
    @property
    def trim_start(self) -> float:
        return (self.project.trim_start if self.project and self.project.trim_start is not None else 0.0)

    @property
    def trim_end(self) -> float:
        if not self.project:
            return 0.0
        return self.project.trim_end if self.project.trim_end is not None else self.project.total_duration

    def to_out(self, pos: float) -> float:
        return pos - self.trim_start

    def from_out(self, t: float) -> float:
        return t + self.trim_start

    # --- profili
    def apply_profile(self, name: str, emit: bool = True) -> None:
        self.profile_name = name
        self.settings.data["current_profile"] = name
        apply_profile(self.spec, self.settings.load_profile(name))
        if emit:
            self.profile_changed.emit()
            self.spec_changed.emit()

    def save_profile(self, name: str) -> None:
        self.settings.save_profile(name, profile_from_spec(self.spec))
        self.profile_name = name
        self.settings.data["current_profile"] = name
        self.settings.save()
        self.profile_changed.emit()

    def touch(self) -> None:
        self.spec_changed.emit()

    def sync_spec_to_project(self) -> None:
        if self.project:
            self.project.spec = self.spec.to_dict()
            self.project.profile_name = self.profile_name

    def load_project(self, proj: Project) -> None:
        self.project = proj
        if proj.spec:
            _assign(self.spec, RenderSpec.from_dict(proj.spec))
        self.project_changed.emit()
        self.profile_changed.emit()
        self.spec_changed.emit()

    # --- annulla / ripristina (editor grafico e impostazioni)
    def _dump(self) -> str:
        return json.dumps(self.spec.to_dict(), sort_keys=True)

    def _schedule_commit(self) -> None:
        if not self._restoring:
            self._undo_timer.start()

    def _commit(self) -> None:
        new = self._dump()
        if new != self._cur:
            self._undo.append(self._cur)
            self._undo = self._undo[-UNDO_LIMIT:]
            self._redo.clear()
            self._cur = new

    @property
    def can_undo(self) -> bool:
        return bool(self._undo) or self._dump() != self._cur

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        self._undo_timer.stop()
        self._commit()
        if not self._undo:
            return False
        self._redo.append(self._cur)
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        self._undo_timer.stop()
        if not self._redo:
            return False
        self._undo.append(self._cur)
        self._restore(self._redo.pop())
        return True

    def _restore(self, dump: str) -> None:
        self._restoring = True
        try:
            _assign(self.spec, RenderSpec.from_dict(json.loads(dump)))
            self._cur = dump
            self.profile_changed.emit()       # le viste si ricostruiscono dai nuovi valori
            self.spec_changed.emit()
        finally:
            self._restoring = False
