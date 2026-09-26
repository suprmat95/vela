# Vela — roadmap in macro task

Data: 2026-09-25. Origine: `docs/spec.md` e intervista del 2026-09-25 (decisioni in
`docs/decisions.md`, sezione "Roadmap in macro task"). Aggiornata il 2026-09-25 per il twist
(50.000 viaggiatori in dieci minuti, spec §4.10): M2 era già conclusa, quindi coda d'acquisto,
scheduler della quota e accettazione asincrona entrano in M5, lo scenario di carico in M13.
Aggiornata il 2026-09-26 con M17 (contratto agente-tool, spec §4.11): M9 e M11 erano già
concluse, quindi il lavoro su parser e contratto dei tool è una task nuova in ondata 5.
Aggiornata il 2026-09-26 per il multi-brand: M10 diventa "Sync multi-brand del catalogo"
(padel = Weebora, tennis = Terrarossa), taglia L, casi d'uso in `docs/usecases/multi-brand.md`.

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
Ondata 5   M10 Sync  M12 ElevenLabs  M13 Load test  M14 Hardening  M17 Contratto agente-tool
                 \      |       |       /               /
Ondata 6          M15 Consegna (ARCHITECTURE, README, video)   [M16 A2A opzionale]
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
| M10 | Sync multi-brand del catalogo da HofJ | L | M5 | 5 / M12, M13, M14 |
| M11 | Raffinamento della scelta (chooser v2) | M | M2 | 2+ / tutte |
| M12 | Agente vocale ElevenLabs | S | M7, M8 | 5 / M10, M13, M14 |
| M13 | Load test e numeri | S | M4, M7 | 5 / M10, M12, M14 |
| M14 | Hardening: log JSON, health, dati personali, segreti | S | M7 | 5 / M10, M12, M13 |
| M15 | Consegna: ARCHITECTURE.md, README, video | M | tutte | 6 / — |
| M16 | (opzionale) Superficie A2A | M | M4, M8 | 6 / M15 |
| M17 | Contratto agente-tool e sinonimi dello sport | M | M3, M4, M9, M11 | 5 / M10, M12, M13, M14 |

Regola per i worktree: le task della stessa ondata toccano file diversi salvo
`vela/domain/orders.py` (M5, M6), `vela/domain/intent.py` (M9, M11) e
`vela/domain/usecases.py` (M10 per il router del carrello, M17 per i campi strutturati): chi arriva secondo fa rebase prima del merge. Ogni task finisce con merge su `master` e test verdi.

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

## M13 — Load test e numeri

**Risultato.** `loadtest/locustfile.py` esercita il flusso completo in replay; `RESULTS.md`
riporta i numeri richiesti da RNF-10.

**Scope.**
- Locust su REST: intento → proposta → rifiuto → accettazione (`queued`) → stato finché
  `awaiting_payment` → checkout replay → stato finché `confirmed`.
- Esecuzione locale e contro Render; `GET /v1/quota` reale prima e dopo (2 chiamate).
- Scenario "twist" (RNF-10, spec §4.10): 50.000 viaggiatori in dieci minuti, adapter replay
  con quota simulata 120/min e latenza 2-6 s per chiamata. Misure: p95 dei cinque casi
  d'uso, acquisti completati al minuto (atteso ≈ 20), scarto tra attesa stimata e reale,
  tempo tra pagamento simulato e prenotazione (atteso < 60 s), errori di quota (atteso 0).
- `RESULTS.md`: utenti, RPS, p50/p95/p99, errori, `limitPerMinute`, latenza del flusso reale
  misurata in M7, più la tabella dello scenario twist e la risposta alla domanda del twist
  ("regge?") con i numeri.

**Test di completamento.**
- Locust headless termina senza errori; p95 < 500 ms sui cinque casi d'uso; quota reale
  invariata; scenario twist con zero errori di quota, ≈ 20 acquisti/min, prenotazione entro
  60 s dal pagamento; `RESULTS.md` compilato.

**Copre.** RNF-05, RNF-10 (incluso lo scenario twist), §10.5.

