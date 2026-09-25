# M5 — HofJ reale: coda d'acquisto, scheduler della quota, prenotazione: piano di esecuzione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m5`. Destinazione di questo file: `docs/plans/2026-09-25-m5-hofj-reale.md`.

**Goal:** l'accettazione diventa asincrona (RF-45): risponde subito `queued` con posizione e attesa stimata; un job d'acquisto a passi ripartibili crea itinerario, cliente, pax, legge il totale reale e produce il link (RF-46); uno scheduler della quota in Postgres a tre classi (`booking` con riserva, `purchase` FIFO, `sync`) garantisce che nessuna chiamata a HofJ parta senza budget (RF-36..38, RF-47); un worker a thread in ogni istanza preleva i job con `FOR UPDATE SKIP LOCKED` (RF-50) ed esegue anche la prenotazione con retry (RF-23, RF-24, RF-51); l'adapter HTTP verso HofJ esiste ed è verificato contro staging.

**Architecture:** regole pure nel dominio (`quota.py`, `purchase.py`, `booking.py`, `jobs.py`), due porte nuove (`JobRepository`, `QuotaStore`) con implementazione in memoria e Postgres sotto un contratto di test condiviso, un `Worker` a thread negli adapter al posto di `BookingRunner`/`InlineRunner`, un adapter `hofj_http.py` su httpx. Le superfici MCP e REST cambiano solo nel contratto di `accept_proposal` e `get_order_status`. Il modo `live` resta rifiutato all'avvio finché M6 non porta i pagamenti Stripe.

**Tech Stack:** Python 3.12 (`uv run python`), FastAPI, SQLAlchemy Core, psycopg 3, Alembic, httpx (già in dipendenze), `unittest`. Nessuna dipendenza nuova, nessuna variabile d'ambiente nuova.

**Spec:** `docs/spec.md` (§4.3, §4.5, §4.7, §4.8, §4.10, §8, RNF-04), `docs/roadmap.md` M5, `docs/decisions.md` ("Roadmap in macro task", "Twist"), `docs/api/internal-checkout.md`, `docs/api/differences.md`, `docs/api/quota-health.md`. Il design approvato nell'intervista è la sezione "Design" qui sotto.

## Contesto

- Esiste già (da M2/M3/M4/M11):
  - `Vela` in `vela/domain/usecases.py`: accept sincrono (L104-143), `_propose` (L79), `_accepted` (L145), `get_order_status` (L154).
  - `OrderService` in `vela/domain/orders.py`: `mark_paid`, `complete_booking` senza retry, `pending_booking_ids`.
  - `BookingRunner`/`InlineRunner` in `vela/adapters/background.py`.
  - `HofJPort` e gli errori `HofJError`/`ProductError`/`QuotaError`/`UpstreamError` in `vela/ports/hofj.py`.
  - `ReplayHofJ` in `vela/adapters/hofj_replay.py` e `FakePayments` in `vela/adapters/stripe_fake.py`.
  - `MemoryRepositories`/`PostgresRepositories`, `schema.py`, migrazioni `0001` e `0002`.
  - `OrderStatus` (5 stati), `AcceptResponse`, `OrderStatusResponse`, `ProposalMade(replaced=...)` in `vela/domain/models.py`.
  - `say.py`, con `say_accept` e `say_status`.
  - `choose(products, criteria, rejected_ids, today)` in `vela/domain/chooser.py`, che filtra `bookable`.
  - `Settings` in `vela/config.py`.
  - `build_vela`, `bootstrap` e `lifespan` in `vela/app.py`.
  - `/health`, con `quota: None` fisso.
  - La route replay `/replay/checkout/{order_id}`, che chiama `runner.submit`.
- Helper di test esistenti:
  - `tests/support.py`: `NOW`, `TODAY`, `make_product`, `FakeHofJ` (che registra `.calls`), `StubPayments`, `assert_single_product`, `assert_problem`.
  - `tests/repo_contract.py` con `RepositoryContract`, eseguito da `test_repo_memory.py` e `test_repo_postgres.py` (schema `vela_test`, `skipUnless(DATABASE_URL)`).
  - Un `Clock` locale in ogni file di test.
- Test legati al contratto sincrono, da aggiornare:
  - `test_usecases.py`: `AcceptProposalTest`, `OrderStatusTest`, `FullReplayFlowTest`.
  - `test_orders.py`: `CompleteBookingTest`, `RunnerTest`.
  - `test_mcp_tools.py`: `test_full_flow_section_10_1`.
  - `test_rest.py`: accept e `FullFlowTest`.
  - `test_app_replay.py`: `test_live_with_database_is_refused`, che cerca `"M5"`.
  - `test_migrations.py`: head `"0002"`.
- Interprete: `uv run python` (3.12). Suite: `uv run python -m unittest discover -s tests`. Prima di iniziare, annotare il numero di test di partenza.
- Parallelismo: M6 (Stripe) tocca `vela/domain/orders.py` e forse aggiunge anch'essa una migrazione `0003`. Chi mergia per secondo fa rebase e rinumera la propria migrazione.

## Decisioni prese nell'intervista (da riportare in `docs/decisions.md`, Task 0)

