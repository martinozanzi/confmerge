"""Impostazioni e profili con nome, salvati in JSON (%APPDATA%\\ConfMerge)."""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

def default_profile() -> dict:
    from .profiles import profile_from_spec
    from .spec import RenderSpec
    return profile_from_spec(RenderSpec())


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    p = Path(base) / "ConfMerge"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "profilo"


class Settings:
    """settings.json + profili in profiles/*.json."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else config_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "profiles").mkdir(exist_ok=True)
        self.file = self.root / "settings.json"
        self.data: dict = {"last_folder": "", "current_profile": "Predefinito", "estimator_corr": {}}
        if self.file.exists():
            try:
                self.data.update(json.loads(self.file.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def save(self) -> None:
        self.file.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    # profili
    def _pfile(self, name: str) -> Path:
        return self.root / "profiles" / f"{_safe(name)}.json"

    def list_profiles(self) -> list[str]:
        names = []
        for f in sorted((self.root / "profiles").glob("*.json")):
            try:
                names.append(json.loads(f.read_text(encoding="utf-8")).get("name", f.stem))
            except (OSError, ValueError):
                continue
        return names or ["Predefinito"]

    def load_profile(self, name: str) -> dict:
        base = default_profile()
        f = self._pfile(name)
        if f.exists():
            try:
                stored = json.loads(f.read_text(encoding="utf-8"))
                for k, v in stored.get("profile", {}).items():
                    if isinstance(v, dict) and isinstance(base.get(k), dict):
                        base[k].update(v)
                    else:
                        base[k] = v
            except (OSError, ValueError):
                pass
        return base

    def save_profile(self, name: str, profile: dict) -> None:
        self._pfile(name).write_text(
            json.dumps({"name": name, "profile": profile}, indent=2, ensure_ascii=False), encoding="utf-8")

    def duplicate_profile(self, name: str, new_name: str) -> None:
        self.save_profile(new_name, copy.deepcopy(self.load_profile(name)))

    def delete_profile(self, name: str) -> None:
        self._pfile(name).unlink(missing_ok=True)

    def export_profile(self, name: str, dest: str | Path) -> None:
        Path(dest).write_text(self._pfile(name).read_text(encoding="utf-8"), encoding="utf-8")

    def import_profile(self, src: str | Path) -> str:
        obj = json.loads(Path(src).read_text(encoding="utf-8"))
        if "profile" not in obj or "name" not in obj:
            raise ValueError("File profilo non valido")
        self.save_profile(obj["name"], obj["profile"])
        return obj["name"]
