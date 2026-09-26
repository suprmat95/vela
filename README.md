# Vela

Vela permette a un viaggiatore di comprare un viaggio di padel o tennis con hotel esprimendo
un solo intento, a parole sue, all'assistente che usa già (Claude via MCP, un agente vocale
ElevenLabs, o un client REST). Non ha una homepage e non mostra liste: propone un viaggio alla
volta, lo prenota sull'API House of Journeys e restituisce il codice di prenotazione.
Requisiti in `docs/spec.md`, roadmap in `docs/roadmap.md`, decisioni in `docs/decisions.md`.

Stato: M3 e M4 (superfici MCP e REST). L'app espone `GET /health`, la superficie MCP su `/mcp`
(vedi "Collegare Claude"), la superficie REST sotto `/v1` (bearer `VELA_API_TOKEN`, contratto e
comandi `curl` in `docs/rest.md`) e, in replay, `GET /replay/checkout/{order_id}` (pagamento
simulato). I cinque casi d'uso (`create_intent`, `get_proposal`, `reject_proposal`,
`accept_proposal`, `get_order_status`) vivono in `vela/domain/usecases.py`.

## Requisiti

- [uv](https://docs.astral.sh/uv/) (gestisce anche l'interprete Python 3.12, vedi `.python-version`)
- Docker, per costruire l'immagine
- Postgres per l'esecuzione reale; i test non lo richiedono

## Avvio in locale

```bash
uv sync                                  # crea .venv con Python 3.12 e le dipendenze di uv.lock
source .venv/bin/activate
export DATABASE_URL=postgresql://user:pass@localhost:5432/vela   # oppure sqlite:////tmp/vela.db per una prova
alembic upgrade head                     # migrazioni
uvicorn vela.app:app --reload            # http://127.0.0.1:8000/health
```

In replay, a ogni avvio l'app riallinea la tabella `products` alle fixture dell'host di
produzione (`fixtures/catalog*.json`, una per brand, `docs/fixtures.md`): se i prodotti attivi
sono diversi carica le fixture e archivia gli altri, senza cancellarli; se sono gli stessi non
tocca nulla (M7). Poi legge la quota HofJ (`GET /v1/quota`, una chiamata), riaccoda la
prenotazione degli ordini `paid_pending_booking` senza job e avvia il worker (M5).

`VELA_UPSTREAM_MODE=live` chiama HofJ vero e richiede `HOFJ_API_KEY`, `HOFJ_BASE_URL`,
`HOFJ_BRANDS` e `STRIPE_SECRET_KEY` (senza pagamento reale l'app non parte). Il catalogo viene dal
sync multi-brand (M10): al boot, dopo la quota, parte un thread che sincronizza subito se il
catalogo è vuoto o più vecchio di 6 ore e poi ogni 6 ore, un'istanza alla volta (advisory lock
Postgres). Ogni brand di `HOFJ_BRANDS` ha il suo client HofJ; carrello e prenotazione usano il
brand del prodotto dell'ordine. Il locale delle chiamate è quello delle fixture registrate su
`HOFJ_BASE_URL` (senza fixture per l'host l'app non parte).

Sync a mano (stampa prima le chiamate previste; `--dry-run` si ferma lì):

```bash
uv run python -m vela.sync --dry-run      # piano, nessuna chiamata
uv run python -m vela.sync                # un giro su tutti i brand, nel DB di DATABASE_URL
uv run python -m vela.sync --record --sport tennis   # rigenera una fixture (docs/fixtures.md)
```

`GET /health` risponde `200 {"status":"ok","db":"ok"}` se il database risponde, altrimenti
`503 {"status":"degraded","db":"error"}`. Non richiede autenticazione.

## Coda e worker (M5)

L'accettazione mette l'ordine in coda e risponde subito con posizione e attesa stimata. Un worker
in ogni istanza (thread nel processo) preleva i job da Postgres con `FOR UPDATE SKIP LOCKED`:
acquisto (carrello HofJ e link di pagamento), verifica del pagamento, prenotazione. Nessuna
chiamata a HofJ parte senza un blocco di quota prenotato nel contatore condiviso (finestra di
60 s, limite effettivo 108 su 120, riserva di 21 per le prenotazioni).

I parametri sono campi di `Settings` con default, non variabili d'ambiente (spec §6):

| Campo | Default | Uso |
|---|---|---|
| `worker_concurrency` | 4 | thread del worker per istanza (0 = nessun thread, solo `drain` nei test) |
| `quota_margin` | 0,10 | margine sul `limitPerMinute` di HofJ |
| `booking_reserve` | 0,20 | quota della finestra riservata alle prenotazioni |
| `purchase_max_attempts` | 3 | tentativi del job d'acquisto su rete/5xx |
| `booking_max_attempts`, `booking_backoff` | 5, (5, 10, 20, 40) s | tentativi e attese della prenotazione |
| `job_lease_seconds` | 120 | dopo quanto un job `running` di un'istanza morta torna prelevabile |
| `payment_poll_seconds` | 60 | intervallo della verifica della Checkout Session |
| `replay_latency`, `replay_limit` | (0, 0), nessuno | latenza e quota simulate dal replay (M13) |

## Test

```bash
uv sync
source .venv/bin/activate
python3 -m unittest discover -s tests
```

Equivalente senza attivare il venv: `uv run python3 -m unittest discover -s tests`.
Nessun test chiama servizi esterni. I test che richiedono Postgres girano solo se
`DATABASE_URL` è impostata, altrimenti vengono saltati. Attenzione: il `python3` di sistema
potrebbe essere una versione vecchia; la suite richiede il 3.12 del venv e lo verifica.

I test Postgres lavorano nello schema `vela_test` (creato se manca) e non toccano le tabelle
dell'app. Fa eccezione il test di migrazione di M0, che applica `alembic upgrade head` allo
schema principale. Per eseguirli in locale: `set -a; . ./.env; set +a; uv run python -m unittest
discover -s tests` in una sola riga, senza stampare le variabili.

## Variabili d'ambiente

Solo variabili d'ambiente: nessun file `.env` viene letto dal codice (e non va mai aperto
dagli agenti). Per uso locale si può esportare a mano o usare `set -a; . ./.env; set +a`.

