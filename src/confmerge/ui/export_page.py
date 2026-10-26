"""Fase «Export e coda» (modalità Avanzata): vista su ExportController."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import encoders
from ..queue import DONE, FAILED
from ..spec import PRESETS
from . import bind
from .controllers import fmt_dur
from .theme import S1, S2, pixmap, theme
from .thumbnail_dialog import ThumbnailDialog
from .widgets import (Card, GhostButton, IconButton, PrimaryButton, ProgressBarThin, SecondaryButton, Section, Toggle, label)

PRESET_LABELS = {"YouTube 1080p": "YouTube, qualità consigliata (1080p)", "YouTube 1440p": "YouTube, alta qualità (1440p)",
                 "YouTube 4K": "YouTube, massima qualità (4K)", "Veloce (copia stream)": "Veloce, senza ricodificare",
                 "Personalizzato": "Personalizzato"}


def confirm_credit_conflict(parent) -> str | None:
    """Con la copia stream il credito non si può aggiungere: 'off' = senza credito, 'encode' = ricodifica, None = annulla."""
    m = QMessageBox(parent)
    m.setWindowTitle("Credito finale")
    m.setText("Con l'export veloce (senza ricodificare) il credito «Created with ConfMerge» non si può aggiungere.")
    b1 = m.addButton("Senza credito (veloce)", QMessageBox.AcceptRole)
    b2 = m.addButton("Con il credito (più lento)", QMessageBox.ActionRole)
    m.addButton("Annulla", QMessageBox.RejectRole)
    m.exec()
    return "off" if m.clickedButton() is b1 else "encode" if m.clickedButton() is b2 else None


def start_export(parent, ctl, state, run_now: bool):
    """Prepara, chiede conferma dove serve e mette in coda; condiviso da Semplice e Avanzata."""
    from .. import export_engine as ee
    prep = ctl.prepare()
    if prep is None:
        return None
    if prep.dec.credit_conflict:
        choice = confirm_credit_conflict(parent)
        if choice is None:
            return None
        if choice == "off":
            prep.spec.credit.enabled = False
        else:
            prep.spec.export.preset = "YouTube 1080p"
        prep.dec = ee.decide(prep.spec, state.clips)
    prep.space_warnings = ctl.space_warnings(prep)
    if prep.space_warnings and QMessageBox.question(parent, "Spazio sul disco", "\n".join(prep.space_warnings)
                                                    + "\n\nContinuare comunque?") != QMessageBox.Yes:
        return None
    item = ctl.enqueue(prep)
    if run_now:
        ctl.start_queue()
    return item


class ExportPage(QWidget):
    def __init__(self, state, review_page, parent=None):
        super().__init__(parent)
        self.state, self.review = state, review_page
        self.ctl = state.export
        main = QVBoxLayout(self)
        main.addWidget(label("Export e coda", "title"))
        cols = QBoxLayout(QBoxLayout.LeftToRight)      # in finestre strette le due colonne vanno una sotto l'altra
        self._cols = cols
        cols.setSpacing(S2)
        main.addLayout(cols, 1)
        left = QVBoxLayout()
        right = QVBoxLayout()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)

        self.box_q = Section("Qualità del video", "exp-quality")
        left.addWidget(self.box_q)
        self.build_settings()
        dest = Section("Dove salvarlo", "exp-dest")
        f = dest.form()
        self.dir_edit = QLineEdit(state.spec.export.out_dir)
        self.dir_edit.textChanged.connect(self._dir_changed)
        b = SecondaryButton("Scegli…", "folder-open")
        b.clicked.connect(self.pick_dir)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit, 1)
        row.addWidget(b)
        w = QWidget()
        w.setLayout(row)
        f.addRow("Cartella", w)
        self.name_edit = QLineEdit(state.spec.export.name)
        self.name_edit.textChanged.connect(lambda t: setattr(state.spec.export, "name", t))
        f.addRow("Nome del file", self.name_edit)
        left.addWidget(dest)
        left.addStretch(1)

        est = Card()
        est.add(label("Quanto tempo e quanto spazio?", "h2", True))
        self.est_time = label("Tempo: calcolo in corso…", "", True)
        self.est_size = label("Dimensione del file: calcolo in corso…", "", True)
        est.add(self.est_time)
        est.add(self.est_size)
        self.est_note = label("", "caption", True)
        est.add(self.est_note)
        self.warn_lbl = label("", "warn", True)
        est.add(self.warn_lbl)
        right.addWidget(est)
        pv = Card()
        row = QHBoxLayout()
        row.addWidget(label("Anteprima di 10 secondi da"))
        self.prev_start = QDoubleSpinBox()
        self.prev_start.setRange(0, 360000)
        self.prev_start.setSuffix(" s")
        self.prev_start.setToolTip("Punto del video finale da cui parte l'anteprima, in secondi")
        row.addWidget(self.prev_start, 1)
        pv.lay.addLayout(row)
        row = QHBoxLayout()
        b = SecondaryButton("Guarda l'anteprima", "play")
        b.clicked.connect(self.preview_sample)
        row.addWidget(b)
        b = SecondaryButton("Crea la miniatura…", "image")
        b.clicked.connect(self.thumbnail)
        row.addWidget(b)
        pv.lay.addLayout(row)
        self.prev_msg = label("", "caption", True)
        pv.add(self.prev_msg)
        right.addWidget(pv)
        row = QHBoxLayout()
        b = SecondaryButton("Aggiungi alla coda", "plus")
        b.clicked.connect(lambda: self.enqueue(False))
        row.addWidget(b)
        b = PrimaryButton("Esporta ora", "download")
        b.clicked.connect(lambda: self.enqueue(True))
        row.addWidget(b)
        right.addLayout(row)
        self.bar = ProgressBarThin()
        right.addWidget(self.bar)
        self.prog_lbl = label("", "caption", True)
        right.addWidget(self.prog_lbl)
        right.addWidget(label("Coda di export", "h2"))
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        ic = QLabel()
        ic.setAlignment(Qt.AlignCenter)
        ic.setMinimumHeight(48)
        self._empty_icon = ic
        el.addWidget(ic)
        t1 = label("Nessun lavoro in coda", "h2")
        t1.setAlignment(Qt.AlignCenter)
        el.addWidget(t1)
        t2 = label("Premi «Aggiungi alla coda» per preparare più video e farli uno dopo l'altro, "
                   "oppure «Esporta ora» per iniziare subito.", "muted", True)
        t2.setAlignment(Qt.AlignCenter)
        el.addWidget(t2)
        right.addWidget(self.empty)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Video", "Previsione", "Stato", "%"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setMinimumHeight(110)
        right.addWidget(self.table, 1)
        row = QHBoxLayout()
        for icon, tip, fn in (("arrow-up", "Sposta su", lambda: self._move(-1)), ("arrow-down", "Sposta giù", lambda: self._move(1))):
            ib = IconButton(icon, tip)
            ib.clicked.connect(fn)
            row.addWidget(ib)
        b = GhostButton("Annulla il selezionato", "x")
        b.clicked.connect(lambda: self.ctl.cancel(self.table.currentRow()))
        row.addWidget(b)
        b = SecondaryButton("Avvia la coda", "play")
        b.clicked.connect(self.ctl.start_queue)
        row.addWidget(b)
        right.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("Quando ha finito:"))
        self.after = QComboBox()
        self.after.addItem("Non fare nulla", "none")
        self.after.addItem("Spegni il computer", "shutdown")
        self.after.addItem("Metti il computer in attesa", "sleep")
        self.after.currentIndexChanged.connect(lambda _: setattr(self.ctl, "after_action", self.after.currentData()))
        row.addWidget(self.after, 1)
        right.addLayout(row)

        self.ctl.estimateStarted.connect(self._est_started)
        self.ctl.estimateReady.connect(self._est_ready)
        self.ctl.estimateFailed.connect(lambda m: self.est_time.setText("Tempo: non disponibile"))
        self.ctl.queueChanged.connect(self.render_queue)
        self.ctl.progress.connect(self._progress)
        self.ctl.finished.connect(self._finished)
        self.ctl.previewReady.connect(self._show_preview)
        self.ctl.previewFailed.connect(lambda m: (self.prev_msg.setText(""), QMessageBox.warning(self, "ConfMerge", m)))
        self.ctl.powerRequested.connect(self._power)
        state.spec_changed.connect(self.ctl.request_estimate)
        state.project_changed.connect(self.on_project)
        theme.changed.connect(self._icons)
        self._icons()
        self.render_queue()

    def _icons(self):
        self._empty_icon.setPixmap(pixmap("list-checks", theme.t.text2, 40))

    # --- impostazioni
    def build_settings(self):
        sec = self.box_q
        while sec.body_lay.count():
            it = sec.body_lay.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
            elif it.layout():
                while it.layout().count():
                    x = it.layout().takeAt(0)
                    if x.widget():
                        x.widget().setParent(None)
        ex = self.state.spec.export
        f = sec.form()
        f.addRow("Per cosa lo vuoi?", bind.combo(ex, "preset", [(PRESET_LABELS[p], p) for p in PRESETS], self._preset_changed))
        self.custom_h = bind.ispin(ex, "custom_height", 240, 4320, self._changed, " px")
        self.custom_row_label = QLabel("Altezza")
        f.addRow(self.custom_row_label, self.custom_h)
        adv = Section("Avanzate (di solito non servono)", "exp-adv", opened=False)
        af = adv.form()
        br = QDoubleSpinBox()
        br.setRange(0, 200)
        br.setSpecialValueText("Automatico")
        br.setSuffix(" Mbit/s")
        br.setValue(ex.bitrate_mbps or 0)
        br.valueChanged.connect(lambda v: (setattr(ex, "bitrate_mbps", v or None), self._changed()))
        af.addRow("Qualità (bitrate)", br)
        self.crf_toggle = bind.check(ex, "crf_mode", "Usa una qualità costante invece del bitrate (CRF)", self._crf_toggled)
        adv.add(self.crf_toggle)
        self.crf_spin = bind.ispin(ex, "crf", 10, 35, self._changed)
        self.crf_row = QWidget()
        cr = QHBoxLayout(self.crf_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.addWidget(label("Valore CRF (più basso = migliore e più pesante)"))
        cr.addWidget(self.crf_spin)
        adv.add(self.crf_row)
        enc = bind.combo(ex, "encoder", [("Automatico", "auto"), ("Processore (x264)", "libx264"), ("Scheda NVIDIA", "h264_nvenc"),
                                         ("Intel Quick Sync", "h264_qsv"), ("Scheda AMD", "h264_amf")], self._changed)
        af.addRow("Come codificare", enc)
        self.hw_lbl = label("", "caption", True)
        adv.add(self.hw_lbl)
        sec.add(adv)
        self._crf_toggled()
        self._preset_changed(refresh=False)

    def _preset_changed(self, refresh: bool = True):
        custom = self.state.spec.export.preset == "Personalizzato"
        self.custom_h.setVisible(custom)
        self.custom_row_label.setVisible(custom)
        if refresh:
            self._changed()
            self.state.touch()

    def _crf_toggled(self):
        self.crf_row.setVisible(bool(self.state.spec.export.crf_mode))
        self._changed()

    def _dir_changed(self, t: str):
        self.state.spec.export.out_dir = t
        self._changed()

    def _changed(self):
        self.ctl.request_estimate()

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella di destinazione", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def on_project(self):
        pr = self.state.project
        if pr and not self.dir_edit.text():
            self.dir_edit.setText(str(Path(pr.clips[0]).parent))
        if pr and self.state.spec.export.name in ("", "conferenza"):
            self.name_edit.setText(Path(pr.clips[0]).parent.name or "conferenza")
        self.build_settings()
        self._changed()

    def showEvent(self, e):
        super().showEvent(e)
        self.ctl.active = True
        hw = encoders.detect_hw() if self.state.project else []
        self.hw_lbl.setText("Scheda video usabile: " + (", ".join(hw) if hw else "nessuna (si usa il processore)"))
        self.ctl.run_estimate()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.ctl.active = False

    def set_available_width(self, w: int) -> None:
        """Chiamata dal contenitore con scroll: sotto ~1020 px le due colonne vanno una sotto l'altra."""
        d = QBoxLayout.TopToBottom if w < 1020 else QBoxLayout.LeftToRight
        if self._cols.direction() != d:
            self._cols.setDirection(d)

    # --- stima: tempo e dimensione si vedono sempre
    def _est_started(self):
        self.est_time.setText("Tempo: calcolo in corso…")
        q = self.ctl.quick_size()
        prev = self.ctl.est
        self.est_size.setText("Dimensione del file: " + (f"circa {q}" if q else
                              (f"{prev.size_text} (aggiornamento in corso…)" if prev else "calcolo in corso…")))

    def _est_ready(self, est):
        self.est_time.setText(f"Tempo: <b>{est.time_text}</b>")
        self.est_time.setTextFormat(Qt.RichText)
        self.est_size.setText(f"Dimensione del file: <b>{est.size_text}</b>" + (" (stima approssimativa)" if est.approximate else ""))
        self.est_size.setTextFormat(Qt.RichText)
        self.est_note.setText((f"Velocità misurata su un campione: {est.speed_x:.1f} volte il tempo reale. " if est.speed_x else "")
                              + " ".join(est.notes))
        self.warn_lbl.setText("\n".join("⚠ " + w for w in self.ctl.warnings()))

    # --- anteprima 10 s
    def preview_sample(self):
        if not self.state.project:
            return
        self.prev_msg.setText("Preparo l'anteprima con tutti gli effetti: ci vuole un po'…")
        self.ctl.make_preview(self.prev_start.value())

    def _show_preview(self, path):
        self.prev_msg.setText("")
        d = QDialog(self)
        d.setWindowTitle("Anteprima di 10 secondi")
        d.resize(960, 560)
        lay = QVBoxLayout(d)
        vw = QVideoWidget()
        lay.addWidget(vw, 1)
        pl = QMediaPlayer(d)
        ao = QAudioOutput(d)
        pl.setAudioOutput(ao)
        pl.setVideoOutput(vw)
        pl.setSource(QUrl.fromLocalFile(str(path)))
        pl.play()
        d.finished.connect(pl.stop)
        d.exec()

    def thumbnail(self):
        if self.state.project:
            ThumbnailDialog(self.state, Path(self.dir_edit.text() or "."), self.name_edit.text() or "conferenza",
                            self.review.player.position, self).exec()

    # --- coda
    def enqueue(self, run_now: bool):
        start_export(self, self.ctl, self.state, run_now)

    def _move(self, d: int):
        r = self.table.currentRow()
        self.ctl.move(r, d)
        self.table.selectRow(max(0, min(r + d, len(self.state.queue.items) - 1)))

    def render_queue(self):
        q = self.state.queue
        self.empty.setVisible(not q.items)
        self.table.setVisible(bool(q.items))
        self.table.setRowCount(len(q.items))
        for r, it in enumerate(q.items):
            for c, v in enumerate((it.name, it.estimate, it.status + (f": {it.error[:60]}" if it.error else ""),
                                   f"{it.progress * 100:.0f}")):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def _progress(self, item, frac: float, remaining, size: int):
        self.bar.setValue(frac)
        self.prog_lbl.setText(f"{item.name}: {frac * 100:.0f}% — tempo rimasto "
                              + (fmt_dur(remaining) if remaining is not None else "in calcolo…")
                              + f" — file finora {size / 1e6:.0f} MB")

    def _finished(self, results):
        self.render_queue()
        self.bar.setValue(1.0 if results and all(it.status == DONE for it, _ in results) else self.bar.value())
        failed = [it for it, _ in results if it.status == FAILED]
        lines = []
        for it, rep in [r for r in results if r[0].status == DONE][-3:]:
            if rep:
                lines.append(f"{it.name}: {fmt_dur(rep.wall_s)}, {rep.size_bytes / 1e6:.0f} MB")
                lines += ["  • " + n for n in rep.notes]
        if failed:
            QMessageBox.critical(self, "Non è riuscito", "\n".join(f"{i.name}: {i.error}" for i in failed)
                                 + "\n\nIl dettaglio è nel file di log (menu Aiuto).")
        elif lines:
            est = self.ctl.est
            QMessageBox.information(self, "Fatto!", "\n".join(lines) + (f"\n\nPrevisione: {est.time_text}, {est.size_text}" if est else ""))
        self.prog_lbl.setText("Completato." if lines else "")

    def _power(self, action: str):
        if QMessageBox.question(self, "ConfMerge", "Il computer si spegnerà (o andrà in attesa) tra poco. Annullare?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            self.ctl.do_power(action)
