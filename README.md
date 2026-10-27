# ConfMerge

Prepara video di conferenze per YouTube: unisce i file video, sostituisce l'audio con una registrazione
esterna sincronizzata automaticamente, taglia inizio e fine, applica ritaglio/zoom/risoluzione, titoli,
overlay, lower third, slide/PiP e logo finale, ed esporta un MP4 pronto da caricare.

Licenza MIT – © 2026 Martino Zanzi – https://github.com/martinozanzi/confmerge
Tutto offline, nessuna telemetria. I video originali non vengono mai modificati.

## Uso
Avvia `ConfMerge.exe`. Ci sono due modalità, sullo stesso progetto (si cambia in alto a destra, senza perdere nulla):

**Semplice** (la scelta di partenza, in tre passi):
1. **Cartella**: trascina la cartella della conferenza. Parte subito l'analisi, con messaggi in italiano semplice.
2. **Controlla**: guarda il video; la sincronia è «Ottima / Buona / Da controllare» (con «Ascolta 10 secondi» e, se serve, «Correggi»);
   conferma inizio e fine; scegli il profilo (titolo, logo, credito), lo **stile del titolo** e della schermata finale tra i modelli
   pronti (stile YouTube/Instagram/Canva), le **transizioni** (anteprima animata al passaggio del mouse) e compila i testi.
3. **Esporta**: scegli «Consigliata per YouTube», «Più veloce» o «Massima qualità», vedi tempo e dimensione, premi «Esporta il video».
   Alla fine: «Apri la cartella», «Guarda il video», «Crea la miniatura», «Nuovo progetto».

**Avanzata**: barra laterale con le fasi (Sorgenti, Sincronia e tagli, Formato, Titoli e transizioni, Logo e grafica, Slide e PiP, Audio, Export e coda),
anteprima sempre visibile, sezioni comprimibili con ricerca rapida, pannello livelli (occhio, lucchetto, trascinamento),
mini-timeline, annulla/ripristina, coda di export, parametri tecnici in «Avanzate» (chiuse di default).

Scorciatoie (elenco completo con F1): `Spazio`/`K` riproduci, `←/→` fotogramma, `Maiusc+←/→` 1 s, `J`/`L` 5 s, `I`/`O` inizio/fine,
`N` cambio slide, `Ctrl+Z` / `Ctrl+Maiusc+Z` annulla/ripristina.

**Sottotitoli e musica** (in Semplice nel passo «Esporta», in Avanzata in «Titoli e sottotitoli» e «Audio»):
- *Sottotitoli automatici*: la trascrizione usa il servizio a consumo di **Groq** (circa 4 centesimi di dollaro per ora di video).
  Serve una chiave gratuita da incollare in **Impostazioni → Sottotitoli automatici** ([istruzioni](docs/GROQ.md)). L'audio viene
  inviato a Groq solo quando premi «Crea i sottotitoli»; la chiave resta sul tuo computer (su Windows cifrata) e non finisce nei
  profili. Puoi correggere ogni riga, scegliere lo stile (carattere, colori, bordo, sfondo, posizione) ed esportare il file `.srt`.
- *Musica di sottofondo*: un brano a tua scelta, con volume e abbassamento automatico quando qualcuno parla.

Il tema è scuro, chiaro o «come il computer» (Impostazioni); «Riduci le animazioni» le disattiva.

Impostazioni e profili: `%APPDATA%\ConfMerge`.

**Log degli errori**: `%LOCALAPPDATA%\ConfMerge\confmerge.log` (errori Python, avvisi di Qt, ffmpeg) e `crash.log` (arresti improvvisi). Da *Aiuto → Apri la cartella dei log* oppure *Copia informazioni per l'assistenza*.

## Build (Windows 10/11, serve solo Python 3.11–3.14)
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
Per le slide PDF si usa solo QtPdf di PySide6 (nessun PyMuPDF). Qt (PySide6 6.12.0) è fissato in `requirements.txt`; funziona con Python 3.11–3.14 (provato su 3.13 e 3.14).

## Architettura
Tutti gli elementi grafici sono disegnati con QPainter su QImage RGBA (`render/`), con la stessa funzione per
anteprima ed export (WYSIWYG): parti statiche = un PNG con `overlay enable=between(t,a,b)`, parti animate =
sequenza PNG solo per la durata dell'animazione, barra di avanzamento = un PNG che scorre con `overlay x=expr(t)`.
Moduli principali: `ffmpeg_wrapper`, `media_scan`, `sync`, `trim_detect`, `audio_fx`, `graph` (filtergraph),
`export_engine`, `estimator`, `slides`, `credit`, `settings`/`profiles`, `project`, `queue`, `worker`, `ui/`.
