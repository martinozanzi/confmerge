"""Controllo degli aggiornamenti: chiede a GitHub l'ultima release e dice dove scaricare il file compilato.

Nessun dato dell'utente viene inviato: è una semplice lettura di `releases/latest` (pubblica, senza chiave)."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import REPO_URL, __version__

API_URL = "https://api.github.com/repos/martinozanzi/confmerge/releases/latest"
PREFERRED_ASSETS = ("ConfMerge.exe", "ConfMerge-cartella.zip")


log = logging.getLogger(__name__)


def log_error(e: Exception) -> None:
    log.warning("Controllo aggiornamenti: %s", e)


class UpdateError(Exception):
    """Errore con messaggio già adatto all'utente."""


@dataclass
class Release:
    tag: str
    version: tuple[int, ...]
    page: str                  # pagina della release su GitHub (note e file)
    download: str              # collegamento diretto al file compilato (o la pagina, se non c'è)
    notes: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    """«v1.2.0» → (1, 2, 0); le parti non numeriche si ignorano. Vuoto se non è una versione."""
    return tuple(int(n) for n in re.findall(r"\d+", text.split("-")[0])[:4])


def is_newer(latest: tuple[int, ...], current: tuple[int, ...] | None = None) -> bool:
    cur = current if current is not None else parse_version(__version__)
    pad = max(len(latest), len(cur))
    return bool(latest) and latest + (0,) * (pad - len(latest)) > cur + (0,) * (pad - len(cur))


def latest_release(url: str | None = None, timeout: float = 10.0) -> Release | None:
    """L'ultima release pubblicata (None se il progetto non ne ha ancora). Solleva UpdateError se la rete non va."""
    req = urllib.request.Request(url or API_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"ConfMerge/{__version__} (+{REPO_URL})"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise UpdateError("GitHub non ha risposto come previsto. Riprova più tardi.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("Non riesco a collegarmi a internet per cercare gli aggiornamenti.") from e
    except ValueError as e:
        raise UpdateError("Risposta di GitHub non comprensibile.") from e
    tag = str(data.get("tag_name") or "")
    ver = parse_version(tag)
    if not ver:
        return None
    page = data.get("html_url") or REPO_URL + "/releases"
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets") or []}
    download = next((assets[n] for n in PREFERRED_ASSETS if assets.get(n)), page)
    return Release(tag, ver, page, download, str(data.get("body") or ""))


def check() -> Release | None:
    """La release più nuova di quella in uso, oppure None se si è già aggiornati."""
    rel = latest_release()
    return rel if rel and is_newer(rel.version) else None
