# Vela — roadmap in macro task

Data: 2026-09-25. Origine: `docs/spec.md` e intervista del 2026-09-25 (decisioni in
`docs/decisions.md`, sezione "Roadmap in macro task"). Aggiornata il 2026-09-25 per il twist
(50.000 viaggiatori in dieci minuti, spec §4.10): M2 era già conclusa, quindi coda d'acquisto,
scheduler della quota e accettazione asincrona entrano in M5, lo scenario di carico in M13.
Aggiornata il 2026-09-26 con M17 (contratto agente-tool, spec §4.11): M9 e M11 erano già
concluse, quindi il lavoro su parser e contratto dei tool è una task nuova in ondata 5.
Aggiornata il 2026-09-26 per il multi-brand: M10 diventa "Sync multi-brand del catalogo"
(padel = Weebora, tennis = Terrarossa), taglia L, casi d'uso in `docs/usecases/multi-brand.md`.
Aggiornata il 2026-09-26 per la seconda lettura del twist
(`docs/plans/2026-09-26-twist-seconda-lettura.md`): M13 diventa M13a e M13b, nuove M18 e M19,
M15 allargata. Aggiornata il 2026-09-26 con M21 (scelta v3, spec §4.12, casi d'uso in
`docs/usecases/scelta.md`): sei task in sequenza, ondata 7.

## Come usare questo file

Ogni macro task ha un blocco "Prompt" da incollare in `/superpowers:brainstorming`, che produce
spec e piano di microtask. Le task marcate con la stessa "ondata" possono girare in worktree
paralleli. Le dipendenze sono sul risultato mergiato su `master`. Taglia: S (< 2 h), M (2-4 h),
L (> 4 h) per una persona che delega.

## Grafo delle dipendenze

```
Ondata 0   M0 Fondamenta+deploy      M1 Fixture catalogo it
                 \                      /
Ondata 1          M2 Dominio + replay
                 /   |    \        \
Ondata 2   M3 MCP  M4 REST  M9 Parser  M11 Chooser v2
            |  \     |
Ondata 3   M8 OAuth  M5 HofJ reale   M6 Stripe
                 \       |        /
Ondata 4          M7 Prima prenotazione reale   [Traguardo B]
                 /    |      |       \
Ondata 5   M10 Sync (conclusa)  M17 Contratto agente-tool (conclusa)  M12 ElevenLabs  M14 Hardening
           M13a Banco di prova   M18 Quota a ritmo   M20 Accept con attesa
                  \               /
                   M13b Rilancio (dopo M13a e M18)
                  /             \
                 |               M19 Meno chiamate per link (opzionale, condizionata)
Ondata 6          M15 Consegna (ARCHITECTURE, README, video; dopo M13b)   [M16 A2A opzionale]

Ondata 7   M21 Scelta v3: M21-A Durata → M21-E Budget → M21-B Ordinamento → M21-D Camere
                          → M21-C Livello → M21-F Rifiuti   (dopo M17, M11, M10, M5)

Ondata 8   M22-a Hotel: bozza, sonda, verdetto (solo documenti, parallela a M21)
                 → M22-b Cambio di hotel (dopo M21-D, M21-F e un verdetto "sì")
```

Traguardo A = M3 completata (prototipo replay su Render, testato da claude.ai).
Traguardo B = M7 completata (codice di prenotazione reale).

## Tabella riassuntiva

| ID | Macro task | Taglia | Dipende da | Ondata / parallela con |
|---|---|---|---|---|
| M0 | Fondamenta del repo e deploy vuoto su Render | M | — | 0 / M1 |
| M1 | Fixture del catalogo in locale `it` | S | — | 0 / M0 |
| M2 | Dominio, casi d'uso e modalità replay | L | M0, M1 | 1 / — |
| M3 | Superficie MCP e primo test da claude.ai | M | M2 | 2 / M4, M9, M11 |
| M4 | Superficie REST | S | M2 | 2 / M3, M9, M11 |
| M5 | HofJ reale: coda d'acquisto, scheduler della quota, prenotazione | L | M2 | 3 / M6, M8 |
| M6 | Stripe: link di pagamento e webhook | M | M2, M4 | 3 / M5, M8 |
| M7 | Prima prenotazione reale end-to-end | S | M3, M4, M5, M6 | 4 / — |
| M8 | OAuth 2.1 sulla superficie MCP | M | M3 | 3 / M5, M6 |
| M9 | Parser completo, rifiuto con motivo, fallback Haiku | M | M2 | 2+ / tutte |
| M10 | Sync multi-brand del catalogo da HofJ | L | M5 | 5 / M12, M13a, M14 |
| M11 | Raffinamento della scelta (chooser v2) | M | M2 | 2+ / tutte |
| M12 | Agente vocale ElevenLabs | S | M7, M8 | 5 / M10, M13a, M14 |
| M13a | Banco di prova e numeri di partenza | M | M5, M10 | 5 / M18, M20; mergiare prima di M18 |
| M13b | Rilancio dopo M18 | S | M13a, M18 | 5 / — |
| M14 | Hardening: log JSON, health, dati personali, segreti | S | M7 | 5 / M10, M12, M13a |
| M15 | Consegna: ARCHITECTURE.md, README, video | M | tutte, in particolare M13b | 6 / — |
| M16 | (opzionale) Superficie A2A | M | M4, M8 | 6 / M15 |
| M17 | Contratto agente-tool e sinonimi dello sport | M | M3, M4, M9, M11 | 5 / M10, M12, M13a, M14 |
| M18 | Quota a ritmo costante | M | M5 | 5 / M13a, M20 |
| M19 | Meno chiamate per link e ordini silenziosi (condizionata) | M | M18, M13b | 5 / — |
| M20 | Accettazione con attesa breve quando la coda è vuota | S | M5 | 5 / M13a, M18; mergiare dopo M13b |
| M21 | Scelta v3 (sei task: A, E, B, D, C, F in sequenza) | L | M17, M11, M10, M5 | 7 / nessuna che tocchi `chooser.py`, `intent.py`, `refine.py` |
| M21-A | Durata | M | M17, M11 | 7 / — |
| M21-E | Budget a testa o totale | S-M | M21-A | 7 / — |
| M21-B | Ordinamento e prodotti equivalenti | M | M21-A | 7 / — |
| M21-D | Persone e camere | M | M21-B, M5 | 7 / — |
| M21-C | Livello e lezioni | M | M21-B, M10 | 7 / — |
| M21-F | Rifiuti con motivo sempre capito | L | M21-A, M21-B, M21-C, M21-D | 7 / — |
| M22 | Scelta dell'hotel con degrado dinamico (due task: a, b) | L | M21-D, M21-F | 8 / — |
| M22-a | Bozza, sonda su `/accommodations`, verdetto | S-M | — | 8 / tutte (niente codice in `vela/`) |
| M22-b | Cambio di hotel a coda vuota (**non si fa**: verdetto di M22-a) | L | M22-a (verdetto "sì"), M21-D, M21-F | 8 / nessuna che tocchi `usecases.py`, `quota.py`, `purchase.py` |

Regola per i worktree: le task della stessa ondata toccano file diversi salvo
`vela/domain/orders.py` (M5, M6), `vela/domain/intent.py` (M9, M11) e
`vela/domain/usecases.py` (M10 per il router del carrello, M17 per i campi strutturati) e
`vela/config.py` (M13a per il modo `loadtest`, M18 per concorrenza e timeout, M20 per
`accept_wait_seconds`): chi arriva secondo fa rebase prima del merge. Ogni task finisce con merge su `master` e test verdi.

---

## M0 — Fondamenta del repo e deploy vuoto su Render

**Risultato.** L'app FastAPI vuota gira su Render con Postgres gestito, `GET /health`
risponde con lo stato del DB, le migrazioni girano al boot, la struttura `vela/` esiste,
`agents-log/` è diventata `agent-log/`.

**Scope.**
- Struttura da spec §9: `vela/domain`, `vela/ports`, `vela/adapters`, `vela/surfaces`,
  `vela/app.py`, `fixtures/`, `loadtest/`, `tests/`.
- Dipendenze da concordare nel brainstorm: `fastapi`, `uvicorn`, `sqlalchemy` (Core),
  `psycopg[binary]`, `alembic`, `httpx`, `mcp`, `stripe`; dev: `locust`. Nessun'altra.
- Configurazione da variabili d'ambiente (spec §6), senza mai leggere `.env`.
- `GET /health` pubblico: stato DB (le altre voci arrivano con M4/M14).
- Alembic con prima migrazione vuota, eseguita al boot.
- Dockerfile, servizio Render + Postgres, `DATABASE_URL` impostata; `README.md` con le variabili.
- `git mv agents-log agent-log`; aggiornare `scripts/agents_log.py`, hook in
  `.claude/settings.json`, `docs/agents-log.md`, test.

**Test di completamento.**
- `python3 -m unittest discover -s tests` verde (test esistenti aggiornati al nuovo path + test
  di `/health` con TestClient che tollera DB assente).
- `curl https://<render>/health` → 200 con `db: "ok"`.
- `docker build .` riesce; il log di Render mostra la migrazione applicata.
- `git log --follow agent-log/` mostra la storia.

**Copre.** RNF-11, RNF-06 (parte `/health`), RNF-07 (segreti in env), spec §6 (`agent-log/`).

**Prompt.**
> Leggi docs/spec.md (§5 RNF-11, §6, §9) e docs/roadmap.md M0. Obiettivo: scaffold `vela/`
> con FastAPI, SQLAlchemy Core + psycopg 3 + Alembic, `GET /health` con stato DB, Dockerfile,
> deploy su Render con Postgres gestito, rinomina `agents-log/` → `agent-log/` aggiornando
> script, hook, doc e test. Nessuna logica di dominio. Test: quelli elencati in M0.

---

## M1 — Fixture del catalogo in locale `it`

**Risultato.** `fixtures/catalog.json` contiene la lista prodotti (locale `it`, brand da
configurazione) e il dettaglio `extended=true` di ogni prodotto non archiviato, registrati
dall'API reale, senza credenziali. Un comando lo rigenera.

**Scope.**
- Script `scripts/record_catalog.py` (stdlib, come `scripts/api_explore.py`, di cui riusa il
  contatore di quota: budget per finestra, attesa fino a `windowEndsAt`, stop su 429).
- Chiamate dichiarate: 2 pagine `GET /v1/products?locale=it&limit=100` + ~92
  `GET /v1/products/{id}?extended=true&locale=it` + 2 `GET /v1/quota` ≈ 96, in 2-3 finestre.
