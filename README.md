# Prenotazione automatica corsi Fit Express Garbagnate

Ogni notte GitHub avvia lo script verso le 23:25 (ora italiana); lo script fa login, si sincronizza con l'orologio del server e alle **00:00:00 esatte** prova a prenotare i corsi del giorno che si apre (mezzanotte di mercoledì → corsi di venerdì), riprovando ogni 0,25 s per 3 minuti. Se il corso è pieno e `waiting_list: true`, si iscrive alla lista d'attesa.

> Uso personale, solo per il tuo account. Probabilmente non è previsto dai termini d'uso dell'app: usalo con moderazione.

## 1. Crea un account GitHub
Vai su https://github.com/signup e registrati (gratis).

## 2. Crea un repository **privato**
1. In alto a destra **+ → New repository**.
2. Nome: `fitexpress-booking`. Seleziona **Private**. Clicca **Create repository**.

## 3. Carica i file
1. Nel repository clicca **uploading an existing file** (oppure **Add file → Upload files**).
2. Estrai lo zip sul PC e trascina **tutto il contenuto** della cartella, compresa la cartella `.github` (se non la vedi, attiva "mostra file nascosti"; in alternativa crea il file a mano: **Add file → Create new file**, nome `.github/workflows/book.yml`, incolla il contenuto).
3. Clicca **Commit changes**.

## 4. Aggiungi le credenziali come Secrets
1. **Settings → Secrets and variables → Actions → New repository secret**.
2. Nome `FITEXPRESS_EMAIL`, valore: l'email dell'app. **Add secret**.
3. Di nuovo: nome `FITEXPRESS_PASSWORD`, valore: la password dell'app.

Le credenziali non vanno mai scritte nei file.

## 5. Scegli i corsi in `courses.yaml`
Apri `courses.yaml`, clicca la matita ✏️ e modifica, ad esempio:
```yaml
courses:
  - name: GAG
    weekday: venerdi
    start: "11:00"
    waiting_list: true
  - name: PILATES
    weekday: lunedi
    start: "19:00"
    waiting_list: false
```
Il nome deve essere uguale a quello mostrato nell'app (maiuscole/minuscole non contano). Giorni: lunedi … domenica. Poi **Commit changes**.

## 6. Prova (senza prenotare)
1. Tab **Actions**; se richiesto, clicca **I understand… enable them**.
2. Seleziona **Prenota corsi Fit Express → Run workflow**, modalità `dry-run`, **Run workflow**.
3. Apri l'esecuzione: nei log devi vedere `login OK` e `trovato <corso> … eventId=…` per i corsi di dopodomani (se dopodomani non c'è nessun corso in elenco vedrai "nessun corso da prenotare").
   La modalità `now` invece **prenota subito** (utile solo se il corso è già aperto).

## 7. Fatto
Da ora gira da solo ogni sera. Per controllare: tab **Actions** → ultima esecuzione → log (`PRENOTATO …`).

### Note
- I due orari nel workflow coprono ora legale e ora solare; quello in più esce subito da solo.
- GitHub può ritardare l'avvio anche di 10-30 minuti: per questo parte alle 23:25. Se un giorno partisse dopo le 00:10, quella notte salta.
- GitHub disattiva i workflow pianificati dopo 60 giorni senza attività nel repository: se succede, riattivalo dalla tab Actions (basta anche una piccola modifica a un file).
