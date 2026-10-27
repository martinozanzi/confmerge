"""Modelli di stile per Studio Social: sottotitoli (tipo, grandezza, posizione), loghi, testi e immagini sul video.

Si salva lo stile di un lavoro con un nome (es. «Reel del sindaco») e lo si riapplica con un clic ad altri lavori.
Non contiene il testo dei sottotitoli né il montaggio: solo l'aspetto."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .render.model import Element
from .serde import from_dict, to_dict
from .spec import BrandSettings, RenderSpec, SubtitleSettings

STYLE_KEYS = ("lines", "range_start", "range_end")


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "modello"


def capture(spec: RenderSpec) -> dict:
    return {
        "subtitles": {k: v for k, v in to_dict(spec.subtitles).items() if k not in STYLE_KEYS},
        "brand": {**to_dict(spec.brand), "safe": []},
        "elements": [e.to_dict() for e in spec.graphics.elements if "main" in e.targets],
    }


def apply(spec: RenderSpec, data: dict) -> None:
    """Applica lo stile al lavoro: sottotitoli (resta il loro testo), loghi, testi e immagini sul video."""
    if data.get("subtitles"):
        old = spec.subtitles
        spec.subtitles = from_dict(SubtitleSettings, data["subtitles"])
        spec.subtitles.lines, spec.subtitles.range_start, spec.subtitles.range_end = old.lines, old.range_start, old.range_end
        spec.subtitles.enabled = True
    if "brand" in data:
        safe = spec.brand.safe
        spec.brand = from_dict(BrandSettings, data["brand"])
        spec.brand.safe = safe
    if "elements" in data:
        others = [e for e in spec.graphics.elements if "main" not in e.targets]
        spec.graphics.elements = [Element.from_dict(copy.deepcopy(d)) for d in data["elements"]] + others


class StyleStore:
    def __init__(self, root: Path):
        self.dir = Path(root) / "modelli_stile"

    def list(self) -> list[str]:
        if not self.dir.exists():
            return []
        out = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")).get("name", f.stem))
            except (OSError, ValueError):
                continue
        return sorted(out, key=str.lower)

    def _file(self, name: str) -> Path:
        return self.dir / f"{_safe(name)}.json"

    def save(self, name: str, spec: RenderSpec) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file(name).with_suffix(".tmp")
        tmp.write_text(json.dumps({"name": name, "style": capture(spec)}, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._file(name))

    def load(self, name: str) -> dict | None:
        try:
            return json.loads(self._file(name).read_text(encoding="utf-8")).get("style")
        except (OSError, ValueError):
            return None

    def delete(self, name: str) -> None:
        self._file(name).unlink(missing_ok=True)