- Formato: `{recorded_at, locale, brand, products: [item lista], details: {id: dettaglio}}`.
- Chiave solo da variabile d'ambiente; il file non contiene header né URL con token.

**Test di completamento.**
- Test unitari dello script con HTTP finto: paginazione, salto archiviati, pacing quota, 429.
- Il file ha tutti i prodotti non archiviati (atteso ~92); ogni item ha `price`, `currency`,
  `minDate`, `maxDate`, `availabilities`; ogni dettaglio ha `category`, `venue`,
  `destination`, `rawAttributes.hotels`.
- `git grep -i "$HOFJ_API_KEY"` non trova nulla (eseguito senza stampare la chiave).
- `python3 scripts/record_catalog.py --dry-run` stampa il numero di chiamate previste senza farle.

**Copre.** RF-32, spec §6 (dichiarazione delle chiamate).

**Prompt.**
> Leggi docs/spec.md (RF-32, §6), docs/api/products.md, docs/api/quota-health.md,
> scripts/api_explore.py e docs/roadmap.md M1. Obiettivo: script che registra
> `fixtures/catalog.json` in locale `it` (lista + extended dei non archiviati) rispettando la
> quota, con `--dry-run`. Prima di eseguirlo dichiara il numero di chiamate. Test: M1.

---

## M2 — Dominio, casi d'uso e modalità replay

**Risultato.** I cinque casi d'uso (RF-39) funzionano in Python puro con porte finte, e in
modalità `VELA_UPSTREAM_MODE=replay` contro Postgres: il catalogo viene caricato da
`fixtures/catalog.json`, l'itinerario è simulato, il pagamento si simula visitando un link.

**Scope.**
- Modelli: intento e criteri, proposta, ordine con stati RF-25, rifiuti per intento.
- Parser minimo it/en: sport, area (dizionario di paesi/regioni/città presi dalle destinazioni
  in fixture), periodo (mese, stagione, "weekend", data), pax, budget, lingua. Una sola domanda
  se manca l'indispensabile (RF-04).
- Chooser v1: esclusioni di RF-07 (archiviati, non prenotabili, rifiutati, sport diverso, date
  fuori `minDate`/`maxDate`, pax fuori range) e ordinamento per prezzo crescente. Motivazione
  di una frase. "Niente di compatibile" con il criterio che fallisce (RF-09).
- Orchestratore dei 5 casi d'uso, campo `say` it/en su ogni risposta (RF-42), invariante
  "un solo prodotto per risposta" (RF-10), dati del viaggiatore all'accettazione (RF-12),
  default di indirizzo da configurazione (RF-13), doppio `accept` idempotente (RNF-03),
  totale reale dichiarato se diverso (RF-16), task post-pagamento in background con ripresa
  all'avvio (RF-27).
- Porte `HofJPort` e `PaymentsPort`; adapter replay: catalogo da fixture, itinerario sintetico
  (totale = prezzo × pax), customer/pax/booking finti con codice `R-<random>`; pagamento finto
  con link a `GET /replay/checkout/{order_id}` che segna l'ordine pagato (solo in replay).
- Repository Postgres con SQLAlchemy Core: `products`, `intents`, `proposals`, `orders`,
  `rejections`; migrazioni Alembic. Repository in memoria per i test.

