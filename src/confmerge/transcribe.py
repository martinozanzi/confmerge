"""Trascrizione con Groq (Whisper large-v3-turbo): audio a pezzi, tempi per parola, errori in italiano.

Usa solo la libreria standard (nessun pacchetto in più, quindi nessun problema con Python 3.14). L'audio viene tagliato
in pezzi da pochi minuti nei punti più silenziosi: ogni pezzo è un invio piccolo, si vede l'avanzamento e un errore
costringe a rifare un solo pezzo."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import ffmpeg_wrapper as fw

log = logging.getLogger(__name__)

BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "whisper-large-v3-turbo"
INSTRUCTIONS_URL = "https://console.groq.com/keys"
USER_AGENT = "ConfMerge/1.0 (+https://github.com/martinozanzi/confmerge)"
CHUNK_S = 300.0                        # circa 5 minuti per invio
MIN_BILLED_S = 10.0                    # Groq fattura almeno 10 secondi per richiesta
COST_PER_HOUR = 0.04                   # dollari, indicativo (da verificare sul sito di Groq)
HALLUCINATIONS = ("sottotitoli creati dalla comunità", "sottotitoli e revisione a cura di", "amara.org",
                  "grazie per la visione", "iscriviti al canale")


class TranscribeError(Exception):
    """Errore con un messaggio già adatto all'utente."""


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Line:
    start: float
    end: float
    text: str


def estimate_cost(seconds: float) -> float:
    return max(seconds, MIN_BILLED_S) / 3600.0 * COST_PER_HOUR


# ------------------------------------------------------------------------------------------------ rete
def _friendly(code: int, body: str) -> str:
    if code in (401, 403):
        return "La chiave di Groq non è valida o è stata revocata. Controllala nelle Impostazioni."
    if code == 429:
        return "Groq ha ricevuto troppe richieste o hai finito il credito gratuito. Riprova tra poco."
    if code == 413:
        return "Il file audio è troppo grande per Groq."
    if code == 400:
        return "Groq non ha accettato l'audio: " + body[:200]
    if code >= 500:
        return "Il servizio di Groq non risponde in questo momento. Riprova più tardi."
    return f"Groq ha risposto con un errore ({code})."


