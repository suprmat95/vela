# quota-constant-rate

- Sessione: `0ab37375-de40-4f53-91d1-32990c829b34`
- Inizio: 2026-09-26 14:37

## Utente 14:37

Leggi docs/roadmap.md M18 (usa il suo blocco Prompt) e docs/plans/2026-09-26-twist-seconda-lettura.md sezioni 3.1-3.3. Esegui M18. Nella voce "Twist, seconda lettura" di decisions.md sostituisci "[da verificare nel codice]" sui job di prenotazione con: verificato, un solo job attivo per ordine (_enqueue_booking), corsa teorica non atomica resa innocua dall'upsert. Nessuna chiamata esterna.

## Agente 14:37

- 🔧 Bash: Locate M18 in roadmap and list docs

- 🔧 Bash: Check roadmap headings and search for twist plan

- 🔧 Bash: Find branch holding the twist plan

- 🔧 Bash: Compare master with current branch

- 🔧 Bash: Read roadmap intro and M13a-M19 from master

The M18 docs are only on `master`: `task/m18` is behind it. I'm now reading the plan's sections 3.1-3.3 and the decisions entry.

- 🔧 Bash: Outline the twist plan and find the decisions placeholder

- 🔧 Bash: Read plan sections 2-3.3, 4-5, 9 and the decisions entry

- 🔧 Bash: Size up M18 code files and find booking enqueue

- 🔧 Bash: Read quota, booking, config and order enqueue code

- 🔧 Bash: Find quota store and related usages

- 🔧 Bash: Read quota store adapters and migrations list

Still mapping the code: I've read the quota store and now I'm checking the worker, health, HofJ client and existing quota tests.

- 🔧 Bash: Read job processor, quota schema and migration

- 🔧 Bash: Read purchase job, health and HofJ timeout

- 🔧 AskUserQuestion

What would you like to clarify before choosing?

For context, here's what's behind each question:

- **Booking reserve.** Today, bookings get a fixed 20% of each 60 s window. A token bucket has no windows. I can either:
  - make bookings take priority (purchases always leave 2 tokens in the bucket), or
  - split the bucket into a 20/min part for bookings and an 80/min part for purchases.
- **Schema.** The bucket needs two new values: the current token count and the time of the last refill. Changing the database needs your OK. I can either add columns to the existing `quota_window` row or create a new table.
- **Orphaned itineraries.** The roadmap says "campo o log", so a field or a log line. A field means a migration on `orders`. A log line needs no schema change.

## Utente 14:40

spiegami meglio questa scelta

## Agente 14:40

Ti spiego la prima scelta, la riserva per le prenotazioni. Se intendevi un'altra delle tre, dimmelo.

**Il problema.** Oggi la finestra di 60 s ha 108 chiamate. Gli acquisti si fermano a 87, così ne restano almeno 21 per le prenotazioni degli ordini pagati. Il token bucket di M18 non ha finestre: ha un serbatoio da 8 gettoni che si riempie di 1,67 gettoni al secondo (100 al minuto). Un acquisto ne consuma 5 in blocco, una prenotazione 1. Bisogna decidere come le prenotazioni restano protette dagli acquisti.

**Opzione A: soglia minima (quella che consiglio).** C'è un solo serbatoio. Un acquisto parte solo se, dopo aver preso i suoi 5 gettoni, nel serbatoio ne restano almeno 2. Deve quindi trovarne almeno 7. Una prenotazione può prendere anche gli ultimi gettoni.

Sotto carico pieno, il serbatoio sale a 7 e un acquisto lo riporta a 2. Una prenotazione che arriva trova sempre almeno 2 gettoni e parte subito, senza mai aspettare gli acquisti.

- Pro: le prenotazioni hanno la precedenza assoluta, coerente con "mai sacrificare le prenotazioni degli ordini pagati" (budget in decisions.md).
- Pro: quando non ci sono prenotazioni, gli acquisti usano tutto il ritmo. Sono fino a 20 al minuto invece di 16, e la riserva non va sprecata come oggi.
- Contro: la riserva non è più "il 20%" ma una precedenza. In teoria una valanga di prenotazioni rallenta gli acquisti. In pratica le prenotazioni sono limitate dagli ordini pagati, che a loro volta sono limitati dagli acquisti, quindi il fenomeno si limita da solo.
- Per l'attesa dichiarata (RF-48) continuerei a contare 16 acquisti al minuto: è una stima prudente.

**Opzione B: due serbatoi.** Uno per le prenotazioni, da 20 al minuto, e uno per gli acquisti, da 80 al minuto. Le capienze sono divise in modo che la somma rispetti B + 60·r ≤ 108.

- Pro: riproduce esattamente la regola di oggi, con 20% garantito alle prenotazioni.
- Contro: gli acquisti restano fermi a 16 al minuto anche quando nessuno sta prenotando. Per non sprecare la riserva servirebbe una regola di "prestito" tra i serbatoi, che vuol dire più stato e più casi da testare.

Con A cambia il significato di "riserva" in RF-47. Lo registrerei in decisions.md con il motivo.

- 🔧 AskUserQuestion

- 🔧 Write /Users/matteodospina/.claude/plans/leggi-docs-roadmap-md-m18-usa-happy-church.md

- 🔧 ToolSearch

- 🔧 ExitPlanMode

- 🔧 Bash: Fast-forward to master and run baseline tests

- 🔧 Bash: Inspect baseline test failures

The suite requires Python 3.12 from the uv venv. I'll try building it from the local cache only, without network access.

- 🔧 Bash: Create venv from uv cache offline and run tests

