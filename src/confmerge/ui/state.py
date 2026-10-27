"""Stato condiviso dell'applicazione: il modello di progetto usato da entrambe le modalità."""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from ..media_scan import MediaInfo
from ..profiles import apply_profile, profile_from_spec
from ..project import Project
from ..queue import ExportQueue
from ..settings import Settings
from ..spec import RenderSpec
from .controllers import AnalysisRunner, ExportController, ReviewController, SourcesModel, SubtitleController

UNDO_LIMIT = 100


@dataclasses.dataclass
class HistoryEntry:
    label: str       # che cosa è cambiato, in parole semplici («Titolo iniziale», «Inizio e fine del video»…)
    when: float
    dump: str


# prefisso del percorso nel JSON → nome per l'utente (vince il prefisso più lungo)
CHANGE_LABELS = {
    ("spec", "graphics", "title"): "Titolo iniziale", ("spec", "graphics", "title_template"): "Titolo iniziale",
    ("spec", "graphics", "outro"): "Schermata finale", ("spec", "graphics", "outro_template"): "Schermata finale",
    ("spec", "graphics", "lower_thirds"): "Nome del relatore", ("spec", "graphics", "elements"): "Logo e scritte",
    ("spec", "graphics", "transition_style"): "Transizioni", ("spec", "graphics"): "Grafica",
    ("spec", "subtitles", "lines"): "Testo dei sottotitoli", ("spec", "subtitles"): "Aspetto dei sottotitoli",
    ("spec", "audio", "music_path"): "Musica", ("spec", "audio", "music_db"): "Musica", ("spec", "audio", "music_duck"): "Musica",
    ("spec", "audio", "music_duck_db"): "Musica", ("spec", "audio", "music_fade"): "Musica", ("spec", "audio"): "Audio",
    ("spec", "image", "clip_transition"): "Transizioni", ("spec", "image", "clip_transition_dur"): "Transizioni",
    ("spec", "image"): "Formato e ritaglio", ("spec", "slides"): "Slide e PiP", ("spec", "credit"): "Credito",
    ("spec", "export"): "Esportazione", ("spec", "variables"): "Testi del video",
    ("project", "trim_start"): "Inizio e fine del video", ("project", "trim_end"): "Inizio e fine del video",
    ("project", "trim_confirmed"): "Inizio e fine del video",
}


def _changed_paths(a, b, path=()):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in a.keys() | b.keys():
            out += _changed_paths(a.get(k), b.get(k), path + (k,))
        return out
    return [path] if a != b else []