def _call(req: urllib.request.Request, timeout: float = 180.0, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                try:
                    wait = float(e.headers.get("Retry-After", ""))
                except (TypeError, ValueError):
                    wait = 2.0 * (attempt + 1)
                time.sleep(min(wait, 20.0))
                continue
            log.warning("Groq HTTP %s: %s", e.code, body[:300])
            raise TranscribeError(_friendly(e.code, body)) from None
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            raise TranscribeError("Non riesco a collegarmi a internet. Controlla la connessione.") from e
        except (TimeoutError, OSError) as e:
            if attempt < retries:
                continue
            raise TranscribeError("Groq non ha risposto in tempo. Riprova.") from e
        except ValueError as e:
            raise TranscribeError("Risposta di Groq non comprensibile.") from e
    raise TranscribeError("Groq non ha risposto.")


def _base(base_url: str | None) -> str:
    return base_url or os.environ.get("CONFMERGE_GROQ_URL") or BASE_URL


def check_key(key: str, base_url: str | None = None) -> str:
    """Prova la chiave. Restituisce un messaggio di conferma; solleva TranscribeError se non va."""
    if not key.strip():
        raise TranscribeError("Incolla prima la chiave.")
    req = urllib.request.Request(_base(base_url) + "/models", headers={"Authorization": f"Bearer {key.strip()}",
                                                                 "User-Agent": USER_AGENT})
    data = _call(req, timeout=20.0, retries=0)
    ids = [m.get("id", "") for m in data.get("data", [])]
    if ids and MODEL not in ids:
        return "La chiave funziona, ma il modello di trascrizione non risulta disponibile nel tuo account."
    return "La chiave funziona."


def _multipart(fields: list[tuple[str, str]], file_field: str, filename: str, payload: bytes, ctype: str):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + payload + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def transcribe_chunk(path: Path, key: str, language: str = "it", prompt: str = "", base_url: str | None = None) -> dict:
    fields = [("model", MODEL), ("response_format", "verbose_json"), ("temperature", "0"),
              ("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment")]
    if language:
        fields.append(("language", language))
    if prompt:
        fields.append(("prompt", prompt[:800]))
    body, ctype = _multipart(fields, "file", path.name, path.read_bytes(), "audio/flac")
    req = urllib.request.Request(_base(base_url) + "/audio/transcriptions", data=body, method="POST", headers={
        "Authorization": f"Bearer {key.strip()}", "Content-Type": ctype, "User-Agent": USER_AGENT})
    return _call(req)


# ------------------------------------------------------------------------------------------------ audio
def plan_chunks(samples: np.ndarray, sr: int, target_s: float = CHUNK_S, search_s: float = 20.0) -> list[tuple[float, float]]:
    """Intervalli (inizio, fine) da circa `target_s`, con i tagli nei punti più silenziosi vicino a ogni confine."""
    total = len(samples) / sr
    if total <= target_s * 1.25:
        return [(0.0, total)]
    win = int(0.2 * sr)
    cuts, pos = [0.0], target_s
    while pos < total - target_s * 0.25:
        lo, hi = max(int((pos - search_s) * sr), win), min(int((pos + search_s) * sr), len(samples) - win)
        if hi > lo:
            seg = np.abs(samples[lo:hi]).astype(np.float32)
            energy = np.convolve(seg, np.ones(win, dtype=np.float32) / win, mode="valid")
            pos = (lo + int(np.argmin(energy)) + win // 2) / sr
        cuts.append(pos)
        pos += target_s
    cuts.append(total)
    return list(zip(cuts[:-1], cuts[1:]))


def _cut_flac(wav: Path, start: float, end: float, out: Path) -> None:
    cmd = [fw.ffmpeg_path(), "-v", "error", "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
           "-i", str(wav), "-ac", "1", "-ar", "16000", "-c:a", "flac", str(out)]
    res = subprocess.run(cmd, capture_output=True, creationflags=fw._CREATIONFLAGS)
    if res.returncode != 0 or not out.exists():
        raise TranscribeError("Non riesco a preparare l'audio per la trascrizione.")


# ------------------------------------------------------------------------------------------------ risposta
def _bad_segment(seg: dict) -> bool:
    text = (seg.get("text") or "").strip().lower()
    if not text:
        return True
    if seg.get("no_speech_prob", 0.0) > 0.8 and seg.get("avg_logprob", 0.0) < -0.8:
        return True
    return any(h in text for h in HALLUCINATIONS)


def parse_words(data: dict, offset: float = 0.0) -> list[Word]:
    """Parole con i tempi, dalla risposta `verbose_json`. Senza tempi per parola si ripartiscono quelli della frase."""
    segs = [s for s in data.get("segments") or [] if not _bad_segment(s)]
    spans = [(s.get("start", 0.0), s.get("end", 0.0)) for s in segs]
    words = []
    for w in data.get("words") or []:
        t = (w.get("word") or "").strip()
        if not t:
            continue
        a, b = float(w.get("start", 0.0)), float(w.get("end", 0.0))
        if segs and not any(lo - 0.05 <= a <= hi + 0.05 for lo, hi in spans):
            continue                                           # parola dentro una frase scartata
        words.append(Word(t, a + offset, max(b, a + 0.05) + offset))
    if words:
        return words
    for s in segs:                                             # ripiego: nessun tempo per parola
        toks = (s.get("text") or "").split()
        if not toks:
            continue
        a, b = float(s.get("start", 0.0)), float(s.get("end", 0.0))
        total = sum(len(t) + 1 for t in toks)
        pos = a
        for t in toks:
            d = (b - a) * (len(t) + 1) / total
            words.append(Word(t, pos + offset, pos + d + offset))
            pos += d
    return words


def build_lines(words: list[Word], max_chars: int = 40, max_dur: float = 6.0, gap: float = 0.8) -> list[Line]:
    """Raggruppa le parole in sottotitoli: a fine frase, dopo una pausa o quando la riga diventa troppo lunga."""
    lines: list[Line] = []
    cur: list[Word] = []

    def flush():
        if cur:
            lines.append(Line(cur[0].start, cur[-1].end, " ".join(w.text for w in cur)))
            cur.clear()

    for w in words:
        if cur:
            text_len = sum(len(x.text) + 1 for x in cur) + len(w.text)
            if (w.start - cur[-1].end > gap or text_len > max_chars or w.end - cur[0].start > max_dur):
                flush()
        cur.append(w)
        if w.text.endswith((".", "?", "!")) and sum(len(x.text) + 1 for x in cur) >= max_chars * 0.5:
            flush()
    flush()
    for a, b in zip(lines, lines[1:]):                         # nessuna sovrapposizione fra righe
        a.end = min(a.end, b.start)
    return [ln for ln in lines if ln.end - ln.start > 0.05]


# ------------------------------------------------------------------------------------------------ percorso completo
def transcribe_wav(wav: Path, key: str, workdir: Path, language: str = "it", vocabulary: str = "",
                   on_progress: Callable[[float, str], None] | None = None,
                   cancel: threading.Event | None = None, base_url: str | None = None) -> list[Word]:
    samples = fw.decode_audio_mono(wav, 16000)
    sr = 16000
    chunks = plan_chunks(samples, sr)
    workdir.mkdir(parents=True, exist_ok=True)
    words: list[Word] = []
    for i, (a, b) in enumerate(chunks):
        if cancel is not None and cancel.is_set():
            raise fw.Cancelled()
        if on_progress:
            on_progress(i / len(chunks), f"Trascrivo la parte {i + 1} di {len(chunks)}…")
        if np.sqrt(np.mean(np.square(samples[int(a * sr):int(b * sr)]))) < 1e-4:
            continue                                           # silenzio totale: niente da inviare
        out = workdir / f"chunk{i:03d}.flac"
        _cut_flac(wav, a, b, out)
        data = transcribe_chunk(out, key, language, vocabulary, base_url)
        words += parse_words(data, a)
        out.unlink(missing_ok=True)
    if on_progress:
        on_progress(1.0, "Trascrizione completata.")
    return words
