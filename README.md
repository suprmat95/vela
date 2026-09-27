# Vela

Vela vende viaggi di padel e tennis con hotel a partire da una sola frase. Il viaggiatore la dice
all'assistente che usa già (Claude via MCP, un agente vocale ElevenLabs o un client REST), per
esempio "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro". Vela propone
**un** viaggio alla volta, mai una lista. Se il viaggiatore lo rifiuta ("troppo caro", "altre
date") ne propone un altro. Se lo accetta, manda il link di pagamento, prenota su House of
Journeys (HofJ) e restituisce il codice di prenotazione.

Tutto il prodotto sta in cinque casi d'uso (`vela/domain/usecases.py`): `create_intent`,
`get_proposal`, `reject_proposal`, `accept_proposal`, `get_order_status`. Requisiti in
`docs/spec.md`, decisioni in `docs/decisions.md`, architettura in `ARCHITECTURE.md`, riferimento
operativo (variabili d'ambiente, worker, Docker, deploy, landing) in `docs/operations.md`.

## Collegare Claude

Vela espone i cinque casi d'uso come tool MCP su `/mcp` (Streamable HTTP, stateless). Il servizio
pubblico è `https://vela-n506.onrender.com/mcp`.

1. In claude.ai: Settings → Connectors → Add custom connector.
2. Nome `Pacchetti Viaggio di Padel Tennis`, URL `https://vela-n506.onrender.com/mcp`, nessuna
   autenticazione.
3. In una chat nuova, con il connector attivo, scrivi per esempio: "Vorrei un weekend di padel in
   Spagna a ottobre, siamo in due, massimo 800 euro".

Claude chiama `create_intent` e `get_proposal` e ripete la frase `say` di Vela. Ogni modifica
richiesta passa da `reject_proposal`. Dopo il sì l'ordine va in coda: Vela dichiara un'attesa e il
link di pagamento arriva quando si chiede lo stato (`get_order_status`). In replay il pagamento si
simula aprendo il link; in live si paga il Checkout di Stripe con la carta di test
`4242 4242 4242 4242`.

Per un'istanza tua: `VELA_PUBLIC_URL` deve essere l'URL pubblico del servizio, perché oltre a
`localhost` è l'unico host che `/mcp` accetta (gli altri ricevono 421). Con il servizio in replay puoi provare il flusso
senza Claude (nessuna chiamata a HofJ o Stripe, lascia un ordine di prova nel DB):

```bash
uv run python scripts/mcp_smoke.py https://<servizio>/mcp
```

La superficie REST (`/v1`, bearer `VELA_API_TOKEN`) è descritta in `docs/rest.md`.

## Avvio in locale

Servono [uv](https://docs.astral.sh/uv/), che installa anche Python 3.12, e un Postgres
(anche usa e getta: `docker run -d --rm -e POSTGRES_USER=vela -e POSTGRES_PASSWORD=vela -p 5432:5432 postgres:16`).
Il modo predefinito è
`replay`: il catalogo viene da `fixtures/`, il pagamento è simulato e non parte nessuna chiamata
esterna.

```bash
uv sync                                    # .venv con Python 3.12 e le dipendenze di uv.lock
export DATABASE_URL=postgresql://vela:vela@localhost:5432/vela
uv run alembic upgrade head                # migrazioni
uv run uvicorn vela.app:app --reload       # http://127.0.0.1:8000
curl -s localhost:8000/health              # {"status":"ok","db":"ok",...}
```

Claude.ai non raggiunge `localhost`: in locale il flusso si prova con
`uv run python scripts/mcp_smoke.py http://localhost:8000/mcp` (lo stesso host dei link di
pagamento, `http://localhost:8000` se `VELA_PUBLIC_URL` non è impostata) oppure via REST
(`export VELA_API_TOKEN=...` prima di `uvicorn`, poi i comandi di `docs/rest.md`).

Test e lint (entrambi devono passare prima di un commit):

```bash
uv run python3 -m unittest discover -s tests   # i test Postgres girano solo con DATABASE_URL
uv run ruff check .
```

Modi `live` e `loadtest`, variabili d'ambiente e Docker sono in `docs/operations.md`.

## Load test

Il load test verifica che, con migliaia di viaggiatori, le chiamate di Vela a HofJ in qualsiasi
intervallo di 60 s restino sotto 108 (il limite di 120 al minuto meno il 10% di margine). Gira
tutto in locale con Docker Compose: Postgres, Vela in modo `loadtest`, un finto HofJ con le
regole di quota e latenza di quello vero, e Locust. **Non tocca mai HofJ vero, Render o Stripe.**

```bash
docker compose up -d --build
docker compose run --rm locust --travelers 10000 --browse 50 --proposal 30 --link 18 \
    --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k
docker compose down -v        # ogni giro riparte con DB, coda e quota puliti
uv run python loadtest/projection.py --rate <link/min misurati> --sizes 10000,50000
```

Il giro aspetta che Vela abbia caricato tutto il catalogo, lancia Locust e scrive il report in
`loadtest/out/<label>/` (`report.md`, `report.json`, `travelers.jsonl`, `calls.jsonl`, statistiche
di Locust). Dopo una modifica a `vela/` serve `docker compose --profile loadtest build`. Risultati
del giro da 10.000 in `loadtest/RESULTS.md`, dettagli in `loadtest/README.md`.

### Il funnel

Ogni viaggiatore sta in uno solo di quattro gruppi. Le percentuali si danno per i primi tre;
il quarto è il resto fino a 100.

| Gruppo | Opzione | Default | Cosa fa | Esito |
|---|---|---|---|---|
| Solo sito | `--browse` | 50 | Naviga la landing, che è statica e separata: viene contato ma non fa richieste a Vela | `site_only` |
| Proposta | `--proposal` | 30 | `create_intent` e `get_proposal`, poi si ferma | `proposal_only` |
| Link | `--link` | 18 | Accetta, conferma il prezzo, arriva al link di pagamento e non paga | `link_unpaid` |
| Pagamento | (resto) | 2 | Accetta, conferma il prezzo, paga e aspetta la conferma della prenotazione | `confirmed` |

- I gruppi hanno numeri esatti: 10.000 al 50/30/18 danno 5.000, 3.000, 1.800 e 200. Il comando li
  stampa prima di partire; se le tre percentuali sommano più di 100 si ferma con un errore.
- Gli arrivi sono uniformi nella finestra degli arrivi e i gruppi sono mescolati con il seme:
  lo scenario non dipende dalle risposte di Vela (modello aperto).
- Chi ha accettato chiede lo stato ogni 30-60 s. Nessuno del funnel rifiuta. Chi alla fine è
  ancora in coda risulta `open_<stato>`.
- Due sentinelle in più, fuori dai gruppi, chiedono lo stato ogni 5 s: **Marco** arriva a 55 s,
  accetta a 60 s e paga appena ha il link; **Anna** arriva al 60% della finestra degli arrivi,
  rifiuta con "troppo caro" e accetta la proposta successiva.

### Opzioni del giro (`loadtest/run.py`)

| Opzione | Default | Cosa fa |
|---|---|---|
| `--travelers` | 10000 | Viaggiatori in arrivo (più le due sentinelle) |
| `--browse` | 50 | % del gruppo "solo sito" |
| `--proposal` | 30 | % del gruppo "proposta" |
| `--link` | 18 | % del gruppo "link"; paga il resto (100 − le tre) |
| `--duration` | 10 | Minuti dell'intero giro, arrivi + coda |
| `--arrival-minutes` | 2/3 di `--duration` | Minuti in cui arrivano i viaggiatori |
| `--tail-minutes` | il resto di `--duration` | Minuti di coda dopo l'ultimo arrivo; con `--arrival-minutes` la somma non supera `--duration` |
| `--seed` | 13 | Seme di arrivi, gruppi e frasi |
| `--label` | `<travelers>` | Nome del giro e della sua cartella in `loadtest/out/` |
| `--vela` | `$VELA_URL` o `http://vela:8000` | URL di Vela |
| `--fake` | `$FAKE_HOFJ_URL` o `http://fake-hofj:8001` | URL del finto HofJ |
| `--brands` | `weebora.com,terrarossa.com` | Brand delle fixture da cui si conta il catalogo atteso |
| `--calls` | `loadtest/out/calls.jsonl` | Registro delle chiamate del finto (volume condiviso) |
| `--out` | `loadtest/out` | Cartella dei report |

### Il finto HofJ

Si configura con variabili d'ambiente passate a `docker compose up`:

| Variabile | Default | Valori |
|---|---|---|
| `FAKE_HOFJ_WINDOW` | `anchored` | `anchored` (60 s dalla prima chiamata dopo la scadenza, come HofJ), `rolling` (ultimi 60 s) |
| `FAKE_HOFJ_LATENCY` | `standard` | `standard` (2-6 s su `POST /v1/itineraries`, 0,3-1,5 s sugli altri), `pessimistic` (2-6 s ovunque), `none` |
| `FAKE_HOFJ_BACKGROUND_RPM` | `12` | Chiamate al minuto di altri usi della stessa chiave (il margine del 10%) |
| `FAKE_HOFJ_FAULTS` | vuota | Guasti `<METODO path>=<tipo>:<probabilità>` separati da `;` |
| `FAKE_HOFJ_SEED` | `13` | Seme di guasti e latenze |

Tipi di guasto: `hang_then_execute` (l'effetto avviene, ma la risposta resta appesa 20 s, oltre il
timeout di 15 s del client), `hang` (appeso senza effetto), `5xx` (503), `product_502` (502 di
prodotto). Una chiamata respinta con 429 conta comunque nella finestra. Esempio di giro con
guasti:

```bash
FAKE_HOFJ_LATENCY=pessimistic \
FAKE_HOFJ_FAULTS="POST /v1/itineraries=hang_then_execute:0.03;POST /v1/bookings=hang_then_execute:0.05" \
docker compose up -d --build
docker compose run --rm locust --travelers 10000 --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k-guasti
```

### Proiezione (`loadtest/projection.py`)

Porta un giro misurato a più viaggiatori con lo stesso funnel, con un modello a coda satura.

| Opzione | Default | Cosa fa |
|---|---|---|
| `--rate` | obbligatoria | Link di pagamento al minuto misurati a regime |
| `--minutes` | 5 | Minuti di arrivi |
| `--tail-minutes` | 3 | Minuti di coda |
| `--browse`, `--proposal`, `--link` | 50, 30, 18 | Il funnel, come in `run.py` |
| `--sizes` | `10000,50000` | Numeri di viaggiatori da proiettare, separati da virgola |
| `--json` | no | Stampa il risultato in JSON |
