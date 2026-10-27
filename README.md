# ConfMerge

Prepara video di conferenze per YouTube: unisce i file video, sostituisce l'audio con una registrazione
esterna sincronizzata automaticamente, taglia inizio e fine, applica ritaglio/zoom/risoluzione, titoli,
overlay, lower third, slide/PiP e logo finale, ed esporta un MP4 pronto da caricare.

Licenza MIT – © 2026 Martino Zanzi – https://github.com/martinozanzi/confmerge
Tutto offline, nessuna telemetria. I video originali non vengono mai modificati.

## Uso di Merge Conferenze
Avvia `ConfMerge.exe`. Ci sono due modalità, sullo stesso progetto (si cambia in alto a destra, senza perdere nulla):

**Semplice** (la scelta di partenza, in tre passi):
1. **Cartella**: trascina la cartella della conferenza. Parte subito l'analisi, con messaggi in italiano semplice.
2. **Controlla**: guarda il video; la sincronia è «Ottima / Buona / Da controllare» (con «Ascolta 10 secondi» e, se serve, «Correggi»);
   conferma inizio e fine; scegli il profilo (titolo, logo, credito), lo **stile del titolo** e della schermata finale tra i modelli
   pronti (stile YouTube/Instagram/Canva), le **transizioni** (anteprima animata al passaggio del mouse) e compila i testi.
3. **Esporta**: scegli «Consigliata per YouTube», «Più veloce» o «Massima qualità», vedi tempo e dimensione, premi «Esporta il video».
   Alla fine: «Apri la cartella», «Guarda il video», «Crea la miniatura», «Nuovo progetto».

## Studio Social

Alla prima apertura scegli lo strumento (poi si ricorda l'ultima scelta; si cambia con «Social / Conferenze» in alto):
**Studio Social** per video brevi pronti per le piattaforme, **Merge Conferenze** per unire riprese e audio esterno.
Studio Social usa l'audio delle clip (non quello esterno) ed è guidato in quattro passi:

1. **Video**: trascina uno o più file (si mettono uno dopo l'altro).
2. **Taglia**: forma d'onda con le parti tolte in scuro. «Togli i silenzi» (sensibilità Delicata/Normale/Decisa) oppure trascina
   su una parte e premi «Togli» (Canc). In riproduzione le parti tolte si saltano. Tutto si annulla con «Indietro» e compare nella Cronologia come «Tagli».
3. **Aspetto**: scegli le piattaforme (YouTube, YouTube Shorts, Instagram Reel, TikTok, Threads, Instagram quadrato, X),
   come entra il video orizzontale nel formato verticale (**Riempi** con posizione regolabile, **Sfocato**, **Bande**), le zone
   coperte dall'app (solo in anteprima, mai nel file), i sottotitoli e la musica.
4. **Esporta**: una versione per piattaforma dallo stesso lavoro (`nome_shorts.mp4`, `nome_youtube.mp4`…), con avviso se supera la durata massima.
   I sottotitoli sono spostati sopra la zona coperta dall'app e la voce è portata a un livello adatto ai social.

**Kit del marchio** (menu Impostazioni → Kit del marchio, oppure la scheda «Marchio» nei lavori): se ne possono avere quanti si
vuole, uno per associazione, partito o candidato. Ognuno ha colori (principale, secondario, evidenza, testo, sfondo), caratteri,
slogan, @canale e **loghi** (principale, **simbolo del partito**, quadrato, orizzontale…; i file sono copiati nel kit, quindi
funzionano anche se li sposti). Sceglierne uno mette i loghi negli angoli del video (si accendono e spostano uno per uno e
restano dentro le zone di sicurezza), dà ai sottotitoli e ai nomi dei relatori i colori del marchio e permette di creare con un
clic un titolo e una schermata finale del marchio. I kit si esportano e importano come file `.zip`.

**Miniature YouTube** (pulsante «Miniatura YouTube…» in Esporta): 8 layout pronti (titolo sull'immagine, immagine e titolo a lato,
titolo evidenziato, fascia in diagonale, evento, citazione, dato in evidenza, solo titolo) con un fotogramma del video a scelta,
i colori e i loghi del marchio e l'anteprima piccola come appare su YouTube. Si salva JPG (sotto i 2 MB) e PNG 1280×720.

Le misure delle piattaforme (formato, durata massima, zone di sicurezza) sono approssimative e cambiano: si possono correggere
con un file `piattaforme.json` nella cartella delle impostazioni, per esempio
`{"tiktok": {"max_s": 600, "safe": [0.12, 0.25, 0.04, 0.14]}}` (margini sopra, sotto, sinistra, destra).

## Merge Conferenze

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

**Lavoro al sicuro**: se chiudi con modifiche non salvate l'app ti chiede se salvare; ogni 30 secondi salva da sola (nel
file del progetto, se ha un nome; altrimenti in una copia di sicurezza che ti viene proposta alla prossima apertura).
I pulsanti «Indietro» e «Avanti» in alto (Ctrl+Z / Ctrl+Maiusc+Z) e la **Cronologia** (orologio) permettono di tornare a
qualsiasi punto, anche per inizio e fine del video.

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
