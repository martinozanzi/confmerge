"""Esegue il controllo degli aggiornamenti in un thread, senza bloccare la finestra."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from .. import updates


class UpdateChecker(QObject):
    done = Signal(object, str)          # release più nuova (o None), messaggio d'errore (vuoto se tutto bene)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            self.done.emit(updates.check(), "")
        except updates.UpdateError as e:
            self.done.emit(None, str(e))
        except Exception as e:  # noqa: BLE001 - un controllo di aggiornamento non deve mai far cadere l'app
            self.done.emit(None, "Non sono riuscito a cercare gli aggiornamenti.")
            updates.log_error(e)
