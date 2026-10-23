"""Schermata «Informazioni»: autore, licenza, repository, crediti delle librerie."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout

from .. import REPO_URL, __author__, __version__

CREDITS = """
<h3>Librerie incluse</h3>
<ul>
<li><b>PySide6 / Qt 6</b> — LGPL v3 — <a href="https://www.qt.io">qt.io</a>. Qt è collegato dinamicamente; nella versione
    «cartella» (onedir) le librerie Qt possono essere sostituite.</li>
<li><b>NumPy</b> — BSD-3 — <a href="https://numpy.org">numpy.org</a></li>
<li><b>SciPy</b> — BSD-3 — <a href="https://scipy.org">scipy.org</a></li>
<li><b>FFmpeg / ffprobe</b> — LGPL/GPL (build con x264: GPL) — <a href="https://ffmpeg.org">ffmpeg.org</a>; sorgenti della build
    indicati in THIRD-PARTY-NOTICES.txt</li>
<li><b>qrcode</b> — BSD — <a href="https://github.com/lincolnloop/python-qrcode">python-qrcode</a></li>
<li><b>PyInstaller</b> — GPL v2 con eccezione per i programmi impacchettati — <a href="https://pyinstaller.org">pyinstaller.org</a></li>
</ul>
<p>Il testo completo e i link ai sorgenti sono in <b>THIRD-PARTY-NOTICES.txt</b>.</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Informazioni su ConfMerge")
        self.resize(520, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h2>ConfMerge {__version__}</h2>"
                             "Prepara video di conferenze per YouTube.<br>"
                             f"Autore: <b>{__author__}</b><br>"
                             "Licenza: <b>MIT</b> — Copyright (c) 2026 Martino Zanzi<br>"
                             f"Repository: <a href='{REPO_URL}'>{REPO_URL}</a><br>"
                             "Funziona interamente offline, senza telemetria."))
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml(CREDITS)
        lay.addWidget(tb, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for lab in self.findChildren(QLabel):
            lab.setOpenExternalLinks(True)
