"""Chiavi API dell'utente (es. Groq), salvate nel profilo Windows dell'utente.

Su Windows la chiave è cifrata con DPAPI (può leggerla solo lo stesso utente, sullo stesso computer); altrove, o se la
cifratura non è disponibile, resta in chiaro nel file `keys.json` della cartella delle impostazioni. Il file è separato
da `settings.json` e dai profili, così una chiave non finisce mai in un profilo esportato."""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

ENV_VARS = {"groq": "GROQ_API_KEY"}


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    dst = Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dst)):
        raise OSError("DPAPI non disponibile")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(dst.pbData)


class KeyStore:
    def __init__(self, root: Path):
        self.file = Path(root) / "keys.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _encode(self, value: str) -> str:
        raw = value.encode("utf-8")
        if sys.platform == "win32":
            try:
                return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
            except Exception:  # noqa: BLE001 - se la cifratura fallisce si salva in chiaro, meglio che perdere la chiave
                log.warning("DPAPI non riuscita: la chiave resta in chiaro", exc_info=True)
        return "plain:" + base64.b64encode(raw).decode()

    def _decode(self, stored: str) -> str:
        kind, _, payload = stored.partition(":")
        try:
            raw = base64.b64decode(payload)
            return (_dpapi(raw, False) if kind == "dpapi" else raw).decode("utf-8")
        except Exception:  # noqa: BLE001
            log.warning("Chiave non leggibile (%s)", kind, exc_info=True)
            return ""

    def get(self, name: str) -> str:
        v = self._load().get(name)
        if v:
            key = self._decode(v)
            if key:
                return key
        return os.environ.get(ENV_VARS.get(name, ""), "").strip()

    def has(self, name: str) -> bool:
        return bool(self.get(name))

    def set(self, name: str, value: str) -> None:
        data = self._load()
        value = value.strip()
        if value:
            data[name] = self._encode(value)
        else:
            data.pop(name, None)
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if sys.platform != "win32":
            try:
                os.chmod(self.file, 0o600)
            except OSError:
                pass


def masked(key: str) -> str:
    """Per mostrare «gsk_…a1b2» senza rivelare la chiave."""
    return "" if not key else (key[:4] + "…" + key[-4:] if len(key) > 10 else "…")
