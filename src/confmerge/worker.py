"""Thread di lavoro per la GUI: esegue una funzione con progresso e annullamento."""
from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from .ffmpeg_wrapper import Cancelled


class Worker(QThread):
    progress = Signal(float, str)     # frazione, messaggio
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], parent=None):
        """`fn(cancel_event, report)` con report(frac, msg='')."""
        super().__init__(parent)
        self._fn = fn
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            res = self._fn(self.cancel_event, lambda f, m="": self.progress.emit(float(f), m))
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.finished_ok.emit(res)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).error("Worker: %s", traceback.format_exc())
            self.failed.emit(str(e))
