# M13a — Banco di prova e numeri di partenza

## Contesto

Seconda lettura del twist (`docs/plans/2026-09-26-twist-seconda-lettura.md` §3.5, decisione
"Twist, seconda lettura" in `docs/decisions.md`): il load test deve **dimostrare un confine**, cioè
chiamate a HofJ al minuto piatte e sotto 108 con 1k, 10k e 50k viaggiatori, contro un finto HofJ
che applica le **regole di HofJ** (finestra ancorata), mai contro HofJ vero né Stripe. M13a misura
il codice di oggi (colonna "prima"); M18 corregge; M13b rilancia. Numeri cattivi sono un risultato
valido: le previsioni [previsto] della seconda lettura (deriva del contatore, ~12 acquisti/min con
4 worker) qui si confermano o si smentiscono.

Vincoli: non toccare `vela/domain/quota.py` né il `QuotaStore` (M18 in parallelo); nessuna
chiamata a HofJ, Stripe o Anthropic; nessuna nuova dipendenza (FastAPI, httpx, uvicorn e locust
ci sono già).

## Decisioni prese nell'intervista (da registrare in `docs/decisions.md`)

| Tema | Scelta |
|---|---|
| Durata di un giro | 10 min di arrivi + 5 min di coda (15 min). Chi è ancora in coda alla fine è contato, non atteso |
| Catalogo in modo `loadtest` | Sync M10 vero contro il finto (stesso percorso del live); lo scenario parte a sync finito; il sync resta nel registro del finto |
| Lancio di Locust | Servizio compose `locust` (profilo `loadtest`), stage del Dockerfile con le dipendenze dev |
| Giri della colonna "prima" | 1k, 10k, 50k puliti (finestra ancorata, latenza standard, `--background-rpm 12`, nessun guasto) + un 50k con guasti e `--latency pessimistic` |
| Marco | Come scritto: accetta a 60 s; il report dice se è confermato entro il minuto 7 e la sua posizione. Previsione a rischio: ~1.000 accettazioni davanti |
| Latenza degli altri endpoint | Uniforme 0,3-1,5 s, marcata [previsto] (acceptance.md ha solo il totale di 53 s); `pessimistic` = 2-6 s su tutti |
| 429 e quota | La chiamata respinta conta nella finestra (ipotesi pessimista, dichiarata) |
| Risposta di `POST /v1/bookings` | Come osservato su staging: `{data: "<itineraryId>"}`, upsert per `itineraryId` |

Decisioni tecniche (approvate con il piano):
- Test di contratto: `HofJHttp` usa un client httpx **sincrono**, e `httpx.ASGITransport` è solo
  asincrono. Uso il transport sincrono del `TestClient` di Starlette (wrapper in `tests/support.py`),
  quindi ASGI in-process senza porte.
- Modello aperto in Locust: uno scheduler degli arrivi nel listener `test_start` lancia un greenlet
  per viaggiatore (orari da seme fisso) con `FastHttpSession`, così le richieste finiscono nelle
  statistiche di Locust. Niente `LoadTestShape` (è a modello chiuso).
- Locale nel modo `loadtest`: quello della fixture registrata per quel brand (qualunque host), dato
  che il finto non è un host con fixture.

## Passi

### 0. Branch e documenti
- `git merge --ff-only master` su `task/m13a` (è 6 commit indietro, 0 avanti: nessuna riscrittura).
- Questo file (piano approvato il 2026-09-26) e le decisioni in `docs/decisions.md`. Commit.

### 1. Regole di quota del finto — `loadtest/fake_hofj/rules.py`
Puro, orologio iniettato. `AnchoredWindow` (60 s dalla prima chiamata dopo la scadenza, come la
sonda) e `RollingWindow` (registro scorrevole di 60 s), stessa interfaccia `admit(key, now) ->
(ok, used, window_start, window_end, retry_after)`; limite 120 per chiave; la chiamata respinta
conta. `Background(rpm)`: consumi sintetici distribuiti uniformemente sulla stessa chiave.

