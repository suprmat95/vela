# M7 — Prima prenotazione reale end-to-end (Traguardo B)

Data: 2026-09-25. Origine: intervista sulla macro task M7 di `docs/roadmap.md`. Design e microtask
in un solo file, senza spec separata (come M0-M9). Copia in
`docs/plans/2026-09-25-m7-prima-prenotazione-reale.md`.

## Contesto

M7 chiude il Traguardo B: su Render, con `VELA_UPSTREAM_MODE=live`, un intento arriva a un codice
di prenotazione reale di HofJ da claude.ai (§10.1) e da REST (§10.3), e un prodotto che fallisce al
carrello viene sostituito senza errore visibile (§10.4). La latenza di un flusso reale va misurata
per M13.

Stato di partenza:
- `task/m7` è fermo a `de0fd25` (M6); `master` locale contiene il merge di M5 (`141293c`).
- M5 ha lasciato un problema aperto (`docs/decisions.md`, "Da verificare in M7"): la fixture
  `fixtures/catalog.json` è il catalogo di **produzione** `it`, mentre le verifiche del carrello
  sono state fatte su **staging** (prodotto 118, che funziona solo in `en`). In live su staging gli
  id della fixture non esistono.
- `HofJHttp` manda sempre `locale=it`; il bootstrap carica la fixture solo se `products` è vuota.
  Il DB di Render contiene il catalogo di produzione, referenziato tramite FK da proposte e ordini
  di replay.
- Su staging `POST /v1/bookings` restituisce l'`itineraryId`: è già stato deciso che quello è il
  `booking_code`.

## Decisioni dell'intervista (da registrare in `docs/decisions.md`)

| Decisione | Scelta |
|---|---|
| Ambiente live | HofJ **staging** (`https://staging.api.hofj.com`, brand `staging.weebora.com`), con un catalogo di staging registrato apposta |
| Locale | Catalogo di staging registrato in `en`; `HofJHttp` usa il `locale` della fixture caricata. Nessuna variabile d'ambiente nuova. Le frasi `say` seguono la lingua del viaggiatore |
| Catalogo sul DB | Una fixture per ambiente: `fixtures/catalog.json` (produzione `it`, replay e test) e `fixtures/catalog-staging.json`. In live si sceglie la fixture con `base_url` uguale a `HOFJ_BASE_URL`; se nessuna coincide, l'app non parte. Al boot, se gli id attivi nel DB sono diversi da quelli della fixture: upsert della fixture e prodotti assenti marcati `archived` (niente DELETE, le FK restano valide) |
| Criterio 4 | Prodotto trappola dichiarato nella fixture di staging: clone di un prodotto reale con id numerico inesistente su HofJ, prezzo più basso del modello, `vela_trap: true`. HofJ risponde 502 (upstream 404), cioè un errore di prodotto vero |
| Criterio 3 e latenza | Nuovo `scripts/rest_flow.py`, cronometrato, simile a `scripts/mcp_smoke.py` |
| Criterio 1 | Eseguito dall'utente in claude.ai col connector Vela. Il pagamento con 4242 lo fa l'utente nel browser. L'agente guida, controlla lo stato e registra gli esiti |
| `render.yaml` | `VELA_UPSTREAM_MODE: value: live`. Le variabili HofJ e Stripe restano `sync: false` e si impostano dalla dashboard |

## Chiamate esterne dichiarate (tutte da confermare al momento dell'esecuzione)

| Servizio | Quando | Stima | Tetto |
|---|---|---|---|
| HofJ staging | Registrazione del catalogo (Task 7): liste + dettagli + sync di quota, rispettando `QuotaGuard` | Numero esatto dopo la prima pagina di lista, dichiarato prima di proseguire | 150 |
| HofJ staging | Boot di ogni deploy (`/v1/quota`) | 1 per deploy, ~3 deploy | 5 |
| HofJ staging | Criterio 3: acquisto 5 + booking 1 | 6 | 10 |
| HofJ staging | Criterio 1: acquisto 5 + booking 1 | 6 | 10 |
| HofJ staging | Criterio 4: POST della trappola 1 + acquisto sostitutivo 5, nessun booking | 6 | 10 |
| Stripe test (chiave `rk_test` di HofJ) | 1 Checkout Session per ordine pagabile (3) + `sessions.retrieve` ogni 60 s e a ogni richiesta di stato mentre l'ordine è `awaiting_payment` | ~30 | 80 |
| Anthropic Haiku | Solo se il parser non riconosce le frasi di prova | 0 | 3 |

