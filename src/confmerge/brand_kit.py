"""Kit del marchio: colori, caratteri, slogan e loghi di un soggetto (un'associazione, un partito, un candidato…).

Se ne possono avere quanti si vuole. Ogni kit sta in una cartella `marchi/<id>/` nelle impostazioni, con una copia dei suoi
loghi: se il file originale viene spostato, il kit continua a funzionare. Applicare un kit a un lavoro copia nella spec
(`spec.brand`, sottotitoli, nomi dei relatori) i valori che servono: il video si ricostruisce anche senza l'archivio."""
from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from .serde import from_dict

ROLES = {"main": "Logo principale", "symbol": "Simbolo del partito o del movimento", "square": "Logo quadrato",
         "wide": "Logo orizzontale", "other": "Altro"}
CORNERS = {"tl": "In alto a sinistra", "tr": "In alto a destra", "bl": "In basso a sinistra", "br": "In basso a destra"}
COLOR_NAMES = {"primary": "Principale", "secondary": "Secondario", "accent": "Evidenza", "text": "Testo", "background": "Sfondo"}
LOGO_EXT = {".png", ".svg", ".jpg", ".jpeg", ".webp"}


@dataclass
class KitColors:
    primary: str = "#1D4ED8"
    secondary: str = "#0F172A"
    accent: str = "#FACC15"
    text: str = "#FFFFFF"
    background: str = "#0B1220"


@dataclass
class KitLogo:
    name: str = ""
    file: str = ""                     # nome del file dentro la cartella `logos` del kit
    role: str = "main"


@dataclass
class BrandKit:
    id: str = ""
    name: str = "Nuovo marchio"
    colors: KitColors = field(default_factory=KitColors)
    font_title: str = "Poppins"
    font_body: str = "Inter"
    slogan: str = ""
    social: str = ""                   # es. @nomecanale
    logos: list[KitLogo] = field(default_factory=list)
    caption_style: str = "box"         # box (sfondo del colore principale) | outline (bordo scuro)
    main_corner: str = "tr"
    symbol_corner: str = "tl"
    logo_size: float = 0.11            # larghezza del logo, frazione della larghezza del video

    def logo(self, role: str) -> KitLogo | None:
        return next((lg for lg in self.logos if lg.role == role), None)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "marchio"


class KitStore:
    """Archivio dei kit (una cartella per kit)."""

    def __init__(self, root: Path):
        self.dir = Path(root) / "marchi"

    def _kit_dir(self, kid: str) -> Path:
        return self.dir / kid

    def list(self) -> list[BrandKit]:
        out = []
        for f in sorted(self.dir.glob("*/kit.json")) if self.dir.exists() else []:
            try:
                out.append(from_dict(BrandKit, json.loads(f.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError):
                continue
        return sorted(out, key=lambda k: k.name.lower())

    def get(self, kid: str) -> BrandKit | None:
        f = self._kit_dir(kid) / "kit.json"
        try:
            return from_dict(BrandKit, json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def save(self, kit: BrandKit) -> None:
        if not kit.id:
            kit.id = f"{_slug(kit.name)}-{uuid.uuid4().hex[:6]}"
        d = self._kit_dir(kit.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "kit.json.tmp"
        tmp.write_text(json.dumps(asdict(kit), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / "kit.json")

    def new(self, name: str = "Nuovo marchio") -> BrandKit:
        kit = BrandKit(name=name)
        self.save(kit)
        return kit

    def duplicate(self, kid: str, name: str = "") -> BrandKit | None:
        src = self.get(kid)
        if src is None:
            return None
        kit = from_dict(BrandKit, asdict(src))
        kit.id, kit.name = "", name or f"{src.name} (copia)"
        self.save(kit)
        if (self._kit_dir(kid) / "logos").exists():
            shutil.copytree(self._kit_dir(kid) / "logos", self._kit_dir(kit.id) / "logos", dirs_exist_ok=True)
        return kit

    def delete(self, kid: str) -> None:
        shutil.rmtree(self._kit_dir(kid), ignore_errors=True)

    # --- loghi
    def add_logo(self, kit: BrandKit, src: str | Path, name: str = "", role: str = "main") -> KitLogo:
        src = Path(src)
        if src.suffix.lower() not in LOGO_EXT:
            raise ValueError("Il logo deve essere un'immagine PNG, SVG, JPG o WEBP (meglio PNG con sfondo trasparente).")
        d = self._kit_dir(kit.id) / "logos"
        d.mkdir(parents=True, exist_ok=True)
        target = d / f"{_slug(name or src.stem)}-{uuid.uuid4().hex[:4]}{src.suffix.lower()}"
        shutil.copyfile(src, target)
        logo = KitLogo(name or src.stem, target.name, role)
        kit.logos.append(logo)
        self.save(kit)
        return logo

    def remove_logo(self, kit: BrandKit, logo: KitLogo) -> None:
        (self._kit_dir(kit.id) / "logos" / logo.file).unlink(missing_ok=True)
        kit.logos = [lg for lg in kit.logos if lg is not logo and lg.file != logo.file]
        self.save(kit)
        logo_size.cache_clear()

    def logo_path(self, kit: BrandKit, logo: KitLogo | None) -> str:
        if logo is None:
            return ""
        p = self._kit_dir(kit.id) / "logos" / logo.file
        return str(p) if p.exists() else ""

    # --- condivisione (un file .zip da dare a un collega)
    def export_zip(self, kid: str, dest: str | Path) -> None:
        d = self._kit_dir(kid)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for f in d.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(d).as_posix())

    def import_zip(self, src: str | Path) -> BrandKit:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if "kit.json" not in names:
                raise ValueError("Questo file non è un kit del marchio.")
            kit = from_dict(BrandKit, json.loads(z.read("kit.json").decode("utf-8")))
            kit.id = ""
            self.save(kit)
            d = self._kit_dir(kit.id)
            for n in names:
                if n.startswith("logos/") and not n.endswith("/") and ".." not in n:
                    (d / n).parent.mkdir(parents=True, exist_ok=True)
                    (d / n).write_bytes(z.read(n))
        return kit


@lru_cache(maxsize=64)
def logo_size(path: str) -> tuple[int, int]:
    """Dimensioni (larghezza, altezza) di un logo; (0, 0) se non si legge."""
    from PySide6.QtGui import QImageReader
    s = QImageReader(path).size()
    return (s.width(), s.height()) if s.isValid() else (0, 0)


def contrast_color(hex_color: str) -> str:
    """Bianco o nero, a seconda di quale si legge meglio sul colore dato."""
    c = hex_color.lstrip("#")
    if len(c) != 6:
        return "#FFFFFF"
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#FFFFFF"
