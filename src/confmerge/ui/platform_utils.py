"""Piccole funzioni di sistema: mostrare un file nella sua cartella."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def reveal_in_folder(path: str | Path) -> bool:
    """Apre la cartella e SELEZIONA il file (Esplora risorse su Windows, Finder su macOS).
    Su Linux apre la cartella. Non fa nulla se CONFMERGE_NO_REVEAL è impostata (test)."""
    p = Path(path)
    if os.environ.get("CONFMERGE_NO_REVEAL"):
        return False
    try:
        if sys.platform == "win32":
            if p.exists():
                subprocess.Popen(["explorer", f"/select,{p}"])
            else:
                os.startfile(str(p.parent))           # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)] if p.exists() else ["open", str(p.parent)])
            return True
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
    except OSError:
        return False
