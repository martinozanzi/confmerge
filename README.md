# ConfMerge

Prepara video di conferenze per YouTube: unisce i file video, sostituisce l'audio con una registrazione
esterna sincronizzata automaticamente, taglia inizio e fine, applica ritaglio/zoom/risoluzione, titoli,
overlay, lower third, slide/PiP e logo finale, ed esporta un MP4 pronto da caricare.

Licenza MIT – © 2026 Martino Zanzi – https://github.com/martinozanzi/confmerge
Tutto offline, nessuna telemetria. I video originali non vengono mai modificati.

## Uso
Avvia `ConfMerge.exe` e segui le schermate: **Selezione → Analisi → Revisione → Grafica → Export**.

- **Selezione**: una cartella (trova video, audio più lungo, slide) oppure file singoli; drag & drop.
- **Revisione**: player con anteprima WYSIWYG, forma d'onda con marker trascinabili, offset in ms,
  «riascolta sincronia», fotogramma ±, ±1 s. Tasti: `Spazio`, `←/→`, `Maiusc+←/→`, `I`/`O` (inizio/fine
  taglio), `N` (cambio slide). I tagli suggeriti non vengono mai applicati senza conferma.
- **Grafica**: immagine (formato, ritaglio, zoom, Ken Burns, fade), overlay/logo/barra, titolo iniziale,
  schermata finale, lower third, slide e PiP, credito, profili («Salva come profilo» sempre disponibile).
- **Export**: preset YouTube 1080p/1440p/4K, Veloce (copia stream), Personalizzato; loudness −14 LUFS,
  filtri voce, stima di tempo (benchmark su 10 s) e dimensione, anteprima 10 s, coda, miniatura 1280×720.

Impostazioni e profili: `%APPDATA%\ConfMerge`. Log: `%LOCALAPPDATA%\ConfMerge\confmerge.log`.

## Build (Windows 10/11, serve solo Python 3.11+)
```
build.bat            (onefile + onedir)
build.bat onefile    dist\onefile\ConfMerge.exe   – un solo file, con splash
build.bat onedir     dist\onedir\ConfMerge\       – avvio più veloce
```
`build.bat` crea `.venv`, installa le dipendenze, scarica ffmpeg/ffprobe statici in `bin\` (se mancano) e
lancia PyInstaller. L'utente finale non installa nulla.

## Sviluppo e riga di comando
```
pip install -r requirements.txt pytest
set PYTHONPATH=src
python -m confmerge                      (GUI)
python -m confmerge run CARTELLA -o uscita.mp4          (CLI: analisi + export)
python -m confmerge analyze CARTELLA -o lavoro.confmerge
python -m confmerge export lavoro.confmerge -o uscita.mp4 --accept-trim
python -m pytest
```
Per le slide PDF si usa solo QtPdf di PySide6 (nessun PyMuPDF). PySide6 è fissato a 6.8.3.

## Architettura
Tutti gli elementi grafici sono disegnati con QPainter su QImage RGBA (`render/`), con la stessa funzione per
anteprima ed export (WYSIWYG): parti statiche = un PNG con `overlay enable=between(t,a,b)`, parti animate =
sequenza PNG solo per la durata dell'animazione, barra di avanzamento = un PNG che scorre con `overlay x=expr(t)`.
Moduli principali: `ffmpeg_wrapper`, `media_scan`, `sync`, `trim_detect`, `audio_fx`, `graph` (filtergraph),
`export_engine`, `estimator`, `slides`, `credit`, `settings`/`profiles`, `project`, `queue`, `worker`, `ui/`.
