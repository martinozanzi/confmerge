"""Schermata 5: export, stima di tempo e dimensione, anteprima 10 s, coda, miniatura."""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import encoders, estimator, export_engine as ee, paths
from ..queue import DONE, FAILED, QueueItem
from ..spec import PRESETS, RenderSpec, output_size
from ..worker import Worker
from . import bind
from .player import fmt
from .thumbnail_dialog import ThumbnailDialog


def _fmt_dur(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class ExportPage(QWidget):
    def __init__(self, state, review_page, parent=None):
        super().__init__(parent)
        self.state, self.review = state, review_page
        self.est_worker: Worker | None = None
        self.run_worker: Worker | None = None
        self.est: ee.Estimate | None = None
        self._est_dirty = False
        self._current_item: QueueItem | None = None
        self._reports: dict[int, ee.ExportReport] = {}
        self._est_mid: dict[int, float] = {}
        self._t_start = 0.0
        self.speed = estimator.MovingSpeed()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.run_estimate)
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(500)
        self.ui_timer.timeout.connect(self.refresh_queue)

        main = QVBoxLayout(self)
        main.addWidget(QLabel("<h2>5. Export</h2>"))
        cols = QHBoxLayout()
        main.addLayout(cols)
        left = QVBoxLayout()
        cols.addLayout(left, 1)
        right = QVBoxLayout()
        cols.addLayout(right, 1)

        self.box_preset = QGroupBox("Preset e codifica")
        left.addWidget(self.box_preset)
        self.build_settings()
        g = QGroupBox("Audio per YouTube")
        f = QFormLayout(g)
        a = state.spec.audio
        self._audio_widgets = [bind.check(a, "loudnorm", "Normalizza a −14 LUFS (true peak −1 dBTP, due passate)", self.changed),
                               bind.check(a, "highpass", "Filtro passa-alto (voce)", self.changed),
                               bind.check(a, "denoise", "Riduzione rumore (afftdn)", self.changed),
                               bind.check(a, "compressor", "Compressore leggero", self.changed)]
        for w in self._audio_widgets:
            f.addRow(w)
        self.loud_lbl = QLabel("Livello: misurato dopo l'export")
        f.addRow(self.loud_lbl)
        left.addWidget(g)
        g = QGroupBox("Destinazione")
        f = QFormLayout(g)
        self.dir_edit = QLineEdit(state.spec.export.out_dir)
        self.dir_edit.textChanged.connect(lambda t: (setattr(state.spec.export, "out_dir", t), self.changed()))
        b = QPushButton("Scegli…")
        b.clicked.connect(self.pick_dir)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit)
        row.addWidget(b)
        w = QWidget()
        w.setLayout(row)
        f.addRow("Cartella", w)
        self.name_edit = QLineEdit(state.spec.export.name)
        self.name_edit.textChanged.connect(lambda t: setattr(state.spec.export, "name", t))
        f.addRow("Nome file", self.name_edit)
        left.addWidget(g)
        left.addStretch(1)

        g = QGroupBox("Stima")
        gl = QVBoxLayout(g)
        self.est_lbl = QLabel("—")
        self.est_lbl.setWordWrap(True)
        self.est_lbl.setTextFormat(Qt.RichText)
        gl.addWidget(self.est_lbl)
        self.warn_lbl = QLabel()
        self.warn_lbl.setWordWrap(True)
        self.warn_lbl.setStyleSheet("color:#d08000")
        gl.addWidget(self.warn_lbl)
        right.addWidget(g)
        row = QHBoxLayout()
        self.prev_start = QDoubleSpinBox()
        self.prev_start.setRange(0, 360000)
        self.prev_start.setSuffix(" s")
        self.prev_start.setToolTip("Inizio dell'anteprima (secondi di uscita)")
        row.addWidget(QLabel("Anteprima 10 s da"))
        row.addWidget(self.prev_start)
        b = QPushButton("▶ Anteprima 10 s")
        b.clicked.connect(self.preview_sample)
        row.addWidget(b)
        b = QPushButton("🖼 Miniatura…")
        b.clicked.connect(self.thumbnail)
        row.addWidget(b)
        right.addLayout(row)
        row = QHBoxLayout()
        b = QPushButton("➕ Aggiungi alla coda")
        b.clicked.connect(lambda: self.enqueue(False))
        row.addWidget(b)
        b = QPushButton("⬇ Esporta ora")
        b.clicked.connect(lambda: self.enqueue(True))
        row.addWidget(b)
        right.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        right.addWidget(self.bar)
        self.prog_lbl = QLabel()
        right.addWidget(self.prog_lbl)
        right.addWidget(QLabel("<b>Coda di export</b>"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Progetto", "Stima", "Stato", "%"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        right.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, fn in (("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1)), ("Annulla elemento", self.cancel_item),
                         ("▶ Avvia coda", self.start_queue)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        right.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Al termine:"))
        self.after = QComboBox()
        self.after.addItems(["Non fare nulla", "Spegni il PC", "Sospendi il PC"])
        row.addWidget(self.after)
        row.addStretch(1)
        right.addLayout(row)
        state.spec_changed.connect(self.changed)
        state.project_changed.connect(self.on_project)

    # --- impostazioni
    def build_settings(self):
        old = self.box_preset.layout()
        if old:
            QWidget().setLayout(old)
        ex = self.state.spec.export
        f = QFormLayout(self.box_preset)
        f.addRow("Preset", bind.combo(ex, "preset", PRESETS, lambda: (self.changed(), self.state.touch())))
        f.addRow("Altezza personalizzata", bind.ispin(ex, "custom_height", 240, 4320, self.changed, " px"))
        br = QDoubleSpinBox()
        br.setRange(0, 200)
        br.setSuffix(" Mbit/s (0 = preset)")
        br.setValue(ex.bitrate_mbps or 0)
        br.valueChanged.connect(lambda v: (setattr(ex, "bitrate_mbps", v or None), self.changed()))
        f.addRow("Bitrate video", br)
        f.addRow(bind.check(ex, "crf_mode", "Avanzato: usa CRF invece del bitrate (dimensione approssimata)", self.changed))
        f.addRow("CRF", bind.ispin(ex, "crf", 10, 35, self.changed))
        enc = bind.combo(ex, "encoder", [("Automatico (hardware se disponibile)", "auto"), ("CPU (x264)", "libx264"),
                                         ("NVIDIA NVENC", "h264_nvenc"), ("Intel QSV", "h264_qsv"), ("AMD AMF", "h264_amf")], self.changed)
        f.addRow("Encoder", enc)
        self.hw_lbl = QLabel("Rilevamento hardware al primo utilizzo")
        f.addRow(self.hw_lbl)

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
        self.changed()

    # --- stima
    def changed(self):
        self.est_lbl.setText("Stima in aggiornamento…")
        self.timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        hw = encoders.detect_hw() if self.state.project else []
        self.hw_lbl.setText("Hardware rilevato: " + (", ".join(hw) if hw else "nessuno (si usa la CPU)"))
        self.run_estimate()

    def _range(self):
        st = self.state
        return st.trim_start, st.trim_end

    def run_estimate(self):
        st = self.state
        if not st.project or not st.clips or not self.isVisible():
            return
        if self.est_worker and self.est_worker.isRunning():
            self._est_dirty = True
            self.est_worker.cancel()
            return
        t0, t1 = self._range()
        spec = RenderSpec.from_dict(st.spec.to_dict())
        proj = copy.deepcopy(st.project)
        corr = st.settings.data.get("estimator_corr", {})
        self._est_dirty = False
        self.est_worker = Worker(lambda c, r: ee.estimate(proj, st.clips, spec, t0, t1, corr, st.sample_cache, c))
        self.est_worker.finished_ok.connect(self._est_done)
        self.est_worker.failed.connect(lambda m: self.est_lbl.setText(f"Stima non disponibile: {m}"))
        self.est_worker.finished.connect(lambda: self.run_estimate() if self._est_dirty else None)
        self.est_worker.start()

    def _est_done(self, est: ee.Estimate):
        self.est = est
        st = self.state
        t0, t1 = self._range()
        txt = f"Tempo: <b>{est.time_text}</b><br>Dimensione: <b>{est.size_text}</b>"
        if est.approximate:
            txt += " <i>(stima approssimativa)</i>"
        if est.speed_x:
            txt += f"<br>Velocità misurata sul campione: {est.speed_x:.1f}× il tempo reale"
        self.est_lbl.setText(txt)
        warns = list(ee.decide(st.spec, st.clips).warnings) + est.notes
        W, H = output_size(st.spec.image, st.spec.export)
        out_dir = Path(self.dir_edit.text() or ".")
        try:
            warns += ee.check_space(out_dir, est.size.high, st.spec, 0, W, H)
        except OSError:
            pass
        self.warn_lbl.setText("\n".join("⚠ " + w for w in warns))

    # --- anteprima 10 s
    def preview_sample(self):
        st = self.state
        if not st.project:
            return
        spec = RenderSpec.from_dict(st.spec.to_dict())
        proj = copy.deepcopy(st.project)
        start = st.from_out(self.prev_start.value())
        out = paths.temp_dir() / f"preview_{int(time.time())}.mp4"
        self.prog_lbl.setText("Creazione dell'anteprima di 10 s con tutti gli effetti…")
        self.run_worker = Worker(lambda c, r: (ee.render_sample(proj, st.clips, spec, start, 10.0, out, c), out)[1])
        self.run_worker.finished_ok.connect(self._show_preview)
        self.run_worker.failed.connect(lambda m: QMessageBox.warning(self, "ConfMerge", m))
        self.run_worker.start()

    def _show_preview(self, path):
        self.prog_lbl.setText("")
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
        st = self.state
        if not st.project:
            return
        out_dir = Path(self.dir_edit.text() or ".")
        ThumbnailDialog(st, out_dir, self.name_edit.text() or "conferenza", self.review.player.position, self).exec()

    # --- coda
    def enqueue(self, run_now: bool):
        st = self.state
        if not st.project:
            return
        spec = RenderSpec.from_dict(st.spec.to_dict())
        proj = copy.deepcopy(st.project)
        dec = ee.decide(spec, st.clips)
        force = None
        if dec.credit_conflict:
            m = QMessageBox(self)
            m.setWindowTitle("Credito finale")
            m.setText("Con la copia stream il credito «Created with ConfMerge» non può essere aggiunto.")
            b1 = m.addButton("Disattiva il credito (copia stream)", QMessageBox.AcceptRole)
            b2 = m.addButton("Ricodifica con il credito", QMessageBox.ActionRole)
            m.addButton("Annulla", QMessageBox.RejectRole)
            m.exec()
            if m.clickedButton() is b1:
                spec.credit.enabled = False
            elif m.clickedButton() is b2:
                spec.export.preset = "YouTube 1080p"
            else:
                return
        out_dir = Path(spec.export.out_dir or Path(proj.clips[0]).parent)
        name = (spec.export.name or "conferenza").strip() or "conferenza"
        out = out_dir / f"{name}.mp4"
        n = 1
        while out.exists() or any(it.name == out.name for it in st.queue.items if it.status not in (DONE, FAILED)):
            n += 1
            out = out_dir / f"{name}_{n}.mp4"
        t0, t1 = self._range()
        est = self.est
        W, H = output_size(spec.image, spec.export)
        sp = ee.check_space(out_dir, est.size.high if est else 0, spec, 0, W, H)
        if sp and QMessageBox.question(self, "Spazio su disco", "\n".join(sp) + "\n\nContinuare comunque?") != QMessageBox.Yes:
            return
        clips = list(st.clips)
        key = id(spec)
        self._est_mid[key] = (est.time_lo + est.time_hi) / 2 if est else 0.0

        def job(cancel, prog, spec=spec, proj=proj, out=out, t0=t0, t1=t1, key=key):
            rep = ee.run_export(proj, clips, spec, out, t0, t1, prog, cancel)
            self._reports[key] = rep

        item = QueueItem(out.name, job, est.time_text + " · " + est.size_text if est else "")
        item.key = key  # type: ignore[attr-defined]
        st.queue.add(item)
        self.refresh_queue()
        if run_now:
            self.start_queue()

    def refresh_queue(self):
        q = self.state.queue
        self.table.setRowCount(len(q.items))
        for r, it in enumerate(q.items):
            for c, v in enumerate((it.name, it.estimate, it.status + (f": {it.error[:60]}" if it.error else ""), f"{it.progress * 100:.0f}")):
                self.table.setItem(r, c, QTableWidgetItem(v))
        cur = self._current_item
        if cur and cur.status == "in corso":
            self.bar.setValue(int(cur.progress * 1000))
            self.speed.add(time.time(), cur.progress)
            rem = self.speed.remaining(cur.progress)
            out = Path(self.state.spec.export.out_dir or ".") / cur.name
            size = out.stat().st_size if out.exists() else 0
            self.prog_lbl.setText(f"{cur.name}: {cur.progress * 100:.0f}% — residuo "
                                  + (_fmt_dur(rem) if rem is not None else "in calcolo…")
                                  + f" — file attuale {size / 1e6:.0f} MB")

    def move(self, d: int):
        r = self.table.currentRow()
        self.state.queue.move(r, d)
        self.refresh_queue()
        self.table.selectRow(max(0, min(r + d, len(self.state.queue.items) - 1)))

    def cancel_item(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.state.queue.items):
            self.state.queue.cancel(r)
            self.refresh_queue()

    def start_queue(self):
        if self.run_worker and self.run_worker.isRunning():
            return
        q = self.state.queue

        def job(cancel, report):
            while True:
                it = q.next_pending()
                if it is None:
                    break
                self._current_item = it
                self._t_start = time.time()
                self.speed = estimator.MovingSpeed()
                q.run_next()
                self._after_item(it)

        self.run_worker = Worker(job)
        self.run_worker.finished.connect(self._queue_done)
        self.ui_timer.start()
        self.run_worker.start()

    def _after_item(self, it: QueueItem):
        key = getattr(it, "key", None)
        rep = self._reports.get(key)
        if rep and rep.mode != "copy" and self._est_mid.get(key):
            estimator.update_correction(self.state.settings.data.setdefault("estimator_corr", {}), rep.encoder,
                                        self._est_mid[key], rep.wall_s)
            self.state.settings.save()

    def _queue_done(self):
        self.ui_timer.stop()
        self.refresh_queue()
        self.bar.setValue(1000 if self._current_item and self._current_item.status == DONE else self.bar.value())
        done = [it for it in self.state.queue.items if it.status == DONE]
        lines = []
        for it in done[-3:]:
            rep = self._reports.get(getattr(it, "key", None))
            if rep:
                lines.append(f"{it.name}: {_fmt_dur(rep.wall_s)} ({rep.wall_s:.0f} s), {rep.size_bytes / 1e6:.0f} MB, {rep.encoder}")
                if rep.loud_before and rep.loud_after:
                    self.loud_lbl.setText(f"Loudness: {rep.loud_before['input_i']:.1f} LUFS → {rep.loud_after['input_i']:.1f} LUFS "
                                          f"(picco {rep.loud_after['input_tp']:.1f} dBTP)")
                for n in rep.notes:
                    lines.append("  • " + n)
        est = self.est
        txt = "\n".join(lines)
        if est and lines:
            txt += f"\n\nStima: {est.time_text}, {est.size_text}"
        failed = [it for it in self.state.queue.items if it.status == FAILED]
        if failed:
            QMessageBox.critical(self, "Export non riuscito", "\n".join(f"{i.name}: {i.error}" for i in failed))
        elif txt:
            QMessageBox.information(self, "Export completato", txt)
        self.prog_lbl.setText("Completato." if done else "")
        self._power_action()

    def _power_action(self):
        choice = self.after.currentIndex()
        if choice == 0 or sys.platform != "win32":
            return
        if QMessageBox.question(self, "ConfMerge", "Il PC si spegnerà/sospenderà tra 60 secondi. Annullare?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            return
        if choice == 1:
            subprocess.Popen(["shutdown", "/s", "/t", "30"])
        else:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
