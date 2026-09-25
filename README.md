# Vela

Vela permette a un viaggiatore di comprare un viaggio di padel o tennis con hotel esprimendo
un solo intento, a parole sue, all'assistente che usa già (Claude via MCP, un agente vocale
ElevenLabs, o un client REST). Non ha una homepage e non mostra liste: propone un viaggio alla
volta, lo prenota sull'API House of Journeys e restituisce il codice di prenotazione.
Requisiti in `docs/spec.md`, roadmap in `docs/roadmap.md`, decisioni in `docs/decisions.md`.

Stato: M0 (fondamenta). L'app espone solo `GET /health`.

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
| `STRIPE_SECRET_KEY` | in `live` | Chiave segreta Stripe (account di test). |
| `STRIPE_WEBHOOK_SECRET` | in `live` | Segreto per verificare la firma dei webhook Stripe. |
| `VELA_API_TOKEN` | da M4 | Bearer token statico delle superfici REST e MCP. |
| `VELA_PUBLIC_URL` | da M6 | URL pubblico di Vela, usato per i ritorni da Stripe. |
| `ANTHROPIC_API_KEY` | no | Se presente abilita il fallback Claude Haiku per gli intenti non capiti dal parser. |

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
5. `curl https://<servizio>.onrender.com/health` → `{"status":"ok","db":"ok"}`.

Il piano free spegne il servizio dopo inattività: la prima richiesta può richiedere
qualche decina di secondi. Il Postgres free scade dopo 30 giorni.

URL live: da compilare dopo il primo deploy.

## Struttura

```
vela/domain     casi d'uso e modelli (M2)
vela/ports      interfacce verso HofJ e Stripe (M2)
vela/adapters   implementazioni: db.py, HofJ, Stripe, replay (M2, M5, M6)
vela/surfaces   health.py, REST (M4), MCP (M3), webhook (M6)
vela/app.py     factory FastAPI
alembic/        migrazioni
fixtures/       catalogo registrato per la modalità replay (M1)
loadtest/       Locust (M13)
tests/          python3 -m unittest discover -s tests
docs/           brief, spec, roadmap, decisioni, piani
agent-log/      trascrizioni delle sessioni con gli agenti (vedi docs/agents-log.md)
```
