# Review UX di ConfMerge (pensata per un utente anziano, non tecnico)

Stato: cosa ho trovato guardando l'app com'era dopo la Fase 1 del restyling, cosa è già stato corretto e cosa resta.

## Principi usati
1. **Una domanda per volta**, scritta come la farebbe una persona ("La voce coincide con le labbra?"), non come un parametro.
2. **Mai numeri grezzi o sigle** (millisecondi, confidenza, deriva, atempo, LUFS, CRF, afftdn): si mostrano parole (Ottima / Buona / Da controllare) e il valore tecnico sta solo nel tooltip.
3. **Un'azione principale evidente** per schermata (pulsante pieno), le alternative in secondo piano.
4. **Ogni azione dice cosa succede e ogni attesa spiega perché** ("Sto preparando l'anteprima di questo punto…").
5. **Niente va tagliato o nascosto**: se il contenuto non ci sta, va a capo o scorre; un controllo automatico lo verifica.

## Problemi trovati
| # | Problema | Stato |
|---|---|---|
| 1 | Sincronia: "Offset 1500 ms", "Confidenza 873.1", "Applica all'anteprima", "Riascolta sincronia" non dicevano cosa fare né cosa aspettarsi | **Corretto** (schermata «Controlla il video») |
| 2 | Non era chiaro come capire a occhio se audio e video sono allineati | **Corretto**: pulsante «Guarda e ascolta 10 secondi» + istruzione "la voce deve coincidere con le labbra"; frecce «Anticipa/Ritarda la voce» da 0,1 s |
| 3 | La forma d'onda non aveva spiegazione | **Corretto**: legenda sotto le onde e nomi leggibili |
| 4 | Tagli: due campi h:mm:ss.cc e pulsanti «Qui»/«Vai» ambigui | **Corretto**: «Usa inizio e fine suggeriti», «Non tagliare», testo "Taglio scelto ✓"; i campi a mano sono in una sezione chiusa |
| 5 | Anteprima lenta (tutto il video convertito) | **Corretto**: solo 10 minuti da quando inizia l'audio, a 360p; se si clicca altrove se ne prepara una di 3 minuti in quel punto |
| 6 | Contenuti tagliati a destra, toggle con anello tagliato | **Corretto**, con controllo automatico (anche barre di scorrimento orizzontali) |
| 7 | Ordine dei video ambiguo | **Corretto**: elenco numerato con data, criterio selezionabile e avviso |
| 8 | Errori invisibili all'utente (nessun log degli errori Python) | **Corretto**: log con rotazione, errori non gestiti, arresti di Qt; menu Aiuto → cartella dei log / copia informazioni |
| 9 | Troppe schede tecniche (CRF, bitrate, encoder, LUFS, afftdn) nella schermata Export | **Corretto**: modalità Semplice (3 scelte) e, in Avanzata, parametri tecnici in «Avanzate» chiuse; l'Audio ha frasi semplici |
| 10 | Breadcrumb testuale al posto di una navigazione chiara | **Corretto**: barra laterale con stato delle fasi (Avanzata) e indicatore a 3 passi (Semplice) |
| 11 | Messaggi in inglese/tecnici residui (es. nomi di filtri, "0 = preset") | **Corretto**: «Automatico», CRF solo se attivato, LUFS/afftdn spiegati o nascosti |
| 12 | Schermata Export con due colonne dense | **Corretto**: sezioni comprimibili, stato vuoto della coda, colonne che si impilano nelle finestre strette |

## Stato
Tutti i punti sono stati affrontati. Restano da provare su un PC Windows reale (DPI, barra del titolo scura, installazione pulita) e con file DJI veri.