L'ordine del criterio 4 va annullato con `reject_proposal` (RF-49 → `cancelled`) subito dopo la
prova, così il polling Stripe si ferma e non gira per 24 ore.

## Microtask

Test: `uv run python -m unittest discover -s tests` (il `python3` di sistema è 3.7). Ogni task in
TDD: prima il test rosso, poi il codice, poi la suite verde, poi un commit piccolo.

### Task 0 — Allineamento e decisioni
- `git merge --ff-only master` su `task/m7` (nessun commit proprio, nessuna riscrittura della storia).
- Suite di base: annotare numero di test e saltati.
- Copiare questo piano in `docs/plans/2026-09-25-m7-prima-prenotazione-reale.md` e aggiungere la
  sezione "M7" in `docs/decisions.md` con la tabella sopra. Commit.

### Task 1 — `record_catalog.py --locale`
- `scripts/record_catalog.py`: opzione `--locale` (default `it`), passata a `record` e a
  `build_catalog`. `base_url` nella fixture = `HOFJ_BASE_URL` in uso (verificare che sia già così
  via `api_explore.BASE_URL`). Docstring aggiornata. Resta compatibile con Python 3.7.
- Test (`tests/test_record_catalog.py`): il dry-run con `--locale en` pianifica le chiamate con
  `locale=en`; `build_catalog(locale="en")` ignora le pagine `it` e scrive `"locale": "en"`;
  default invariato (`it`).

### Task 2 — Prodotto trappola (`--trap-from ID`)
- `record_catalog.py`: `add_trap(catalog, template_id)` clona `products` e `details` del modello
  con id `str(900000 + int(template_id))`, prezzo del modello meno 1 € (stesso formato del campo
  `price`) e `vela_trap: true` in `details[id].catalog`. Opzione `--trap-from` usabile anche con
  `--build-only`.
- Test: clone con stesse date, destinazione e hotel; prezzo inferiore; marcatore presente; id non
  in collisione con gli esistenti (altrimenti `BuildError`); modello assente → `BuildError`; senza
  opzione nessun clone.

### Task 3 — Scelta della fixture per ambiente
- `vela/adapters/hofj_replay.py` (o `vela/domain/catalog.py`, dove sta `load_fixture`):
  `fixture_meta(path)` → `{base_url, locale, brand}` e `select_fixture(fixtures_dir, base_url)`
  → percorso della fixture `catalog*.json` il cui `base_url` coincide (confronto senza `/`
  finale). Nessuna corrispondenza → `RuntimeError` che elenca i `base_url` trovati.
- `vela/app.py` `build_vela`: in replay resta `fixtures/catalog.json`; in live il `catalog_loader`
  legge la fixture scelta.
- Test (nuovo `tests/test_fixture_select.py`, fixture minime in una cartella temporanea): scelta
  per `base_url`, slash finale indifferente, nessuna corrispondenza → errore con i `base_url`,
  replay invariato. In `tests/test_app_replay.py`: live con env finta e fixture di staging → il
  loader carica gli id di staging.

### Task 4 — `HofJHttp` col locale della fixture
- `build_hofj` passa `locale=fixture_meta(...)["locale"]` a `HofJHttp`.
- Test: in live con una fixture `en` le richieste del carrello hanno `?locale=en` (verificato con
  `httpx.MockTransport` in `tests/test_hofj_http.py` o dal wiring in `test_app_replay.py`).

### Task 5 — Riallineo del catalogo al boot
- Porta `ProductRepository.archive_missing(keep_ids) -> int` (interna, nessuna interfaccia
  pubblica toccata); implementazioni in `vela/adapters/repo_memory.py` e
  `vela/adapters/repo_postgres.py` (un `UPDATE ... SET archived = true WHERE id NOT IN ...`).
- `vela/app.py` `bootstrap`: se il DB è vuoto oppure l'insieme degli id non archiviati è diverso
  da quello della fixture → `upsert_many` + `archive_missing`; altrimenti non fa niente, così i
  flag `bookable` di RF-33 sopravvivono ai riavvii. Il risultato include `catalog_archived`.
- Test: contratto in `tests/repo_contract.py` (memoria sempre, Postgres con `DATABASE_URL`):
  archivia solo gli assenti e restituisce il conteggio. In `tests/test_app_replay.py`: DB vuoto →
  carica; stessa fixture → nessun upsert e `bookable=false` preservato; fixture diversa → vecchi
  prodotti archiviati, ordini e proposte che li referenziano intatti, il chooser non propone
  archiviati; ritorno a replay → riallineo opposto.

