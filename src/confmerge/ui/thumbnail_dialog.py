"""Miniatura YouTube: scelta del fotogramma, grafica con lo stesso editor, export JPG (<2 MB) e PNG 1280×720."""
from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout)

from .. import paths, thumbnail
from ..ffmpeg_wrapper import FFmpegError
from ..render.model import Background, Element, Scene
from .canvas import Canvas
from .element_editor import ElementEditor
from .graphics_page import new_element


class ThumbnailDialog(QDialog):
    def __init__(self, state, out_dir: Path, name: str, pos_fn, parent=None):
        super().__init__(parent)
        self.state, self.out_dir, self.name, self.pos_fn = state, out_dir, name, pos_fn
        self.setWindowTitle("Miniatura")
        self.resize(1100, 700)
        pr = state.project
        saved = pr.thumbnail if pr else {}
        self.elements = [Element.from_dict(e) for e in saved.get("elements", [])]
        self.t = saved.get("t", (state.trim_start + state.trim_end) / 2 if pr else 0.0)
        self.scene = Scene(True, 1.0, Background("transparent"), self.elements)
        self.frame_full = None

        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.cands = QListWidget()
        self.cands.setViewMode(QListWidget.IconMode)
        self.cands.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(160, 90))
        self.cands.setFixedHeight(130)
        self.cands.setFlow(QListWidget.LeftToRight)
        self.cands.setWrapping(False)
        self.cands.itemClicked.connect(lambda it: self.set_time(it.data(Qt.UserRole)))
        left.addWidget(QLabel("Fotogrammi proposti (equidistanti) — oppure usa la posizione corrente della Revisione"))
        left.addWidget(self.cands)
        self.canvas = Canvas(state)
        self.canvas.mode, self.canvas.scene, self.canvas.fixed_size = "scene", self.scene, (1280, 720)
        self.canvas.scene_target = "thumb"
        self.canvas.elementMoved.connect(lambda *_: None)
        self.canvas.elementPicked.connect(self.pick_list)
        left.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        for text, fn in (("Fotogramma corrente del player", self.use_current), ("+ Testo", lambda: self.add("text")),
                         ("+ Immagine", lambda: self.add("image")), ("+ Forma", lambda: self.add("shape")),
                         ("Elimina", self.delete), ("💾 Esporta JPG + PNG", self.export)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        lay.addLayout(left, 3)
        right = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.pick)
        right.addWidget(self.list, 1)
        self.editor = ElementEditor()
        self.editor.changed.connect(self.canvas.update)
        right.addWidget(self.editor, 4)
        lay.addLayout(right, 2)
        self.refresh()
        self.fill_candidates()
        self.set_time(self.t)

    def fill_candidates(self):
        st = self.state
        if not st.proxy or not st.project:
            return
        for t in thumbnail.suggest_times(st.trim_start, st.trim_end):
            try:
                img = thumbnail.grab_frame(st.proxy, t, paths.temp_dir() / f"cand_{int(t)}.png", 320)
            except FFmpegError:
                continue
            it = QListWidgetItem(QIcon(QPixmap.fromImage(img)), f"{t:.0f} s")
            it.setData(Qt.UserRole, t)
            self.cands.addItem(it)

    def use_current(self):
        self.set_time(self.pos_fn())

    def set_time(self, t: float):
        self.t = t
        st = self.state
        try:
            clip, local = thumbnail.locate(st.clips, t)
            self.frame_full = thumbnail.grab_frame(clip.path, local, paths.temp_dir() / "thumb_frame.png")
        except (FFmpegError, IndexError):
            self.frame_full = st.last_frame
        self.canvas.set_frame(self.frame_full)
        self.canvas.update()

    def refresh(self):
        self.list.clear()
        for e in self.elements:
            self.list.addItem(e.text[:28] if e.kind == "text" else e.kind)

    def pick(self, i: int):
        self.editor.frame_wh = (1280, 720)
        self.editor.set_element(self.elements[i] if 0 <= i < len(self.elements) else None)
        self.canvas.selected = i
        self.canvas.update()

    def pick_list(self, i: int):
        if i >= 0:
            self.list.setCurrentRow(i)

    def add(self, kind: str):
        el = new_element(kind, self.state.settings.data.get("font", "Segoe UI"))
        el.targets = ["main"]
        if kind == "text":
            el.size, el.bold, el.text = 0.12, True, "TITOLO"
            el.outline.width = 0.006
        if kind == "image":
            from PySide6.QtWidgets import QFileDialog
            p, _ = QFileDialog.getOpenFileName(self, "Immagine", "", "Immagini (*.png *.svg *.jpg)")
            if not p:
                return
            el.path = p
        self.elements.append(el)
        self.refresh()
        self.list.setCurrentRow(len(self.elements) - 1)

    def delete(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.elements[i]
            self.refresh()
            self.canvas.update()

    def _save_state(self):
        if self.state.project:
            self.state.project.thumbnail = {"t": self.t, "elements": [e.to_dict() for e in self.elements]}

    def export(self):
        if self.frame_full is None:
            return
        img = thumbnail.compose(self.frame_full, self.elements)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        jpg, png = self.out_dir / f"{self.name}_miniatura.jpg", self.out_dir / f"{self.name}_miniatura.png"
        try:
            size = thumbnail.save_jpg_under_limit(img, jpg)
            img.save(str(png), "PNG")
        except FFmpegError as e:
            QMessageBox.warning(self, "ConfMerge", str(e))
            return
        self._save_state()
        QMessageBox.information(self, "ConfMerge", f"Miniature salvate:\n{jpg} ({size / 1e6:.2f} MB)\n{png}")
