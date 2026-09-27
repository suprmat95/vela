# Vela readme rewrite

- Sessione: `07ad0a98-85f5-49e5-85cd-f88fe9dcc9fb`
- Inizio: 2026-09-27 20:31

## Utente 20:31

riscrivi il readme, indicando semplicemente cos'è vela, come si collega a claude, come avviarlo in locale e come avviare il load test indicando tuti i paramentri del funnel

## Agente 20:31

- 🔧 Bash: wc -l README.md loadtest/README.md && ls loadtest && cat README.md

- 🔧 Bash: cat loadtest/README.md && sed -n 1,200p loadtest/scenario.py && sed -n 1,80p loa…

- 🔧 Bash: grep -n "add_argument" -A2 loadtest/run.py loadtest/projection.py | head -80; ls…

Ho letto il README attuale (205 righe), `loadtest/README.md`, `docker-compose.yml`, `loadtest/run.py`, `loadtest/scenario.py` e `loadtest/projection.py`. Come chiede il CLAUDE.md, prima di scrivere ti propongo l'approccio.

**Nuovo README, quattro sezioni:**

1. **Cos'è Vela.** Tre o quattro righe: una frase all'assistente, una sola proposta per volta, prenotazione su HofJ dopo il pagamento, codice di prenotazione. Nominerei i cinque casi d'uso e rimanderei a `docs/spec.md`.
2. **Collegarlo a Claude.** Il connector MCP personalizzato in claude.ai (Settings → Connectors → Add custom connector, nome `Pacchetti Viaggio di Padel Tennis`, URL `https://vela-n506.onrender.com/mcp`, nessuna autenticazione) e una frase d'esempio. Aggiungerei lo smoke test `scripts/mcp_smoke.py` e il vincolo `VELA_PUBLIC_URL` = host accettato da `/mcp`.
3. **Avvio in locale.** `uv sync`, `DATABASE_URL` (anche SQLite), `alembic upgrade head`, `uvicorn` e `curl /health`, in replay (il modo predefinito, senza chiamate esterne). Poi test e lint in due righe.
4. **Load test.** Il flusso completo: `docker compose up -d --build`, `run`, `down -v`, `projection.py`. Poi le tabelle con tutti i parametri del funnel:
   - `run.py`: `--travelers`, `--browse` / `--proposal` / `--link` (il resto paga), `--duration`, `--arrival-minutes`, `--tail-minutes`, `--seed`, `--label`, più `--vela`, `--fake`, `--brands`, `--calls`, `--out`;
   - i quattro gruppi del funnel spiegati (cosa fa ciascuno, esiti), l'esempio 10k → 5.000 / 3.000 / 1.800 / 200 e le sentinelle Marco e Anna;
   - il finto HofJ: `FAKE_HOFJ_WINDOW`, `LATENCY`, `BACKGROUND_RPM`, `FAKE_HOFJ_FAULTS` (con i tipi di guasto), `SEED`;
   - `projection.py`: `--rate`, `--minutes`, `--tail-minutes`, `--browse` / `--proposal` / `--link`, `--sizes`, `--json`;
   - un rimando a `loadtest/README.md` per output e dettagli.

