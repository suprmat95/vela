# Task m4 execution plan

- Sessione: `e37af65c-57b4-4f16-9c63-cd3a306b634c`
- Inizio: 2026-09-25 16:27

## Utente 16:27

❯ /superpowers:brainstorming Leggi la task m4 in docs/roadmap.md. Obiettivo: intervistami e scrivi il
      piano di esecuzione in un file in docs/plans/ Il piano dovrà indicare i microtask e i test che
  coprono il codice prodotto. Dopodiché lancerò l'esecuzione del piano

## Agente 16:27

- 🔧 Skill superpowers:brainstorming

Uso il brainstorming per capire M4 e arrivare al piano. Parto dal contesto del progetto.

- 🔧 Bash: List project docs and read roadmap

- 🔧 Bash: Inspect code structure and app

- 🔧 Bash: Grep spec for REST requirements

- 🔧 Bash: Read spec surfaces and current use cases

- 🔧 Bash: Scan domain models and errors

- 🔧 Bash: Read M2 plan format, decisions headings, app tests

- 🔧 Bash: Read to_dict contract, M2 decisions, responses

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

Ultimi punti che decido io, salvo tua obiezione:
- Corpi delle richieste come modelli Pydantic. I campi extra vengono ignorati, non rifiutati, così un agente che manda qualcosa in più non riceve un errore.
- Il token si confronta con `hmac.compare_digest`.
- `/docs` e `/openapi.json` di FastAPI restano pubblici.

**Approcci per la superficie**

1. **(Consigliato) `APIRouter` con prefisso `/v1` e una dependency `require_token`.** Gli exception handler dell'app emettono 7807 solo quando il path inizia con `/v1`. È il pattern già usato da `health.py` e `replay.py`, e l'OpenAPI resta unica.
2. **Sotto-app FastAPI montata su `/v1`.** Handler isolati per costruzione, ma l'OpenAPI finisce separata e le dependency sono duplicate.
3. **Middleware ASGI per l'autenticazione.** Protegge tutto in un punto, ma è più difficile da testare, e i 401 non compaiono nell'OpenAPI.

**Design, sezione 1: contratto HTTP**

| Endpoint | Body | Esiti |
|---|---|---|
| `POST /v1/intents` | `{text, profile?}` | 201 `intent_created`, 200 `question` |
| `GET /v1/intents/{id}/proposal` | — | 200 `proposal` o `no_match` |
| `POST /v1/proposals/{id}/reject` | `{reason?}` | 200 `proposal` o `no_match` |
| `POST /v1/proposals/{id}/accept` | `{traveler?}` | 201 `order` (anche al secondo accept, che restituisce lo stesso ordine), 200 `missing_traveler_data` |
| `GET /v1/orders/{id}` | — | 200 `order_status` |

- Ogni corpo di successo è `{"outcome": ..., **to_dict()}`, quindi il dominio non cambia e M3 non viene toccato.
- `profile` e `traveler` passano da `profile_from_dict` e hanno la stessa forma di `profile_to_dict`.
- Gli errori sono tutti `application/problem+json`, con `type` `/problems/<slug>`, `title`, `status`, `detail`, `instance` e `say`:

| Codice | Slug | Quando |
|---|---|---|
| 401 | `unauthorized` | token mancante o sbagliato, con `WWW-Authenticate: Bearer` |
| 404 | `not-found` | `NotFound` del dominio o route sconosciuta sotto `/v1` |
| 422 | `invalid-request` | validazione Pydantic, con l'elenco dei campi |
| 503 | `rest-not-configured` | `VELA_API_TOKEN` assente |
| 503 | `domain-unavailable` | niente `DATABASE_URL` |
| 500 | `internal-error` | errore inatteso, senza traceback nel corpo |

**Sezione 2: `/health`**
- Aggiungo `ProductRepository.last_fetched_at()` in memoria e su Postgres (`MAX(fetched_at)`), più `count()`, che esiste già.
- La risposta aggiunge `catalog: {products, fetched_at, age_seconds}`, che vale `null` senza dominio, e `quota: null` fino a M5.
- Il codice di stato dipende ancora solo dal DB.