**Test di completamento.**
- Parser: tabella di intenti it/en → criteri attesi (incluso l'esempio di §10.1).
- Chooser: mai un prodotto rifiutato, archiviato o non prenotabile; ordinamento; messaggio RF-09.
- Orchestratore con porte in memoria: flusso completo intento → proposta → rifiuto → proposta
  diversa → accettazione → pagamento simulato → `confirmed` con codice; doppio accept → stesso
  ordine; ripresa all'avvio di un `paid_pending_booking`.
- Invariante RF-10 verificato su ogni risposta dei test.
- Test dei repository Postgres eseguiti solo con `DATABASE_URL` (altrimenti `skip`).

**Copre.** RF-01, RF-02 (minimo), RF-04, RF-05, RF-06, RF-07 (v1), RF-08 (base), RF-09,
RF-10, RF-11, RF-12, RF-13, RF-15, RF-16, RF-25, RF-26, RF-27, RF-39, RF-42, RNF-01,
RNF-02, RNF-03, RNF-08.

**Prompt.**
> Leggi docs/spec.md (§2, §4.1-4.5, RF-39, RF-42, §5) e docs/roadmap.md M2. Obiettivo:
> dominio esagonale in `vela/domain`, porte in `vela/ports`, adapter replay in
> `vela/adapters`, repository Postgres con SQLAlchemy Core, parser minimo, chooser v1,
> orchestratore dei 5 casi d'uso con `say`. Nessuna superficie HTTP oltre
> `/replay/checkout`. Test: M2.

---

## M3 — Superficie MCP e primo test da claude.ai (Traguardo A)

**Risultato.** Su Render, in replay, un connector custom di claude.ai vede cinque tool e
completa il flusso di §10.1 (proposta singola, "troppo caro" → altra, "sì" → link, pagamento
simulato, stato `confirmed` con codice).

**Scope.**
- Server MCP con trasporto Streamable HTTP montato su `/mcp` nella stessa app FastAPI (SDK
  `mcp`), senza auth (ponte fino a M8), senza sessioni in memoria (RNF-13).
- Cinque tool con i nomi di RF-39; descrizioni per un modello che parla a voce: mai
  elencare alternative, leggere `say`, non leggere gli URL.
- Deploy su Render in replay; connector configurato in claude.ai; esecuzione del flusso.
- `docs/acceptance.md` nasce qui: tabella dei criteri di §10 con data, modalità, esito.

**Test di completamento.**
- Test in-process con il client MCP: `list_tools` restituisce 5 tool; il flusso completo
  passa; nessun risultato contiene più di un prodotto.
- Manuale: conversazione in claude.ai riportata in `docs/acceptance.md` (criterio 1 in replay,
  criterio 6).

**Copre.** RF-41 (parte Claude), RF-10 sulla superficie, §10.1 in replay, §10.6.

**Prompt.**
> Leggi docs/spec.md (RF-39, RF-41, RF-42, RF-10) e docs/roadmap.md M3. Obiettivo:
> superficie MCP Streamable HTTP su `/mcp` senza auth, 5 tool con descrizioni per uso vocale,
> deploy su Render in replay, test dal connector claude.ai, `docs/acceptance.md`. Test: M3.

---

## M4 — Superficie REST

**Risultato.** I cinque endpoint di RF-40 con bearer token, errori RFC 7807, `/health`
arricchito.

**Scope.**
- `POST /v1/intents`, `GET /v1/intents/{id}/proposal`, `POST /v1/proposals/{id}/reject`,
  `POST /v1/proposals/{id}/accept`, `GET /v1/orders/{id}`.
- Bearer `VELA_API_TOKEN`; 401 senza; `/health` pubblico con età catalogo e quota nota.
- Errori RFC 7807 (`application/problem+json`).

**Test di completamento.**
- TestClient: 401 senza token; flusso completo in replay con token; forma 7807; invariante RF-10.
- Manuale: criterio §10.3 in replay con `curl` contro Render, riportato in `docs/acceptance.md`.

**Copre.** RF-40, RF-43 (REST), RNF-06 (`/health`).

**Prompt.**
> Leggi docs/spec.md (RF-40, RF-43, RNF-06) e docs/roadmap.md M4. Obiettivo: adapter REST
> in `vela/surfaces/rest.py` sui casi d'uso esistenti, bearer statico, RFC 7807, `/health`
> con età catalogo e quota. Test: M4.

---

## M5 — HofJ reale: coda d'acquisto, scheduler della quota, prenotazione

**Risultato.** L'accettazione è asincrona (spec §4.10): risponde subito con stato `queued` e
attesa stimata; un job d'acquisto crea itinerario, cliente, pax, legge il totale reale e
produce il link; la prenotazione degli ordini pagati ha una riserva di quota garantita. Con
`VELA_UPSTREAM_MODE=live` tutto questo avviene contro HofJ vero. Il twist (50.000
viaggiatori in dieci minuti) diventa attesa dichiarata, non errori.

**Scope.**
- Primo passo, le verifiche di spec §8 (dichiarare ≤ 8 chiamate): `GET /v1/quota`,
  `POST /v1/itineraries` sul prodotto `t0054825`, `PUT customer`, `GET/PUT pax`,
  `POST /v1/bookings` con un `paymentIntentId` di un Checkout di test creato a mano. Esito e
  fallback (§8 riga 3) registrati in `docs/decisions.md`.
- Dominio (partendo da M2, già su `master`): `accept_proposal` diventa asincrono (RF-45);
  nuovi stati `queued`, `replaced`, `cancelled`, `failed` (RF-25); job d'acquisto a passi
  ripartibili (RF-46) al posto dell'accettazione sincrona; sostituzione in coda (RF-17);
  rinuncia (RF-49); ripresa al boot dei job (RF-27); attesa stimata (RF-48) e frasi `say`
  per attesa, sostituzione, fallimento.
- Scheduler della quota (RF-47, RF-36..38): contatore per finestra in Postgres, classi
  `booking`/`purchase`/`sync`, riserva configurabile, prenotazione atomica dei blocchi, 429,
  `/v1/quota` solo al boot e dopo un 429.
- Worker (RF-50): tabella `jobs`, prelievo con `FOR UPDATE SKIP LOCKED`, concorrenza per
  istanza; sostituisce `BookingRunner` di M2 (la prenotazione diventa un job di classe
  `booking`, RF-51). Migrazione `0003`.
- `vela/adapters/hofj_http.py` (httpx, timeout 15 s, envelope, RFC 7807, 502 `upstream-error`
  indistinguibile da id sbagliato, indirizzo `Address` da OAS non da DOCS).
- Prodotti non prenotabili: `bookable=false` e riabilitazione dopo 24 h (RF-33..35).
- Prenotazione (RF-23, RF-24): backoff, massimo tentativi, `booking_failed`.
- Adapter replay aggiornato: latenza e quota simulate configurabili (default zero e
  illimitata), così M13 può imporre 120/min e 2-6 s.
- Superfici già mergiate (M3, M4) adattate al nuovo contratto di `accept_proposal` e
  `get_order_status` (RF-19, RF-39), descrizione del tool `accept_proposal` aggiornata (RF-41).

**Test di completamento.**
- Accettazione: risponde `queued` con attesa senza chiamare le porte; doppio accept → stesso
  ordine; rinuncia → `cancelled` e proposta successiva.
- Job d'acquisto con porte in memoria: passi in sequenza, esito salvato per passo,
  interruzione a metà e ripresa senza ricreare l'itinerario, tre tentativi poi `failed`,
  errore prodotto → `replaced` con proposta sostitutiva, nuovo accept in testa alla coda.
- Scheduler con orologio finto: riserva `booking` rispettata a finestra piena, `purchase`
  FIFO, `sync` solo a coda vuota, blocco atomico, 429 azzera il budget, nessuna chiamata a
  `/v1/quota` in ciclo. Con due worker concorrenti sullo stesso contatore (test Postgres,
  saltato senza `DATABASE_URL`) il totale per finestra non supera mai il limite.
- Attesa stimata: posizione × 60 ÷ ((limite − riserva) ÷ 5); ricalcolata a ogni stato.
- Adapter HTTP con `httpx.MockTransport`: timeout, 429, 502, mapping errori prodotto/quota/rete.
- Prodotti: marcato al primo errore prodotto, riabilitato dopo 24 h.
- Booking: retry con backoff su 5xx, stop dopo N, `booking_failed` con motivo.
- Manuale: un itinerario reale creato e un booking reale su itinerario di test, chiamate
  contate in `docs/decisions.md`.

**Copre.** RF-14, RF-16, RF-17, RF-19, RF-23, RF-24, RF-25, RF-27, RF-33..38, RF-45..51,
RNF-04, spec §8.

**Prompt.**
> Leggi docs/spec.md (§4.3, §4.5, §4.7, §4.8, §4.10, §8, RNF-04), docs/decisions.md (sezioni
> "Roadmap" e "Twist"), docs/api/internal-checkout.md, docs/api/differences.md,
> docs/api/quota-health.md, il dominio di M2 in `vela/domain` e `vela/adapters`, e
> docs/roadmap.md M5. Obiettivo: accettazione asincrona con coda d'acquisto, scheduler della
> quota a tre classi, worker in ogni istanza, adapter HofJ HTTP, prenotazione con retry,
> superfici adattate al nuovo contratto. Prima le verifiche di §8, dichiarando le chiamate.
> Test: M5.

---

## M6 — Stripe: link di pagamento e webhook

**Risultato.** L'accettazione restituisce un link Stripe di test per il totale reale; il
pagamento arriva via webhook firmato, idempotente, e avvia la prenotazione; i link scadono.

**Scope.**
- `vela/adapters/stripe_links.py`: da decidere nel brainstorm se Payment Link o Checkout
  Session con `expires_at` (24 h, RF-21: i Payment Link non scadono da soli). EUR, `metadata`
  con ordine e itinerario, `VELA_PUBLIC_URL` per il ritorno.
- `vela/surfaces/webhooks.py`: `checkout.session.completed` e `checkout.session.expired`,
  firma con `STRIPE_WEBHOOK_SECRET`, tabella eventi per l'idempotenza, transizioni di stato.
- Il trigger della prenotazione usa il runner di M2; quando M5 è mergiata diventa un job di
  classe `booking` (RF-51): chi arriva secondo tra M5 e M6 fa l'adattamento.
- Nessun dato di carta in Vela (RF-21, RNF-07).

**Test di completamento.**
- Webhook con payload firmati (helper di firma di `stripe`): completed → `paid_pending_booking`
  e booking avviato; evento duplicato → nessun effetto; firma errata → 400; expired → `expired`.
- Manuale: Checkout di test con `4242 4242 4242 4242` contro Render (HofJ ancora replay):
  ordine `confirmed` con codice finto.

**Copre.** RF-18..22, RNF-03, RNF-07 (carte).

**Prompt.**
> Leggi docs/spec.md (§4.4, RNF-03, RNF-07) e docs/roadmap.md M6. Obiettivo: adapter Stripe
> reale (link con scadenza 24 h, metadata), webhook firmato e idempotente, transizioni
> dell'ordine, trigger della prenotazione in background. Test: M6.

---

## M7 — Prima prenotazione reale end-to-end (Traguardo B)

**Risultato.** Su Render in `live`, da claude.ai e da `curl`, un intento finisce in un codice di
prenotazione reale di HofJ. Un prodotto che fallisce al carrello viene sostituito.

**Scope.**
- Render in `VELA_UPSTREAM_MODE=live` con tutte le variabili.
- Criteri §10.1, §10.3, §10.4 eseguiti e registrati in `docs/acceptance.md` con codice.
- Latenza di un flusso reale misurata (serve a M13).
- Correzioni di ciò che si rompe, in questa task.

**Test di completamento.**
- Suite verde; `docs/acceptance.md` con criteri 1, 3, 4 verdi, data, codice di prenotazione.

**Copre.** §10.1, §10.3, §10.4, §10.7 (prima verifica).

**Prompt.**
> Leggi docs/spec.md §10 e docs/roadmap.md M7. Obiettivo: eseguire i criteri 1, 3 e 4 in
> `live` su Render, dichiarando le chiamate HofJ e Stripe, correggere quel che si rompe,
> registrare esiti e latenza in docs/acceptance.md. Test: M7.

---

## M8 — OAuth 2.1 sulla superficie MCP

**Risultato.** `/mcp` richiede un bearer ottenuto con OAuth 2.1; il connector claude.ai si
autorizza da solo; i client senza OAuth (ElevenLabs) usano un token statico pre-provisionato.

**Scope.**
- Authorization server nella stessa app: metadata (RFC 8414, RFC 9728), registrazione dinamica
  (RFC 7591), PKCE, endpoint di autorizzazione con pagina minima protetta da `VELA_API_TOKEN`
  (unica pagina web oltre Stripe: da confermare nel brainstorm), endpoint token, token e client
  in Postgres.
- `/mcp` risponde 401 con `WWW-Authenticate` senza token; il ponte senza auth viene rimosso.
- `VELA_API_TOKEN` accettato anche su `/mcp` come token statico per ElevenLabs.

**Test di completamento.**
- Test HTTP: metadata, DCR, flusso PKCE completo con client finto, `/mcp` 401 senza token e
  200 con token OAuth o statico.
- Manuale: connector claude.ai ricreato con OAuth, flusso replay ripetuto (criterio 1).

**Copre.** RF-43 (MCP, come modificato).

**Prompt.**
> Leggi docs/spec.md (RF-43 aggiornato, RF-41), docs/decisions.md (roadmap) e
> docs/roadmap.md M8. Obiettivo: OAuth 2.1 per `/mcp` (metadata, DCR, PKCE, token in
> Postgres), pagina di consenso minima, token statico per client senza OAuth, rimozione del
> ponte senza auth. Test: M8.

---

## M9 — Parser completo, rifiuto con motivo, fallback Haiku

**Risultato.** RF-02, RF-03 e RF-08 completi: dizionari it/en estesi, intervalli di date,
motivi di rifiuto che modificano i criteri, fallback Claude Haiku 4.5 solo con chiave presente.

**Scope.**
- Dizionari: paesi, regioni, città (da `destinations` e `geohierarchy` della fixture), mesi,
  stagioni, intervalli ("dal 10 al 14 ottobre"), "weekend", pax ("siamo in due"), budget
  ("max 800 euro", "under 1000").
- Rifiuto: "troppo caro" abbassa il budget sotto il prezzo proposto, "più a sud"/"più vicino"
  cambia area, "a novembre" cambia periodo, motivo non riconosciuto → esclude solo il prodotto.
- Fallback: SDK `anthropic` (dipendenza da concordare), modello `claude-haiku-4-5-20251001`,
  schema identico, attivo solo se manca sport o periodo e `ANTHROPIC_API_KEY` esiste; chiamate
  dichiarate nei test manuali. Interruttore a concorrenza limitata (RNF-12): oltre il limite
  si pone la domanda di RF-04.

**Test di completamento.**
- Tabelle parser it/en (≥ 30 casi); rifiuti con motivo → criteri attesi; fallback con client
  finto; chiave assente → nessun errore, nessuna chiamata.

**Copre.** RF-02, RF-03, RF-08.

**Prompt.**
> Leggi docs/spec.md (RF-02, RF-03, RF-04, RF-08) e docs/roadmap.md M9. Obiettivo: parser
> deterministico completo it/en, interpretazione dei motivi di rifiuto, fallback Haiku
> opzionale. Nessuna chiamata ad Anthropic nei test automatici. Test: M9.

---

## M10 — Sync multi-brand del catalogo da HofJ

**Risultato.** Il catalogo in Postgres contiene tutti i brand configurati (padel = Weebora,
tennis = Terrarossa; su staging `staging.weebora.com` e `staging.tennis.weebora.com`) e si
aggiorna da solo: al boot se vuoto o vecchio, poi ogni 6 h, con advisory lock, per lotti,
ritmato dal guardiano; `python -m vela.sync` lo forza. Se l'utente chiede tennis Vela cerca in
Terrarossa, se chiede padel in Weebora, con `sport=any` in entrambi. Ogni chiamata del carrello
e della prenotazione usa il brand del prodotto dell'ordine, anche dopo un riavvio o un retry del
job. Le fixture, una per (host, brand), si rigenerano dallo stesso codice e servono solo a
replay e test. Casi d'uso in `docs/usecases/multi-brand.md` (MB1-MB9).

**Scope.**
- Config: `HOFJ_BRANDS="padel=weebora.com,tennis=terrarossa.com"` (sport → brand) al posto di
  `HOFJ_BRAND`. Sport ammessi `padel` e `tennis`, brand distinti, almeno una voce; errori →
  l'app non parte con un messaggio esplicito. `HOFJ_BRAND` impostata senza `HOFJ_BRANDS` →
  l'app non parte e dice di migrare. Una sola voce è valida: l'altro sport dà il `no_match`
  esistente. `render.yaml`, `vela/config.py`, `docs/fixtures.md` aggiornati.
- `vela/sync.py`: per ogni brand della mappa, lista paginata `limit=100` con `?brand=`,
  dettaglio solo per nuovi o `updatedAt` cambiato, filtro non archiviati, scrittura per lotti
  nella stessa tabella `products`, advisory lock unico per tutti i brand, scheduler in
  background, comando manuale. Archiviazione **per brand**: un prodotto sparito dalla lista di
  un brand è archiviato solo tra i prodotti di quel brand, e un brand il cui sync fallisce non
  archivia nulla. Un id già presente con un altro brand ferma il sync di quel brand con un
  errore esplicito (decisione M10 sulla chiave degli id).
- `products.brand` (migrazione Alembic `0006`, colonna nullable, nessun'altra tabella cambia):
  il sync la scrive; lo sport si ricava dal brand tramite la mappa della config; `detect_sport`
  resta solo come fallback (fixture senza brand, brand non in mappa). Le righe già su Render
  hanno `brand` NULL finché il primo sync non le riscrive.
- Carrello: un `HofJHttp` per brand, stessa chiave e stesso host. Nuova porta `HofJRouter`
  (`client(brand) -> HofJPort`, `get_quota()`); `HofJPort` invariata. `PurchaseJob` e
  `BookingJob` ricavano il brand da ordine → `product_id` → `products.brand` a ogni esecuzione e
  usano quel client per tutte le chiamate; con `brand` NULL usano il brand dello sport del
  prodotto. La quota è per chiave API: una sola, letta da un client qualsiasi. In replay tutti i
  brand puntano allo stesso `ReplayHofJ`.
- Live: il sync sostituisce `realign_catalog` e la fixture al boot (decisione M7 superata per il
  live). Replay e test: una fixture per (host, brand), `select_fixture` diventa la selezione di
  tutte le fixture dell'host, il replay carica tutti i brand dell'host. Il comando di
  rigenerazione usa lo stesso codice del sync (sostituisce `scripts/record_catalog.py` o lo
  riusa). Da registrare: Terrarossa in produzione e `staging.tennis.weebora.com` su staging,
  chiamate dichiarate prima.
- `is_trip`: esclude la gift card di qualunque brand, non solo "Weebora", e la categoria dei
  pacchetti evento (Terrarossa: `categoryId` 23 in produzione, 15 su staging), identificata
  per nome di categoria perché gli id cambiano tra gli host. Il nome si legge dai dettagli
  quando si registrano le fixture Terrarossa, senza chiamate dedicate. Tutta la categoria è
  esclusa, anche Watch & Play e i tornei amatoriali (decisione M10).
- Chooser, MCP e REST non cambiano: il filtro sport basta (`sport=any` = nessun filtro, M17).
- Tabella `products` completa di RF-28.

**Test di completamento.**
- Sync con porta finta e due brand finti: prodotti di entrambi scritti con il loro `brand` e lo
  sport ricavato dal brand; nuovi/cambiati/invariati; lotti; interruzione a metà → catalogo
  coerente; un brand che fallisce non archivia nulla e non tocca l'altro; id duplicato fra
  brand → errore esplicito; lock (test saltato senza DB); scheduler con orologio finto.
- Un ordine tennis usa il client Terrarossa in tutte le chiamate del carrello (client finti per
  brand che registrano le chiamate).
- Una ricerca con `sport=any` restituisce candidati di entrambi i brand.
- `is_trip` falso per un prodotto finto della categoria evento e per la gift card di un brand
  diverso da Weebora; MB9 (tennis a Torino a novembre non propone l'Hospitality delle Finals).
- Un retry del job di booking dopo un riavvio (nuovo processore, stesso DB) usa ancora il brand
  giusto.
- Config: formato valido, sport sconosciuto, brand duplicato, `HOFJ_BRAND` senza
  `HOFJ_BRANDS` → errore all'avvio.
- Migrazione `0006` applicata anche su SQLite (`tests/test_migrations.py`).
- MB1-MB9 di `docs/usecases/multi-brand.md` come test dei casi d'uso con repository in memoria.
- Manuale: un sync su Render con chiamate contate; `/health` mostra l'età aggiornata; da
  claude.ai una richiesta di tennis riceve una proposta Terrarossa (in `docs/acceptance.md`).

**Copre.** RF-28..31, RF-32 (una fixture per host e brand), RF-56.

**Taglia.** L (> 4 h): al sync incrementale si aggiungono config, migrazione, router del
carrello e fixture per brand. **Dipende da** M5 (su `master`). **Ondata** 5, in parallelo con
M12, M13, M14 e M17 (M10 non tocca `chooser.py`: `sport=any` resta di M17; file comune
possibile `usecases.py`).

**Prompt.**
> Leggi docs/spec.md (§4.6, §4.8, RF-56, §6), docs/usecases/multi-brand.md, docs/decisions.md
> (M7 e 2026-09-26 M10 multi-brand), vela/app.py (build_hofj, realign_catalog),
> vela/domain/catalog.py, vela/adapters/hofj_http.py, vela/adapters/schema.py,
> vela/domain/purchase.py, vela/domain/booking.py e docs/roadmap.md M10. Obiettivo: config
> `HOFJ_BRANDS`, job di sync incrementale multi-brand con advisory lock e scheduler, colonna
> `products.brand` (migrazione 0006), router del carrello per brand, una fixture per (host,
> brand) rigenerata dallo stesso codice. Dichiara le chiamate prima di ogni sync o
> registrazione reale. Test: M10.

---

## M11 — Raffinamento della scelta (chooser v2)

**Risultato.** L'ordinamento completo di RF-07 (aderenza all'area, rispetto del budget, prezzo)
con compatibilità di date su finestre di disponibilità e durata, e motivazioni legate all'intento.

**Scope.**
- Aderenza geografica su `geohierarchy` (città > regione > paese); budget totale = prezzo × pax;
  date: intersezione del periodo con `availabilities`, durata; pax entro `minPax`/`maxPax`.
- Motivazione di 1-2 frasi che cita il criterio soddisfatto; RF-09 dice quale criterio manca.

**Test di completamento.**
- Tabelle sul catalogo in fixture: stesso intento → prodotto atteso; rifiuti in sequenza; casi
  limite (nessun match su area, budget, periodo).
- Proprietà: mai rifiutato/archiviato/non prenotabile, mai più di un prodotto.

**Copre.** RF-06, RF-07, RF-09 (completi).

**Prompt.**
> Leggi docs/spec.md (§4.2) e docs/roadmap.md M11. Obiettivo: chooser v2 deterministico con
> ordinamento completo e motivazioni. Test: M11.

---

## M12 — Agente vocale ElevenLabs

**Risultato.** Un agente ElevenLabs Conversational AI collegato all'MCP completa il flusso a
voce; il link di pagamento viene consegnato per testo.

**Scope.**
- Configurazione dell'agente (prompt di sistema in italiano, tool MCP con token statico di M8),
  prova del flusso, fallback di spec §8 riga 5 se il link non passa.
- `docs/elevenlabs.md` con la configurazione riproducibile (senza segreti).

**Test di completamento.**
- Manuale: criterio §10.2 registrato in `docs/acceptance.md`.

**Copre.** RF-41 (ElevenLabs), §10.2, spec §8 riga 5.

**Prompt.**
> Leggi docs/spec.md (RF-41, RF-42, §8, §10.2) e docs/roadmap.md M12. Obiettivo: agente
> ElevenLabs collegato all'MCP, flusso vocale completo, configurazione documentata. Test: M12.

---

## M13a — Banco di prova e numeri di partenza

**Risultato.** Un load test lanciabile da chiunque con `docker compose up` e un comando, che
colpisce solo la nostra edge; `loadtest/RESULTS.md` con la colonna "prima" misurata sul codice
attuale. Il test dimostra un confine: le chiamate a HofJ al minuto restano sotto 108 con
1.000, 10.000 e 50.000 viaggiatori. Decisione del 2026-09-26 in `docs/decisions.md` ("Twist,
seconda lettura").

**Scope.**
- Finto HofJ HTTP in `loadtest/fake_hofj/`: app ASGI asincrona, un processo; stato da
  `ReplayHofJ` con latenza 0 e quota illimitata; sopra, uno strato di regole con le rotte del
  carrello, `/v1/quota`, `POST /v1/bookings`, lista e dettaglio prodotti dalle 4 fixture per il
  sync di M10; forme reali dell'envelope e degli errori.
- Il finto applica le **regole di HofJ, non le nostre**: quota per chiave, 120/min, con
  `--window anchored` (default, come misurato in `docs/api/quota-health.md`) o `rolling`;
  `--background-rpm` per gli altri usi della chiave; latenza 2-6 s su `POST /v1/itineraries` e
  tarata su `scripts/rest_flow.py` per gli altri endpoint, `--latency pessimistic`; guasti per
  endpoint: esegui-e-resta-appeso oltre 15 s, appeso senza eseguire, 5xx, 502 di prodotto;
  seme fisso; registro JSONL di ogni chiamata; `/_fake/stats` e `/_fake/reset` fuori quota.
  Le verifiche si fanno sul registro del finto, non sui log di Vela.
- Modo `VELA_UPSTREAM_MODE=loadtest`: HofJ via HTTP verso il finto, pagamenti finti, checkout
  di replay; rifiuta host diversi da localhost o `fake-hofj`. Serve perché il modo `live`
  richiede `STRIPE_SECRET_KEY` e non monta il checkout finto (`vela/app.py`), e perché
  `render.yaml` punta a HofJ staging: un load test contro Render porterebbe il carico a HofJ.
- `docker-compose.yml` con vela, postgres, fake-hofj.
- Scenario Locust a modello aperto: 50.000 arrivi in 10 minuti, imbuto parametrico (100%
  proposta, 30% "troppo caro", 20% accetta, stato ogni 30-60 s, 60% paga); sentinelle Marco
  (accetta al minuto 1, confermato entro il 7) e Anna (arriva al 6, proposta < 500 ms e attesa
  dichiarata); giri a 1k, 10k, 50k.
- `loadtest/report.py`, `loadtest/RESULTS.md`, `loadtest/README.md`.
- Non tocca `vela/domain/quota.py` né il `QuotaStore` (M18 in parallelo).

**Misure del report.** Massimo di chiamate in qualsiasi 60 s; numero di 429; chiamate per
endpoint e al minuto nei tre giri; link al minuto; Marco pagamento → confermato; scarto p95
tra attesa dichiarata e reale; prenotazioni per `itineraryId`; itinerari orfani; età della
coda; p50/p95/p99 dei cinque casi d'uso.

**Test di completamento.**
- Test unitari del finto: finestra ancorata e scorrevole ai bordi; esegui-e-appeso sul booking
  → un solo codice.
- Test di contratto del vero `HofJHttp` contro il finto via transport ASGI.
- Scenario eseguito e `RESULTS.md` compilato anche se i numeri sono cattivi: sono il "prima".
  Le previsioni della seconda lettura (deriva del contatore, ~12 acquisti/min con 4 worker) si
  confermano o si smentiscono qui.
- Nessuna chiamata a HofJ né a Stripe.

**Copre.** RNF-05, RNF-10, §10.5.

**Taglia.** M. **Dipende da** M5, M10. **Ondata** 5, parallela con M18 e M20; mergiare prima
di M18.

**Prompt.**
> Leggi docs/spec.md (§4.8, §4.10, RNF-05, RNF-08, RNF-10, §10.5), docs/decisions.md
> ("2026-09-26 — Twist, seconda lettura"), docs/plans/2026-09-26-twist-seconda-lettura.md
> (sezioni 3.5, 5, 6), docs/api/quota-health.md, docs/api/internal-checkout.md,
> vela/adapters/replay.py, vela/adapters/hofj_http.py, vela/app.py, render.yaml,
> scripts/rest_flow.py e docs/roadmap.md M13a. Obiettivo: finto HofJ HTTP con le regole di
> HofJ (finestra ancorata di default), modo `loadtest`, docker compose, scenario Locust a
> modello aperto con le sentinelle Marco e Anna, report e colonna "prima" di RESULTS.md sul
> codice attuale. Non toccare `vela/domain/quota.py`. Nessuna chiamata a HofJ né a Stripe.
> Test: M13a.

---

## M13b — Rilancio dopo M18

**Risultato.** Lo stesso scenario di M13a (seme, imbuto, finestre `anchored` e `rolling`, tre
giri) rilanciato sul codice con M18; `loadtest/RESULTS.md` con le colonne "prima" e "dopo" e una
frase per ogni differenza. I due risultati affiancati sono la prova del "diff nel pensiero".

**Scope.**
- Nessuna modifica allo scenario né al finto rispetto a M13a.
- Se un criterio fallisce (429 > 0, più di 108 chiamate in 60 s, Marco oltre il minuto 7,
  prenotazioni doppie) si riporta il dato, non si aggiusta il test.

**Test di completamento.**
- `RESULTS.md` con "prima" e "dopo" per entrambe le finestre e i tre giri; ogni criterio
  riportato come passato o fallito con il numero.

**Copre.** RNF-05, RNF-10, §10.5.

**Taglia.** S. **Dipende da** M13a, M18. **Ondata** 5.

**Prompt.**
> Leggi docs/roadmap.md M13a, M13b e M18, loadtest/README.md e loadtest/RESULTS.md.
> Obiettivo: rilanciare lo scenario di M13a senza cambiarlo sul codice con M18 e compilare la
> colonna "dopo" con una frase per differenza. Se un criterio fallisce, riportare il dato
> senza aggiustare il test. Test: M13b.

---

## M18 — Quota a ritmo costante

**Risultato.** Nessun intervallo di 60 s contiene più di 108 chiamate HofJ, qualunque sia la
regola della finestra di HofJ (ancorata come misurato, a griglia o scorrevole come dicono
brief e OAS). Corregge la deriva del contatore a griglia di `vela/domain/quota.py` rispetto
alla finestra ancorata di HofJ (effetto previsto, da confermare con M13a) e porta concorrenza e
timeout al livello richiesto dalla latenza. Decisione del 2026-09-26 in `docs/decisions.md`
("Twist, seconda lettura").

**Scope.**
- `QuotaStore` come token bucket condiviso in Postgres: ritmo r, capienza B, con
  B + 60·r ≤ 108 (esempio B = 8, r = 100/60); stesse classi `booking`/`purchase`/`sync` e
  priorità, riserva `booking`, prenotazione atomica di blocchi.
- 429 → bucket svuotato e una sola rilettura di `/v1/quota` (1 token `booking`), mai ripetizione
  immediata.
- `next_window_start` e attesa stimata (RF-48) aggiornati al ritmo del bucket.
- `worker_concurrency` ~10 (legge di Little: ~6-9 chiamate contemporanee con 2-6 s di
  latenza); il ritmo lo decide il bucket, non il numero di thread.
- Timeout del client HofJ a 20 s (`TIMEOUT_SECONDS` in `vela/adapters/hofj_http.py`), più di
  quello di HofJ verso il brand (15 s).
- Timeout su `POST /v1/itineraries` contato come itinerario orfano (campo o log) e messo nel
  budget; `POST /v1/bookings` resta ripetuto perché upsert idempotente su `itineraryId`.
- Lease dei job (`job_lease_seconds`) rivisto per 5 chiamate × 20 s.
- `/health` con età della coda e stato del bucket.

**Test di completamento.**
- Contratto condiviso memoria/Postgres del bucket: mai più di 108 in una finestra scorrevole
  simulata di 60 s, anche con finestre HofJ ancorate a istanti diversi.
- 8 thread su Postgres (saltato senza `DATABASE_URL`).
- Riserva `booking` rispettata a coda piena.
- 429 senza ripetizione immediata.
- `LaunchBurstTest` aggiornato.
- Nessuna chiamata esterna.

**Copre.** RF-36..RF-38, RF-47, RF-48, RNF-04.

**Taglia.** M. **Dipende da** M5. **Ondata** 5, parallela con M13a e M20; mergiare dopo M13a.

**Prompt.**
> Leggi docs/spec.md (RF-36..RF-38, RF-47, RF-48, RNF-04), docs/decisions.md ("2026-09-26 —
> Twist, seconda lettura"), docs/plans/2026-09-26-twist-seconda-lettura.md (sezioni 3.1-3.3),
> docs/api/quota-health.md, vela/domain/quota.py, vela/domain/purchase.py,
> vela/domain/booking.py, vela/adapters/hofj_http.py, vela/config.py e docs/roadmap.md M18.
> Obiettivo: token bucket condiviso in Postgres con B + 60·r ≤ 108, concorrenza ~10, client a
> 20 s, orfani contati, lease rivisto, `/health` con età della coda. Nessuna chiamata
> esterna. Test: M18.

---

## M19 — Meno chiamate per link e ordini silenziosi (condizionata)

**Risultato.** Le chiamate HofJ si spendono su chi pagherà (look-to-book): se HofJ lo consente,
chi non paga costa 2 chiamate invece di 5 e i link al minuto passano da ~17 a ~43 (stima,
da misurare con lo scenario di M13a); gli ordini in coda il cui viaggiatore non dà più segni di
vita non consumano quota. Proposta del 2026-09-26 in `docs/decisions.md` ("Twist, seconda
lettura").

**Scope.**
- Primo passo, verifica su staging con 2-3 chiamate dichiarate (lanciate dal terminale
  dell'utente): `PUT customer` e `PUT pax` sono accettati dopo il pagamento? Il totale resta
  invariato dopo i pax? (Domanda 10 in `docs/hofj-questions.md`.)
- Se sì: il job d'acquisto si ferma a itinerario + totale + link; cliente e pax passano nel
  job di booking (riserva `booking` a 4 chiamate per ordine pagato).
- Scadenza degli ordini in coda senza richieste di stato da N minuti.
- Se la verifica dice no: solo il trade-off documentato in `ARCHITECTURE.md` (M15).

**Test di completamento.**
- Job d'acquisto a 2 chiamate e job di booking a 4 con porte in memoria; ordine silenzioso
  scaduto senza chiamate HofJ; scenario di M13a rilanciato con i link al minuto.
- Chiamate a staging solo quelle dichiarate nel primo passo.

**Copre.** RF-46, RF-47 (ripartizione del budget), RF-51.

**Taglia.** M. **Dipende da** M18, M13b (cambia i numeri). **Ondata** 5, condizionata.

**Prompt.**
> Leggi docs/decisions.md ("2026-09-26 — Twist, seconda lettura"),
> docs/plans/2026-09-26-twist-seconda-lettura.md (sezione 3.4), docs/hofj-questions.md
> (domanda 10), docs/api/internal-checkout.md, vela/domain/purchase.py,
> vela/domain/booking.py, loadtest/RESULTS.md e docs/roadmap.md M19. Obiettivo: prima la
> verifica su staging (2-3 chiamate, dichiarate e lanciate dall'utente); se HofJ accetta
> cliente e pax dopo il pagamento, spostarli nel job di booking; scadenza degli ordini
> silenziosi. Se la verifica dice no, solo il trade-off. Test: M19.

---

## M14 — Hardening: log JSON, health, dati personali, segreti

**Risultato.** Log strutturati, `/health` completo, comando di cancellazione dei dati
personali, verifica che nessun segreto sia nel repo né negli agent-log.

**Scope.**
- Log JSON su stdout con id intento/ordine, chiamate HofJ con esito e quota residua.
- `/health`: DB, età catalogo, quota residua nota.
- Catalogo in memoria per istanza, ricaricato da Postgres ogni minuto (RNF-12).
- `python -m vela.forget <order_id|--all>` cancella i dati di RF-12.
- Script di verifica: `git grep` sulle chiavi note (senza stamparle), ricerca di letture di
  `.env` in `agent-log/`.

**Test di completamento.**
- Test dei log (righe JSON con gli id), di `/health`, del comando di cancellazione.
- Script di verifica eseguito e verde (§10.7).

**Copre.** RNF-06, RNF-07, §10.7.

**Prompt.**
> Leggi docs/spec.md (RNF-06, RNF-07, §10.7) e docs/roadmap.md M14. Obiettivo: log JSON,
> `/health` completo, comando di cancellazione dati, script di verifica segreti. Test: M14.

---

## M15 — Consegna: ARCHITECTURE.md, README, video

**Risultato.** Tutte le consegne del brief pronte: URL live, repo, `ARCHITECTURE.md`,
`agent-log/`, load test, video.

**Scope.**
- `ARCHITECTURE.md`: decisioni e compromessi (da `docs/decisions.md`), vincoli del prototipo
  (RF-13), prossimi passi: adapter A2A (agent card, mapping dei task sui 5 casi d'uso, RF-44),
  email del codice (RF-26), OAuth per REST.
- `ARCHITECTURE.md`, sezione twist con le 5 richieste del brief (fonte:
  `docs/plans/2026-09-26-twist-seconda-lettura.md` e `docs/decisions.md`, "2026-09-26 — Twist,
  seconda lettura"): (1) l'architettura e il diff nel pensiero (sezione 4 del piano); (2) il
  budget di quota per browse, cart, hotel, booking e cosa si sacrifica per primo (sezione 5);
  (3) cosa degrada e cosa no, con il minuto sei visto da Marco e Anna (sezione 6); (4)
  l'upsert idempotente di `POST /v1/bookings` e dove ci contiamo già, con il riferimento a
  `BookingJob.run` (sezione 3.3); (5) il load test con i numeri "prima" e "dopo" di
  `loadtest/RESULTS.md` (M13a, M13b). Più i precedenti documentati (sezione 7 del piano).
- `README.md`: variabili, avvio, test, deploy, load test, come collegare Claude ed ElevenLabs.
- Video 3-5 min: acquisto reale con Claude e con ElevenLabs.
- Checklist finale dei 7 criteri di §10 in `docs/acceptance.md`.

**Test di completamento.**
- Tabella di §10 tutta verde; un lettore esterno deploya seguendo solo il README; video
  caricato e linkato nel README.

**Copre.** RF-13 (documentazione), RF-26, RF-44, spec §9.

**Dipende da** tutte, in particolare M13b (i numeri del load test).

**Prompt.**
> Leggi docs/brief.md (Deliverables e "The twist"), docs/spec.md (§9, §10, RF-44, RF-26),
> docs/decisions.md, docs/plans/2026-09-26-twist-seconda-lettura.md, loadtest/RESULTS.md e
> docs/roadmap.md M15. Obiettivo: ARCHITECTURE.md con la sezione twist (5 richieste del brief e
> precedenti), README, video, checklist finale. Test: M15.

---

## M16 — (opzionale) Superficie A2A

Solo se resta tempo dopo M15. Agent card, mapping dei task A2A sui 5 casi d'uso, stessa auth
di M8. Test: client A2A finto che completa il flusso in replay. Copre RF-44 (implementazione).

---

## M17 — Contratto agente-tool e sinonimi dello sport

**Risultato.** L'agente passa a Vela i criteri che ha già capito come campi strutturati, e
ogni cambiamento dopo una proposta passa da `reject_proposal` sullo stesso intento: il caso
osservato il 2026-09-26 ("troppo caldo, vorrei un posto più freddo" → nuovo `create_intent` →
stessa proposta) non si ripete. Lo sport è sempre chiesto; "indifferente" vale `any`. Il `say`
ripete i criteri capiti. I client che mandano solo testo funzionano come prima, più la domanda
sullo sport. Casi d'uso in `docs/usecases/agente-tool.md` (UC1-UC9).

**Scope.**
- Campi strutturati opzionali su `create_intent` e `reject_proposal` (RF-52), MCP e REST con lo
  stesso contratto: `sport` (`padel` | `tennis` | `any`), `area`, `period_start`,
  `period_end`, `pax`, `budget`; `direction` (`north` | `south`) solo sul rifiuto. `text` e
  `reason` restano. Modifica additiva; `docs/rest.md` aggiornato.
- Precedenza e validazione (RF-53) in `usecases.py`, `intent.py`, `refine.py`: campo valido >
  parser > Haiku (solo `create_intent`); campo invalido scartato e dichiarato; conflitto
  testo/campo e `area`/`direction` nei log.
- RF-04 nuovo: sport sempre indispensabile, `question` "Padel o tennis?" / "Padel or tennis?"
  prima di pax, nessun intento salvato; RF-03: Haiku parte quando manca lo sport; lo schema di
  `adapters/haiku.py` accetta `any`.
- `sport=any` nei criteri (valore nuovo nel JSON di `intents.criteria`, nessuna migrazione) e
  nel chooser: nessun filtro sport. `None` resta "non detto".
- `say` (RF-54): criteri capiti sempre ripetuti, campi scartati, motivo non traducibile.
- Descrizioni dei tool MCP (RF-41): chiedere lo sport prima di `create_intent`; dopo una
  proposta ogni cambiamento via `reject_proposal`; `get_proposal` e `create_intent` non
  suggeriscono più di riformulare; "più fresco" → `north`, "più caldo" → `south`.
- "Niente di compatibile" dopo un rifiuto (RF-55): la risposta riporta l'id della proposta
  rifiutata; un secondo `reject_proposal` su quella proposta aggiorna i criteri senza un nuovo
  rifiuto (vincolo `uq_rejections_proposal_id` invariato).
- Parser, decisioni aperte da chiudere nel brainstorm (raccomandazione in grassetto):
  - Sinonimi ("terra rossa", "clay", "Terrarossa" → tennis; "paddle", "Weebora" → padel):
    **A) dizionario fisso in `intent.py`**, deterministico e testabile; B) dizionario ricavato
    dai titoli del catalogo (lega il parser al catalogo); C) solo Haiku.
  - "padel e tennis" nella stessa frase (oggi vince il primo): **A) `any`**, è quello che il
    viaggiatore ha detto; B) domanda "Padel o tennis?"; C) il primo, come oggi.
  - "beach tennis", "paddle tennis": **A) esclusioni controllate prima dei sinonimi → sport non
    riconosciuto → domanda**; B) frase dedicata "non vendiamo beach tennis", solo se il caso
    capita davvero.
  - Nomi di tornei (es. Internazionali di Roma → tennis, solo se il catalogo li vende):
    **A) fuori da M17: l'agente li risolve col campo `sport`, Haiku come riserva**; B) lista
    fissa attiva solo se un titolo del catalogo la contiene; C) nomi estratti dai titoli del
    catalogo. B e C tra i prossimi passi.
  - "più fresco", "più freddo", "cooler" / "più caldo", "warmer" nel motivo di rifiuto:
    **A) `refine.py` li traduce in north/south come rete di sicurezza per i client solo testo**;
    B) solo tramite `direction` passato dall'agente.

