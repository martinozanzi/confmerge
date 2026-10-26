"""Diagnostica: errori non gestiti, arresti di Qt e crash nativi finiscono nel log, con un messaggio comprensibile."""
from __future__ import annotations

import faulthandler
import logging
import platform
import sys
import threading
import time
import traceback

from . import __version__, paths

log = logging.getLogger("confmerge")
_crash_file = None
_last_dialog = 0.0


def support_info(lines: int = 150) -> str:
    """Testo da incollare quando si chiede assistenza: versioni + ultime righe del log."""
    try:
        import PySide6
        qt = PySide6.__version__
    except Exception:  # noqa: BLE001
        qt = "?"
    head = (f"ConfMerge {__version__} | Python {platform.python_version()} | PySide6 {qt} | {platform.platform()}\n"
            f"Log: {paths.log_file()}\n")
    try:
        tail = "".join(paths.log_file().read_text(encoding="utf-8", errors="replace").splitlines(True)[-lines:])
    except OSError:
        tail = "(log non disponibile)"
    crash = paths.data_dir() / "crash.log"
    try:
        if crash.exists() and crash.stat().st_size:
            tail += "\n--- crash.log ---\n" + crash.read_text(encoding="utf-8", errors="replace")[-3000:]
    except OSError:
        pass
    return head + "\n" + tail


def _qt_handler(mode, ctx, msg):
    try:
        text = str(msg)
        if "No audio device" in text or "pipewire" in text.lower():
            return
        level = {0: logging.DEBUG, 1: logging.WARNING, 2: logging.ERROR, 3: logging.CRITICAL}.get(int(mode), logging.WARNING)
        if level >= logging.WARNING:
            log.log(level, "Qt: %s", text)
    except Exception:  # noqa: BLE001
        pass


def _show_dialog(text: str) -> None:
    """Messaggio semplice, al massimo uno ogni 10 secondi (evita cascate di finestre)."""
    global _last_dialog
    if time.time() - _last_dialog < 10:
        return
    _last_dialog = time.time()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None or threading.current_thread() is not threading.main_thread():
            return
        m = QMessageBox(QMessageBox.Warning, "Qualcosa non ha funzionato",
                        "Si è verificato un problema, ma puoi continuare a lavorare.\n\n"
                        "Se si ripete, usa «Aiuto → Copia informazioni per l'assistenza» e invia il testo a chi ti aiuta.\n\n"
                        f"Dettaglio: {text[:200]}")
        b = m.addButton("Apri la cartella dei log", QMessageBox.ActionRole)
        m.addButton("Continua", QMessageBox.AcceptRole)
        m.exec()
        if m.clickedButton() is b:
            open_log_folder()
    except Exception:  # noqa: BLE001
        pass


def open_log_folder() -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir())))


def install() -> None:
    """Da chiamare una volta all'avvio, dopo setup_logging()."""
    global _crash_file

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        log.critical("Errore non gestito:\n%s", text)
        _show_dialog(f"{etype.__name__}: {value}")

    sys.excepthook = hook
    threading.excepthook = lambda a: log.critical("Errore nel thread %s:\n%s", getattr(a.thread, "name", "?"),
                                                  "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
    try:
        _crash_file = open(paths.data_dir() / "crash.log", "a", encoding="utf-8")
        _crash_file.write(f"\n=== avvio {time.strftime('%Y-%m-%d %H:%M:%S')} ConfMerge {__version__} ===\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)      # arresti nativi (es. Qt/multimedia)
    except OSError:
        pass
    try:
        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(_qt_handler)
    except Exception:  # noqa: BLE001
        pass
    log.info("Avvio: %s", support_info(0).splitlines()[0])