**Sezione 3: test (TestClient con `Vela` in memoria, `InlineRunner` e orologio finto, come `test_app_replay.py`)**
- **Autenticazione:** 401 senza token, con token sbagliato e con schema diverso da Bearer; 503 senza configurazione; `/health` e `/replay` restano senza token.
- **Flusso completo:** intento, proposta, rifiuto, proposta diversa, accept, doppio accept con lo stesso ordine, checkout replay, `confirmed` con codice `R-`.
- **Esiti:** `question`, `no_match`, `missing_traveler_data`.
- **Errori:** forma 7807 su 401, 404, 422, 503 e 500; nessun 7807 fuori da `/v1`.
- **RF-10:** `assert_single_product` su ogni risposta.
- **Repository:** contratto di `last_fetched_at` in memoria, e su Postgres solo con `DATABASE_URL`.
- **Health:** età del catalogo con orologio finto.

**Sezione 4: documentazione**
- `docs/rest.md` con i comandi `curl` del flusso §10.3 (token da `$VELA_API_TOKEN`, mai scritto in chiaro).
- Voce in `docs/decisions.md` e aggiornamento del README.
- Ultimo microtask manuale: dopo il merge imposti il token su Render, esegui i `curl` e registriamo l'esito in `docs/acceptance.md`. Se M3 non l'ha ancora creato, lo creo io, e chi arriva secondo fa rebase.

Approvi approccio 1 e design? Se sì, scrivo il piano in `docs/plans/2026-09-25-m4-superficie-rest.md` con microtask TDD e test associati, e mi fermo per la tua revisione prima dell'esecuzione.

## Utente 16:45

vai

## Agente 16:45

- 🔧 Skill superpowers:writing-plans

Uso la skill writing-plans per scrivere il piano. Prima leggo il codice che i microtask toccheranno.

- 🔧 Bash: Read repository ports and adapters

- 🔧 Bash: Read existing test patterns

- 🔧 Bash: Read say, parser questions, plan task 0/13

- 🔧 Bash: Check parser, chooser, README, python

- 🔧 Bash: Check versions, git status, README sections

- 🔧 Bash: Check render.yaml env configuration

Verifico nel scratchpad alcuni comportamenti di FastAPI da cui dipende il piano (ordine auth/validazione, handler 500, 404 su route sconosciute).

- 🔧 Bash: Probe FastAPI auth, validation and error handling

- 🔧 Bash: Check NotFound kinds and postgres imports

- 🔧 Bash: Check test run command convention

- 🔧 Bash: Check single-test run convention

- 🔧 Bash: Run baseline test suite

La suite di partenza è verde: 271 test, 11 saltati. Scrivo il piano.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

Rileggo il piano: sistemo il test lasciato rosso di proposito nel Task 4 e un paio di istruzioni ambigue.

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/docs/plans/2026-09-25-m4-superficie-rest.md

Ho scritto il piano in `docs/plans/2026-09-25-m4-superficie-rest.md`. Non è ancora committato: lo committa il Task 0, insieme alle decisioni dell'intervista in `docs/decisions.md`, come avete fatto per M2.

**Microtask e test:**

| Task | Cosa produce | Test |
|---|---|---|
| 0 | Piano e decisioni nel repo | — |
| 1 | `ProductRepository.last_fetched_at()` in memoria e su Postgres | Test nel contratto condiviso dei repository (Postgres solo con `DATABASE_URL`) |
| 2 | `/health` con `catalog` e `quota: null` | Aggiorna `test_health.py` e aggiunge `CatalogHealthTest` (età, catalogo vuoto, DB giù, nessun token richiesto) |
| 3 | `problems.py`: errori 7807 solo sotto `/v1` | `test_problems.py` (401, 404, 405, 422, JSON malformato, 500 senza dettagli interni, formato predefinito fuori da `/v1`) |
| 4 | `rest.py`: autenticazione, `POST /v1/intents`, `GET .../proposal`, collegamento in `app.py` | `AuthTest` e `IntentEndpointsTest` |
| 5 | reject, accept e stato ordine | `ProposalEndpointsTest`, flusso completo §10.3 in replay con RF-10 su ogni risposta, token richiesto su tutti e cinque gli endpoint |
| 6 | `docs/rest.md` con i comandi `curl`, README, decisioni prese in esecuzione, verifica finale | — |
| 7 | Passo manuale dopo il merge: imposti `VELA_API_TOKEN` su Render, esegui i `curl` e registriamo l'esito in `docs/acceptance.md` | — |