Baseline is green: 916 tests, 47 skipped. Now I'm reading the quota tests and every caller of the current rules.

- 🔧 Bash: Read quota contract tests and callers

- 🔧 Bash: Read worker threading and memory quota

- 🔧 Bash: Find consumers of quota snapshot fields

- 🔧 Bash: Read job processor tests

- 🔧 Bash: Find repo construction and refresh callers

I have the full picture. Writing the pure token-bucket rules first.

- 🔧 Bash: Check snapshot and error types

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m18/vela/domain/quota.py

- 🔧 Bash: Check usecases wait and adapter imports

Now the port, then the two adapters.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m18/vela/ports/quota.py

- 🔧 Bash: Rewrite MemoryQuota as a token bucket

- 🔧 Bash: Tidy import and view Postgres schema

- 🔧 Bash: Rewrite PostgresQuota and schema columns

- 🔧 Bash: Add imports and view latest migration

- 🔧 Bash: Add migration 0007 and inspect Order model

- 🔧 Bash: Inspect orders table and repo mapping

Bucket rules, port, adapters and migration are written. Now I'm adding the orphan counter on `orders`.

- 🔧 Bash: Add orphan_itineraries to Order and mapping

- 🔧 Bash: Read purchase steps and HofJ http error mapping

- 🔧 Bash: Read HofJ error mapper

- 🔧 Bash: Add UpstreamTimeout and 20s client timeout

- 🔧 Bash: Count orphan itineraries in PurchaseJob

Now the job processor: a single re-read after a 429, and no immediate retry.

- 🔧 Bash: Rewrite quota refresh in JobProcessor

- 🔧 Bash: Delay job after 429 and update callers

Wiring the settings (concurrency 10, lease 180, bucket parameters) into the app and sync.

- 🔧 Bash: Wire bucket settings, concurrency and lease

- 🔧 Bash: Read job and order ports

- 🔧 Bash: Add queue age and orphan total queries

- 🔧 Bash: Add health queue info and run suite

Expected fallout from the change. I'm working through the failures, starting with the migrations.

- 🔧 Bash: Inspect migration test failures

- 🔧 Bash: Run migration tests from tests dir

- 🔧 Bash: Read migration tests

- 🔧 Bash: Update migration tests, check config/http tests

- 🔧 Bash: Read config and http timeout tests

- 🔧 Bash: Read timeout error-mapping tests

Still updating the tests for the new values (config, 20 s timeout, `UpstreamTimeout`). Then I'll move on to the quota contract.

- 🔧 Bash: Update config and HofJ http tests

- 🔧 Bash: Import UpstreamTimeout in http tests

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m18/tests/quota_contract.py

- 🔧 Bash: Rewrite quota rules tests and run quota suites

- 🔧 Bash: Tidy test and inspect job processor failures

- 🔧 Bash: Rewrite job processor tests for the bucket

The booking was being deferred to the time a full purchase fits. I'm making the deferral depend on the job's class and size.

- 🔧 Bash: Class-aware deferral and one-window retry floor

That's the right behaviour: at 61 s the only token goes to the re-read, and the booking follows 0.2 s later. I'm fixing the test, not the code.

- 🔧 Bash: Fix test timing and rerun full suite

- 🔧 Bash: Read payment check and fixtures record tests

- 🔧 Bash: Fix payment/fixtures tests and read health tests

- 🔧 Bash: Read health test helpers

- 🔧 Bash: Update health tests for bucket and queue

- 🔧 Bash: Add order stub and run health tests

Health, payment and fixture tests are green. Left to fix: `LaunchBurstTest`, the end-to-end flow and the queue position.

- 🔧 Bash: Read queue flow tests

- 🔧 Bash: Read usecases queue position test

- 🔧 Bash: Update queue-flow and usecase tests, rerun suite

Suite is green. Now the missing orphan-itinerary tests in `test_purchase_job.py`.

- 🔧 Bash: Read purchase job tests

- 🔧 Bash: Add orphan itinerary tests

Unit tests are OK. Checking whether a local Postgres is available to run the skipped tests, without reading `.env`.

- 🔧 Bash: Check for a local Postgres

Postgres.app is installed but not running. I'll start a throwaway cluster in the scratchpad on a separate port, touching nothing of yours, to run the Postgres tests.

- 🔧 Bash: Start a throwaway local Postgres in scratchpad

- 🔧 Bash: Read Postgres startup log

- 🔧 Bash: Start Postgres with TCP only

- 🔧 Bash: Run full suite against local Postgres

- 🔧 Bash: Fix Postgres head test and rerun both suites

Green in memory and on Postgres, including the 8-thread test and the Postgres contract. Now `decisions.md`.

- 🔧 Bash: Inspect decisions log structure

- 🔧 Bash: Read an execution-decisions entry for format

- 🔧 Bash: Replace the unverified booking-jobs note

No response requested.

## Utente 15:27

continua

## Agente 15:27

- 🔧 Bash: Check whether decisions edit applied

The interrupted `decisions.md` edit wasn't applied. I'm checking that the code is intact, then redoing it.

- 🔧 Bash: Verify quota module and suite

- 🔧 Bash: Update decisions log with verification and M18 entry

- 🔧 Bash: Find docs describing health quota fields

- 🔧 Bash: Read the drift note in quota-health doc

- 🔧 Bash: Read full README health line

- 🔧 Bash: Update README and quota-health notes

Everything is done and green. Now committing: code and tests in one commit (the pieces depend on each other, so a split would leave broken intermediate commits), documentation in a second.

- 🔧 Bash: Commit code and docs
