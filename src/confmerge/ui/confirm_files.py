"""«Conferma i file»: prima di preparare il lavoro si vedono i video, l'audio e le slide trovati e si tolgono quelli che non c'entrano."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFileInfo, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from .widgets import GhostButton, PrimaryButton, Segmented, label

KINDS = [("Conferenza (video + audio a parte)", "merge"), ("Video social (audio nei video)", "social")]


def _size_text(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{max(1, n // 1000)} kB"


class ConfirmFilesDialog(QDialog):
    def __init__(self, det, kind: str, parent=None):
        super().__init__(parent)
        self.det = det
        self.setWindowTitle("Conferma i file")
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        where = f" in «{det.folder.name}»" if det.folder else ""
        lay.addWidget(label(f"Ho trovato questi file{where}", "h2"))
        lay.addWidget(label("Togli la spunta a quelli che non c'entrano: verranno ignorati. Se il tipo di lavoro non è giusto, cambialo qui sotto.",
                            "caption", True))
        self.seg = Segmented(KINDS)
        self.seg.setValue(kind)
        self.seg.changed.connect(self._kind_changed)
        lay.addWidget(self.seg)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(280)
        lay.addWidget(self.tree, 1)
        self.groups: dict[str, QTreeWidgetItem] = {}
        parts = {p.resolve() for p in det.audios}
        self._add_group("video", "Video", det.videos, set(det.videos))
        self._add_group("audio", "Registrazione audio", det.all_audios or det.audios, parts or set(det.all_audios))
        self._add_group("slides", "Slide", det.all_slides, set(det.all_slides))
        self.tree.expandAll()
        self.tree.itemChanged.connect(lambda *_: self._refresh())
        self.summary = label("", "caption", True)
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = GhostButton("Annulla")
        cancel.clicked.connect(self.reject)
        self.ok = PrimaryButton("Continua", "chevron-right")
        self.ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self._kind_changed(kind)

    def _add_group(self, key: str, title: str, files: list[Path], checked: set) -> None:
        if not files:
            return
        top = QTreeWidgetItem(self.tree, [title])
        top.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
        self.groups[key] = top
        use = {Path(p).resolve() for p in checked}
        for f in files:
            info = QFileInfo(str(f))
            when = datetime.fromtimestamp(info.lastModified().toSecsSinceEpoch()).strftime("%d/%m/%Y %H:%M")
            it = QTreeWidgetItem(top, [f"{f.name}    ·    {_size_text(info.size())}    ·    {when}"])
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            it.setCheckState(0, Qt.Checked if Path(f).resolve() in use else Qt.Unchecked)
            it.setData(0, Qt.UserRole, str(f))
            it.setToolTip(0, str(f))

    def kind(self) -> str:
        return self.seg.value()

    def _checked(self, key: str) -> list[Path]:
        top = self.groups.get(key)
        if top is None:
            return []
        return [Path(top.child(i).data(0, Qt.UserRole)) for i in range(top.childCount())
                if top.child(i).checkState(0) == Qt.Checked]

    def selected_paths(self) -> list[Path]:
        """I file confermati: i video; con «conferenza» anche l'audio e le slide."""
        out = self._checked("video")
        if self.kind() == "merge":
            out += self._checked("audio") + self._checked("slides")
        return out

    def _kind_changed(self, kind) -> None:
        merge = kind == "merge"
        for key in ("audio", "slides"):                       # per un video social l'audio sta nei video: il resto non si usa
            if key in self.groups:
                self.groups[key].setDisabled(not merge)
        self._refresh()

    def _refresh(self) -> None:
        v, a, s = len(self._checked("video")), len(self._checked("audio")), len(self._checked("slides"))
        merge = self.kind() == "merge"
        txt = f"{v} video" + (f", {a} file audio, {s} slide" if merge else "") + " selezionati."
        if merge and a == 0:
            txt += " Senza audio dovrai sceglierlo dopo."
        self.summary.setText(txt)
        self.ok.setEnabled(v > 0)