| Variabile | Obbligatoria | Uso |
|---|---|---|
| `DATABASE_URL` | sì | Postgres (`postgres://...` di Render viene riscritto in `postgresql+psycopg://`). Senza, `/health` risponde 503 e le migrazioni falliscono. |
| `VELA_UPSTREAM_MODE` | no, default `replay` | `replay` usa `fixtures/` senza chiamate esterne; `live` chiama HofJ vero e richiede le variabili HofJ e `STRIPE_SECRET_KEY`. |
| `HOFJ_API_KEY` | in `live` | Chiave dell'API House of Journeys. |
| `HOFJ_BASE_URL` | in `live` | Base URL dell'API HofJ. |
| `HOFJ_BRANDS` | in `live` | Mappa sport → brand HofJ, es. `padel=weebora.com,tennis=terrarossa.com` (M10). Sport `padel` e `tennis`, brand distinti, almeno una voce. La vecchia `HOFJ_BRAND` da sola blocca l'avvio con l'indicazione di migrare. |
| `STRIPE_SECRET_KEY` | per Stripe reale | Chiave Stripe di test (una `rk_test` fornita da HofJ). Se impostata, i link di pagamento sono Checkout Session reali (M6), anche con HofJ in replay; richiede `VELA_PUBLIC_URL`. Vedi `docs/stripe.md`. |
| `STRIPE_WEBHOOK_SECRET` | no | Non usata: niente webhook Stripe; il pagamento si verifica leggendo la Checkout Session e si chiude con `POST /v1/bookings` di HofJ (M5). |
| `VELA_API_TOKEN` | per usare `/v1` | Bearer token statico della superficie REST (e token statico MCP da M8). Senza, `/v1/*` risponde 503. |
| `VELA_PUBLIC_URL` | in replay su Render | URL pubblico di Vela: base del link di checkout replay (M2) e dei ritorni Stripe (M6). Senza, i link puntano a `http://localhost:8000`. Obbligatoria con `STRIPE_SECRET_KEY`. |
| `ANTHROPIC_API_KEY` | no | Se presente abilita il fallback Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) quando il parser non trova né sport né periodo; timeout 5 s, 1 retry. Prova manuale (una chiamata): `uv run python scripts/try_haiku.py "testo"`. |

## Docker

```bash
docker build -t vela .
docker run --rm -e DATABASE_URL=sqlite:////tmp/vela.db -p 8000:8000 vela
curl -s localhost:8000/health
```

`docker-entrypoint.sh` esegue `alembic upgrade head` e poi `uvicorn` sulla porta `PORT`
(default 8000; Render la imposta da sé). Senza `DATABASE_URL` il container termina con un
errore esplicito.

