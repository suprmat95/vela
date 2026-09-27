# M21-B ordinamento e prodotti equivalenti

- Sessione: `da1cd37a-34ff-47c7-ac99-f9c0f7bbdb36`
- Inizio: 2026-09-27 13:18

## Utente 13:18

<pasted_content id="e547">
Task M21-B — Ordinamento e prodotti equivalenti (UC-B). Su master ci sono già M21-A (durata) e
M21-E (budget a testa o totale). M22 è chiusa con il verdetto di M22-a (decisions.md,
2026-09-27): non toccare nulla che la riguardi.

Leggi docs/spec.md (§4.12, RF-06, RF-07, RF-60, RF-61), docs/usecases/scelta.md (UC-B),
docs/decisions.md (2026-09-26 "Scelta v3", "M21-A Durata", 2026-09-27 "M21-E Budget a testa o
totale", la sezione di M22-a su "prodotti senza hotel"), vela/domain/chooser.py,
vela/domain/intent.py, vela/domain/refine.py, vela/domain/say.py, vela/domain/usecases.py,
vela/domain/catalog.py, vela/sync.py, vela/surfaces/mcp.py, vela/surfaces/rest.py e
docs/roadmap.md M21 (regole comuni) e M21-B.

Obiettivo: il caso UC-B con i suoi test. Ordinamento di RF-60 in chooser.py (il livello
"livello e lezioni" resta neutro fino a M21-C); partenza più vicina all'inizio del periodo;
featured e special_offer letti dal sync (migrazione 0010: due colonne su products, valorizzate
dal prossimo sync e dalle fixture); raggruppamento dei prodotti equivalenti di RF-61;
motivazione che spiega la scelta ("parte a inizio novembre"); docs/rest.md e descrizioni MCP
aggiornate dove cambiano.

Decisioni aperte della roadmap, con le mie preferenze (confermale o proponi di meglio prima di
scrivere codice):
- Prova del criterio §10.4 con la trappola (900078): A) add_trap con un'opzione che archivia
  l'originale nella fixture di prova. Il test di UC-B resta: 78 proposto, 900078 solo dopo un
  rifiuto del 78 che non sia `hotel`.
- Soglia di equivalenza del prezzo: A) 5%.
- Migrazione 0010: mostrami lo schema e aspetta il mio OK prima di scriverla.

Vincoli:
- Nessuna chiamata a servizi esterni: i campi che servono sono già nelle fixture.
- Il catalogo non ha cache: list_all() fa una SELECT a ogni proposta (decisions.md, M21-E). Non
  aggiungere letture in più; se il raggruppamento di RF-61 ne richiede, dimmelo prima.
- Mettere featured e special_offer nelle fixture non deve cambiare il conteggio dei prodotti
  atteso dal load test (loadtest/run.py lo calcola dalle fixture: oggi 190).
- I test che fissano l'ordinamento v2 si aggiornano senza indebolire le asserzioni e si elencano
  in decisions.md.
- TDD, suite e ruff verdi, commit piccoli, fermati per il mio OK prima del merge su master.
</pasted_content id="e547">

## Agente 13:18

I'll start by loading the brainstorming skill, since this task begins with a design proposal before any code.

- 🔧 Skill superpowers:brainstorming

- 🔧 Bash: Count lines in the files to read and list migrations, fixtures and tests

- 🔧 Bash: Locate the spec sections for UC-B and RF-06/07/60/61

- 🔧 Bash: Read spec §4.1 and §4.2 (RF-06, RF-07)

- 🔧 Bash: Read spec §4.12 (RF-58..75)

- 🔧 Bash: Read spec §10 acceptance criteria

- 🔧 Bash: Read the UC-B use case document

- 🔧 Bash: List headings in decisions.md to find the relevant sections

- 🔧 Bash: List headings in roadmap.md to find M21 and M22 sections

- 🔧 Bash: Read the chooser

- 🔧 Bash: Read the catalog domain model

- 🔧 Bash: Read decisions: Scelta v3, Prezzo effettivo, M21-A, M20 absorbed

- 🔧 Bash: Find the M21-E and M22-a decision entries