**Test di completamento.**
- UC1-UC9 di `docs/usecases/agente-tool.md` come test dei casi d'uso con repository in memoria,
  e i casi UC1, UC4, UC7, UC8 anche come test MCP (`test_mcp_tools`) e REST (`test_rest`).
- UC4 in particolare: dopo "troppo caldo" con `direction=north` la proposta è diversa da quella
  rifiutata e l'intento è lo stesso.
- Tabelle parser: sinonimi, "padel e tennis" → `any`, "beach tennis"/"paddle tennis" non
  diventano tennis, "più fresco" → north.
- Precedenza: campo > parser > Haiku (client finto, nessuna chiamata reale); campo invalido
  scartato e presente nel `say`; conflitto nei log (`assertLogs`).
- RF-04: senza sport → `question` e nessun intento nel repository; `any` → nessun filtro sport.
- Client solo testo: i test di parser, rifiuto e flusso esistenti restano verdi (modifica
  additiva), salvo quelli che fissavano "sport oppure periodo", aggiornati e elencati in
  `docs/decisions.md`.
- `no_match` dopo un rifiuto → secondo `reject_proposal` sulla stessa proposta → nuova proposta,
  un solo rifiuto registrato.
- Descrizioni MCP: nessuna contiene l'invito a riformulare con `create_intent` dopo una proposta.
- Manuale: in claude.ai, il dialogo del 2026-09-26 ripetuto in replay (UC4), registrato in
  `docs/acceptance.md`.