**Da decidere: cosa fare di ciò che esce dal README** (tabella delle variabili d'ambiente, parametri del worker, deploy su Render, Docker, sync a mano, landing, struttura):

- **A (consigliata):** lo sposto in un nuovo `docs/operations.md` e il README ci rimanda. Non si perde niente, e il README diventa corto come chiedi. Il CLAUDE.md dice che tutto ciò che guida il lavoro resta nel repository.
- **B:** lo elimino. Parte di queste informazioni è già in `CLAUDE.md` e nei `docs/`, ma la tabella delle variabili d'ambiente e il deploy su Render esistono solo qui.
- **C:** lo tengo in fondo al README, in una sezione "Riferimento" compatta.

Lingua: italiano, come oggi. A lavoro finito eseguo un commit piccolo solo con il README (e `docs/operations.md` se scegli A), senza push.

Va bene così? E per le parti che escono scegli A, B o C?

## Utente 20:31

si

## Agente 20:31

- 🔧 Bash: tail -20 docs/decisions.md; grep -n "^## " docs/decisions.md | tail -5; git stat…

Scrivo prima `docs/operations.md` con le parti che escono dal README, poi il README nuovo.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/master/docs/operations.md

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/master/README.md

Controllo due affermazioni nuove: se `/mcp` accetta `localhost` senza `VELA_PUBLIC_URL`, e se `ARCHITECTURE.md` esiste.

- 🔧 Bash: ls ARCHITECTURE.md; grep -n "421\|allowed_host\|public_url\|localhost" vela/surf…

`localhost` e `127.0.0.1` sono sempre accettati: correggo "l'unico host" e poi verifico davvero l'avvio in locale.

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/master/README.md

- 🔧 Bash: S=/private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-master/07ad0…

- 🔧 Bash: tail -30 /private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-maste…

- 🔧 Bash: S=/private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-master/07ad0…

- 🔧 Bash: S=/private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-master/07ad0…

Lo smoke test passa: ordine pagato in replay e codice di prenotazione restituito. Aggiorno il README.

- 🔧 Bash: python3 - <<'EOF' p='README.md'; s=open(p).read() old_a='''Serve [uv](https://do…

- 🔧 Bash: python3 - <<'EOF' p='docs/operations.md'; s=open(p).read() old='''errore esplici…

Ho riscritto il README e fatto il commit `b4c30e6` su `master`, senza push. Il commit contiene solo `README.md`, `docs/operations.md` e `docs/decisions.md`. Il log degli agenti che il hook ha preparato è ancora in staging e non l'ho toccato.

**Cosa ho fatto**
- **README**, quattro parti:
  - **Cos'è Vela:** una frase, una sola proposta alla volta, i cinque casi d'uso.
  - **Collegare Claude:** il connector MCP su claude.ai e come si svolge la conversazione.
  - **Avvio in locale:** in replay, più test e lint.
  - **Load test:** i comandi, la tabella del funnel con i quattro gruppi, le tre percentuali (il resto paga), l'esito di ogni gruppo e le sentinelle Marco e Anna. Poi le tabelle con tutte le opzioni di `run.py`, le variabili e i tipi di guasto del finto HofJ, e le opzioni di `projection.py`.
- **`docs/operations.md`:** qui ho spostato tutto quello che è uscito dal README, senza tagliare niente: variabili d'ambiente, worker, sync, Docker, deploy su Render, landing, struttura.
- **`docs/decisions.md`:** ho aggiunto la voce su questa scelta.

**Cosa ho verificato**
Ho avviato Vela in locale su un Postgres usa e getta: `/health` risponde ok con 190 prodotti. `scripts/mcp_smoke.py` fa il flusso completo in replay e restituisce il codice di prenotazione. Il load test invece non l'ho lanciato: comandi e parametri li ho presi dal codice (`run.py`, `scenario.py`, `projection.py`, `docker-compose.yml`), non da un giro fatto adesso.

**Cosa ho deciso**
- **Postgres per l'avvio in locale, non più SQLite.** Con SQLite l'app non si avvia: il contatore della quota confronta date con e senza fuso orario (`vela/domain/quota.py:120`, `TypeError`). Il bug c'era già e non l'ho corretto. L'ho segnalato in `docs/operations.md`.
- **Smoke test su `http://localhost:8000/mcp`, non `127.0.0.1`.** Lo smoke test controlla che il link di pagamento punti allo stesso host dell'URL chiamato, e senza `VELA_PUBLIC_URL` il link è su `localhost:8000`.

**Cosa resta da decidere**
- **Il bug di SQLite tocca anche `CLAUDE.md`.** Il `docker run ... sqlite` che vi è indicato per provare l'immagine oggi non supera l'avvio. Vuoi che lo corregga come compito a parte, o che aggiorni solo `CLAUDE.md`?
- **L'URL del connector è quello di Render** (`vela-n506.onrender.com`), preso da `landing/config.js`. Se cambia, va aggiornato anche nel README.

## Utente 21:00

quindi l'esaminatore come avvia il load test?

## Agente 21:01

L'esaminatore ha bisogno solo di Docker (Docker Desktop su Mac). Non servono chiavi, account o `uv`, perché tutto gira nei container. Dalla cartella del repository:

```bash
# 1. avvia Postgres, Vela (modo loadtest) e il finto HofJ
docker compose up -d --build

# 2. lancia il giro: 10.000 viaggiatori, 5 min di arrivi + 3 di coda
docker compose run --rm locust --travelers 10000 --browse 50 --proposal 30 --link 18 \
    --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k

# 3. legge il risultato
cat loadtest/out/10k/report.md

# 4. spegne tutto e cancella il DB (il giro dopo riparte pulito)
docker compose down -v
```

Durante il giro:
- **Prima di Locust:** il comando aspetta che Vela abbia caricato il catalogo (190 prodotti), poi stampa quanti viaggiatori ci sono in ogni gruppo del funnel (5.000 / 3.000 / 1.800 / 200).
- **Durata:** circa 8 minuti, più il tempo della prima build.
- **Risultato:** il report dice se le chiamate a HofJ sono rimaste sotto 108 in ogni finestra di 60 s e quanti viaggiatori di ogni gruppo sono arrivati al loro esito.
- **Parametri:** per cambiare il funnel basta cambiarli nel passo 2 (per esempio `--travelers 2000 --link 10`). Per il finto HofJ si mettono le variabili davanti al passo 1 (per esempio `FAKE_HOFJ_LATENCY=pessimistic docker compose up -d --build`).
- **Porte:** devono essere libere la 8000 e la 8001.

Resta un passo opzionale, `projection.py`, che porta il giro a 50.000 viaggiatori. Richiede `uv` sulla macchina e come `--rate` il numero di link al minuto letto nel report. Nel README ho scritto questi passi, ma non spiego da dove si legge quel numero: lo posso aggiungere.

Il load test non l'ho mai lanciato in questa sessione: i comandi li ho presi dal codice e da `loadtest/README.md`. Il punto da controllare è il passo 2: `locust` sta nel profilo `loadtest`, quindi il passo 1 non costruisce la sua immagine. Mi aspetto che la costruisca `docker compose run`, ma non l'ho verificato.

Se vuoi, faccio una prova breve (per esempio `--travelers 200 --duration 3`, qualche minuto, nessuna chiamata esterna). Così verifichiamo che un esaminatore possa seguire il README da zero e, se serve, lo correggo.

## Utente 21:02

scrivi cat loadtest/out/10k/report.md per leggere il risultato

## Agente 21:02

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/master/README.md

- 🔧 Bash: git commit -q -m "README: show how to read the load test report  Co-Authored-By:…

Ho aggiunto `cat loadtest/out/10k/report.md   # il risultato del giro` nel blocco di comandi del load test nel README, tra il lancio del giro e `docker compose down -v`. Il commit è `c283421` su `master`, senza push.

La cartella prende il nome da `--label`, quindi con un'etichetta diversa il percorso diventa `loadtest/out/<label>/report.md`. Il paragrafo sotto i comandi del README lo spiega già.

## Utente 21:02

ok committa e pusha

## Agente 21:02

- 🔧 Bash: git status --short && git fetch -q origin && git log --oneline origin/master..ma…