### 2. App del finto — `loadtest/fake_hofj/app.py`, `faults.py`, `log.py`, `__main__.py`
- FastAPI async, un processo. Stato: `ReplayHofJ(latency=(0,0), limit=None)` di
  `vela/adapters/hofj_replay.py` per itinerari, customer e pax; prodotti indicizzati per brand da
  tutte e 4 le fixture (`vela.domain.catalog.load_fixture`).
- Rotte: `GET /v1/quota`, `POST /v1/itineraries`, `GET /v1/itineraries/{id}`,
  `PUT .../customer`, `GET|PUT .../pax`, `POST /v1/bookings`, `GET /v1/products` (paginata,
  `?brand=`, `cursor`), `GET /v1/products/{id}?extended=true`, `GET /health`; fuori quota
  `/_fake/stats` e `/_fake/reset`.
- Forme reali (`docs/api/internal-checkout.md`, `quota-health.md`): envelope `{data, meta:{now}}`,
  errori RFC 7807 in `application/json`, `checkout.openAmount.amount` stringa, `pax-1` precompilato
  dal customer, 401 senza Bearer, 429 con `retryAfterSeconds` nel corpo e nessun header, prodotto
  assente per il brand → 502 `upstream-error` con `detail` "… returned 404" (mappato a
  `ProductError` da `HofJHttp`).
- Ordine per chiamata: auth → quota → guasto → latenza (`asyncio.sleep`) → esecuzione.
- Latenza: `standard` = `POST /v1/itineraries` 2-6 s, altri 0,3-1,5 s; `pessimistic` = 2-6 s ovunque.
- Guasti per endpoint con probabilità, `--fault "POST /v1/bookings=hang_then_execute:0.05"`
  ripetibile: `hang_then_execute` (esegue, poi resta appeso `--hang-seconds`, default 20 > 15 s del
  client), `hang` (appeso senza eseguire), `5xx` (503), `product_502`. Seme fisso `--seed`.
- Registro JSONL di ogni chiamata (istante, chiave, metodo, rotta, status, esito, contatore,
  finestra, `itineraryId`, latenza, origine `vela|background`).

