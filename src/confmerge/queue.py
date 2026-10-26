"""Coda di export: più progetti in sequenza, riordinabile, annullabile per elemento."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

PENDING, RUNNING, DONE, FAILED, CANCELLED = "in attesa", "in corso", "completato", "errore", "annullato"


@dataclass
class QueueItem:
    name: str
    job: Callable[[threading.Event, Callable[[float, float | None], None]], None]
    estimate: str = ""
    status: str = PENDING
    progress: float = 0.0
    error: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)


class ExportQueue:
    def __init__(self):
        self.items: list[QueueItem] = []

    def add(self, item: QueueItem) -> None:
        self.items.append(item)

    def move(self, i: int, delta: int) -> None:
        j = i + delta
        if 0 <= i < len(self.items) and 0 <= j < len(self.items):
            if PENDING in (self.items[i].status, self.items[j].status) and \
               self.items[i].status != RUNNING and self.items[j].status != RUNNING:
                self.items[i], self.items[j] = self.items[j], self.items[i]

    def cancel(self, i: int) -> None:
        it = self.items[i]
        if it.status == PENDING:
            it.status = CANCELLED
        elif it.status == RUNNING:
            it.cancel.set()

    def next_pending(self) -> QueueItem | None:
        return next((it for it in self.items if it.status == PENDING), None)

    def run_next(self, on_progress: Callable[[QueueItem], None] | None = None) -> QueueItem | None:
        """Esegue (sincrono, da chiamare nel thread worker) il prossimo elemento."""
        from .ffmpeg_wrapper import Cancelled
        it = self.next_pending()
        if it is None:
            return None
        it.status = RUNNING

        def prog(frac: float, speed: float | None) -> None:
            it.progress = frac
            if on_progress:
                on_progress(it)

        try:
            it.job(it.cancel, prog)
            it.status, it.progress = DONE, 1.0
        except Cancelled:
            it.status = CANCELLED
        except Exception as e:  # noqa: BLE001
            it.status, it.error = FAILED, str(e)
        if on_progress:
            on_progress(it)
        return it

    def run_all(self, on_progress=None) -> None:
        while self.run_next(on_progress):
            pass
