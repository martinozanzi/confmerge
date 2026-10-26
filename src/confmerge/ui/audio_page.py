"""Fase «Audio» (modalità Avanzata): opzioni per la voce, in parole semplici."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import bind
from .widgets import Card, label

HELP = {
    "loudnorm": "Porta la voce a un livello giusto per YouTube: né troppo bassa né troppo alta. Consigliato.",
    "denoise": "Attenua il fruscio e il rumore di fondo (ventola, aria condizionata). Se la voce suona strana, spegnilo.",
    "highpass": "Toglie i suoni molto gravi e fastidiosi: rimbombi, urti sul microfono, vento.",
    "compressor": "Rende la voce più regolare: i passaggi sussurrati si sentono meglio e quelli forti non coprono.",
}


def describe_level(lufs: float) -> str:
    """Il livello del volume in parole (il valore tecnico resta nel tooltip)."""
    if lufs < -20:
        return "molto basso"
    if lufs < -16.5:
        return "un po' basso"
    if lufs <= -12:
        return "giusto per YouTube"
    return "troppo alto"


class AudioPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        lay.addWidget(label("Audio", "title"))
        lay.addWidget(label("La registrazione esterna sostituisce l'audio della telecamera. Qui scegli come migliorarla.",
                            "muted", True))
        card = Card()
        a = state.spec.audio
        self._toggles = []
        for attr, text in (("loudnorm", "Volume uniforme per YouTube"), ("denoise", "Attenua il rumore di fondo"),
                           ("highpass", "Togli i suoni gravi fastidiosi"), ("compressor", "Rendi la voce più regolare")):
            t = bind.check(a, attr, text, state.touch)
            self._toggles.append((attr, t))
            card.add(t)
            card.add(label(HELP[attr], "caption", True))
        lay.addWidget(card)
        self.result = Card()
        self.result.add(label("Volume del video finito", "h2", True))
        self.result_txt = label("Dopo l'export qui vedrai com'era il volume prima e com'è diventato.", "muted", True)
        self.result.add(self.result_txt)
        lay.addWidget(self.result)
        lay.addStretch(1)
        state.export.finished.connect(self._finished)
        state.profile_changed.connect(self._sync)

    def _sync(self):
        a = self.state.spec.audio
        for attr, t in self._toggles:
            t.blockSignals(True)
            t.setChecked(getattr(a, attr))
            t.blockSignals(False)
            # il Toggle è legato all'oggetto `a` originale: dopo un annulla il valore resta coerente (stesso oggetto)

    def _finished(self, results):
        for it, rep in reversed(results):
            if rep and rep.loud_before and rep.loud_after:
                b, af = rep.loud_before["input_i"], rep.loud_after["input_i"]
                self.result_txt.setText(f"Prima: {describe_level(b)}. Dopo: {describe_level(af)}.")
                self.result_txt.setToolTip(f"Valori tecnici: prima {b:.1f} LUFS, dopo {af:.1f} LUFS "
                                           f"(picco {rep.loud_after['input_tp']:.1f} dBTP)")
                return
