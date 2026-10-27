# Come ottenere la chiave di Groq (sottotitoli automatici)

ConfMerge usa il servizio di trascrizione di **Groq** per creare i sottotitoli. Si paga solo quello che si usa: circa
**4 centesimi di dollaro per ogni ora di video** (prezzo indicativo, controlla sul sito di Groq). L'audio viene inviato
a Groq solo quando premi «Crea i sottotitoli».

1. Apri <https://console.groq.com/keys> e registrati o accedi (si può usare un account Google o GitHub).
2. Premi **Create API Key**, dai un nome (per esempio «ConfMerge») e conferma.
3. **Copia subito la chiave** (inizia con `gsk_`): per sicurezza Groq la mostra una volta sola.
4. In ConfMerge apri **Impostazioni → Sottotitoli automatici**, incolla la chiave e premi **Salva**.
5. Premi **Prova la chiave**: deve comparire «La chiave funziona».

Note:
- Se finisci il credito gratuito o superi i limiti, il programma te lo dice; puoi aggiungere un metodo di pagamento
  nella console di Groq per continuare a pagare a consumo.
- La chiave resta sul tuo computer (su Windows è cifrata per il tuo utente) e non viene mai salvata nei profili o nei progetti.
- Se la chiave finisce in mani sbagliate, eliminala dalla console di Groq e creane una nuova.