**Copre.** RF-01, RF-02 (sport `any`, sinonimi), RF-03, RF-04, RF-08, RF-09, RF-39..42
(contratto aggiornato), RF-52..55.

**Taglia.** M (3-4 h). **Dipende da** M3, M4, M9, M11 (tutte su `master`). **Ondata** 5, in
parallelo con M10 (file comune possibile `usecases.py`; `chooser.py` è solo di M17), M12 (se M12 parte prima,
il prompt ElevenLabs va riletto dopo il merge di M17: le descrizioni dei tool cambiano), M13,
M14.

**Prompt.**
> Leggi docs/spec.md (RF-01..04, RF-08, RF-09, RF-39..42, §4.11), docs/usecases/agente-tool.md,
> docs/decisions.md (2026-09-26, contratto agente-tool), vela/surfaces/mcp.py,
> vela/surfaces/rest.py, vela/domain/intent.py, vela/domain/refine.py,
> vela/domain/usecases.py, vela/domain/chooser.py, vela/domain/say.py e docs/roadmap.md M17.
> Obiettivo: campi strutturati su `create_intent` e `reject_proposal` (MCP e REST), precedenza
> campo > parser > Haiku, sport sempre chiesto con `any`, `say` che ripete i criteri, descrizioni
> dei tool che mandano ogni cambiamento dopo una proposta su `reject_proposal`, sinonimi dello
> sport. Prima chiudi le decisioni aperte sul parser. Nessuna chiamata ad Anthropic nei test.
> Test: M17.

