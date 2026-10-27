"""Salvataggio automatico di recupero: un solo «lavoro non salvato» nella cartella delle impostazioni.

Se il progetto ha già un nome, l'autosave scrive direttamente quel file (vedi AppState.autosave). Se non ce l'ha, o se
l'app si chiude male, resta qui una copia da cui riprendere all'avvio successivo."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .project import Project


def _dir(root: Path) -> Path:
    d = Path(root) / "autosave"
    d.mkdir(parents=True, exist_ok=True)
    return d


def recovery_file(root: Path, slot: str = "") -> Path:
    """`slot`: «» per Merge Conferenze, «social» per Studio Social (due lavori distinti)."""
    return _dir(root) / (f"recupero_{slot}.confmerge" if slot else "recupero.confmerge")


def _meta_file(root: Path, slot: str = "") -> Path:
    return _dir(root) / (f"recupero_{slot}.json" if slot else "recupero.json")


def write_recovery(project: Project, root: Path, name: str = "", slot: str = "") -> None:
    project.save(recovery_file(root, slot))
    _meta_file(root, slot).write_text(json.dumps({"saved_at": time.time(), "name": name}), encoding="utf-8")


def has_recovery(root: Path, slot: str = "") -> bool:
    return recovery_file(root, slot).exists()


def recovery_info(root: Path, slot: str = "") -> dict:
    try:
        return json.loads(_meta_file(root, slot).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clear_recovery(root: Path, slot: str = "") -> None:
    for f in (recovery_file(root, slot), _meta_file(root, slot)):
        try:
            f.unlink()
        except OSError:
            pass