### 3. Modo `VELA_UPSTREAM_MODE=loadtest` — `vela/app.py` (+ nota in `vela/config.py`)
- `build_hofj`: ramo `loadtest` come `live` (un `HofJHttp` per brand, `BrandRouter`, sync M10), ma
  host ammessi solo `localhost`, `127.0.0.1`, `fake-hofj` (altrimenti `RuntimeError` all'avvio).
- `build_payments`: in `loadtest` sempre `FakePayments`, anche con `STRIPE_SECRET_KEY` impostata.
- Router `/replay/checkout` montato in `replay` e `loadtest`.
- Messaggio di modo sconosciuto aggiornato; README con il nuovo valore.

### 4. Docker — `docker-compose.yml`, `Dockerfile`
- Servizi: `postgres` (16), `fake-hofj` (stessa immagine, `python -m loadtest.fake_hofj`, volume
  `loadtest/out/`), `vela` (`VELA_UPSTREAM_MODE=loadtest`, `HOFJ_BASE_URL=http://fake-hofj:8001`,
  `HOFJ_BRANDS=padel=weebora.com,tennis=terrarossa.com`, chiave e token finti dichiarati come
  tali), `locust` con profilo `loadtest`.
- Dockerfile: stage `app` (l'attuale, con `uv sync --frozen --no-dev`), stage `loadtest` da `app`
  con le dipendenze dev, stage finale `FROM app`, così Render continua a costruire l'immagine di
  oggi. `tests/test_docker_files.py` resta verde.

### 5. Scenario — `loadtest/locustfile.py`, `loadtest/scenario.py`
- `scenario.py` puro e testato: orari di arrivo (N in 10 min, seme), piano del viaggiatore (100%
  proposta, 30% "troppo caro", 20% accetta, stato ogni 30-60 s, 60% paga), frasi di intento valide
  sul catalogo di produzione con profilo (come `scripts/rest_flow.py`).
- `locustfile.py`: argomenti `--travelers`, `--arrival-minutes 10`, `--tail-minutes 5`, `--seed`;
  richieste nominate per caso d'uso (`create_intent`, `get_proposal`, `reject_proposal`,
  `accept_proposal`, `get_order_status`, `replay_checkout`); sentinelle **Marco** (accetta a 60 s,
  paga appena ha il link) e **Anna** (arriva a 360 s: proposta < 500 ms e attesa dichiarata);
  eventi JSONL per viaggiatore (arrivo, accept, attesa e posizione dichiarate, link, pagamento,
  conferma, stato finale).
- `loadtest/run.py` (comando del servizio `locust`): aspetta `/health` con catalogo sincronizzato,
  `/_fake/reset` del registro, Locust headless con `--csv`, poi `report.py`.
- Ogni giro parte da compose pulito (`docker compose down -v`), scritto nel README.

### 6. Report — `loadtest/report.py`, `loadtest/RESULTS.md`, `loadtest/README.md`
Funzioni pure sul registro del finto + eventi + CSV di Locust: massimo di chiamate in qualsiasi
60 s (Vela e totale con background); numero di 429; chiamate per endpoint e al minuto; link al
minuto; Marco pagamento → confermato; scarto p95 tra attesa dichiarata e reale; prenotazioni per
`itineraryId`; itinerari orfani (creati e mai più toccati); età della coda al minuto; p50/p95/p99
dei cinque casi d'uso. `RESULTS.md` con la colonna "prima" dei 4 giri e il confronto con le
previsioni [previsto].

### 7. Esecuzione dei giri
`docker compose up -d` + `docker compose run --rm locust --travelers 1000|10000|50000`, poi il 50k
con guasti. Circa 15 min l'uno + sync iniziale (~130 chiamate, 1-2 min). Tutto in locale; le sole
reti esterne sono i pull delle immagini Docker (uv, postgres). Nessuna chiamata a HofJ né Stripe.

## Test (`python3 -m unittest discover -s tests`, e `uv run`)
- `tests/test_fake_hofj_rules.py`: finestra ancorata ai bordi (59,999 s nella stessa finestra;
  dopo una pausa la nuova parte alla chiamata, esempio 3,8 s della sonda), scorrevole ai bordi,
  respinte contate, background.
- `tests/test_fake_hofj_app.py`: envelope e 401/429/502/503; `hang_then_execute` sul booking con
  retry del client → **un solo codice** e una sola prenotazione per `itineraryId`; `hang` senza
  effetto; `/_fake/*` fuori quota; stesso seme → stessi guasti; righe JSONL.
- `tests/test_fake_hofj_contract.py`: il vero `HofJHttp` contro il finto (transport del
  `TestClient`): carrello completo, booking, quota, `list_page`/`detail` per brand, 429 →
  `QuotaError`, 502 prodotto → `ProductError`, 503 e timeout → `UpstreamError`.
- `tests/test_app_loadtest_mode.py`: host non ammesso → errore; pagamenti finti anche con chiave
  Stripe; `/replay/checkout` montato; locale per brand.
- `tests/test_loadtest_scenario.py`, `tests/test_loadtest_report.py`: arrivi e imbuto con seme;
  massimo in 60 s, orfani, prenotazioni per itinerario, percentili, link al minuto.
- Suite esistente verde; nessun test chiama servizi esterni.

## Verifica end-to-end
1. Suite verde.
2. `docker compose up -d`; `curl localhost:8000/health` mostra il catalogo sincronizzato;
   `curl localhost:8001/_fake/stats` mostra le chiamate del sync.
3. Giro da 1k → report generato; controllo a mano di un ordine confermato nel registro del finto.
4. I 4 giri → `loadtest/RESULTS.md` compilato; `git grep` nessun segreto (chiavi del compose sono
   finte e dichiarate).

## Rischi e cose di cui non sono sicuro
- Locust in un solo processo con ~10k viaggiatori che fanno polling (~200 req/s) + Vela uvicorn a
  un worker su Docker Desktop: se Locust satura la CPU i p95 misurano il banco, non Vela. Il report
  riporterà la CPU di Locust (avviso nativo di Locust) e, se serve, si passa a master+worker.
- Marco al minuto 1 con 1.000 accettazioni davanti probabilmente non sarà confermato entro il 7:
  va scritto come previsione della §6 smentita, non corretto nello scenario.
- Il sync al boot a 120/min rallenta l'avvio di ogni giro di 1-2 min.