---

## M20 — Accettazione con attesa breve quando la coda è vuota

**Stato (2026-09-27).** Assorbita dalla conferma del prezzo ("Prezzo effettivo prima del link",
2026-09-26): `accept_proposal` aspetta già il job fino a 100 s per ogni posizione. Da M20 restano
solo test e la correzione di RNF-04 (`docs/decisions.md`, "M20 assorbita dalla conferma del
prezzo"). Il resto della sezione è il piano originale.

**Risultato.** Chi accetta una proposta senza nessuno davanti in coda riceve il link di
pagamento nella stessa risposta, quando HofJ è abbastanza veloce, invece di sentirsi dire "ti
ho messo in coda" e dover chiedere lo stato. Sotto picco non cambia nulla. Il percorso resta
uno solo: il carrello lo prepara sempre il job d'acquisto, `accept_proposal` continua a non
chiamare HofJ né Stripe (RF-45). Decisione del 2026-09-26 in `docs/decisions.md`
("Accettazione con attesa breve").

**Scope.**
- `accept_proposal` (`vela/domain/usecases.py`): dopo aver accodato l'ordine, se la posizione
  è 1 attende fino a `accept_wait_seconds` (campo di `Settings`, default 10, nessuna variabile
  d'ambiente nuova) rileggendo l'ordine; se nel frattempo è `awaiting_payment` restituisce lo
  stato dell'ordine con il link (`OrderStatusResponse`, forma già usata per il doppio accept),
  altrimenti `OrderQueued` come oggi. Con posizione > 1 risponde subito. L'attesa passa da un
  parametro `sleep` iniettabile, così i test non aspettano davvero.
- Frase `say` (it/en) per posizione 1 ancora in lavorazione alla fine dell'attesa: "Sto
  preparando il pagamento con il fornitore, ci vogliono pochi secondi. Chiedimi a che punto è."
  al posto di "Ti ho messo in coda: tra circa 1 minuto…".
- Esiti dell'attesa diversi da `awaiting_payment` (`replaced`, `failed`) restituiti come stato
  dell'ordine con la loro frase, senza attendere oltre.
- REST: 200 `order_status` quando il link è pronto, 202 `order_queued` come oggi negli altri
  casi; `docs/rest.md` aggiornato. MCP: descrizione di `accept_proposal` aggiornata ("il link
  può arrivare subito o con `get_order_status`").
- Spec: RF-45 e RNF-04 (durata massima dell'accettazione = `accept_wait_seconds`) aggiornati.

**Test di completamento.**
- Coda vuota, job che finisce durante l'attesa (worker finto) → risposta con `payment_url`.
- Coda vuota, job lento → dopo `accept_wait_seconds` `OrderQueued` con la frase nuova.
- Posizione > 1 → risposta immediata, nessuna attesa (sleep finto mai chiamato).
- Job che sostituisce il prodotto durante l'attesa → stato `replaced` con la proposta nuova.
- `accept_proposal` non chiama `HofJPort` né `PaymentsPort` (test esistente invariato).
- Doppio accept durante l'attesa: stesso ordine, un solo job.
- Scenario di M13: sotto picco nessuna richiesta di accept supera il p95 di M13b.

**Da decidere nel brainstorm.**
- Durata dell'attesa: **A) 10 s per tutti**; B) più corta per l'agente vocale (M12), dove 10 s
  sono silenzio; C) nessun default, solo configurazione.
- Condizione: **A) posizione 1**; B) posizione ≤ acquisti per finestra (anche il quarto in coda
  potrebbe avere il link in tempo).

**Copre.** RF-45 (aggiornato), RNF-04.

**Taglia.** S (1-2 h). **Dipende da** M5. **Ondata** 5, mergiare dopo M13b (le misure di M13b restano
confrontabili con M13a solo se questa modifica arriva dopo).

**Prompt.**
> Leggi docs/spec.md (RF-45, RF-48, RNF-04), docs/decisions.md (2026-09-26, "Accettazione con
> attesa breve"), vela/domain/usecases.py (`accept_proposal`, `get_order_status`),
> vela/domain/say.py, vela/surfaces/rest.py, vela/surfaces/mcp.py e docs/roadmap.md M20.
> Obiettivo: con l'ordine in posizione 1, `accept_proposal` attende fino a
> `accept_wait_seconds` il link preparato dal job e lo restituisce; altrimenti risponde come
> oggi. Il percorso resta uno solo e l'accettazione non chiama HofJ né Stripe. Prima chiudi le
> decisioni aperte. Test: M20.

---

## M21 — Scelta v3

**Risultato.** Vela capisce e rispetta la durata, il livello, le lezioni, le camere e se il
budget è a testa o in tutto; senza budget non propone più "il più economico" ma il viaggio che
parte quando il viaggiatore ha chiesto; ogni rifiuto viene capito (hotel, luogo escluso, stesso
viaggio in altre date) oppure produce una domanda chiusa invece di una proposta a caso. Casi
d'uso in `docs/usecases/scelta.md` (UC-A..UC-F), requisiti in `docs/spec.md` §4.12
(RF-58..75), decisioni in `docs/decisions.md` (2026-09-26, "Scelta v3").

**Regole comuni.**
- Sei task in sequenza, nell'ordine A, E, B, D, C, F, una alla volta (toccano tutte
  `intent.py`, `chooser.py`, `refine.py`, `say.py`, `usecases.py`, `models.py`, `mcp.py`,
  `rest.py`): ognuna parte da `master` con la precedente mergiata.
- Ogni task aggiorna `docs/rest.md`, le descrizioni MCP che la riguardano e la riga dei criteri
  in `say` (RF-54). Campi nuovi validati come RF-53: invalido scartato e dichiarato.
- Cambi di schema: una migrazione per task che ne ha bisogno (0010 in B, 0011 in D, 0012 in C,
  0013 in F), ognuna da approvare all'inizio della task. I criteri nuovi stanno nel JSON di
  `intents.criteria` senza migrazione.
- I test esistenti che fissano l'ordinamento v2 o "motivo non capito → proposta successiva"
  si aggiornano ed elencano in `docs/decisions.md`, senza indebolire le asserzioni.
- Nessuna chiamata a HofJ, Stripe o Anthropic: i campi del catalogo che servono
  (`description`, `maxPaxPerRoom`, `featured`, `isSpecialOffer`) sono già nelle fixture.

### M21-A — Durata (UC-A)

**Scope.** Parser della durata (tabella di UC-A, it/en) in `intent.py`; "un weekend" non è più
un periodo, "questo/prossimo weekend" sì; campi `duration_min_nights`, `duration_max_nights` su
`create_intent` e `reject_proposal`; criterio morbido nel chooser (livello "durata" di RF-60,
inserito dopo il budget nell'ordinamento v2); motivazione e `say` di RF-59; `nights` nella
risposta `proposal`; rifiuto "troppo lungo/troppo corto" che sposta la durata.
**Test.** Quelli di UC-A in `docs/usecases/scelta.md`.
**Copre.** RF-02 (durata), RF-06 (notti), RF-52 (campi), RF-58, RF-59.
**Taglia.** M. **Dipende da** M17, M11.
**Da decidere nel brainstorm.** Prodotti senza `defaultDurationInDays` e con finestra aperta:
**A) durata sconosciuta = compatibile**; B) esclusi dal livello "durata compatibile".

