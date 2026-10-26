"""Stato condiviso dell'applicazione fra le schermate."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from ..media_scan import MediaInfo
from ..profiles import apply_profile, profile_from_spec
from ..project import Project
from ..settings import Settings
from ..spec import RenderSpec
from ..queue import ExportQueue


class AppState(QObject):
    spec_changed = Signal()       # qualsiasi modifica a grafica/immagine/audio/export
    project_changed = Signal()    # nuovo progetto / offset / trim
    profile_changed = Signal()

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
        self.profile_name = self.settings.data.get("current_profile", "Predefinito")
        self.apply_profile(self.profile_name, emit=False)

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
            self.spec = RenderSpec.from_dict(proj.spec)
        self.project_changed.emit()
        self.spec_changed.emit()