- 🔧 Bash: Read roadmap M21 common rules and the M21-B..F sections

- 🔧 Bash: Read the domain models

- 🔧 Bash: Read the sync module

- 🔧 Bash: Read the use cases

- 🔧 Bash: Read refine.py and docs/rest.md

- 🔧 Bash: Compare the task branch with master and list branches

- 🔧 Bash: Read the M21-E and M22-a decision entries from master

- 🔧 Bash: Show which files differ between the branch and master

- 🔧 Bash: Diff chooser against master and check models on master for new fields

- 🔧 Bash: Read the last migrations and the products table definition

- 🔧 Bash: Inspect fixtures for featured, isSpecialOffer and trap products

- 🔧 Bash: Find where the trap product is defined and used

The branch has no commits of its own and sits 20 commits behind master, so I'll fast-forward it to master (no history rewrite), then read the files that changed there.

- 🔧 Bash: Fast-forward the task branch to master

- 🔧 Bash: Read the M22-a decision entry

- 🔧 Bash: Read the chooser tail on master and the M21-E diffs to usecases, scelta.md, spec.md

- 🔧 Bash: Read say.py

- 🔧 Bash: Read the existing chooser tests

- 🔧 Bash: Read the chooser filters, fixture and duration tests

- 🔧 Bash: Read the fixture module with add_trap and its usages

- 🔧 Bash: Find the loadtest product count and any existing featured references

- 🔧 Bash: Read the test support helpers for building products

- 🔧 Bash: Find the products table definition and the row mapping in the Postgres repo

- 🔧 Bash: Read the products table definition and the row mapping

- 🔧 Bash: Read the fixture format doc and the projection tests

- 🔧 Bash: Read the trap tests, the staging fixture test and the trap intent in rest_flow

- 🔧 Bash: Check how the load test counts products and how replay and the fake HofJ read fixtures

- 🔧 Bash: Find tests and surface texts that assert the cheapest-product wording

- 🔧 Bash: Find other tests and scripts pinned to specific fixture product ids

- 🔧 Bash: Read the MCP tool descriptions and instructions

- 🔧 Bash: Read the migration test and list recent plans

- 🔧 Bash: Check featured consistency and look for naturally equivalent products in the fixtures

- 🔧 Bash: Read the products table schema and compute the load test expected product count

- 🔧 Bash: Read the duration reason tests

- 🔧 Bash: Read the use case tests that pin ordering and reason wording

- 🔧 Bash: Read the REST doc ordering notes and the HofJ sample builders

- 🔧 Bash: Scan the fixture, sync and repository contract tests for product field checks

- 🔧 Bash: Read the acceptance table and find trap or id references in replay and smoke tests

- 🔧 Bash: Read the staging scenario tests and the landing test that names fixture products

- 🔧 Bash: Check how the roadmap marks completed tasks

Ho letto tutto quello che serviva. Prima una nota di stato, poi la proposta: mi fermo qui e aspetto il tuo OK prima di scrivere codice.

**Stato del branch.** `task/m21b` era fermo 20 commit dietro `master` (senza M21-E né M22-a). Non aveva commit propri, quindi l'ho portato avanti con un fast-forward a `326d661`. Nessuna riscrittura di storia.

**Cosa ho trovato nelle fixture** (conta per le decisioni sotto):
- `featured` e `isSpecialOffer` stanno in `details[id].raw` e negli item di lista, ma **non** in `details[id].catalog`, perché `project_detail` non li proietta. Prodotti attivi con `featured`: 11 padel, 1 tennis (363), 3 su staging padel. `isSpecialOffer` falso ovunque.
- Nessun gruppo di equivalenti naturale nelle quattro fixture: RF-61 oggi colpisce solo la trappola.
- **34 prodotti padel attivi su 77 non hanno hotel**, compreso il 78 di staging. Quindi la trappola 900078 ha `hotel = None` come il 78: l'equivalenza deve trattare "nessun hotel" uguale a "nessun hotel", altrimenti la trappola non si raggruppa mai.
- Conteggio del load test: `expected_products` con i brand di default dà **126** (i non archiviati di `catalog.json` e `catalog-tennis.json`), non 190; 190 sono gli item di lista archiviati compresi. In ogni caso aggiungo solo due chiavi a ogni `catalog`, nessun prodotto in più o in meno: lo verifico prima e dopo.

