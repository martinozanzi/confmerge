"""Overlay salvati: un testo, un'immagine o un overlay animato (anche con sfondo trasparente) con il suo aspetto,
da riusare in altri lavori con un clic. Il file dell'immagine si copia nella raccolta: resta anche se l'originale si sposta."""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from .render.model import Element


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "overlay"


class OverlayLibrary:
    def __init__(self, root: Path):
        self.dir = Path(root) / "overlay_salvati"

    def _file(self, name: str) -> Path:
        return self.dir / f"{_safe(name)}.json"

    def list(self) -> list[str]:
        out = []
        for f in sorted(self.dir.glob("*.json")) if self.dir.exists() else []:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")).get("name", f.stem))
            except (OSError, ValueError):
                continue
        return sorted(out, key=str.lower)

    def save(self, name: str, el: Element) -> None:
        d = el.to_dict()
        self.dir.mkdir(parents=True, exist_ok=True)
        if d.get("path") and Path(d["path"]).exists():
            assets = self.dir / "file"
            assets.mkdir(exist_ok=True)
            target = assets / f"{_safe(name)}{Path(d['path']).suffix.lower()}"
            if Path(d["path"]).resolve() != target.resolve():
                shutil.copy2(d["path"], target)
            d["path"] = str(target)
        tmp = self._file(name).with_suffix(".tmp")
        tmp.write_text(json.dumps({"name": name, "element": d}, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._file(name))

    def load(self, name: str) -> Element | None:
        try:
            d = json.loads(self._file(name).read_text(encoding="utf-8"))["element"]
        except (OSError, ValueError, KeyError):
            return None
        d["id"] = uuid.uuid4().hex[:6]
        d["targets"] = ["main"]
        return Element.from_dict(d)

    def delete(self, name: str) -> None:
        f = self._file(name)
        try:
            path = json.loads(f.read_text(encoding="utf-8"))["element"].get("path", "")
        except (OSError, ValueError, KeyError):
            path = ""
        f.unlink(missing_ok=True)
        if path and Path(path).parent == self.dir / "file":
            Path(path).unlink(missing_ok=True)
