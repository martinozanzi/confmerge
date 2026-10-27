"""Impostazioni (aspetto, animazioni, profili, credito) e elenco delle scorciatoie."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QTextBrowser, QVBoxLayout

from .graphics_page import CreditTab, ProfileBar
from .theme import theme
from .widgets import Card, Segmented, Toggle, label

SHORTCUTS = [
    ("Spazio / K", "Riproduci e pausa"), ("Sinistra / Destra", "Un fotogramma indietro / avanti"),
    ("Maiusc + Sinistra / Destra", "Un secondo indietro / avanti"), ("J / L", "Cinque secondi indietro / avanti"),
    ("I", "Imposta l'inizio del video nel punto attuale"), ("O", "Imposta la fine del video nel punto attuale"),
    ("N", "Segna un cambio di slide"), ("Ctrl + Z", "Annulla l'ultima modifica (grafica e impostazioni)"),
    ("Ctrl + Maiusc + Z  /  Ctrl + Y", "Ripristina la modifica annullata"), ("Ctrl + N", "Nuovo progetto"),
    ("Ctrl + O", "Apri un progetto"), ("Ctrl + S", "Salva il progetto"), ("F1", "Mostra questo elenco"),
]


class SettingsDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        c = Card()
        c.add(label("Aspetto", "h2"))
        self.theme_seg = Segmented([("Scuro", "dark"), ("Chiaro", "light"), ("Come il computer", "system")])
        self.theme_seg.setValue(theme.mode)
        self.theme_seg.changed.connect(theme.set_mode)
        c.add(self.theme_seg)
        self.motion = Toggle("Riduci le animazioni")
        self.motion.setChecked(theme.reduce_motion)
        self.motion.toggled.connect(theme.set_reduce_motion)
        c.add(self.motion)
        c.add(label("Utile se le animazioni ti disturbano o il computer è lento.", "caption", True))
        self.reveal = Toggle("Alla fine dell'export apri la cartella e seleziona il video")
        self.reveal.setChecked(theme.prefs.get("reveal_after_export", True))
        self.reveal.toggled.connect(lambda on: theme.prefs.set("reveal_after_export", on))
        c.add(self.reveal)
        lay.addWidget(c)
        c2 = Card()
        c2.add(label("Profili", "h2"))
        c2.add(label("Un profilo ricorda titolo, logo, scritte e credito: ne puoi avere uno per ogni canale o evento.",
                     "caption", True))
        c2.add(ProfileBar(state))
        lay.addWidget(c2)
        lay.addWidget(CreditTab(state))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).setText("Chiudi")
        lay.addWidget(bb)


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scorciatoie da tastiera")
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        rows = "".join(f"<tr><td style='padding:4px 16px 4px 0'><b>{k}</b></td><td>{v}</td></tr>" for k, v in SHORTCUTS)
        tb.setHtml(f"<table>{rows}</table>")
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).setText("Chiudi")
        lay.addWidget(bb)