### Task 6 — `scripts/rest_flow.py`
- Flusso §10.3 contro un URL: `POST /v1/intents` → proposta → rifiuto con "troppo caro" (la nuova
  proposta deve costare meno) → accept (202 `order_queued`) → polling di `GET /v1/orders/{id}`
  fino a `payment_url` → stampa il link e continua il polling fino a `confirmed` con
  `booking_code` (timeout configurabile). Modalità `--trap`: dopo l'accept aspetta
  `proposal_changed`/`replaced` con una proposta diversa, verifica che `say` non contenga
  dettagli d'errore, poi annulla con il rifiuto (RF-49) e si ferma.
- Token solo da `VELA_API_TOKEN`, mai stampato. A ogni risposta verifica al massimo un prodotto,
  riusando `count_products` di `scripts/mcp_smoke.py`. In uscita: tabella dei tempi per passo
  (intent, proposta, rifiuto, accept, accept→link, link→confirmed, totale), id dell'ordine e
  codice, pronta per `docs/acceptance.md`. Hook `open_url`/`tick` come in `mcp_smoke.py` per i test.
- Costanti `INTENT_FLOW` e `INTENT_TRAP`: fissate nel Task 7 dopo aver letto il catalogo di
  staging.
- Test (nuovo `tests/test_rest_flow.py`, app replay in-process con `TestClient` e repository in
  memoria, come `tests/test_mcp_smoke.py`): flusso completo fino a `confirmed` con tabella dei
  tempi; token assente → uscita senza chiamate; token assente dall'output; risposta con due
  prodotti → fallimento; proposta dopo il rifiuto non più economica → fallimento; timeout →
  fallimento chiaro; `--trap` con una HofJ finta che solleva `ProductError` per l'id trappola →
  proposta sostitutiva diversa e ordine `cancelled`.

### Task 7 — Registrazione del catalogo di staging (manuale, con l'utente)
- Dichiarare le chiamate. L'utente esegue con `!` (la chiave non passa dall'agente):
  `HOFJ_BASE_URL=https://staging.api.hofj.com HOFJ_BRAND=staging.weebora.com uv run python
  scripts/record_catalog.py --raw-dir <fuori dal repo> --locale en --out fixtures/catalog-staging.json`
  (prima `--dry-run`).
- L'agente legge la fixture e sceglie: il modello della trappola (area diversa da quella di
  `INTENT_FLOW`, con almeno un altro prodotto reale compatibile per la sostituzione),
  `INTENT_FLOW` (sostituisce la frase di §10.1 se staging non ha "padel in Spagna a ottobre":
  la frase effettiva va dichiarata in acceptance) e `INTENT_TRAP`. Poi `--build-only --trap-from ID`.
- Test (`tests/test_catalog_fixture.py`, `tests/test_chooser_fixture.py`): la fixture di staging
  è valida, con `locale en`, `base_url` di staging ed esattamente una trappola; con il chooser
  reale sulla fixture di staging `INTENT_FLOW` dà una proposta non trappola e "troppo caro" una più
  economica; `INTENT_TRAP` dà per prima la trappola, e dopo il suo rifiuto per errore di prodotto
  un prodotto reale diverso. La fixture di produzione e i suoi test restano invariati.

### Task 8 — Render in live
- `render.yaml`: `VELA_UPSTREAM_MODE` `value: live`; `tests/test_render_yaml.py` aggiornato.
- `docs/rest.md` (sezione del flusso: `scripts/rest_flow.py`) e `docs/stripe.md` (test manuale
  ora possibile) aggiornati.
- Suite verde. Merge di `task/m7` su `master` **con l'OK dell'utente** → autodeploy.
- L'utente imposta in dashboard: `HOFJ_API_KEY`, `HOFJ_BASE_URL` (staging), `HOFJ_BRAND`
  (`staging.weebora.com`), `STRIPE_SECRET_KEY`, `VELA_PUBLIC_URL`, `VELA_API_TOKEN`.
- Verifica: `curl <url>/health` → `db ok`, `catalog.products` = numero di prodotti di staging,
  `quota` valorizzata; log di boot con `catalog_archived`.

### Task 9 — Criterio 3 (REST, live)
- `uv run python scripts/rest_flow.py <url>` con `VELA_API_TOKEN` nell'ambiente dell'utente.
  L'utente paga il link con `4242 4242 4242 4242`. Esito: `confirmed` + codice, tabella dei tempi.

