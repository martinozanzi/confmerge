"""Scheda «Sottotitoli automatici» delle Impostazioni: chiave di Groq, prova e istruzioni."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLineEdit

from .. import transcribe
from ..secrets_store import masked
from .widgets import Card, LinkButton, SecondaryButton, Toggle, label

HELP_URL = "https://github.com/martinozanzi/confmerge/blob/main/docs/GROQ.md"


class _Tester(QObject):
    done = Signal(bool, str)

    def run(self, key: str):
        def work():
            try:
                self.done.emit(True, transcribe.check_key(key))
            except transcribe.TranscribeError as e:
                self.done.emit(False, str(e))
            except Exception as e:  # noqa: BLE001
                self.done.emit(False, f"Prova non riuscita: {e}")
        threading.Thread(target=work, daemon=True).start()


class ApiKeysCard(Card):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.keys = state.settings.keys
        self.state = state
        self.add(label("Sottotitoli automatici", "h2"))
        self.add(label("Per creare i sottotitoli serve una chiave gratuita di Groq: si paga solo quello che si usa, "
                       "circa 4 centesimi di dollaro per ogni ora di video. L'audio viene inviato a Groq solo quando "
                       "premi «Crea i sottotitoli».", "caption", True))
        links = QHBoxLayout()
        b1 = LinkButton("Istruzioni passo passo")
        b1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HELP_URL)))
        b2 = LinkButton("Crea la chiave su Groq")
        b2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(transcribe.INSTRUCTIONS_URL)))
        links.addWidget(b1)
        links.addWidget(b2)
        links.addStretch(1)
        self.lay.addLayout(links)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText("Incolla qui la chiave (inizia con gsk_)")
        self.edit.setAccessibleName("Chiave di Groq")
        cur = self.keys.get("groq")
        if cur:
            self.edit.setText(cur)
        row.addWidget(self.edit, 1)
        self.show_key = Toggle("Mostra")
        self.show_key.toggled.connect(lambda on: self.edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        row.addWidget(self.show_key)
        self.lay.addLayout(row)
        btns = QHBoxLayout()
        self.save_btn = SecondaryButton("Salva", "save")
        self.save_btn.clicked.connect(self.save)
        self.test_btn = SecondaryButton("Prova la chiave", "check")
        self.test_btn.clicked.connect(self.test)
        self.clear_btn = SecondaryButton("Rimuovi", "trash-2")
        self.clear_btn.clicked.connect(self.clear)
        for b in (self.save_btn, self.test_btn, self.clear_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        self.lay.addLayout(btns)
        self.status = label(self._status_text(), "caption", True)
        self.add(self.status)
        self._tester = _Tester()
        self._tester.done.connect(self._tested)

    def _status_text(self) -> str:
        k = self.keys.get("groq")
        return f"Chiave salvata: {masked(k)}" if k else "Nessuna chiave salvata."

    def save(self):
        self.keys.set("groq", self.edit.text())
        self.status.setText(self._status_text())
        self.state.keys_changed.emit()

    def clear(self):
        self.edit.clear()
        self.keys.set("groq", "")
        self.status.setText(self._status_text())
        self.state.keys_changed.emit()

    def test(self):
        self.save()
        self.status.setText("Provo la chiave…")
        self.test_btn.setEnabled(False)
        self._tester.run(self.edit.text())

    def _tested(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self.status.setText(("✓ " if ok else "✗ ") + msg)