## Decisioni aperte della roadmap

- **Prova di §10.4: A confermata.** `add_trap(catalog, template_id, archive_template=False)`: con l'opzione l'item del modello diventa `archived: true` e il suo dettaglio viene tolto, così il filtro `archived` lo scarta prima del raggruppamento e la trappola resta sola nel suo gruppo. Il test di UC-B resta: fixture di staging più trappola → 78 proposto; rifiuto del 78 per date → 900078. Il caso "rifiuto `hotel` → nessuno dei due" arriva con RF-72 in M21-F: lo scrivo nella decisione, non lo posso testare ora.
- **Soglia 5%: A confermata**, misurata sul prezzo del prodotto con l'id più basso del gruppo: `|prezzo − prezzo_anchor| ≤ 5% × prezzo_anchor`. Raggruppo scorrendo i candidati in ordine di id numerico: chi non sta entro il 5% di nessun anchor esistente della stessa chiave (hotel, titolo normalizzato, destinazione) diventa un anchor nuovo. Deterministico e senza catene transitive.
- **Migrazione 0010, schema da approvare:**

```
products.featured       BOOLEAN NOT NULL DEFAULT false
products.special_offer  BOOLEAN NOT NULL DEFAULT false
```

  `batch_alter_table` come la 0006 (gira su SQLite nei test). **Aggiunta che ti chiedo di approvare:** un backfill nella stessa migrazione, in Python riga per riga, che legge `raw->featured` e `raw->isSpecialOffer` già salvati (la 0009 fa già dati). Senza, il sync incrementale scarica solo i prodotti con `updatedAt` cambiato: su Render le righe esistenti resterebbero a `false` a tempo indeterminato. Downgrade: drop delle due colonne.

## Approccio

- **Modello e sync.** `Product.featured` e `Product.special_offer` (default `False`, in coda ai campi). `featured` e `isSpecialOffer` entrano in `CATALOG_FIELDS`, quindi `project_detail` li proietta e `product_from_entry` li legge da dettaglio e da item di lista. Repository Postgres aggiornato. Le quattro fixture: `catalog` riproiettato da `raw` con `project_detail`, in locale, zero chiamate. Aggiorna `test_catalog_projection` (elenco esatto delle chiavi) e `docs/fixtures.md`.
- **RF-61 in `chooser.py`**, dopo gli otto filtri duri e prima dell'ordinamento. Non è un filtro: `FILTERS` non cambia e non produce mai `NoChoice`. Chiave: `(hotel or "", " ".join(title.lower().split()), destination or "")`. `cheapest_total` di M21-E resta sui soli filtri duri, senza raggruppamento: la differenza è al più il 5%, e la regola 4 chiede il più economico compatibile, che esiste comunque. Nessuna lettura in più del catalogo.
- **RF-60.** Chiave di ordinamento: `(-area, fuori budget, durata non ok, [livello: neutro fino a M21-C], inizio della partenza, non featured/special_offer, prezzo, id)`. La partenza si ordina per data di inizio: ogni partenza valida è già ≥ inizio periodo (o ≥ oggi senza periodo), quindi la distanza dall'inizio coincide con la data. Il tie-break su id diventa **numerico** (oggi è stringa: "100" < "78"), coerente con RF-61; cambia le sequenze registrate solo a parità di tutto il resto.
- **Motivazione.** La seconda frase oggi dice "è la più economica compatibile" in modo incondizionato: con l'ordine nuovo sarebbe spesso falsa. La frase resta com'è quando il prodotto è davvero il più economico tra i pari (stessa area, stesso stato di budget e durata). Altrimenti dice il livello che ha deciso: "Parte il 2 novembre 2026, la prima partenza nel periodo che hai chiesto, con un totale a partire da 640 euro[, dentro il tuo budget di 800 euro]" oppure, senza periodo, "la prima partenza disponibile"; se ha vinto su `featured`, "…con un totale a partire da 640 euro, ed è tra i viaggi in evidenza del catalogo". Inglese equivalente. Uso "la prima partenza nel periodo che hai chiesto" invece di "a inizio novembre" di UC-B: dice la regola vera e vale per qualunque periodo; allineo l'esempio in `scelta.md` come ha fatto M21-E.
- **Superfici e docs.** `docs/rest.md`: un punto "Ordinamento" accanto a "Durata" e "Budget". MCP: una frase nella descrizione di `get_proposal` ("Vela picks it by area, budget, length, earliest departure in the period, featured, then price"), così l'agente non promette "il più economico". Nessun campo nuovo. Decisioni in `decisions.md`, stato in spec §4.12 e roadmap.
- **Test (TDD).** Nuovo `tests/test_chooser_ordering.py`: tabella di coppie che differiscono per un solo livello con il vincitore atteso (7 livelli, il 4 annotato), partenza più vicina batte prezzo senza budget, `featured` batte prezzo a parità dei livelli 1-5, RF-61 (entro/oltre 5%, hotel diverso, entrambi senza hotel, originale rifiutato o archiviato → equivalente proposto), determinismo con ingresso mescolato, frasi it/en. Trappola in `tests/test_staging_fixture.py` con fixture temporanea da `add_trap` (78 poi 900078; con `archive_template` subito 900078). `test_fixtures_record` per l'opzione. Migrazione: head 0010, colonne e backfill su SQLite.
- **Test esistenti da aggiornare**, senza indebolire le asserzioni, elencati in `decisions.md`: `test_chooser_fixture` (tabelle delle prime tre scelte e chiave di monotonia nella proprietà), `test_chooser_filters` (sequenze ri-registrate con v3, docstring aggiornata), `test_catalog_projection`, `test_migrations`, e `test_staging_fixture.CriteriaScenarioTest` se le sequenze 158 → 115 → 28 cambiano con la partenza. Li aggiorno solo dopo aver verificato ogni differenza a mano.

