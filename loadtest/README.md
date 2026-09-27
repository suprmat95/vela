# Load test del twist (M13a, M13b)

Il test dimostra un confine: con 1.000, 10.000 e 50.000 viaggiatori in dieci minuti, le chiamate
di Vela a HofJ in qualsiasi intervallo di 60 s restano sotto 108 (120 × 0,9). Gira tutto in
locale con Docker: **mai contro HofJ vero, mai contro Render, mai Stripe**. Contesto:
`docs/plans/2026-09-26-twist-seconda-lettura.md` §3.5, decisioni in `docs/decisions.md`
("Twist, seconda lettura" e "M13a: banco di prova"). Risultati in `loadtest/RESULTS.md`.

## Cosa gira

| Servizio | Cosa fa |
|---|---|
| `fake-hofj` | Finto HofJ HTTP (`loadtest/fake_hofj`) con le **regole di HofJ**: quota di 120/min per chiave con finestra ancorata (come misurato, `docs/api/quota-health.md`), latenza 2-6 s su `POST /v1/itineraries`, guasti a richiesta, registro JSONL di ogni chiamata |
| `vela` | Vela in `VELA_UPSTREAM_MODE=loadtest`: HofJ via HTTP verso il finto (rifiuta ogni host diverso da `fake-hofj`/`localhost`), pagamenti finti, `GET /replay/checkout/{id}` per pagare. Il catalogo parte dalle fixture dei brand (le stesse del finto): lo scheduler del sync resta ma lo trova fresco |
| `postgres` | Postgres 16 locale |
| `locust` | Profilo `loadtest`: `loadtest/run.py` aspetta il catalogo, lancia Locust e scrive il report |

## Un giro

```sh
docker compose up -d --build
docker compose run --rm locust --travelers 1000 --label 1k --duration 10
docker compose down -v        # ogni giro parte da DB, coda e quota pulite
```

`run.py` aspetta che `/health` di Vela abbia tutto il catalogo (126 prodotti, caricati al boot),
lancia Locust per `--duration` minuti (default 10: 2/3 di arrivi, 1/3 di coda), poi scrive in
`loadtest/out/<label>/` (ignorata da git):

- `report.md`, `report.json`: le misure del giro;
- `calls.jsonl`, `fake_stats.json`: il registro del finto, da cui vengono le misure sulla quota;
- `travelers.jsonl`: una riga per viaggiatore (arrivo, accettazione, attesa dichiarata, link,
  pagamento, conferma, esito);
- `locust_stats.csv` e compagni: p50/p95/p99 dei casi d'uso.

Opzioni di `run.py`: `--travelers`, `--label`, `--duration` (minuti dell'intero giro, default 10),
`--arrival-minutes` e `--tail-minutes` per dividerlo a mano (la somma non supera `--duration`),
`--seed` (13). Anna arriva al 60% della finestra degli arrivi, Marco a 55 s.

I giri di `RESULTS.md` (colonne "prima", M13a, e "dopo", M13b) sono cinque, tutti con
`--duration 8 --arrival-minutes 5 --tail-minutes 3` e un `docker compose down -v` tra l'uno e
l'altro: A-500, B-1000, C-2500 (`--travelers` 500, 1000, 2500), D-1000-guasti (sotto) ed
E-1000-rolling (`FAKE_HOFJ_WINDOW=rolling`). Il giro con la cache del prezzo (RF-84, 2026-09-27) è C-2500 con gli stessi parametri e
`--label 2500-cache`. Dopo una modifica a `vela/` serve
`docker compose --profile loadtest build`. Il report di un giro già fatto si rigenera con `python loadtest/report.py`.

## Scenario (modello aperto)

Gli arrivi sono fissati dallo scenario (`loadtest/scenario.py`, seme fisso), non dalle risposte di
Vela: 100% riceve una proposta, 30% dice "troppo caro", 20% accetta, chi ha accettato chiede lo
stato ogni 30-60 s, 60% di chi riceve il link paga. Due sentinelle in più: **Marco** accetta a
60 s e paga appena ha il link; **Anna** arriva al minuto 6, rifiuta e accetta.

Con la cache del prezzo (RF-84) chi accetta un viaggio già prezzato riceve subito
`200 awaiting_confirmation`: il viaggiatore finto lo tratta come un prezzo arrivato e conferma al
primo giro di polling.

## Il finto HofJ

Variabili del compose (o opzioni di `python -m loadtest.fake_hofj`):

| Variabile | Default | Valori |
|---|---|---|
| `FAKE_HOFJ_WINDOW` | `anchored` | `anchored` (60 s dalla prima chiamata dopo la scadenza), `rolling` (ultimi 60 s) |
| `FAKE_HOFJ_LATENCY` | `standard` | `standard` (2-6 s su `POST /v1/itineraries`, 0,3-1,5 s sugli altri), `pessimistic` (2-6 s ovunque), `none` |
| `FAKE_HOFJ_BACKGROUND_RPM` | `12` | chiamate al minuto degli altri usi della stessa chiave (il margine del 10%) |
| `FAKE_HOFJ_FAULTS` | vuota | guasti separati da `;`, es. `POST /v1/bookings=hang_then_execute:0.05` |
| `FAKE_HOFJ_SEED` | `13` | seme di guasti e latenze |

Tipi di guasto: `hang_then_execute` (l'effetto avviene, la risposta resta appesa 20 s, oltre il
timeout di 15 s del client), `hang` (appeso senza effetto), `5xx` (503), `product_502` (502 di
prodotto). Una chiamata respinta con 429 conta nella finestra (ipotesi pessimista).
`GET /_fake/stats` e `POST /_fake/reset` non consumano quota.

Il giro con guasti di `RESULTS.md`:

```sh
FAKE_HOFJ_LATENCY=pessimistic \
FAKE_HOFJ_FAULTS="POST /v1/itineraries=hang_then_execute:0.03;POST /v1/itineraries=5xx:0.02;POST /v1/bookings=hang_then_execute:0.05;GET /v1/itineraries/{id}=5xx:0.02" \
docker compose up -d --build
docker compose run --rm locust --travelers 50000 --label 50k-guasti
```

## Note

- Chiave HofJ e token REST del compose (`loadtest-key`, `loadtest-token`) sono finti.
- `OPENSSL_armcap=0` evita un SIGILL di OpenSSL su Apple M4 dentro Docker Desktop.
- Test del banco: `uv run python -m unittest discover -s tests -p "test_*loadtest*"` e
  `-p "test_fake_hofj_*"`.
