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

In replay, al primo avvio con la tabella `products` vuota, l'app carica `fixtures/catalog.json`
(110 prodotti) e riprende gli ordini `paid_pending_booking`. `VELA_UPSTREAM_MODE=live` è rifiutato
fino a M5.

`GET /health` risponde `200 {"status":"ok","db":"ok"}` se il database risponde, altrimenti
`503 {"status":"degraded","db":"error"}`. Non richiede autenticazione.

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
| `VELA_UPSTREAM_MODE` | no, default `replay` | `replay` usa `fixtures/` senza chiamate esterne; `live` chiama HofJ e Stripe (da M5/M6). |
| `HOFJ_API_KEY` | in `live` | Chiave dell'API House of Journeys. |
| `HOFJ_BASE_URL` | in `live` | Base URL dell'API HofJ. |
| `HOFJ_BRAND` | in `live` | Brand/canale di distribuzione HofJ. |
| `STRIPE_SECRET_KEY` | per Stripe reale | Chiave segreta Stripe (account di test). Se impostata, i link di pagamento sono Checkout Session reali (M6), anche con HofJ in replay; vedi `docs/stripe.md`. |
| `STRIPE_WEBHOOK_SECRET` | con `STRIPE_SECRET_KEY` | Segreto per verificare la firma dei webhook su `/webhooks/stripe`. Senza, con la chiave impostata l'app non parte. |
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
3. Inserire nella dashboard le variabili marcate `sync: false` che servono alla modalità in uso
   (per M0 basta `VELA_UPSTREAM_MODE=replay`, già nel file).
4. Nel log del deploy compare `Running upgrade  -> 0001`: le migrazioni sono state applicate.
5. `curl https://<servizio>.onrender.com/health` → `{"status":"ok","db":"ok","catalog":{...},"quota":null}`
   (`catalog`: numero di prodotti, `fetched_at`, `age_seconds`; `quota` arriva con M5).

Il piano free spegne il servizio dopo inattività: la prima richiesta può richiedere
qualche decina di secondi. Il Postgres free scade dopo 30 giorni.

URL live: https://vela-n506.onrender.com (`GET /health`, deploy M0 verificato il 2026-09-25).

## Collegare Claude (connector MCP)

La superficie MCP è su `https://<servizio>.onrender.com/mcp` (Streamable HTTP, stateless, senza
autenticazione fino a M8). Su Render `VELA_PUBLIC_URL` deve essere l'URL pubblico del servizio:
serve al link di checkout replay ed è l'host che `/mcp` accetta (gli altri ricevono 421).

1. Verifica il servizio: `curl https://<servizio>.onrender.com/health`.
2. Smoke test del flusso di spec §10.1 (solo replay, nessuna chiamata a HofJ o Stripe; lascia un
   ordine di prova nel DB):
   `uv run python scripts/mcp_smoke.py https://<servizio>.onrender.com/mcp`
3. In claude.ai: Settings → Connectors → Add custom connector, nome `Vela`, URL
   `https://<servizio>.onrender.com/mcp`, nessuna autenticazione.
4. In una chat nuova, con il connector attivo: "Vorrei un weekend di padel in Spagna a ottobre,
   siamo in due, massimo 800 euro". Il pagamento in replay si simula aprendo il link ricevuto.

In replay "troppo caro" produce una proposta diversa ma non necessariamente più economica:
l'interpretazione del motivo del rifiuto arriva con M9.

## Struttura

```
vela/domain     modelli, parser, chooser, frasi say, ordini, casi d'uso (M2)
vela/ports      HofJPort, PaymentsPort, repository (M2)
vela/adapters   db.py, repository memoria/Postgres, replay HofJ, pagamento finto, runner (M2); HofJ HTTP (M5), Stripe (M6)
vela/surfaces   health.py, replay.py (M2), mcp.py (M3), rest.py e problems.py (M4), webhook (M6)
vela/app.py     factory FastAPI
alembic/        migrazioni
fixtures/       catalogo registrato per la modalità replay (M1)
loadtest/       Locust (M13)
tests/          python3 -m unittest discover -s tests
docs/           brief, spec, roadmap, decisioni, piani
agent-log/      trascrizioni delle sessioni con gli agenti (vedi docs/agents-log.md)
```