**Commit previsti**, piccoli: (1) migrazione, modello, proiezione, fixture; (2) RF-61; (3) RF-60 e motivazione con i test aggiornati; (4) `add_trap` e prova della trappola; (5) docs e decisioni. Mi fermo per il tuo OK prima del merge.

Dimmi se confermi le tre decisioni, il backfill nella 0010, l'equivalenza tra prodotti senza hotel, l'id numerico e le frasi della motivazione, oppure cosa cambiare.

## Utente 13:26

<pasted_content id="e547">
Confermo tutto:
- §10.4 con add_trap(archive_template=...) come descritto; il caso "rifiuto hotel → né 78 né
  900078" va scritto in decisions.md come test da fare in M21-F.
- Soglia 5% sull'anchor con id più basso, raggruppamento deterministico senza catene: ok.
- Migrazione 0010 approvata, compreso il backfill in Python da raw->featured e
  raw->isSpecialOffer; downgrade con drop delle due colonne.
- Equivalenza "nessun hotel" = "nessun hotel": ok.
- Spareggio su id numerico: ok, ma con fallback: un id non numerico si ordina dopo i numerici,
  come stringa, senza eccezioni (decisions.md M10 prevede possibili prefissi t:/p:). Un test.
- Frasi della motivazione it/en e allineamento di scelta.md: ok.
- cheapest_total senza raggruppamento: ok.
- Prima e dopo le fixture verifica che expected_products resti 126.

Procedi con i commit nell'ordine proposto, TDD, suite e ruff verdi. Fermati prima del merge.
</pasted_content id="e547">

## Agente 13:26

Approvato. Carico la skill TDD e parto con il commit 1 (migrazione, modello, proiezione, fixture).

- 🔧 Skill superpowers:test-driven-development

- 🔧 Bash: Run the full suite and lint for a baseline

- 🔧 Bash: Read the rest of the migration tests

- 🔧 Bash: Read the catalog tests

- 🔧 Bash: Read the repository round-trip test and the fixture field checks

- 🔧 Bash: Find Product constructors and read the 0007 migration for the data-update style

- 🔧 Bash: Read the sync test helpers and check for a local Postgres

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog_projection.py

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog.py

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_migrations.py

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/repo_contract.py

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog_fixture.py

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/hofj_samples.py