| Decisione | Scelta | Motivo |
|---|---|---|
| Ambiente delle verifiche §8 e di M7 | Staging: `staging.api.hofj.com`, brand `staging.weebora.com`, un prodotto di staging (es. 118) invece di `t0054825` | È l'unico ambiente dove i carrelli sono già stati verificati; un booking non crea una prenotazione reale |
| Budget delle verifiche §8 | ≤ 8 chiamate HofJ: quota, POST itinerary, PUT customer, GET pax, PUT pax, GET itinerary, POST booking, più 1 di margine | Il booking (§8 riga 3) richiede il carrello completo; con meno chiamate la risposta resterebbe ambigua. La riga 2 è già coperta da M1 e la riga 5 è M12 |
| `paymentIntentId` per la verifica del booking | Lo crea l'agente con 1 chiamata Stripe in modalità test (`PaymentIntent` confermato con `pm_card_visa`), `STRIPE_SECRET_KEY` da env | Nessuna dipendenza da operazioni manuali in dashboard |
| Momento delle verifiche §8 | Task 1 del piano, manuale con l'utente; l'adapter HTTP (Task 15) parte dalle forme reali | Le forme reali arrivano prima di scrivere l'adapter; il resto procede con porte in memoria |
| Modello della finestra di quota | Finestra fissa di 60 s allineata a HofJ: `window_start`/`window_end` da `/v1/quota` al boot e dopo un 429, poi avanza di 60 s col nostro orologio | È il comportamento osservato su HofJ (finestra ancorata alla prima richiesta) e si realizza con una riga e un `UPDATE` atomico |
| Margine di sicurezza sul limite | Configurabile, default 10%: limite effettivo = floor(`limitPerMinute` × 0,9) = 108 | La chiave è condivisa con script ed esplorazioni |
| Riserva `booking` e formula dell'attesa | Riserva = floor(limite effettivo × 0,20) = 21; acquisti per finestra = (108 − 21) ÷ 5 = 17,4 | Coerenti con il margine: la formula usa il limite effettivo |
| Parametri "configurabili" | Campi di `Settings` con default, senza variabili d'ambiente nuove | L'elenco delle variabili d'ambiente di §6 resta chiuso; M13 imposta i valori nel proprio setup |
| Retry della prenotazione (RF-24) | 5 tentativi, attese di 5, 10, 20 e 40 s tra un tentativo e l'altro, solo su rete, timeout o 5xx; un 4xx porta subito a `booking_failed` | Circa 75 s in totale, vicino a RF-51 |
| Errore "del prodotto" (RF-17, RF-33) | Solo su `POST /v1/itineraries`: 400/404, oppure 502 il cui `detail` riporta un errore upstream 4xx/500 che non sia un timeout. Timeout, rete e altri 5xx sono errori di rete (retry). 401/403 sono errori di configurazione (`failed`, prodotto non marcato) | HofJ risponde 502 sia per un id sbagliato sia per un guasto; non si vogliono marcare prodotti buoni per 24 h |
| Posizione dopo una sostituzione | Il nuovo ordine eredita l'`enqueued_at` dell'ordine sostituito | FIFO per `enqueued_at`: passa davanti a chi è arrivato dopo, senza priorità speciali |
| Rinuncia (RF-49) esteso | Ordine `queued`, in lavorazione o `awaiting_payment` → `cancelled`, e si restituisce la proposta successiva; il job si ferma al passo seguente; l'itinerario HofJ resta orfano. Dopo il pagamento l'ordine non si tocca | Un rifiuto è sempre rispettato finché non c'è denaro in gioco |
| Pagamento in M5 | Il job usa `PaymentsPort`. `VELA_UPSTREAM_MODE=live` rifiuta l'avvio finché M6 non c'è (il `RuntimeError` cita M6) | Scostamento dalla roadmap («con live tutto avviene contro HofJ vero»): la prova reale di M5 passa da Task 1 e dai test con `MockTransport` |
| Esecuzione del worker | N thread per processo (default 4) con polling di 1 s sulla tabella `jobs`; un job `running` con lease scaduto (2 min) torna prelevabile | Il dominio è sincrono; il lease copre RF-27 anche con più istanze |
| Blocco di quota per job | Un acquisto prenota le chiamate HofJ dei passi che restano (nuovo job: 5); una prenotazione ne prenota 1 | Non si spreca budget su retry e riprese; la formula dell'attesa resta a 5 |
| Posizione in coda | Parte da 1 e conta solo i `purchase` in stato `pending` con `enqueued_at` precedente; `wait_seconds = ceil(pos × 60 ÷ acquisti_per_finestra)`; `say` arrotonda i minuti per eccesso, minimo 1 | Stima semplice e spiegabile |
| Contratto delle risposte | Accept: `{order_id, status, position, wait_seconds, say}`. Status: `{order_id, status, position, wait_seconds, total, currency, price_from_total, total_differs, payment_url, booking_code, failure_reason, proposal_changed, proposal, say}`, con `null` quando non pertinente | Forma stabile per MCP, REST e test |
| REST accept | 202 Accepted, outcome `order_queued`, header `Location: /v1/orders/{id}`; un doppio accept risponde 200 `order_status` con lo stato attuale | Semantica HTTP corretta per il lavoro asincrono |

## Modifiche dopo le verifiche di §8 (Task 1, 2026-09-25)

Il Task 1 è stato eseguito su staging (`docs/decisions.md`, "M5: verifiche di spec §8"). Queste
regole prevalgono sul resto del piano dove differiscono:

- **Importo del link = `checkout.openAmount`**, non `checkout.total`. DOCS: `paymentType: "full"`
  addebita "the entire open amount". `get_itinerary` legge `Itinerary(total=openAmount)`;
  `checkout.total` è registrato solo nei test dell'adapter come campo ignorato.
  `Money.amount` è una stringa, a volte senza decimali (`"337"`): `Decimal(amount)`.