Prima di scrivere il piano ho controllato in uno script di prova nello scratchpad alcuni comportamenti di FastAPI su cui si appoggia:
- l'autenticazione viene controllata prima della validazione del body;
- l'handler del 500 funziona;
- una route sconosciuta sotto `/v1` arriva all'handler degli errori HTTP;
- i campi extra nel body vengono ignorati.

La suite di partenza è verde (271 test, 11 saltati).

**Punti da tenere d'occhio:**
- Lo stesso `test_health.py` cambia: i due test che confrontavano il corpo esatto di `/health` ora includono `catalog` e `quota`.
- M3 modifica anch'essa `vela/app.py` e crea `docs/acceptance.md`: chi fa merge per secondo deve fare rebase.

Lo lanci tu. Per un piano così ti consiglio l'esecuzione **subagent-driven**: i Task 3→4→5 dipendono uno dall'altro tramite interfacce precise (`Problem`, `reply`, `make_client`), e un reviewer per ogni task intercetta subito gli errori sul contratto HTTP, che è pubblico. Il piano rispecchia quello che vuoi?

## Utente 16:54

/superpowers:brainstorming: docs/plans/2026-09-25-m4-superficie-rest.md.

## Agente 16:54

Hai rilanciato il brainstorming sul piano M4 appena scritto (`docs/plans/2026-09-25-m4-superficie-rest.md`). Il piano c'è già e riprende le decisioni dell'intervista: token assente → 503, esiti 2xx con `outcome`, `/health` con `last_fetched_at` e `quota: null`, errori 7807 solo sotto `/v1`, nessuno script (solo `curl` in `docs/rest.md`). Prima di muovermi, cosa vuoi fare con il piano?

- 🔧 AskUserQuestion

Certo. Cosa vuoi chiarire? Può riguardare la domanda stessa, un punto del piano o il motivo per cui hai riaperto il brainstorming. Dimmelo liberamente e riparto da lì.

## Utente 16:55

❯ /superpowers:test-driven-development docs/plans/2026-09-25-m4-superficie-rest.md

## Agente 16:55

- 🔧 Skill superpowers:test-driven-development

Eseguo il piano in TDD, task per task. Prima leggo le regole sui test richieste dalla skill.

- 🔧 Bash: Read test-writing rules and check git state

**Task 0**: registro le decisioni e committo il piano.

- 🔧 Bash: Record decisions and commit plan

**Task 1**, fase RED: aggiungo il test del contratto per `last_fetched_at`.

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m4/tests/repo_contract.py

- 🔧 Bash: Run new test to see it fail

- 🔧 Bash: Show failure reason

Fallisce per il motivo atteso. Fase GREEN:

- 🔧 Bash: Implement last_fetched_at and run repo tests

Verde in memoria. Eseguo il contratto anche su Postgres, nello schema `vela_test`, caricando l'ambiente senza stamparlo:

- 🔧 Bash: Run Postgres repository contract tests

Il worktree non ha un `.env`, quindi i test Postgres restano saltati. Non vado a cercare il file altrove e lo segnalo nel resoconto finale. Committo il Task 1.

- 🔧 Bash: Commit Task 1

**Task 2**, fase RED: test di `/health`.

- 🔧 Bash: Write health tests and watch them fail

I test falliscono perché mancano `catalog` e `quota`. `test_health_needs_no_token` passa già: è una guardia di regressione. Fase GREEN:

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m4/vela/surfaces/health.py

- 🔧 Bash: Run health tests and full suite

- 🔧 Bash: Commit Task 2

**Task 3**, fase RED: l'helper `assert_problem` e i test 7807.

- 🔧 Bash: Write 7807 tests and watch them fail

- 🔧 Bash: Check test file convention for main guard

- 🔧 Bash: Drop main guard to match domain test style

Il modulo manca, come atteso. Fase GREEN:

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m4/vela/surfaces/problems.py

- 🔧 Bash: Run 7807 tests and full suite

- 🔧 Bash: Check test output for noise