Now the RED tests for commit 1: projection keys, product flags, fixture flags, sync, repository round trip, migration 0010.

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog_projection.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/repo_contract.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/hofj_samples.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog_fixture.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_catalog_fixture.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_sync.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_migrations.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_migrations.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_migrations.py

- 🔧 Bash: Run the new tests and confirm they fail for the expected reasons

- 🔧 Bash: Add the flags to the model, projection, schema, repository and write migration 0010

- 🔧 Bash: Show the failing migration test

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_migrations.py

- 🔧 Bash: Rerun the migration, catalog, sync and memory repository tests

- 🔧 Bash: Reproject the fixture catalogs from raw, check the product count and the shape of the diff

- 🔧 Bash: Update the fixture format doc, then run the full suite and lint

- 🔧 Bash: Check whether a Postgres reachable from the host is available for the DB tests

- 🔧 Bash: Start a throwaway Postgres and run the full suite including the DB tests

- 🔧 Bash: Show the failing Postgres test

- 🔧 Bash: Read the Postgres migration test that pins the head revision

- 🔧 Bash: Find other tests that pin the head revision number

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_migrations.py

- 🔧 Bash: Rerun the full suite with Postgres, lint, and show the working tree

Full suite green with Postgres too (1282 tests, no skips). Committing commit 1.

- 🔧 Bash: Commit the migration, model, projection and fixture changes

Commit 2 next: RF-61 grouping. Writing the failing tests first in a new `tests/test_chooser_ordering.py`.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_chooser_ordering.py

- 🔧 Bash: Run the RF-61 tests and confirm they fail

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_chooser_ordering.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_chooser_ordering.py

- 🔧 Bash: Confirm the corrected tests still fail before implementing

Seven RED for the right reasons. Now the GREEN implementation in `chooser.py`: the id key, the equivalence key, the grouping, and its call in `choose`.

- 🔧 Bash: Implement RF-61 grouping and the numeric id key in the chooser, then run the chooser tests

- 🔧 Bash: Keep the string id tie-break in the sort until commit 3

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m21b/tests/test_chooser_ordering.py

- 🔧 Bash: Rerun the chooser tests

- 🔧 Bash: Run the full suite and lint before committing commit 2

- 🔧 Bash: Show the lint findings

- 🔧 Bash: Remove the unused imports, re-check lint and tests, commit RF-61

Commit 3 now: RF-60 ordering plus the motivation. I'll write the failing tests first (level table, departure and featured precedence, determinism, id tie-break, reason wording it/en), then implement.

- 🔧 Bash: Check the default products of the use case tests

- 🔧 Bash: Add the RF-60 ordering and reason tests and confirm they fail

All 16 fail for the right reason (v2 still sorts by price and string id). Now the GREEN implementation: the v3 sort key, the "why" flags, and the new sentence forms.

- 🔧 Bash: List the chooser's top-level definitions and current docstring

- 🔧 Bash: Implement the RF-60 sort key, the Why flags and the new motivation sentences, then run the chooser tests

- 🔧 Bash: Summarise which chooser tests still fail

- 🔧 Bash: Compare the first three v2 and v3 choices on the production fixture for every pinned intent

- 🔧 Bash: Re-record the v3 sequences on the fixtures and check they contain the same products as the v2 ones

- 🔧 Bash: Run the staging scenario tests and list every failing test in the whole suite

- 🔧 Bash: Print the v3 first-three-choice tuples for the fixture table

- 🔧 Bash: Re-record the v3 sequences and docstrings in the filters test and run it

The filters test is green. Now the fixture table: I'll replace the eight changed rows, the monotonicity key and the docstring, and tidy the blank lines my regex left in the sequences file.

- 🔧 Bash: Update the fixture table and property key, then run the chooser tests, the full suite and lint

Suite green (1306 tests) and lint clean. A quick review of the chooser diff before committing commit 3.

- 🔧 Bash: Review the chooser diff for commit 3

The diff reads right. Committing commit 3.

- 🔧 Bash: Commit the RF-60 ordering and motivation