## Deploy su Render

`render.yaml` descrive un web service Docker e un Postgres gestito (piano free, Frankfurt).

1. Dashboard Render → New → Blueprint → questo repository e branch.
2. Render crea `vela-db` e il servizio `vela`; `DATABASE_URL` è collegata al database.
3. Inserire nella dashboard le variabili marcate `sync: false`. Il Blueprint fissa
   `VELA_UPSTREAM_MODE=live` (M7, HofJ staging): servono `HOFJ_API_KEY`,
   `HOFJ_BASE_URL=https://staging.api.hofj.com`, `HOFJ_BRANDS=padel=staging.weebora.com,tennis=staging.tennis.weebora.com`,
   `STRIPE_SECRET_KEY`, `VELA_PUBLIC_URL` e `VELA_API_TOKEN`, altrimenti l'app non parte. Per tornare
   in replay si cambia il valore nel file.
4. Nel log del deploy compare `Running upgrade  -> 0001`: le migrazioni sono state applicate.
5. `curl https://<servizio>.onrender.com/health` →
   `{"status":"ok","db":"ok","catalog":{...},"quota":{...},"queue":{...}}`
   (`catalog`: numero di prodotti, `fetched_at`, `age_seconds`; `quota`: token bucket con limite
   effettivo, capienza, ritmo, gettoni, soglia e ultima finestra nota di HofJ; `queue`: età del
   più vecchio acquisto in coda e itinerari orfani).

Il piano free spegne il servizio dopo inattività: la prima richiesta può richiedere
qualche decina di secondi. Il Postgres free scade dopo 30 giorni.

URL live: https://vela-n506.onrender.com (`GET /health`, deploy M0 verificato il 2026-09-25).

## Collegare Claude (connector MCP)

La superficie MCP è su `https://<servizio>.onrender.com/mcp` (Streamable HTTP, stateless, senza
autenticazione fino a M8). Su Render `VELA_PUBLIC_URL` deve essere l'URL pubblico del servizio:
serve al link di checkout replay ed è l'host che `/mcp` accetta (gli altri ricevono 421).

1. Verifica il servizio: `curl https://<servizio>.onrender.com/health`.
2. Solo con il servizio in replay: smoke test del flusso di spec §10.1 (nessuna chiamata a HofJ o
   Stripe; lascia un ordine di prova nel DB):
   `uv run python scripts/mcp_smoke.py https://<servizio>.onrender.com/mcp`. In live il flusso si
   prova con `scripts/rest_flow.py` (`docs/rest.md`).
3. In claude.ai: Settings → Connectors → Add custom connector, nome `Vela`, URL
   `https://<servizio>.onrender.com/mcp`, nessuna autenticazione.
4. In una chat nuova, con il connector attivo: "Vorrei un weekend di padel in Spagna a ottobre,
   siamo in due, massimo 800 euro". Dopo il sì Vela dichiara un'attesa; il link arriva con la
   domanda sullo stato. Il pagamento in replay si simula aprendo il link ricevuto; in live si paga
   il Checkout di Stripe con `4242 4242 4242 4242`.

"Troppo caro" produce sempre una proposta più economica, anche fuori dall'area chiesta
(dichiarandolo); se non ce n'è, Vela lo dice (M7).

## Struttura

```
vela/domain     modelli, parser, chooser, frasi say, ordini, casi d'uso (M2); quota, job d'acquisto, prenotazione e verifica del pagamento, processore (M5)
vela/sync.py    sync multi-brand del catalogo, scheduler e comando `python -m vela.sync` (M10); vela/fixtures.py registra le fixture
vela/ports      HofJPort, PaymentsPort, repository (M2); JobRepository, QuotaStore (M5); HofJRouter, CatalogSource (M10)
vela/adapters   db.py, repository memoria/Postgres, replay HofJ, pagamento finto (M2); HofJ HTTP e worker (M5), Stripe (M6); router per brand, catalogo da fixture (M10)
vela/surfaces   health.py, replay.py (M2), mcp.py (M3), rest.py e problems.py (M4), checkout_pages.py (M6)
vela/app.py     factory FastAPI
alembic/        migrazioni
fixtures/       catalogo registrato per replay e test, una fixture per host e brand (M1, M10)
loadtest/       Locust (M13)
tests/          python3 -m unittest discover -s tests
docs/           brief, spec, roadmap, decisioni, piani
agent-log/      trascrizioni delle sessioni con gli agenti (vedi docs/agents-log.md)
```