**Prompt.**
> Leggi docs/spec.md (§4.10, RNF-05, RNF-08, RNF-10, §10.5) e docs/roadmap.md M13.
> Obiettivo: load test Locust in replay con lo scenario twist (quota e latenza simulate) e
> risultati documentati. Test: M13.

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
- `README.md`: variabili, avvio, test, deploy, load test, come collegare Claude ed ElevenLabs.
- Video 3-5 min: acquisto reale con Claude e con ElevenLabs.
- Checklist finale dei 7 criteri di §10 in `docs/acceptance.md`.

**Test di completamento.**
- Tabella di §10 tutta verde; un lettore esterno deploya seguendo solo il README; video
  caricato e linkato nel README.

**Copre.** RF-13 (documentazione), RF-26, RF-44, spec §9.

**Prompt.**
> Leggi docs/brief.md (Deliverables), docs/spec.md (§9, §10, RF-44, RF-26), docs/decisions.md
> e docs/roadmap.md M15. Obiettivo: ARCHITECTURE.md, README, video, checklist finale. Test: M15.

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

## Matrice dei requisiti

| Requisito | Macro task |
|---|---|
| RF-01 | M2, M17 (campi strutturati) |
| RF-02 | M2 (minimo), M9 (completo), M17 (sport `any`, sinonimi) |
| RF-03 | M9, M17 (precedenza, fallback senza sport) |
| RF-04 | M2, M9, M17 (sport sempre indispensabile) |
| RF-05 | M2 |
| RF-06 | M2, M11 |
| RF-07 | M2 (v1), M11 (completo) |
| RF-08 | M2 (base), M9, M17 (campi e direzione) |
| RF-09 | M2, M11, M17 (niente di compatibile dopo un rifiuto) |
| RF-10 | M2, M3, M4 |
| RF-11 | M2 |
| RF-12 | M2 |
| RF-13 | M2 (default), M5 (invio a HofJ), M15 (documentazione) |
| RF-14 | M5 |
| RF-15 | M5 |
| RF-16 | M2, M5 |
| RF-17 | M5 |
| RF-18, RF-19 | M6 |
| RF-20, RF-21, RF-22 | M6 |
| RF-23, RF-24 | M5 |
| RF-25, RF-26 | M2 (RF-26 prossimi passi: M15) |
| RF-27 | M2, M5 |
| RF-28..RF-31 | M10 |
| RF-32 | M1, M10 (una fixture per host e brand) |
| RF-33..RF-35 | M5 |
| RF-36..RF-38 | M5 |
| RF-39 | M2, M17 |
| RF-40 | M4, M17 |
| RF-41 | M3 (Claude), M12 (ElevenLabs), M17 (descrizioni dei tool) |
| RF-42 | M2, M17 |
| RF-43 | M4 (REST), M8 (MCP OAuth) |
| RF-44 | M15 (documentazione), M16 (opzionale) |
| RF-45..RF-51 | M5 |
| RF-52..RF-55 | M17 |
| RF-56 | M10 |
| RNF-01, RNF-02, RNF-03 | M2, M6 |
| RNF-04 | M5 |
| RNF-05 | M13 |
| RNF-06 | M0, M4, M14 |
| RNF-07 | M0, M6, M14 |
| RNF-08 | M2 |
| RNF-09 | ogni task (suite `unittest` senza servizi esterni; DB test saltati senza `DATABASE_URL`) |
| RNF-10 | M13 |
| RNF-11 | M0 |
| RNF-12 | M9 (interruttore Haiku), M14 (catalogo in memoria) |
| RNF-13 | M3 (MCP stateless), M8 |
| §6 `agent-log/` | M0 |
| §8 verifiche | M5 |
| §9 consegne | M15 |
| §10.1, .3, .4, .7 | M7 (poi M14, M15) |
| §10.2 | M12 |
| §10.5 | M13 |
| §10.6 | M2, M3, M4 |

Tutti i 56 RF, i 13 RNF, i vincoli di §6, le verifiche di §8, le consegne di §9 e i 7 criteri
di §10 hanno almeno una macro task.
