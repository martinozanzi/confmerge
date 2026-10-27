"""Impostazioni (aspetto, animazioni, profili, credito) e elenco delle scorciatoie."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget

from .api_keys import ApiKeysCard
from .graphics_page import CreditTab, ProfileBar, scrolled
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
        self.state_ = state
        self.resize(760, 700)
        outer = QVBoxLayout(self)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 8, 0)
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
        self.autosave = Toggle("Salva da solo i progetti che hanno un nome (ogni 30 secondi)")
        self.autosave.setChecked(state.settings.data.get("autosave_named", True))
        self.autosave.toggled.connect(self._set_autosave)
        c.add(self.autosave)
        c.add(label("Se un progetto non ha ancora un nome, il programma tiene comunque una copia di sicurezza e te la "
                    "propone alla prossima apertura.", "caption", True))
        lay.addWidget(c)
        c2 = Card()
        c2.add(label("Profili", "h2"))
        c2.add(label("Un profilo ricorda titolo, logo, scritte e credito: ne puoi avere uno per ogni canale o evento.",
                     "caption", True))
        c2.add(ProfileBar(state))
        lay.addWidget(c2)
        lay.addWidget(ApiKeysCard(state))
        lay.addWidget(CreditTab(state))
        outer.addWidget(scrolled(body))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).setText("Chiudi")
        outer.addWidget(bb)

    def _set_autosave(self, on: bool):
        self.state_.settings.data["autosave_named"] = on
        self.state_.settings.save()


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
