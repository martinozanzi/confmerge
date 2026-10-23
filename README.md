# ConfMerge

Prepara video di conferenze per YouTube: unisce i file video, sostituisce l'audio con una registrazione
esterna sincronizzata automaticamente, taglia inizio e fine ed esporta un MP4.

Licenza MIT – © 2026 Martino Zanzi – https://github.com/martinozanzi/confmerge

> **Stato: Fase 1 di 8** – pipeline da riga di comando (unione + sync + trim + export).
> La GUI, la grafica, le slide, la coda e il packaging `.exe` arrivano nelle fasi successive.

## Uso (sviluppo)

Servono Python 3.11+, `ffmpeg` e `ffprobe` (in `bin/` oppure nel PATH).

```
python -m venv .venv && .venv\Scripts\activate      (Windows)
pip install -r requirements.txt
set PYTHONPATH=src

python -m confmerge analyze CARTELLA -o lavoro.confmerge
python -m confmerge export lavoro.confmerge -o uscita.mp4 --accept-trim
python -m confmerge run CARTELLA -o uscita.mp4          (analizza e chiede conferma del taglio)
```

- `CARTELLA`: i video MP4/MOV vengono ordinati per `creation_time` (ripiego sul nome); l'audio esterno
  è il file audio più lungo (oppure `--audio FILE`).
- Il taglio suggerito **non** viene mai applicato senza conferma: `--accept-trim`, oppure `--start/--end`
  (secondi o `mm:ss`).
- `--mode auto|copy|encode`: la copia stream taglia sul keyframe precedente (lo script lo segnala);
  la ricodifica è esatta al fotogramma.
- `--drift-correct`: applica la correzione di deriva dei clock (atempo) se misurata.
- I video originali non vengono mai modificati. Log in `%LOCALAPPDATA%\ConfMerge`.

## Test

```
pip install pytest
python -m pytest
```