- **Booking**: `create_booking` manda `{itineraryId, paymentType: "full", paymentIntentId,
  paymentStatus}` da `PaymentProof` (il `payment_ref` salvato dal webhook o dal polling è l'id
  del PaymentIntent). OAS: "forwarded to the brand site when present"; è uno dei due modi con
  cui HofJ può riconoscere il pagamento (l'altro è `metadata.checkoutRefId`, messo da M6).
  Con `payment_intent_id` vuoto i due campi non vengono inviati.
- **Codice di prenotazione** = la stringa `data` restituita, qualunque forma abbia (`R-…` da
  DOCS, `itineraryId` osservato senza pagamento HofJ). Nessuna validazione del formato.
- **Envelope reale**: `meta` è `{now}` o `{}`; `PUT customer` e `PUT pax` rispondono
  `data: {now}`. L'adapter non legge `data` delle PUT.
- **Test dell'adapter (Task 15)** con i corpi reali: 502 `detail` `Brand "…" POST /itinerary
  returned 404: {…NOT_FOUND_ERROR…}` → `ProductError`; `GET pax` con `pax-1` precompilato.
- **Lingua**: `HofJHttp` usa `locale` del costruttore (default `it`). Un prodotto non tradotto
  dà 502 con 404 upstream → `ProductError` → sostituzione (RF-17). Nessun fallback su `en` in
  M5; il rischio è annotato per M7.

## Integrazione con M6 e M9 (decisa il 2026-09-25, prima del Task 2)

`master` contiene M9; M6 è completa su `task/m6` (Checkout Session, webhook, `stripe_events`).
Ordine dei merge e rebase di `task/m5`: **da confermare con l'utente prima del Task 2**. Le
regole sotto valgono sul codice dopo il rebase e prevalgono sul resto del piano.

- **Migrazione**: M6 ha `0003_stripe_events`. La migrazione di M5 è `0004_jobs_quota`
  (`down_revision = "0003"`); `test_migrations.py` attende head `"0004"`.
- **Frasi**: M9 ha reso le frasi bilingui (`lang` da `criteria.language`, firma
  `say_status(status, booking_code, failure_reason, lang="it", total=None)` dopo il merge M6+M9).
  Il Task 9 scrive ogni frase nuova in italiano e in inglese, con un test per lingua.
- **Porta dei pagamenti**: `create_payment_link(order, description)` (titolo del prodotto) e
  `PaymentsError` (M6). Il passo 5 del job d'acquisto passa il titolo; `PaymentsError` è trattato
  come `UpstreamError` (retry nella finestra successiva, al terzo tentativo `failed`), senza
  consumare quota HofJ.
- **Accept**: `_ensure_link` di M6 sparisce: il link lo crea solo il job. La 503
  `payments-unavailable` di REST e la frase MCP di M6 non si applicano più all'accept.
- **Webhook**: `checkout.session.completed` fa `mark_paid` e **accoda un job `booking`** al posto
  di `runner.submit` (punto di aggancio già segnato da M6 in `vela/surfaces/webhooks.py`).
  La logica "pagamento arrivato" (controlli di stato, valuta, importo, `mark_paid`, accodamento)
  si sposta in `OrderService.settle_payment(order_id, status, amount_cents, currency,
  payment_ref)`, usata dal webhook e dal polling.
- **Eventi di HofJ**: l'account Stripe è condiviso con HofJ; un evento senza `metadata.order_id`
  è registrato a livello `debug`, non `warning`.
- **Modo live**: la scelta dei pagamenti è di M6 (`STRIPE_SECRET_KEY` → `StripePayments`). Il
  `RuntimeError` "live in attesa di M6" del Task 16 non si fa: `live` costruisce `HofJHttp` e i
  pagamenti di M6.
- **Stato dell'ordine**: M6 ha già `total`, `currency`, `payment_url` in `OrderStatusResponse`; M5
  aggiunge solo gli altri campi del contratto.

### Task 13b: polling dei pagamenti (riserva del webhook)

Il webhook va registrato sull'account Stripe di HofJ (domanda 3 di `docs/hofj-questions.md`).
Finché non c'è, e dopo come recupero di eventi persi, un job controlla lo stato delle sessioni.

**Files:** Modify `vela/ports/payments.py`, `vela/adapters/stripe_links.py`,
`vela/adapters/stripe_fake.py`, `vela/domain/orders.py`, `vela/domain/jobs.py`,
`vela/domain/purchase.py`, `vela/surfaces/webhooks.py`, `vela/config.py`; Test
`tests/test_payment_poll.py`, `tests/test_stripe_links.py`, `tests/test_webhooks.py`.

**Produces:**
- `PaymentsPort.link_status(reference) -> LinkStatus(state: "open"|"paid"|"expired",
  amount_cents, currency, payment_ref)`; `StripePayments` usa `checkout.sessions.retrieve`
  (errori → `PaymentsError`); `FakePayments` legge lo stato dal checkout di replay.
- `JobKind.PAYMENT_CHECK`: accodato dal passo 5 del job d'acquisto con `run_after = now +
  payment_poll_seconds` (nuovo campo di `Settings`, default 60). Nessuna quota HofJ.
- Esito: `paid` → `settle_payment` (che accoda il `booking`); `expired` → `expire`; `open` →
  ripianificato; ordine non più `awaiting_payment` (già pagato dal webhook, annullato, scaduto) →
  job chiuso senza effetti. `PaymentsError` → ripianificato.

**Test:**
- `test_poll_paid_session_settles_and_enqueues_booking_once`
- `test_poll_open_session_reschedules`
- `test_poll_expired_session_expires_order`
- `test_poll_after_webhook_is_noop` (nessun secondo booking)
- `test_webhook_after_poll_is_noop`
- `test_poll_amount_mismatch_does_not_settle`
- `test_poll_uses_no_hofj_quota`
- `test_stripe_link_status_maps_session` (client finto: `complete`/`paid` → paid, `expired`, `open`)
- `test_webhook_event_without_order_id_logs_debug`

- [ ] TDD, poi commit «Poll Stripe sessions as a fallback for the payment webhook».

## Global Constraints

- Nessuna dipendenza nuova in `pyproject.toml` e nessuna modifica a `uv.lock`. Nessuna variabile d'ambiente nuova (spec §6).
- `uv run python -m unittest discover -s tests` verde senza servizi esterni e senza `DATABASE_URL`; i test Postgres sono saltati senza `DATABASE_URL`.
- Mai aprire, stampare o loggare `.env`, chiavi o token. Le chiamate reali (Task 1) vanno dichiarate e contate prima di farle.
- Il dominio (`vela/domain`) non importa httpx, SQLAlchemy o FastAPI.
- `accept_proposal` non chiama mai `HofJPort` né `PaymentsPort` (RF-45).
- Nessuna chiamata HofJ parte dal worker senza un `QuotaStore.acquire` riuscito (RF-37).
- `say` senza markdown e senza URL (i test esistenti controllano `http` e `**`).
- Commit piccoli, uno per task, messaggio imperativo in inglese con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nessun force push.

## Review Focus

1. Due worker non superano mai il limite della finestra (Task 5, `test_concurrent_acquire_never_exceeds_limit`, Postgres).
2. La riserva `booking` resta disponibile anche a finestra piena di `purchase` (Task 4 e Task 5, `test_booking_reserve_survives_full_purchase_window`).
3. Una ripresa a metà job non ricrea l'itinerario (Task 11, `test_resume_after_customer_does_not_recreate_itinerary`).
4. Il rifiuto durante la lavorazione ferma il job prima del passo successivo (Task 11, `test_cancelled_order_stops_job`).
5. Il 429 non è ripetuto subito e non conta come tentativo (Task 13, `test_429_zeroes_budget_and_retries_next_window`).
6. Nessuna chiamata a `/v1/quota` in ciclo (Task 13, `test_quota_refresh_only_at_boot_and_after_429`).
7. Mappatura dei 502 di HofJ tra errore del prodotto ed errore di rete (Task 15).

---

## Design

### Struttura dei file

```
vela/config.py                      + worker_concurrency=4, quota_margin=0.10, booking_reserve=0.20,
                                      purchase_max_attempts=3, booking_max_attempts=5,
                                      booking_backoff=(5,10,20,40), job_lease_seconds=120,
                                      replay_latency=(0.0,0.0), replay_limit=None
vela/domain/models.py               + OrderStatus QUEUED/REPLACED/CANCELLED/FAILED; Order.total Optional,
                                      enqueued_at, replacement_proposal_id; Job, JobKind, JobStatus;
                                      QuotaClass; OrderQueued; OrderStatusResponse esteso
vela/domain/quota.py         NUOVO  effective_limit, booking_reserve, cap_for(cls), purchases_per_window,
                                      estimated_wait_seconds, wait_minutes
vela/domain/purchase.py      NUOVO  PurchaseJob.run(job) -> JobOutcome (passi 0..5, classificazione errori)
vela/domain/booking.py       NUOVO  BookingJob.run(job) -> JobOutcome (retry/backoff)
vela/domain/jobs.py          NUOVO  JobProcessor.run_once() -> bool (claim, acquire, esecuzione, reschedule, 429)
vela/domain/usecases.py             accept asincrono, reject → cancelled, get_order_status nuovo contratto
vela/domain/orders.py               mark_paid accoda il booking; complete_booking rimosso (→ booking.py)
vela/domain/chooser.py              choose(..., now=None): bookable=False ma controllato da ≥ 24 h → candidato
vela/domain/say.py                  say_queued, say_status per i nuovi stati, say_price_changed, say_replaced
vela/ports/hofj.py                  create_itinerary -> str; get_itinerary(id) -> Itinerary; get_quota() -> QuotaSnapshot;
                                      ConfigError(HofJError); QuotaError.retry_after
vela/ports/jobs.py           NUOVO  JobRepository
vela/ports/quota.py          NUOVO  QuotaStore
vela/ports/repositories.py          ProductRepository.set_bookable; OrderRepository.get_by_replacement;
                                      Repositories.jobs, Repositories.quota
vela/adapters/schema.py             jobs_t, quota_window_t; orders_t: total nullable, enqueued_at, replacement_proposal_id
alembic/versions/0003_jobs_quota.py NUOVO
vela/adapters/repo_memory.py        MemoryJobs, MemoryQuota (lock), set_bookable, get_by_replacement
vela/adapters/repo_postgres.py      PostgresJobs (SKIP LOCKED), PostgresQuota (UPDATE atomico)
vela/adapters/hofj_replay.py        get_itinerary, get_quota, latency e limit simulati (429)
vela/adapters/hofj_http.py   NUOVO  HofJHttp(base_url, api_key, brand, locale="it", transport=None, timeout=15)
vela/adapters/worker.py      NUOVO  Worker(processor, concurrency, idle_sleep=1.0): start/stop/drain
vela/adapters/background.py         RIMOSSO (BookingRunner/InlineRunner sostituiti da Worker)
vela/app.py                         build_vela restituisce (Vela, Worker, loader); bootstrap: sync della quota,
                                      riaccodamento dei booking; live: HofJHttp + RuntimeError "M6"
vela/surfaces/mcp.py                descrizioni accept/get_order_status (RF-41), INSTRUCTIONS
vela/surfaces/rest.py               202 order_queued + Location; OUTCOMES
vela/surfaces/replay.py             mark_paid accoda il booking (niente runner.submit)
vela/surfaces/health.py             quota da QuotaStore.snapshot()
docs/rest.md, docs/api/internal-checkout.md, docs/decisions.md, README.md
```

### Stati dell'ordine

```
queued ──(job ok)──────────────▶ awaiting_payment ──(pagato)──▶ paid_pending_booking ──▶ confirmed
  │  └─(errore prodotto)──▶ replaced                   │                      └──(5 tentativi / 4xx)──▶ booking_failed
  │  └─(3 tentativi / 401-403)──▶ failed               └─(link scaduto)──▶ expired
  └─(reject, anche in lavorazione o awaiting_payment)──▶ cancelled
```

### Job d'acquisto (RF-46)

| Passo | Azione | Chiamate HofJ | Esito salvato |
|---|---|---|---|
| 0 | `create_itinerary(product, start, pax, 1, currency)` | 1 | `order.itinerary_id`; prodotto riabilitato se era `bookable=False` |
| 1 | `set_customer` | 1 | `job.step=2` |
| 2 | `get_pax` | 1 | in memoria del job; il passo 3 lo ripete se ripreso (costo già nel blocco) |
| 3 | `set_pax` (nomi, `refId` preservati) | 1 | `job.step=4` |
| 4 | `get_itinerary` → importo da pagare (`checkout.openAmount`) | 1 | `order.total` |
| 5 | `payments.create_payment_link(order)` | 0 | `payment_url`, `payment_ref`, stato `awaiting_payment`, job `done` |

Nota: i passi 2 e 3 sono un'unità di ripresa. Se il job si interrompe dopo il passo 2, riparte dal 2 prenotando 3 chiamate.

Blocco da prenotare = numero di chiamate HofJ dei passi che restano (5, 4, 3, 1, 0).

**Esiti degli errori:**

| Errore | Esito |
|---|---|
| `UpstreamError` | `attempts+1`, `run_after` = inizio della finestra successiva; al terzo tentativo `failed` con «Non sono riuscito a preparare il pagamento, riprova tra qualche minuto.» |
| `QuotaError` | `QuotaStore.on_429()`, `run_after` = finestra successiva, `attempts` invariato |
| `ProductError` al passo 0 | `products.set_bookable(id, False, now)`, `_propose(intent)` → `replacement_proposal_id`, stato `replaced`, job `done` |
| `ConfigError` (401/403) | `failed` |

### Scheduler della quota

- Riga unica `quota_window(id=1, window_start, window_end, limit_per_minute, used, needs_refresh)`.
- `acquire(cls, n, now, purchase_waiting)`, in un solo `UPDATE`:
  - se `now >= window_end`, la finestra avanza a `window_end + k·60` e `used` riparte da 0;
  - poi `used = used + n`, con la condizione `used + n <= cap(cls)` e, per `sync`, anche `NOT purchase_waiting`;
  - restituisce `True` o `False`.
- Tetti: `cap(booking) = effective_limit`; `cap(purchase) = cap(sync) = effective_limit − reserve`.
- `on_429(now)` porta `used = effective_limit` e `needs_refresh = true`.
- `sync_from_snapshot(snapshot)` imposta la finestra e `used` da `/v1/quota`.
- Al boot: `JobProcessor.refresh_quota()`. Dopo un 429 il refresh si fa alla prima finestra utile e costa 1 chiamata di classe `booking`.

### Contratto delle risposte

`OrderQueued.to_dict()`:
```json
{"order_id": "...", "status": "queued", "position": 3, "wait_seconds": 11, "say": "..."}
```

`OrderStatusResponse.to_dict()`:
```json
{"order_id": "...", "status": "awaiting_payment", "position": null, "wait_seconds": null,
 "total": "720.00", "currency": "EUR", "price_from_total": "700.00", "total_differs": true,
 "payment_url": "...", "booking_code": null, "failure_reason": null,
 "proposal_changed": false, "proposal": null, "say": "..."}
```

Con `status="replaced"`: `proposal_changed: true` e `proposal` nella forma `ProposalMade.to_dict()` (RF-06).

REST:
- `POST /v1/proposals/{id}/accept` risponde **202** `{"outcome":"order_queued", ...}` con `Location`.
- Un doppio accept risponde 200 `{"outcome":"order_status", ...}`.
- `MissingTravelerData` resta 200.

---

### Task 0: Piano e decisioni nel repo

**Files:** Create `docs/plans/2026-09-25-m5-hofj-reale.md` (questo file); Modify `docs/decisions.md` (in coda).

- [ ] Step 1: aggiungere in coda a `docs/decisions.md` la sezione `## 2026-09-25 — M5: HofJ reale, coda d'acquisto e scheduler della quota`, con `Origine: intervista sulla macro task M5, piano in docs/plans/2026-09-25-m5-hofj-reale.md.` e la tabella delle decisioni copiata integralmente.
- [ ] Step 2: commit «Add the M5 execution plan and record the interview decisions».

### Task 1 (manuale, con l'utente): verifiche di spec §8 su staging

**Files:** Modify `docs/decisions.md`, `docs/api/internal-checkout.md` (forme reali). Script usa-e-getta nello scratchpad: niente nel repo.

- [ ] Step 1: dichiarare all'utente le chiamate e **attendere l'OK**: fino a 8 chiamate HofJ su staging (quota, POST itinerary sul prodotto 118 o su un altro prodotto di staging indicato dall'utente, PUT customer con `Address` OAS, GET pax, PUT pax, GET itinerary, POST booking, 1 di margine) e 1 chiamata Stripe in modalità test (`PaymentIntent.create(amount=totale, currency=eur, payment_method="pm_card_visa", confirm=True, automatic_payment_methods={"enabled": True, "allow_redirects": "never"})`). Chiavi solo da env (`HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND`, `STRIPE_SECRET_KEY`), mai stampate.
- [ ] Step 2: eseguire con httpx. Per ogni chiamata registrare status, forma di `data`/`meta` e dove sta il totale (`checkout.total`? `totalPrice`?). Il booking va provato con `{itineraryId, paymentType:"full", paymentIntentId, paymentStatus:"succeeded"}`.
- [ ] Step 3: registrare in `docs/decisions.md` la sezione `## 2026-09-25 — M5: verifiche di spec §8`, con: chiamate contate, esito delle righe 1, 3 e 4 (403 o no, booking accettato o no, `limitPerMinute`), fallback adottato se il booking rifiuta il `paymentIntentId` (in quel caso **fermarsi e chiedere all'utente**, perché cambia M6). Aggiornare `docs/api/internal-checkout.md` con le forme verificate.
- [ ] Step 4: commit «Record the section 8 checks against HofJ staging».

### Task 2: parametri in `Settings`

**Files:** Modify `vela/config.py`, `tests/test_config.py`.
- [ ] Test `SettingsDefaultsTest.test_m5_defaults`: i default elencati nel Design; `from_env` non legge variabili nuove (un env con `VELA_WORKER_CONCURRENCY=9` lascia 4).
- [ ] Implementare i campi con default nel dataclass frozen. Commit «Add worker, quota and replay tuning to the settings».

### Task 3: modello, stati e migrazione `0003`

**Files:** Modify `vela/domain/models.py`, `vela/adapters/schema.py`, `vela/adapters/repo_postgres.py` (mapping di orders), `tests/test_migrations.py`, `tests/repo_contract.py`; Create `alembic/versions/0003_jobs_quota.py`.

**Produces:**
- `OrderStatus.QUEUED/REPLACED/CANCELLED/FAILED`.
- `Order.total: Optional[Decimal]`, `Order.enqueued_at: Optional[datetime]`, `Order.replacement_proposal_id: Optional[str]`.
- `JobKind(purchase, booking)`, `JobStatus(pending, running, done, dead)`.
- `Job(id, kind, order_id, status, step, attempts, run_after, enqueued_at, locked_at, last_error)`.
- `QuotaClass(booking, purchase, sync)`.
- `QuotaSnapshot(limit_per_minute, used_in_window, window_started_at, window_ends_at)` in `vela/ports/hofj.py`.

- [ ] Test:
  - `test_migrations.py`: head `"0003"` (3 punti), upgrade/downgrade su SQLite, idempotenza Postgres.
  - Contratto: `test_order_roundtrip_with_queue_fields` (queued, `total=None`, `enqueued_at`, `replacement_proposal_id`).
- [ ] Migrazione:
  - crea `jobs` con indice `(status, kind, run_after, enqueued_at)` e `ix_jobs_order_id`;
  - crea `quota_window`;
  - `orders`: `total` nullable, `enqueued_at`, `replacement_proposal_id` con indice.
  - Tipi neutri, così che la migrazione giri anche su SQLite (`batch_alter_table`).
- [ ] Commit «Add queue states, jobs and quota window tables in migration 0003».

### Task 4: regole pure della quota (`vela/domain/quota.py`)

**Test** `tests/test_quota_rules.py`:
- `test_effective_limit_applies_margin` (120 → 108)
- `test_booking_reserve` (108 → 21)
- `test_caps_per_class` (booking 108, purchase/sync 87)
- `test_purchases_per_window` (17.4)
- `test_estimated_wait_formula` (pos 1 → 4 s, pos 18 → 63 s, pos 1000 → 3449 s, senza tetto)
- `test_wait_minutes_rounds_up_min_one` (4 s → 1, 61 s → 2)

- [ ] TDD, poi commit «Add the quota rules and the estimated wait».

### Task 5: `QuotaStore` (porta, memoria, Postgres)

**Files:** Create `vela/ports/quota.py`, `tests/quota_contract.py`, `tests/test_quota_memory.py`, `tests/test_quota_postgres.py`; Modify `repo_memory.py`, `repo_postgres.py`, `vela/ports/repositories.py` (`Repositories.quota`).

**Produces:**
```python
QuotaStore.acquire(cls, n, now, purchase_waiting=False) -> bool
QuotaStore.on_429(now) -> None
QuotaStore.needs_refresh(now) -> bool
QuotaStore.sync_from_snapshot(snapshot) -> None
QuotaStore.snapshot(now) -> dict
QuotaStore.next_window_start(now) -> datetime
```

**Test di contratto** (orologio finto):
- `test_acquire_within_cap`
- `test_purchase_blocked_at_cap`
- `test_booking_reserve_survives_full_purchase_window`
- `test_block_is_atomic_all_or_nothing` (86 usate, `acquire(purchase, 5)` → False, `used` invariato)
- `test_window_rolls_after_60s`
- `test_sync_only_without_waiting_purchase`
- `test_429_zeroes_remaining_budget`
- `test_sync_from_snapshot_aligns_window`
- `test_needs_refresh_after_429_only`

**Solo Postgres:** `test_concurrent_acquire_never_exceeds_limit` (8 thread × 200 `acquire(purchase, 1)` → totale concesso nella finestra ≤ 87).

- [ ] TDD, poi commit «Add the shared quota store with atomic block reservation».

### Task 6: `JobRepository` (porta, memoria, Postgres)

**Files:** Create `vela/ports/jobs.py`, `tests/jobs_contract.py`, `tests/test_jobs_memory.py`, `tests/test_jobs_postgres.py`; Modify `repo_memory.py`, `repo_postgres.py`, `repositories.py` (`Repositories.jobs`).

**Produces:**
```python
enqueue(job) -> None
claim(now, lease_seconds) -> Optional[Job]   # booking prima, poi purchase per enqueued_at; run_after <= now; pending o running con lease scaduto
save(job) -> None
active_for_order(order_id) -> Optional[Job]
queued_purchase_position(order_id) -> Optional[int]
purchase_waiting(now) -> bool
```

**Test di contratto:**
- `test_claim_prefers_booking`
- `test_claim_purchase_fifo_by_enqueued_at`
- `test_claim_respects_run_after`
- `test_claimed_job_not_claimed_twice`
- `test_expired_lease_is_reclaimed`
- `test_position_counts_only_pending_purchases_before`
- `test_position_none_when_not_queued`

**Solo Postgres:** `test_skip_locked_two_sessions_get_different_jobs`.

- [ ] TDD, poi commit «Add the job queue with skip-locked claiming and leases».

### Task 7: porta HofJ estesa, `FakeHofJ` e `ReplayHofJ`

**Files:** Modify `vela/ports/hofj.py`, `tests/support.py`, `vela/adapters/hofj_replay.py`, `tests/test_replay_adapters.py`.

**Produces:**
- `create_itinerary(...) -> str`
- `get_itinerary(id) -> Itinerary`
- `get_quota() -> QuotaSnapshot`
- `ConfigError(HofJError)`
- `QuotaError(retry_after: Optional[float])`
- `FakeHofJ`: `fail_at={"set_customer": [UpstreamError(...)]}` (errori in sequenza per metodo), `.calls` con nome del metodo
- `ReplayHofJ(latency=(0,0), limit=None, now=None, sleep=time.sleep)`

**Test:**
- `test_replay_get_itinerary_returns_total`
- `test_replay_quota_unlimited_by_default`
- `test_replay_limit_raises_429_after_limit_in_window` (limit 3 → la quarta chiamata `QuotaError`, riparte dopo 60 s)
- `test_replay_latency_uses_injected_sleep`
- `test_replay_get_quota_snapshot_counts_calls`

- [ ] TDD, poi commit «Split the itinerary total read and simulate latency and quota in replay».

### Task 8: prodotti non prenotabili (RF-33..35)

**Files:** Modify `repositories.py`, `repo_memory.py`, `repo_postgres.py`, `vela/domain/chooser.py`, `tests/repo_contract.py`, `tests/test_chooser.py`.

**Produces:**
- `ProductRepository.set_bookable(product_id, bookable, checked_at)`
- `choose(..., now: Optional[datetime] = None)`

**Test:**
- `test_set_bookable_roundtrip` (contratto)
- `test_unbookable_product_excluded_within_24h`
- `test_unbookable_product_candidate_again_after_24h`
- `test_choose_without_now_keeps_old_behaviour`

- [ ] TDD, poi commit «Mark products unbookable and let them back after 24 hours».

### Task 9: frasi `say`

**Files:** Modify `vela/domain/say.py`, `tests/test_say.py`.

**Produces:**
- `say_queued(minutes)`
- `say_awaiting_payment(total, price_from_total, total_differs)` (RF-16: la differenza è detta prima del link)
- `say_replaced(proposal, product, criteria)` (introduzione + `say_proposal`, nessuna parola «errore»)
- `say_status` esteso a queued/replaced/cancelled/failed
- `say_cancelled_then(next)`

**Test:**
- `test_say_queued_minutes_singular_plural`
- `test_awaiting_payment_states_difference_before_link`
- `test_replaced_does_not_mention_error`
- `test_failed_includes_reason`
- `test_new_phrases_have_no_url_or_markdown`

- [ ] TDD, poi commit «Add spoken sentences for the queue, replacement and failure».

### Task 10: casi d'uso — accept asincrono, rinuncia, stato

**Files:** Modify `vela/domain/usecases.py`, `vela/domain/models.py` (`OrderQueued`, `OrderStatusResponse`), `tests/test_usecases.py`.

**Consumes:** Task 3, 5, 6, 8, 9.

**Test** (`AcceptProposalTest` riscritto, `RejectQueuedTest`, `OrderStatusTest`):
- `test_accept_returns_queued_without_calling_ports` (`FakeHofJ.calls == []`, `StubPayments.links == []`)
- `test_accept_enqueues_purchase_job`
- `test_double_accept_returns_same_order`
- `test_accept_missing_traveler_data_unchanged`
- `test_accept_on_replacement_inherits_enqueued_at`
- `test_reject_queued_order_cancels_and_proposes_next`
- `test_reject_awaiting_payment_cancels`
- `test_reject_after_payment_leaves_order`
- `test_status_recomputes_wait_on_each_call` (la posizione scende quando un job precedente è fatto)
- `test_status_awaiting_payment_has_link_and_total_differs`
- `test_status_replaced_has_proposal_and_flag`
- `test_status_failed_has_reason`

- [ ] TDD, poi commit «Make accept asynchronous with a queued order and a declared wait».

### Task 11: `PurchaseJob` (RF-46, RF-17)

**Files:** Create `vela/domain/purchase.py`, `tests/test_purchase_job.py`.

**Produces:**
- `PurchaseJob(repos, hofj, payments, propose, now, settings).run(job) -> JobOutcome`
- `JobOutcome(done: bool, retry_at: Optional[datetime], counted_attempt: bool, calls_used: int)`
- `calls_needed(job) -> int`

**Test:**
- `test_steps_in_sequence_and_saved_per_step`
- `test_resume_after_customer_does_not_recreate_itinerary`
- `test_resume_after_get_pax_repeats_get_pax`
- `test_calls_needed_decreases_with_steps`
- `test_network_error_retries_next_window_then_fails_after_three`
- `test_product_error_marks_unbookable_and_replaces`
- `test_product_error_without_alternative_fails_with_no_match_reason`
- `test_config_error_fails_without_marking_product`
- `test_success_reenables_unbookable_product`
- `test_cancelled_order_stops_job`
- `test_real_total_saved_and_link_created`

- [ ] TDD, poi commit «Add the resumable purchase job».

### Task 12: `BookingJob` e `mark_paid` (RF-23, RF-24, RF-51)

**Files:** Create `vela/domain/booking.py`, `tests/test_booking_job.py`; Modify `vela/domain/orders.py` (`mark_paid` accoda un job `booking`; `complete_booking` rimosso), `tests/test_orders.py`.

**Test:**
- `test_booking_confirms_with_code`
- `test_retry_with_backoff_on_5xx` (`run_after` a +5, +10, +20, +40 s)
- `test_stops_after_max_attempts_booking_failed_with_reason`
- `test_4xx_fails_immediately`
- `test_mark_paid_enqueues_booking_once`
- `test_mark_paid_on_cancelled_order_is_ignored`

- [ ] TDD, poi commit «Book paid orders through a retried booking job».

### Task 13: `JobProcessor` (scheduler + esecuzione)

**Files:** Create `vela/domain/jobs.py`, `tests/test_job_processor.py`.

**Produces:**
- `JobProcessor(repos, hofj, purchase, booking, settings, now).run_once() -> bool`
- `refresh_quota()`
- `resume_bookings() -> List[str]` (ordini `paid_pending_booking` senza job attivo)

**Test** (orologio finto, `FakeHofJ`, repository in memoria):
- `test_no_hofj_call_without_acquired_block`
- `test_booking_reserve_respected_with_full_window`
- `test_purchase_fifo`
- `test_job_waits_next_window_when_budget_short`
- `test_429_zeroes_budget_and_retries_next_window`
- `test_quota_refresh_only_at_boot_and_after_429` (conteggio di `get_quota` in 50 cicli)
- `test_resume_bookings_enqueues_missing_jobs`
- `test_unused_calls_not_refunded` (semplicità: il blocco resta consumato)

- [ ] TDD, poi commit «Add the job processor that runs jobs under the quota scheduler».

### Task 14: `Worker`, cablaggio dell'app, replay checkout, `/health`

**Files:** Create `vela/adapters/worker.py`, `tests/test_worker.py`; Delete `vela/adapters/background.py`; Modify `vela/app.py`, `vela/surfaces/replay.py`, `vela/surfaces/health.py`, `tests/test_app_replay.py`, `tests/test_health.py`, `tests/test_orders.py` (rimozione di `RunnerTest`).

**Produces:** `Worker(processor, concurrency, idle_sleep, sleep=time.sleep)`, con:
- `start()`, `stop(wait)`: thread `vela-worker-N`, un'eccezione è loggata e il loop continua;
- `drain(max_iterations=1000) -> int`: sincrono, per i test.

`build_vela -> (Vela, Worker, loader)`; `bootstrap` fa: catalogo, `refresh_quota`, `resume_bookings`.

**Test:**
- `test_worker_threads_process_jobs_and_stop`
- `test_worker_survives_exception`
- `test_drain_runs_until_idle`
- `test_bootstrap_refreshes_quota_and_resumes_bookings`
- `test_replay_checkout_enqueues_booking_and_drain_confirms`
- `test_health_reports_quota_snapshot`

- [ ] TDD, poi commit «Run jobs in worker threads and wire the queue into the app».

### Task 15: adapter `hofj_http.py` (RNF-04)

**Files:** Create `vela/adapters/hofj_http.py`, `tests/test_hofj_http.py`.

**Consumes:** le forme reali del Task 1.

**Produces:** `HofJHttp(base_url, api_key, brand, locale="it", transport=None, timeout=15.0)`, che implementa `HofJPort` con:
- `?brand=&locale=` su ogni chiamata;
- `Bearer` in intestazione;
- envelope `{data, meta}` con `meta` opzionale;
- 7807 letto senza filtrare sul content-type;
- `Address` nella forma OAS.

**Mappatura:** timeout / `ConnectError` → `UpstreamError`; 429 → `QuotaError(retry_after dal body se presente)`; 401/403 → `ConfigError`; 400/404 su `POST /itineraries` → `ProductError`; 502 su `POST /itineraries` con `detail` che riporta un 4xx/500 upstream non-timeout → `ProductError`; altri 502/5xx → `UpstreamError`.

**Test** (`httpx.MockTransport`):
- `test_create_itinerary_request_shape`
- `test_set_customer_uses_oas_address`
- `test_set_pax_preserves_ref_ids`
- `test_get_itinerary_reads_open_amount` (corpo reale: `total` 368, `openAmount` 337 → 337)
- `test_create_booking_sends_only_itinerary_and_payment_type` (niente `paymentIntentId`)
- `test_create_booking_returns_data_string_as_code`
- `test_get_quota_snapshot`
- `test_timeout_is_upstream_error`
- `test_429_is_quota_error_with_retry_after`
- `test_401_403_are_config_errors`
- `test_502_wrong_id_is_product_error` (con il `detail` reale del Task 1)
- `test_money_amount_without_decimals`
- `test_502_reservation_period_is_product_error`
- `test_502_upstream_timeout_is_upstream_error`
- `test_502_on_customer_is_upstream_error`
- `test_meta_missing_is_tolerated`
- `test_api_key_never_in_error_messages`

- [ ] TDD, poi commit «Add the HofJ HTTP adapter with error mapping».

### Task 16: modo `live` (vedi "Integrazione con M6 e M9": niente `RuntimeError`)

**Files:** Modify `vela/app.py`, `tests/test_app_replay.py`.

**Test:**
- `test_live_builds_http_adapter_and_m6_payments`
- `test_live_requires_hofj_settings` (manca `HOFJ_API_KEY` → errore chiaro, senza stampare valori)

- [ ] TDD, poi commit «Build the live HofJ adapter and wait for M6 payments».

### Task 17: superfici MCP e REST

**Files:** Modify `vela/surfaces/mcp.py`, `vela/surfaces/rest.py`, `tests/test_mcp_tools.py`, `tests/test_rest.py`.

**Test MCP:**
- `test_accept_description_says_wait_not_link` (RF-41)
- `test_status_description_lists_new_states`
- `test_accept_returns_queued_shape`
- `test_full_flow_section_10_1` aggiornato: accept → `drain` → `awaiting_payment` con link → checkout replay → `drain` → `confirmed`

**Test REST:**
- `test_accept_returns_202_order_queued_with_location`
- `test_double_accept_returns_200_order_status`
- `test_order_status_new_contract`
- `FullFlowTest` aggiornato

- [ ] TDD, poi commit «Adapt the MCP and REST surfaces to the queued accept».

### Task 18: flusso completo e scenario del twist in replay

**Files:** Create `tests/test_queue_flow.py`.

**Test** (repository in memoria, `ReplayHofJ(limit=120)`, orologio finto, `drain`):
- `test_two_hundred_accepts_all_queued_with_growing_wait` (nessun errore; `wait_seconds` monotona)
- `test_throughput_never_exceeds_effective_limit_per_window`
- `test_paid_order_booked_within_next_window` (RF-51, con 150 acquisti in coda)
- `test_replacement_flow_end_to_end`
- `test_restart_mid_job_resumes_without_new_itinerary` (nuovo `Vela`/processor sugli stessi repository)

- [ ] TDD, poi commit «Cover the queued flow and the launch burst in replay».

### Task 19: documentazione, decisioni e verifica finale

**Files:** `docs/rest.md` (202, nuovi campi, stati), `docs/api/internal-checkout.md`, `README.md` (parametri in `Settings`, live in attesa di M6), `docs/decisions.md`.

- [ ] Sezione `## 2026-09-25 — M5: decisioni prese durante l'esecuzione`: deviazioni, oppure «Nessuna deviazione dal piano» con il numero di test.
- [ ] Verifica:
  - `uv run python -m unittest discover -s tests` verde, anche con `DATABASE_URL` se disponibile;
  - `git grep -nE "import (httpx|sqlalchemy|fastapi)" vela/domain` vuoto;
  - `git diff master -- pyproject.toml uv.lock` vuoto;
  - `git status` pulito.
- [ ] Commit «Document the queued accept, the quota scheduler and the M5 decisions».

## Copertura dei test di completamento della roadmap M5

| Test di completamento (roadmap) | Dove |
|---|---|
| Accept risponde `queued` con attesa senza chiamare le porte; doppio accept → stesso ordine; rinuncia → `cancelled` e proposta successiva | Task 10 (`test_accept_returns_queued_without_calling_ports`, `test_double_accept_returns_same_order`, `test_reject_queued_order_cancels_and_proposes_next`) |
| Job d'acquisto: passi in sequenza, esito per passo, ripresa senza ricreare l'itinerario, tre tentativi poi `failed`, errore prodotto → `replaced`, nuovo accept in testa | Task 11 e Task 10 (`test_accept_on_replacement_inherits_enqueued_at`), Task 18 |
| Scheduler: riserva `booking`, `purchase` FIFO, `sync` a coda vuota, blocco atomico, 429 azzera, nessuna `/v1/quota` in ciclo, due worker concorrenti ≤ limite | Task 5, Task 6, Task 13 |
| Attesa stimata: formula e ricalcolo a ogni stato | Task 4, Task 10 (`test_status_recomputes_wait_on_each_call`) |
| Adapter HTTP con `MockTransport`: timeout, 429, 502, mapping | Task 15 |
| Prodotti: marcato al primo errore, riabilitato dopo 24 h | Task 8, Task 11 |
| Booking: retry con backoff su 5xx, stop dopo N, `booking_failed` con motivo | Task 12 |
| Manuale: itinerario reale e booking su staging, chiamate contate | Task 1 |

## Requisiti coperti

- RF-14 (Task 11, 15)
- RF-16 (Task 9, 10)
- RF-17 (Task 10, 11)
- RF-19 (Task 10, 17)
- RF-23 e RF-24 (Task 12)
- RF-25 (Task 3, 10)
- RF-27 (Task 6, 13, 18)
- RF-33..35 (Task 8, 11)
- RF-36..38 (Task 5, 13)
- RF-39 (Task 10, 17)
- RF-41 (Task 17)
- RF-45..48 (Task 4, 10, 11, 13)
- RF-49 (Task 10, 11)
- RF-50 (Task 6, 14)
- RF-51 (Task 12, 18)
- RNF-04 (Task 15)
- spec §8 righe 1, 3 e 4 (Task 1)

## Fuori scope (task successive)

- Link Stripe reale e webhook, scadenza dei link (M6). Il job usa `PaymentsPort`; il modo live si avvia solo dopo M6.
- Sync incrementale del catalogo (M10): la classe `sync` esiste nello scheduler ma nessun job la usa.
- Frasi `say` in inglese (M9). Load test con 120/min e 2-6 s (M13, usando `replay_limit` e `replay_latency`).
- Cancellazione degli itinerari HofJ orfani dopo una rinuncia.
