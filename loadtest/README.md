# Load test

Il test lancia N viaggiatori divisi in quattro gruppi (solo sito, proposta, link senza pagare,
pagamento) e verifica un confine: le chiamate di Vela a HofJ in qualsiasi intervallo di 60 s
restano sotto 108 (120 × 0,9). Gira tutto in
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

Il giro di `RESULTS.md`: 10.000 viaggiatori in 5 minuti + 3 di coda, 50% naviga solo il sito,
30% chiede la proposta, 18% arriva al link senza pagare, paga il resto (2%).

```sh
docker compose up -d --build
docker compose run --rm locust --travelers 10000 --browse 50 --proposal 30 --link 18 \
    --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k
docker compose down -v        # ogni giro parte da DB, coda e quota pulite
python loadtest/projection.py --rate <link/min misurati> --sizes 10000,50000
```

| Opzione di `run.py` | Default | Cosa fa |
|---|---|---|
| `--travelers` | 10000 | viaggiatori in arrivo (più le due sentinelle) |
| `--browse` | 50 | % che naviga solo il sito: contato, nessuna richiesta a Vela (la landing è statica e separata) |
| `--proposal` | 30 | % che fa `create_intent` e `get_proposal` e si ferma |
| `--link` | 18 | % che accetta, conferma il prezzo, arriva al link e non paga |
| (resto) | 2 | % che paga: 100 − le tre sopra; somma oltre 100 → errore prima del giro |
| `--duration` | 10 | minuti dell'intero giro, arrivi + coda (2/3 e 1/3 se non si divide a mano) |
| `--arrival-minutes`, `--tail-minutes` | — | la divisione a mano; la somma non supera `--duration` |
| `--seed` | 13 | seme di arrivi, gruppi e frasi |
| `--label` | `<N>` | nome del giro e della sua cartella |

I gruppi hanno numeri esatti (10.000 al 50/30/18 → 5.000, 3.000, 1.800, 200), mescolati con il
seme lungo tutta la finestra degli arrivi; il comando li stampa prima di partire. Se sulla
macchina gira già un altro stack del banco (porte 8000/8001 occupate), si usa un nome di progetto
diverso (`docker compose -p <nome>`) e un override che toglie `ports:` dai servizi.

`run.py` aspetta che `/health` di Vela abbia tutto il catalogo delle fixture dei brand (190 prodotti al 2026-09-27, caricati al boot),
lancia Locust, poi scrive in `loadtest/out/<label>/` (ignorata da git):

- `report.md`, `report.json`: le misure del giro, con una tabella per gruppo (quanti hanno avuto
  la proposta, il link, pagato, confermato, raggiunto l'esito del gruppo, ancora in corso);
- `calls.jsonl`, `fake_stats.json`: il registro del finto, da cui vengono le misure sulla quota;
- `travelers.jsonl`: una riga per viaggiatore (gruppo, arrivo, accettazione, attesa dichiarata,
  link, pagamento, conferma, esito);
- `locust_stats.csv` e compagni: p50/p95/p99 dei casi d'uso.

Dopo una modifica a `vela/` serve `docker compose --profile loadtest build`. Il report di un giro
già fatto si rigenera con `python loadtest/report.py`.

`loadtest/projection.py` porta il giro a più viaggiatori con gli stessi gruppi (modello a coda
satura, `--rate` = link al minuto misurati a regime); opzioni `--browse`, `--proposal`, `--link`,
`--minutes`, `--tail-minutes`, `--sizes`, `--json`.

## Scenario (modello aperto)

Gli arrivi sono fissati dallo scenario (`loadtest/scenario.py`, seme fisso), non dalle risposte di
Vela. Esiti per gruppo nel `travelers.jsonl`: `site_only`, `proposal_only`, `link_unpaid`,
`confirmed`; chi è ancora in coda alla fine è `open_<stato>`. Nessuno dice "troppo caro". Chi ha
accettato chiede lo stato ogni 30-60 s. Due sentinelle in più, fuori dai gruppi: **Marco** accetta
a 60 s e paga appena ha il link; **Anna** arriva al 60% della finestra degli arrivi, rifiuta e
accetta. Entrambe chiedono lo stato ogni 5 s.

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

Un giro con guasti (non in `RESULTS.md`), per esempio:

```sh
FAKE_HOFJ_LATENCY=pessimistic \
FAKE_HOFJ_FAULTS="POST /v1/itineraries=hang_then_execute:0.03;POST /v1/itineraries=5xx:0.02;POST /v1/bookings=hang_then_execute:0.05;GET /v1/itineraries/{id}=5xx:0.02" \
docker compose up -d --build
docker compose run --rm locust --travelers 10000 --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k-guasti
```

## Note

- Chiave HofJ e token REST del compose (`loadtest-key`, `loadtest-token`) sono finti.
- `OPENSSL_armcap=0` evita un SIGILL di OpenSSL su Apple M4 dentro Docker Desktop.
- Test del banco: `uv run python -m unittest discover -s tests -p "test_*loadtest*"` e
  `-p "test_fake_hofj_*"`.