def describe_change(old_dump: str, new_dump: str) -> str:
    try:
        paths_ = _changed_paths(json.loads(old_dump), json.loads(new_dump))
    except ValueError:
        return "Modifica"
    labels: list[str] = []
    for p in paths_:
        for n in range(len(p), 0, -1):
            lab = CHANGE_LABELS.get(p[:n])
            if lab:
                if lab not in labels:
                    labels.append(lab)
                break
    if not labels:
        return "Modifica"
    return labels[0] if len(labels) == 1 else "Più modifiche (" + ", ".join(sorted(labels)[:3]) + ")"


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
        self.subtitles = SubtitleController(self)
        # profilo e annulla/ripristina
        self.settings.ensure_starter_profile()
        self.profile_name = self.settings.data.get("current_profile", "Predefinito")
        self.apply_profile(self.profile_name, emit=False)
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(450)
        self._undo_timer.timeout.connect(self._commit)
        self._restoring = False
        self.project_path: Path | None = None      # file .confmerge del progetto (None = mai salvato con un nome)
        self._clean_fp = self._autosaved_fp = ""
        self._cur, self._hist, self._idx = "", [], 0
        self.reset_history()
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
        self.reset_history()
        self.mark_clean()

    # --- cronologia: annulla / ripristina e ritorno a un punto qualsiasi (editor, impostazioni, inizio e fine)
    def _dump(self) -> str:
        data = {"spec": self.spec.to_dict()}
        pr = self.project
        if pr is not None:
            data["project"] = {"trim_start": pr.trim_start, "trim_end": pr.trim_end, "trim_confirmed": pr.trim_confirmed}
        return json.dumps(data, sort_keys=True)

    def reset_history(self) -> None:
        """Nuovo punto di partenza (nuovo progetto, progetto aperto): la cronologia precedente non vale più."""
        self._undo_timer.stop()
        self._cur = self._dump()
        self._hist = [HistoryEntry("Inizio", time.time(), self._cur)]
        self._idx = 0

    def _schedule_commit(self) -> None:
        if not self._restoring:
            self._undo_timer.start()

    def _commit(self) -> None:
        new = self._dump()
        if new == self._cur:
            return
        del self._hist[self._idx + 1:]                     # una modifica nuova cancella il «futuro» annullato
        self._hist.append(HistoryEntry(describe_change(self._cur, new), time.time(), new))
        if len(self._hist) > UNDO_LIMIT:
            self._hist = self._hist[-UNDO_LIMIT:]
        self._idx = len(self._hist) - 1
        self._cur = new

    @property
    def history(self) -> list["HistoryEntry"]:
        self._undo_timer.stop()
        self._commit()
        return self._hist

    @property
    def history_index(self) -> int:
        return self._idx

    @property
    def can_undo(self) -> bool:
        return self._idx > 0 or self._dump() != self._cur

    @property
    def can_redo(self) -> bool:
        return self._idx < len(self._hist) - 1

    def undo(self) -> bool:
        self._undo_timer.stop()
        self._commit()
        return self.jump(self._idx - 1)

    def redo(self) -> bool:
        self._undo_timer.stop()
        return self.jump(self._idx + 1)

    def jump(self, i: int) -> bool:
        """Torna al punto `i` della cronologia (avanti o indietro)."""
        self._undo_timer.stop()
        self._commit()
        if not (0 <= i < len(self._hist)) or i == self._idx:
            return False
        self._idx = i
        self._restore(self._hist[i].dump)
        return True

    def _restore(self, dump: str) -> None:
        self._restoring = True
        try:
            data = json.loads(dump)
            _assign(self.spec, RenderSpec.from_dict(data["spec"]))
            pr, saved = self.project, data.get("project")
            trim_changed = False
            if pr is not None and saved:
                new = (saved["trim_start"], saved["trim_end"], saved["trim_confirmed"])
                trim_changed = (pr.trim_start, pr.trim_end, pr.trim_confirmed) != new
                pr.trim_start, pr.trim_end, pr.trim_confirmed = new
            self._cur = dump
            self.profile_changed.emit()       # le viste si ricostruiscono dai nuovi valori
            if trim_changed:
                self.review.trimChanged.emit()
            self.spec_changed.emit()
        finally:
            self._restoring = False

    # --- file di progetto: nome, «non salvato», salvataggio automatico
    def fingerprint(self) -> str:
        if self.project is None:
            return ""
        self.sync_spec_to_project()
        return json.dumps(dataclasses.asdict(self.project), sort_keys=True)

    def mark_clean(self) -> None:
        self._clean_fp = self.fingerprint()
        self._autosaved_fp = self._clean_fp

    def is_dirty(self) -> bool:
        return self.project is not None and self.fingerprint() != self._clean_fp

    def save_to(self, path: str | Path) -> None:
        from ..autosave import clear_recovery
        self.sync_spec_to_project()
        self.project.save(path)
        self.project_path = Path(path)
        self.mark_clean()
        clear_recovery(self.settings.root)

    def autosave(self) -> str:
        """Salva in silenzio se c'è qualcosa di nuovo. Restituisce «file», «recupero» o «» (niente da fare)."""
        if self.project is None:
            return ""
        fp = self.fingerprint()
        if fp == self._autosaved_fp:
            return ""
        from ..autosave import write_recovery
        try:
            if self.project_path is not None and self.settings.data.get("autosave_named", True):
                self.project.save(self.project_path)
                self._clean_fp = self._autosaved_fp = fp
                return "file"
            write_recovery(self.project, self.settings.root, self.project_path.name if self.project_path else "")
        except OSError:
            return ""
        self._autosaved_fp = fp
        return "recupero"
