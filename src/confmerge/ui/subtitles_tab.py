"""Scheda «Sottotitoli»: crea con Groq, scegli lo stile, correggi il testo, esporta il file .srt."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QMessageBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import subtitles as S
from ..spec import SubLine
from . import bind
from .widgets import PrimaryButton, ProgressBarThin, SecondaryButton, Section, label

FONTS = [("Poppins", "Poppins"), ("Inter", "Inter"), ("Bebas Neue", "Bebas Neue"), ("Anton", "Anton"),
         ("DM Serif Display", "DM Serif Display"), ("Space Mono", "Space Mono"), ("Segoe UI", "Segoe UI")]


def fmt_t(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t) // 60}:{t % 60:04.1f}".replace(".", ",")


def parse_t(text: str) -> float | None:
    """«1:23,4», «83,4» o «83» → secondi."""
    try:
        parts = text.strip().replace(",", ".").split(":")
        v = 0.0
        for p in parts:
            v = v * 60 + float(p)
        return v
    except ValueError:
        return None


class SubtitlesTab(QWidget):
    def __init__(self, state, page, parent=None):
        super().__init__(parent)
        self.state, self.page = state, page
        self.ctl = state.subtitles
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(label("Il programma ascolta il parlato e scrive i sottotitoli; tu puoi correggere ogni riga e "
                            "scegliere come appaiono.", "muted", True))
        # --- crea
        self.make_box = Section("Crea i sottotitoli", "subs:make")
        self.status = label("", "caption", True)
        self.make_box.body_lay.addWidget(self.status)
        row = QHBoxLayout()
        self.make_btn = PrimaryButton("Crea i sottotitoli", "sparkles")
        self.make_btn.clicked.connect(self.create)
        self.cancel_btn = SecondaryButton("Annulla", "x")
        self.cancel_btn.clicked.connect(self.ctl.cancel)
        self.cancel_btn.setVisible(False)
        row.addWidget(self.make_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        self.make_box.body_lay.addLayout(row)
        self.bar = ProgressBarThin()
        self.bar.setVisible(False)
        self.make_box.body_lay.addWidget(self.bar)
        self.msg = label("", "caption", True)
        self.make_box.body_lay.addWidget(self.msg)
        self.show_form = self.make_box.form()
        lay.addWidget(self.make_box)
        # --- stile
        self.style_box = Section("Aspetto", "subs:style")
        self.style_form = self.style_box.form()
        lay.addWidget(self.style_box)
        # --- testo
        self.text_box = Section("Testo e tempi", "subs:text", opened=True)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Inizio", "Fine", "Testo"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(220)
        self.table.setMinimumWidth(0)
        self.table.horizontalHeader().setMinimumSectionSize(60)
        self.table.itemChanged.connect(self._edited)
        self.table.currentCellChanged.connect(lambda r, *_: self._goto(r))
        self.text_box.body_lay.addWidget(self.table)
        btns = QGridLayout()                       # due colonne: nei pannelli stretti i pulsanti non allargano la scheda
        btns.setHorizontalSpacing(8)
        btns.setVerticalSpacing(8)
        for n, (text, ic, fn) in enumerate((("Elimina la riga", "trash-2", self.delete_row),
                                            ("Esporta .srt…", "save", self.export_srt),
                                            ("Cancella tutto", "x", self.clear_all))):
            b = SecondaryButton(text, ic)
            b.clicked.connect(fn)
            btns.addWidget(b, n // 2, n % 2)
        btns.setColumnStretch(2, 1)
        self.text_box.body_lay.addLayout(btns)
        lay.addWidget(self.text_box)
        lay.addStretch(1)
        self.ctl.progress.connect(self._progress)
        self.ctl.finished.connect(self._finished)
        self.ctl.failed.connect(self._failed)
        self.ctl.cancelled.connect(lambda: self._busy(False, "Annullato."))
        state.profile_changed.connect(self.refresh)
        state.project_changed.connect(self.refresh)
        self.refresh()

    # --- stato
    def sub(self):
        return self.state.spec.subtitles

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def refresh(self):
        self._status()
        self._build_style()
        self._fill_table()

    def _status(self):
        st, sub = self.state, self.sub()
        if not st.project:
            self.status.setText("Prima apri una cartella di video e controlla inizio e fine.")
        elif sub.lines:
            self.status.setText(f"{len(sub.lines)} righe di sottotitoli, create per il tratto "
                                f"{fmt_t(sub.range_start - st.trim_start)}–{fmt_t(sub.range_end - st.trim_start)} del video."
                                + ("" if abs(sub.range_start - st.trim_start) < 0.5 and abs(sub.range_end - st.trim_end) < 0.5
                                   else " Hai cambiato inizio o fine: se serve, crea di nuovo i sottotitoli."))
        else:
            self.status.setText(f"Costo stimato: {self.ctl.cost_text()} (servizio Groq, si paga a consumo). "
                                "L'audio viene inviato a Groq solo quando premi il pulsante.")
        why = self.ctl.blocker()
        self.msg.setText(why if why and st.project else "")
        self.make_btn.setEnabled(not self.ctl.running and not why)
        self.make_btn.setText("Crea di nuovo i sottotitoli" if sub.lines else "Crea i sottotitoli")

    def _build_style(self):
        f = self.style_form
        while f.rowCount():
            f.removeRow(0)
        sub, cb = self.sub(), self._style_changed
        f.addRow(bind.check(sub, "enabled", "Mostra i sottotitoli sul video", cb))
        presets = QComboBox()
        presets.addItem("Scegli uno stile pronto…", "")
        for n in S.PRESETS:
            presets.addItem(n, n)
        presets.currentIndexChanged.connect(lambda _: self._preset(presets.currentData()))
        f.addRow("Stile pronto", presets)
        f.addRow("Carattere", bind.combo(sub, "font", FONTS, cb))
        f.addRow("Grandezza (%)", bind.spin(sub, "size", 2, 14, 0.2, 1, "", 100, cb))
        f.addRow("Colore del testo", bind.color(sub, "color", cb))
        f.addRow("Posizione", bind.combo(sub, "position", [(v, k) for k, v in S.POSITIONS.items()], cb))
        f.addRow("Distanza bordo (%)", bind.spin(sub, "margin", 0, 40, 0.5, 1, "", 100, cb))
        f.addRow(bind.check(sub, "bold", "Grassetto", cb))
        f.addRow(bind.check(sub, "uppercase", "Tutto maiuscolo", cb))
        f.addRow(bind.check(sub, "shadow", "Ombra", cb))
        f.addRow("Bordo (%)", bind.spin(sub, "outline", 0, 2, 0.05, 2, "", 100, cb))
        f.addRow("Colore del bordo", bind.color(sub, "outline_color", cb))
        f.addRow(bind.check(sub, "box", "Sfondo dietro il testo", cb))
        f.addRow("Colore dello sfondo", bind.color(sub, "box_color", cb))
        f.addRow("Opacità sfondo (%)", bind.spin(sub, "box_opacity", 0, 100, 5, 0, "", 100, cb))
        f.addRow("Caratteri per riga", bind.ispin(sub, "max_chars", 20, 80, lambda: None))
        f.addRow(label("La lunghezza vale solo quando crei i sottotitoli.", "caption", True))

    def _style_changed(self):
        self.state.touch()
        self.page.canvas.update()

    def _preset(self, name: str):
        if name:
            S.apply_preset(self.sub(), name)
            self.sub().enabled = True
            self.state.touch()
            self._build_style()
            self.page.canvas.update()

    # --- creazione
    def create(self):
        sub = self.sub()
        if sub.lines and QMessageBox.question(self, "Crea di nuovo",
                                              "I sottotitoli attuali (e le correzioni fatte) verranno sostituiti. Continuare?"
                                              ) != QMessageBox.Yes:
            return
        self._busy(True, "Avvio…")
        self.ctl.start()

    def _busy(self, on: bool, text: str = ""):
        self.make_btn.setVisible(not on)
        self.cancel_btn.setVisible(on)
        self.bar.setVisible(on)
        self.msg.setText(text)
        if not on:
            self._status()

    def _progress(self, f: float, m: str):
        self.bar.setValue(f)
        self.msg.setText(m)

    def _finished(self, n: int):
        self._busy(False, f"Fatto: {n} righe. Controllale e correggi dove serve." if n else
                   "Non ho trovato parlato da trascrivere.")
        self.refresh()
        if n:
            self.page.seek_out(max(0.0, self.sub().lines[0].start - self.state.trim_start))

    def _failed(self, m: str):
        self._busy(False, m)
        self.msg.setText(m)

    # --- tabella
    def _fill_table(self):
        sub, t0 = self.sub(), self.state.trim_start
        self.table.blockSignals(True)
        self.table.setRowCount(len(sub.lines))
        for r, ln in enumerate(sub.lines):
            for c, v in enumerate((fmt_t(ln.start - t0), fmt_t(ln.end - t0), ln.text)):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)

    def _edited(self, it: QTableWidgetItem):
        sub, t0 = self.sub(), self.state.trim_start
        r, c = it.row(), it.column()
        if r >= len(sub.lines):
            return
        ln = sub.lines[r]
        if c == 2:
            ln.text = it.text()
        else:
            v = parse_t(it.text())
            if v is None:
                self._fill_table()
                return
            if c == 0:
                ln.start = min(v + t0, ln.end - 0.1)
            else:
                ln.end = max(v + t0, ln.start + 0.1)
            self._fill_table()
        self._style_changed()

    def _goto(self, r: int):
        sub = self.sub()
        if 0 <= r < len(sub.lines):
            self.page.seek_out(max(0.0, sub.lines[r].start - self.state.trim_start + 0.2))

    def delete_row(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.sub().lines):
            del self.sub().lines[r]
            self._fill_table()
            self._style_changed()
            self._status()

    def clear_all(self):
        if self.sub().lines and QMessageBox.question(self, "Cancella tutto", "Eliminare tutte le righe?") == QMessageBox.Yes:
            self.sub().lines = []
            self._fill_table()
            self._style_changed()
            self._status()

    def export_srt(self):
        st = self.state
        if not self.sub().lines:
            QMessageBox.information(self, "ConfMerge", "Non ci sono sottotitoli da esportare.")
            return
        base = Path(st.spec.export.out_dir or str(Path.home())) / f"{st.spec.export.name or 'sottotitoli'}.srt"
        path, _ = QFileDialog.getSaveFileName(self, "Esporta sottotitoli", str(base), "Sottotitoli (*.srt)")
        if path:
            Path(path).write_text(S.to_srt(self.sub(), st.ranges()), encoding="utf-8")


def SimpleSubtitlesCard(state, open_settings=None, parent=None):
    """Scheda dei sottotitoli per Semplice e Studio Social (vedi subtitle_card.py)."""
    from .subtitle_card import SubtitleCard
    return SubtitleCard(state, open_settings, parent)