### M21-E — Budget a testa o totale (UC-E)

**Scope.** Parole "in tutto/totale/in total" nel parser; campo `budget_scope` su
`create_intent` e `reject_proposal`; regola 4 di RF-69 in `create_intent` (il caso d'uso legge
il catalogo per trovare il prodotto compatibile più economico); `budget_scope` nei criteri; frase
di RF-70 in ogni `say` con un budget.
**Test.** Quelli di UC-E.
**Copre.** RF-02 (budget), RF-52 (`budget_scope`), RF-53, RF-69, RF-70.
**Taglia.** S-M. **Dipende da** M21-A.
**Da decidere nel brainstorm.** Dove calcolare la regola 4: **A) `create_intent`, salvata nei
criteri**, così il `say` la dichiara subito; B) a ogni scelta (la lettura può cambiare col
catalogo).

### M21-B — Ordinamento e prodotti equivalenti (UC-B)

**Scope.** Ordinamento di RF-60 in `chooser.py` (il livello "livello e lezioni" è neutro fino a
M21-C); partenza più vicina all'inizio del periodo; `featured`/`special_offer` letti dal sync
(migrazione 0010: due colonne su `products`, valorizzate dal prossimo sync e dalle fixture);
raggruppamento dei prodotti equivalenti di RF-61; motivazione che spiega la scelta ("parte a
inizio novembre").
**Test.** Quelli di UC-B, compresa la trappola (78 proposto, 900078 solo dopo un rifiuto del 78
che non sia `hotel`).
**Copre.** RF-06 (motivazione), RF-07, RF-60, RF-61.
**Taglia.** M. **Dipende da** M21-A.
**Da decidere nel brainstorm.**
- Prova del criterio §10.4 con la trappola: oggi la trappola vince da sola; dopo RF-61 arriva
  solo se il 78 è escluso. **A) `add_trap` con un'opzione che archivia l'originale nella
  fixture di prova**; B) procedura manuale: rifiutare il 78 per date, poi accettare la
  trappola; C) nessuna trappola, §10.4 si prova con un errore del replay.
- Soglia di equivalenza del prezzo: **A) 5%**; B) prezzo identico o −1 € (solo la trappola).

### M21-D — Persone e camere (UC-D)

**Scope.** Parser delle camere ("tre camere", "two rooms", "due coppie"); campo `rooms` su
`create_intent`, `reject_proposal`, `accept_proposal`; domanda "In quante camere?" con pax > 2
(RF-04, RF-65), default 1 con pax ≤ 2; `max_pax_per_room` dal sync e filtro duro `rooms` (RF-66)
dopo `pax`; `NoChoice("rooms")` e il `say` di "da solo" (RF-68); `orders.rooms` e il job
d'acquisto che passa le camere a `create_itinerary` (RF-67); migrazione 0011
(`products.max_pax_per_room`, `orders.rooms` default 1); descrizione MCP di `create_intent`
con la domanda sulle camere.
**Test.** Quelli di UC-D; il job d'acquisto con HofJ finto riceve `rooms=3`; replay di
`create_itinerary` con `rooms`; migrazione su Postgres.
**Copre.** RF-04, RF-06 (camere), RF-12, RF-14, RF-39..41, RF-52, RF-65..68.
**Taglia.** M. **Dipende da** M21-B, M5.
**Da decidere nel brainstorm.** Ordini già in tabella: **A) `rooms` = 1 (default della
colonna, come oggi)**; B) ricalcolato dal prodotto.

### M21-C — Livello e lezioni (UC-C)

**Scope.** Parser di `level` e `wants_coaching`; campi su `create_intent` e `reject_proposal`;
etichette del prodotto nel sync (RF-63) da `description` e `shortDescription`, migrazione 0012
(`levels`, `levels_exclusive`, `coaching`); filtro duro solo con `levels_exclusive` (RF-64),
livello "livello e lezioni" di RF-60 attivo; frasi del `say`; rifiuto "troppo difficile" che
abbassa il livello.
**Test.** Quelli di UC-C, con una tabella di frasi vere del catalogo (962, 1027, 218, un
"tutti i livelli", un prodotto senza parole sul livello).
**Copre.** RF-02 (livello), RF-52, RF-62..64.
**Taglia.** M. **Dipende da** M21-B, M10.
**Da decidere nel brainstorm.** Descrizioni in inglese nei cataloghi `it`: **A) stesse regole
it/en su ogni catalogo**; B) regole per lingua del catalogo.

### M21-F — Rifiuti con motivo sempre capito (UC-F)

**Scope.** Classificazione del rifiuto in `refine.py` (RF-71) e campo `reject_kind`;
`rejections.kind` e `rejections.keep_product` (migrazione 0013); esclusione per hotel ricavata
dai rifiuti (RF-72); `excluded_areas` e luogo negato (RF-73), Marbella aggiunta a `geo`;
stesso prodotto con altre date (RF-74) in `chooser.departure` con finestre escluse, e
`keep_product=false` sulla stessa proposta che aggiorna il rifiuto (RF-55); domanda chiusa per
il motivo non classificabile, senza rifiuto registrato né cancellazione dell'ordine `queued`
(RF-75, RF-49); risposta `question` con `proposal_id` su MCP e REST; descrizione MCP di
`reject_proposal`.
**Test.** Quelli di UC-F (F1-F4 e "Altri tipi").
**Copre.** RF-08, RF-09, RF-39..41, RF-49, RF-52..55, RF-71..75.
**Taglia.** L. **Dipende da** M21-A, M21-B, M21-C (tipi `duration`, `level`), M21-D (tipo
`pax` con le camere).
**Da decidere nel brainstorm.** Motivo con più tipi ("troppo caro e troppo lontano"): **A)
criteri aggiornati tutti, tipo registrato = il primo dell'elenco di RF-71**; B) domanda "cosa
conta di più?".

