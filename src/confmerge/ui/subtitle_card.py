"""Scheda dei sottotitoli (Semplice e Studio Social): attivali, scegli grandezza e posizione, vedi subito un esempio, crea."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSlider, QVBoxLayout

from .. import subtitles as S
from .widgets import Card, PrimaryButton, ProgressBarThin, SecondaryButton, Segmented, Toggle, label

SAMPLE_SECONDS = 4.0


class SubtitleCard(Card):
    def __init__(self, state, open_settings=None, parent=None, wide: bool = False):
        """`wide`: due colonne (Crea | Aspetto), per le pagine senza scorrimento di Studio Social."""
        super().__init__(parent)
        self.state, self.open_settings, self.wide = state, open_settings, wide
        self.ctl = state.subtitles
        self._cols = (QVBoxLayout(), QVBoxLayout())
        if wide:
            self._cols[0].setSpacing(6)
            self._cols[1].setSpacing(6)
        c = 0
        self.add(label("Sottotitoli", "h2", True))
        if wide:
            hh = QHBoxLayout()
            hh.setSpacing(18)
            hh.addLayout(self._cols[0], 1)
            hh.addLayout(self._cols[1], 1)
            self.lay.addLayout(hh)
        self.status = label("", "caption", True)
        self._put(self.status, c)
        self.on = Toggle("Mostra i sottotitoli nel video")
        self.on.toggled.connect(self._toggled)
        self._put(self.on, c)
        self._put(label("Finché non li crei, nell'anteprima vedi una frase di esempio con lo stile che scegli.", "caption", True), c)
        # lingue: del video e dei sottotitoli (se diversa, si traduce)
        from ..transcribe import LANGS
        self._put(label("Lingua parlata nel video", ""), c)
        self.src = QComboBox()
        self.src.addItem("Riconosci da sola", "")
        for code, nm in LANGS:
            self.src.addItem(nm, code)
        self.src.currentIndexChanged.connect(self._langs)
        self._put(self.src, c)
        self._put(label("Lingua dei sottotitoli", ""), c)
        self.out = QComboBox()
        self.out.addItem("La stessa del video", "")
        for code, nm in LANGS:
            self.out.addItem(nm, code)
        self.out.setToolTip("Se scegli un'altra lingua, i sottotitoli vengono tradotti (costo trascurabile)")
        self.out.currentIndexChanged.connect(self._langs)
        self._put(self.out, c)
        # come compaiono
        self._put(label("Parole per volta", ""), c)
        self.chunk = QComboBox()
        for k, v in S.CHUNKS.items():
            self.chunk.addItem(v, k)
        self.chunk.currentIndexChanged.connect(self._chunk)
        self._put(self.chunk, c)
        self._put(label("Animazione", ""), c)
        self.anim = QComboBox()
        for k, v in S.ANIMS.items():
            self.anim.addItem(v, k)
        self.anim.currentIndexChanged.connect(self._anim)
        self._put(self.anim, c)
        # aspetto: stile pronto, carattere e colori
        c = 1
        self.style = QComboBox()
        self.style.addItem("Stile pronto: scegli…", "")
        for n in S.PRESETS:
            self.style.addItem(n, n)
        self.style.currentIndexChanged.connect(self._preset)
        self._put(self.style, c)
        from PySide6.QtWidgets import QFontComboBox, QLabel, QWidget
        self._put(label("Carattere", ""), c)
        self.font = QFontComboBox()
        self.font.currentFontChanged.connect(self._font)
        self._put(self.font, c)
        self.colors = QWidget()
        cl = QHBoxLayout(self.colors)
        cl.setContentsMargins(0, 0, 0, 0)
        self._color_btns = {}
        for attr, text in (("color", "Testo"), ("outline_color", "Bordo"), ("hl_color", "Evidenziata")):
            col = QVBoxLayout()
            col.addWidget(label(text, "caption"))
            btn = self._color_button(attr)
            self._color_btns[attr] = (btn, col)
            col.addWidget(btn)
            cl.addLayout(col)
        cl.addStretch(1)
        self._put(self.colors, c)
        self.out_lbl = label("", "", True)
        self._put(self.out_lbl, c)
        self.outline = QSlider(Qt.Horizontal)
        self.outline.setRange(0, 15)                        # spessore del bordo: 0 … 1,5 % dell'altezza
        self.outline.valueChanged.connect(self._outline)
        self._put(self.outline, c)
        # grandezza
        self.size_lbl = label("", "", True)
        self._put(self.size_lbl, c)
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(20, 140)                         # decimi di punto percentuale: 2,0 % … 14,0 % dell'altezza
        self.size.valueChanged.connect(self._size)
        self._put(self.size, c)
        # posizione
        self._put(label("Posizione", ""), c)
        self.pos = Segmented([("In basso", "bottom"), ("Al centro", "middle"), ("In alto", "top")])
        self.pos.changed.connect(self._pos)
        self._put(self.pos, c)
        self.margin_lbl = label("", "", True)
        self._put(self.margin_lbl, c)
        self.margin = QSlider(Qt.Horizontal)
        self.margin.setRange(0, 350)
        self.margin.valueChanged.connect(self._margin)
        self._put(self.margin, c)
        c = 0
        row = QHBoxLayout()
        self.make = PrimaryButton("Crea i sottotitoli", "sparkles")
        self.make.clicked.connect(self._create)
        self.cancel = SecondaryButton("Annulla", "x")
        self.cancel.setVisible(False)
        self.cancel.clicked.connect(self.ctl.cancel)
        self.keybtn = SecondaryButton("Apri le Impostazioni", "settings")
        self.keybtn.clicked.connect(self._open)
        for b in (self.make, self.cancel, self.keybtn):
            row.addWidget(b)
        row.addStretch(1)
        self._put_layout(row, c)
        self.bar = ProgressBarThin()
        self.bar.setVisible(False)
        self._put(self.bar, c)
        self.msg = label("", "caption", True)
        self._put(self.msg, c)
        self.ctl.progress.connect(lambda f, m: (self.bar.setValue(f), self.msg.setText(m)))
        self.ctl.finished.connect(lambda n: self._done(f"Fatto: {n} righe." if n else "Non ho trovato parlato da trascrivere."))
        self.ctl.failed.connect(self._done)
        self.ctl.cancelled.connect(lambda: self._done("Annullato."))
        state.project_changed.connect(self.refresh)
        state.profile_changed.connect(self.refresh)
        state.keys_changed.connect(self.refresh)            # chiave salvata nelle Impostazioni: si aggiorna da sola
        self.refresh()

    def _put(self, w, c: int = 0) -> None:
        (self._cols[c] if self.wide else self.lay).addWidget(w)

    def _put_layout(self, lo, c: int = 0) -> None:
        (self._cols[c] if self.wide else self.lay).addLayout(lo)

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    # --- stato
    def sub(self):
        return self.state.spec.subtitles

    def refresh(self):
        s, st = self.sub(), self.state
        why = self.ctl.blocker()
        have = bool(s.lines)
        self.status.setText(f"{len(s.lines)} righe pronte." if have else
                            f"Costo stimato: {self.ctl.cost_text()}. L'audio va a Groq solo quando premi «Crea».")
        for w, v in ((self.on, s.enabled), ):
            w.blockSignals(True)
            w.setChecked(v)
            w.blockSignals(False)
        self.size.blockSignals(True)
        self.size.setValue(round(s.size * 1000))
        self.size.blockSignals(False)
        self.margin.blockSignals(True)
        self.margin.setValue(round(s.margin * 1000))
        self.margin.blockSignals(False)
        self.pos.setValue(s.position)
        self.outline.blockSignals(True)
        self.outline.setValue(round(s.outline * 1000))
        self.outline.blockSignals(False)
        self.font.blockSignals(True)
        from PySide6.QtGui import QFont
        self.font.setCurrentFont(QFont(s.font))
        self.font.blockSignals(False)
        self._sync_colors()
        for cb, v in ((self.src, s.source_lang), (self.out, s.lang), (self.chunk, s.chunk_words), (self.anim, s.anim)):
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(v)))
            cb.blockSignals(False)
        self._labels()
        self.make.setEnabled(not self.ctl.running and not why)
        self.make.setText("Crea di nuovo" if have else "Crea i sottotitoli")
        self.keybtn.setVisible(bool(why) and "chiave" in why and self.open_settings is not None)
        if not self.ctl.running:
            self.msg.setText(why if st.project else "")

    def _labels(self):
        s = self.sub()
        self.out_lbl.setText(f"Spessore del bordo: {self.sub().outline * 100:.1f} %".replace(".", ","))
        for attr, (btn, col) in self._color_btns.items():
            btn.setVisible(attr != "hl_color" or self.sub().anim == "highlight")
            col.itemAt(0).widget().setVisible(btn.isVisible())
        self.size_lbl.setText(f"Grandezza: {s.size * 100:.1f} % dell'altezza".replace(".", ","))
        self.margin_lbl.setText(f"Distanza dal bordo: {s.margin * 100:.0f} %")
        self.margin.setVisible(s.position != "middle")
        self.margin_lbl.setVisible(s.position != "middle")
        safe = self.state.spec.brand.safe
        edge = (safe[0] if s.position == "top" else safe[1]) if len(safe) >= 2 and s.position != "middle" else 0.0
        if edge and S.effective_margin(s, safe) > s.margin + 1e-6:
            self.margin_lbl.setText(f"Distanza dal bordo: {S.effective_margin(s, safe) * 100:.0f} % (sopra la zona coperta dall'app)")

    # --- modifiche: ogni volta si mostra la frase di esempio per qualche secondo
    def _sample(self):
        st = self.state
        st.subtitle_sample_until = time.monotonic() + SAMPLE_SECONDS
        st.touch()
        QTimer.singleShot(int(SAMPLE_SECONDS * 1000) + 100, st.spec_changed.emit)      # poi torna al testo vero

    def _toggled(self, v: bool):
        self.sub().enabled = v
        self._sample() if v else self.state.touch()

    def _preset(self, _):
        n = self.style.currentData()
        if n:
            S.apply_preset(self.sub(), n)
            self.sub().enabled = True
            self.refresh()
            self._sample()

    def _size(self, v: int):
        self.sub().size = v / 1000
        self.sub().enabled = True
        self._labels()
        self._sample()

    def _color_button(self, attr: str):
        """Pulsante-campione che legge e scrive sempre l'impostazione corrente (anche dopo un nuovo modello di stile)."""
        from PySide6.QtWidgets import QPushButton
        from .color_picker import ColorPicker
        from .theme import theme
        btn = QPushButton()
        btn.setMinimumWidth(72)
        btn.setToolTip("Clicca per scegliere il colore")

        def paint():
            btn.setStyleSheet(f"background:{getattr(self.sub(), attr)}; border:1px solid {theme.t.border}; border-radius:8px;")
        btn.paint = paint                                   # type: ignore[attr-defined]

        def pick():
            pk = ColorPicker(getattr(self.sub(), attr), btn)

            def live(c: str):
                setattr(self.sub(), attr, c)
                self.sub().enabled = True
                paint()
                self._sample()
            pk.colorChanged.connect(live)
            pk.show_below(btn)
        btn.clicked.connect(pick)
        paint()
        return btn

    def _sync_colors(self):
        for btn, _ in self._color_btns.values():
            btn.paint()
        self._labels()

    def _font(self, f):
        self.sub().font = f.family()
        self.sub().enabled = True
        self._sample()

    def _outline(self, v: int):
        self.sub().outline = v / 1000
        self._labels()
        self._sample()

    def _langs(self, _=0):
        s = self.sub()
        s.source_lang, s.lang = self.src.currentData(), self.out.currentData()
        self.state.touch()

    def _chunk(self, _=0):
        self.sub().chunk_words = self.chunk.currentData()
        self.sub().enabled = True
        self._sample()

    def _anim(self, _=0):
        self.sub().anim = self.anim.currentData()
        self.sub().enabled = True
        self._sample()

    def _pos(self, v):
        self.sub().position = v
        self.sub().x, self.sub().y = 0.5, -1.0                 # scegliere una posizione annulla il trascinamento
        self.sub().enabled = True
        self._labels()
        self._sample()

    def _margin(self, v: int):
        self.sub().margin = v / 1000
        self.sub().x, self.sub().y = 0.5, -1.0
        self._labels()
        self._sample()

    # --- creazione
    def _open(self):
        if self.open_settings:
            self.open_settings()
        self.refresh()

    def _create(self):
        self.make.setVisible(False)
        self.cancel.setVisible(True)
        self.bar.setVisible(True)
        self.msg.setText("Avvio…")
        self.ctl.start()

    def _done(self, text: str):
        self.make.setVisible(True)
        self.cancel.setVisible(False)
        self.bar.setVisible(False)
        self.refresh()
        if text:
            self.msg.setText(text)
