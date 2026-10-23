"""Percorsi dell'applicazione: risorse, cartella temporanea, log."""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

_temp_dir: Path | None = None


def app_root() -> Path:
    """Radice delle risorse: _MEIPASS se impacchettato, altrimenti la radice del repo."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def bin_dir() -> Path:
    return app_root() / "bin"


def data_dir() -> Path:
    """%LOCALAPPDATA%\\ConfMerge su Windows, ~/.local/share/ConfMerge altrove."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    path = Path(base) / "ConfMerge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_dir() -> Path:
    """Cartella temporanea dedicata, ripulita all'uscita."""
    global _temp_dir
    if _temp_dir is None or not _temp_dir.exists():
        _temp_dir = Path(tempfile.mkdtemp(prefix="ConfMerge-"))
        atexit.register(cleanup_temp)
    return _temp_dir


def cleanup_temp() -> None:
    global _temp_dir
    if _temp_dir is not None:
        shutil.rmtree(_temp_dir, ignore_errors=True)
        _temp_dir = None


def setup_logging(verbose: bool = False) -> Path:
    log_file = data_dir() / "confmerge.log"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )
    return log_file