### Task 10 — Criterio 1 (claude.ai, live)
- L'utente conduce la conversazione col connector Vela: `INTENT_FLOW`, "troppo caro", "sì", dati
  del viaggiatore, richiesta di stato, pagamento, richiesta di stato. L'agente controlla l'ordine
  con `GET /v1/orders/{id}` e registra la proposta singola a ogni turno, lo stato `queued` con
  attesa, il link e `confirmed` con codice.

### Task 11 — Criterio 4 (live)
- `uv run python scripts/rest_flow.py <url> --trap`: la trappola fallisce al carrello, arriva una
  proposta diversa senza errore visibile, l'ordine viene annullato. Controllo nei log che il
  prodotto sia marcato `bookable=false`.

### Task 12 — Correzioni
- Ogni guasto dei Task 8-11: `superpowers:systematic-debugging`, test rosso che riproduce, fix,
  commit, nuovo merge e deploy con OK, ripetizione del criterio. Ogni correzione va in
  `docs/decisions.md` ("M7: decisioni prese durante l'esecuzione").

### Task 13 — Registrazione e chiusura
- `docs/acceptance.md`: righe `live` dei criteri 1, 3 e 4 con data, superficie, esito, id
  dell'ordine e codice di prenotazione; tabella di latenza (per M13); note su staging, trappola e
  frase effettiva. Nessun token né dato personale.
- `docs/decisions.md`: suite finale (numero di test), chiamate effettivamente usate per servizio.
- Suite verde, commit, merge su `master` con OK.

## File critici

- `scripts/record_catalog.py`, `scripts/rest_flow.py` (nuovo), `scripts/mcp_smoke.py` (riuso di `count_products`)
- `vela/app.py` (`build_hofj`, `build_vela`, `bootstrap`), `vela/adapters/hofj_replay.py`, `vela/domain/catalog.py`
- `vela/ports/repositories.py`, `vela/adapters/repo_memory.py`, `vela/adapters/repo_postgres.py`
- `fixtures/catalog-staging.json` (nuovo), `render.yaml`
- Test: `tests/test_record_catalog.py`, `tests/test_fixture_select.py` (nuovo), `tests/test_app_replay.py`,
  `tests/repo_contract.py`, `tests/test_rest_flow.py` (nuovo), `tests/test_catalog_fixture.py`,
  `tests/test_chooser_fixture.py`, `tests/test_render_yaml.py`
- Docs: `docs/decisions.md`, `docs/acceptance.md`, `docs/rest.md`, `docs/stripe.md`

## Verifica end-to-end

1. `uv run python -m unittest discover -s tests` verde dopo ogni task. I test Postgres del
   contratto `archive_missing` si eseguono dove `DATABASE_URL` è disponibile, con
   `PGOPTIONS=-csearch_path=vela_test`.
2. `/health` su Render in live con il catalogo di staging e la quota letta.
3. Criteri 3, 1 e 4 eseguiti come nei Task 9-11, con esiti e latenza in `docs/acceptance.md`.

## Punti incerti da tenere d'occhio

- Contenuto del catalogo di staging: potrebbe non avere padel in Spagna a ottobre. In quel caso la
  frase di §10.1 cambia e viene dichiarata.
- La domanda 2 di `docs/hofj-questions.md` è ancora aperta (il codice è l'`itineraryId`): il
  criterio 1 vale con "il codice restituito da `POST /v1/bookings`", come già deciso in M5.
- Titolo della trappola uguale al modello: il viaggiatore vede una proposta plausibile. Resta
  nella fixture di staging, dichiarata, utile anche per il video e per M12.

## Stato al 2026-09-25 (fine sessione)

Fatti: Task 0-8 (più il 6b "troppo caro", deciso durante l'esecuzione), merge `d31e51e` su
`master` e deploy live su staging, Task 9 (criterio 3 ok, codice `wury5zaxzkec`). Commit dopo il
merge solo su `task/m7` (frase su Barcellona, registrazioni): vanno mergiati a fine M7.
Da fare: Task 10 (criterio 1 in claude.ai, con la frase su Barcellona), Task 11 (criterio 4 con
`rest_flow.py --trap`), Task 12 se qualcosa si rompe, Task 13 (righe finali di acceptance,
decisioni, merge). Esiti e latenza già registrati in `docs/acceptance.md`.