**Test di completamento di M21.** Tutti i test elencati in `docs/usecases/scelta.md`; suite e
lint verdi; manuale: in claude.ai, in replay, UC-A, UC-D (cinque persone) e UC-F4 registrati in
`docs/acceptance.md`.

**Copre.** RF-02, RF-04, RF-06..09, RF-12, RF-14, RF-39..41, RF-49, RF-52..55, RF-58..75.

**Taglia.** L in totale (circa 12-16 h). **Dipende da** M17, M11, M10, M5 (tutte su
`master`). **Ondata** 7, dopo le task di ondata 5-6 che toccano il dominio; nessuna parallela
che tocchi `chooser.py`, `intent.py`, `refine.py`.

**Prompt** (uno per task, sostituendo la lettera).
> Leggi docs/spec.md (§4.12, RF-02, RF-04, RF-06..09, RF-52..55), docs/usecases/scelta.md
> (UC-<lettera>), docs/decisions.md (2026-09-26, "Scelta v3"), vela/domain/intent.py,
> vela/domain/chooser.py, vela/domain/refine.py, vela/domain/say.py, vela/domain/usecases.py,
> vela/surfaces/mcp.py, vela/surfaces/rest.py e docs/roadmap.md M21-<lettera>. Obiettivo: il
> caso UC-<lettera> con i suoi test. Prima chiudi le decisioni aperte della task e, se la task
> ha una migrazione, chiedi l'OK sullo schema. Nessuna chiamata a servizi esterni.

---

## M22 — Scelta dell'hotel con degrado dinamico

**Stato (2026-09-27).** M22-a conclusa con il verdetto **"M22-b non si fa"**: la sonda non ha
mai visto un `PATCH` possibile (`docs/api/accommodations.md`). Condizioni per riaprire in
`docs/decisions.md` (2026-09-27, "M22-a", "Sonda e verdetto"). Il resto della sezione è il
piano, tenuto come archivio.

**Risultato.** Su un ordine in `awaiting_confirmation` il viaggiatore può rifiutare l'hotel,
con o senza una preferenza (più vicino al campo, più economico, più stelle, recensioni
migliori), e Vela propone un solo hotel alternativo dello stesso viaggio con la motivazione e
il nuovo totale. Il
cambio avviene solo a coda d'acquisto vuota; con la coda piena Vela tiene l'hotel incluso e lo
dice. Priorità della quota: `booking` > `purchase` > `hotel` > `sync`. Bozza dei requisiti
(RF-15 riscritto, RF-76..RF-82), casi d'uso UC-G e domande aperte in
`docs/plans/2026-09-27-m22-hotel.md`; decisioni in `docs/decisions.md` (2026-09-27, "M22-a").

### M22-a — Bozza, sonda, verdetto

**Scope.** Solo documenti e uno script: bozza in `docs/plans/2026-09-27-m22-hotel.md` (non
in `docs/spec.md`, che ogni task di M21 modifica); sonda su HofJ staging
(`scripts/accommodations_probe.py`, sul modello di `scripts/quota_probe.py`): latenza di
`/accommodations`, formato e risposta del `PATCH` con i `roomIds`, totale dopo il `PATCH`,
risposta di un prodotto con `hotelSelection=false`; esiti in `docs/api/accommodations.md` e
`docs/api/differences.md`. Verdetto: M22-b si fa o no. Testo per `ARCHITECTURE.md` (branch
`doc/architecture`) §5.2 (bilancio della quota, nuovo ordine di sacrificio) e §5.3 (cosa
degrada: il viaggiatore a coda piena) in entrambi i casi. Tre fasi, ognuna con l'OK dell'utente.
**Test.** Nessun codice in `vela/`; suite e lint verdi.
**Copre.** Bozza di RF-15, RF-76..RF-82 (spec in M22-b).
**Taglia.** S-M. **Dipende da** nessuna (le chiamate della sonda si dichiarano prima).

### M22-b — Cambio di hotel a coda vuota (condizionata al verdetto)

**Scope.** Testi della bozza portati in `docs/spec.md` (§4.13, RF-15, §7, RF modificati) e
UC-G in `docs/usecases/scelta.md`; campo `hotel_preference` e parser it/en; i tre rami di RF-77
in `reject_proposal`; job `hotel_change` (lista, `PATCH`, rilettura del totale); classe
`hotel` nello scheduler della quota (tutti i gettoni insieme, mai con acquisti in attesa, sync
dopo i cambi); hotel nel `say` della conferma del prezzo; porte `HofJPort` nuove e replay;
migrazione 0014 (cinque campi hotel sull'ordine, approvata in M22-a); istruzioni del server
MCP e descrizione di `reject_proposal` (nessuna domanda preventiva sulla preferenza; la
risposta può essere di nuovo una conferma del prezzo); `docs/rest.md`; `scripts/rest_flow.py`
se serve; nota su ElevenLabs: `response_timeout_secs` resta ≥ 120 anche per `reject_proposal`.
**Test.** Quelli di UC-G nella bozza (§5).
**Copre.** RF-15, RF-16, RF-25, RF-37, RF-39..41, RF-47, RF-49, RF-52, RF-72, RF-76..RF-82,
RNF-04.
**Taglia.** L. **Dipende da** M22-a (verdetto "sì"), M21-D (`orders.rooms`, `create_itinerary`
con le camere), M21-F (tipo di rifiuto `hotel`, RF-71, RF-72).
**Da decidere nel brainstorm.** Niente di aperto: le domande di §10 della bozza sono chiuse
(`docs/decisions.md`, 2026-09-27, "M22-a"); restano i dettagli che dipendono dalla sonda.

**Prompt** (M22-b).
> Leggi docs/plans/2026-09-27-m22-hotel.md, docs/api/accommodations.md, docs/decisions.md
> (2026-09-27, "M22-a"), docs/spec.md (RF-15, RF-16, RF-47, RF-49, RF-71..75), vela/domain/quota.py,
> vela/domain/purchase.py, vela/domain/usecases.py, vela/domain/refine.py e docs/roadmap.md M22-b.
> Obiettivo: UC-G con i suoi test. Proponi l'approccio e aspetta l'OK. Nessuna chiamata a
> servizi esterni.

---

## Matrice dei requisiti

| Requisito | Macro task |
|---|---|
| RF-01 | M2, M17 (campi strutturati) |
| RF-02 | M2 (minimo), M9 (completo), M17 (sport `any`, sinonimi), M21-A, M21-E, M21-C, M21-D |
| RF-03 | M9, M17 (precedenza, fallback senza sport) |
| RF-04 | M2, M9, M17 (sport sempre indispensabile), M21-D (camere) |
| RF-05 | M2 |
| RF-06 | M2, M11, M21-A, M21-B, M21-D |
| RF-07 | M2 (v1), M11 (completo), M21-B (v3) |
| RF-08 | M2 (base), M9, M17 (campi e direzione), M21-F (tipi, eccezioni) |
| RF-09 | M2, M11, M17 (niente di compatibile dopo un rifiuto), M21-F |
| RF-10 | M2, M3, M4 |
| RF-11 | M2 |
| RF-12 | M2, M21-D |
| RF-13 | M2 (default), M5 (invio a HofJ), M15 (documentazione) |
| RF-14 | M5, M21-D (camere) |
| RF-15 | M5, M22-b (cambio di hotel) |
| RF-16 | M2, M5, M22-b (hotel nel `say`) |
| RF-17 | M5 |
| RF-18, RF-19 | M6 |
| RF-20, RF-21, RF-22 | M6 |
| RF-23, RF-24 | M5 |
| RF-25, RF-26 | M2 (RF-26 prossimi passi: M15) |
| RF-27 | M2, M5 |
| RF-28..RF-31 | M10 |
| RF-32 | M1, M10 (una fixture per host e brand) |
| RF-33..RF-35 | M5 |
| RF-36..RF-38 | M5, M18 |
| RF-39 | M2, M17, M21-D, M21-F |
| RF-40 | M4, M17, M21-D, M21-F |
| RF-41 | M3 (Claude), M12 (ElevenLabs), M17 (descrizioni dei tool), M21-D, M21-F |
| RF-42 | M2, M17 |
| RF-43 | M4 (REST), M8 (MCP OAuth) |
| RF-44 | M15 (documentazione), M16 (opzionale) |
| RF-45..RF-51 | M5 (RF-45 anche M20; RF-47 anche M18; RF-49 anche M21-F) |
| RF-52..RF-55 | M17, M21 (campi nuovi; RF-54 e RF-55 in M21-F) |
| RF-56 | M10 |
| RF-57 | task/twilio-setup (SMS, fuori dalle macro task) |
| RF-58, RF-59 | M21-A |
| RF-60, RF-61 | M21-B |
| RF-62..RF-64 | M21-C |
| RF-65..RF-68 | M21-D |
| RF-69, RF-70 | M21-E |
| RF-71..RF-75 | M21-F (RF-72 anche M22-b) |
| RF-76..RF-82 | M22-a (bozza), M22-b |
| RNF-01, RNF-02, RNF-03 | M2, M6 |
| RNF-04 | M5, M18 |
| RNF-05 | M13a, M13b |
| RNF-06 | M0, M4, M14 |
| RNF-07 | M0, M6, M14 |
| RNF-08 | M2 |
| RNF-09 | ogni task (suite `unittest` senza servizi esterni; DB test saltati senza `DATABASE_URL`) |
| RNF-10 | M13a, M13b |
| RNF-11 | M0 |
| RNF-12 | M9 (interruttore Haiku), M14 (catalogo in memoria) |
| RNF-13 | M3 (MCP stateless), M8 |
| §6 `agent-log/` | M0 |
| §8 verifiche | M5 |
| §9 consegne | M15 |
| §10.1, .3, .4, .7 | M7 (poi M14, M15) |
| §10.2 | M12 |
| §10.5 | M13a, M13b |
| §10.6 | M2, M3, M4 |

Tutti gli 82 RF (RF-76..RF-82 in bozza fino a M22-b), i 13 RNF, i vincoli di §6, le verifiche di §8, le consegne di §9 e i 7 criteri
di §10 hanno almeno una macro task.
