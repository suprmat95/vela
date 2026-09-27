# M21-E budget a totale

- Sessione: `705f14ce-0acd-4601-b384-673abfbfde7c`
- Inizio: 2026-09-27 12:42

## Utente 12:42

<pasted_content id="70e2">
Task M21-E — Budget a testa o totale (UC-E). M21-A è già su master; M20 è stata assorbita dalla
conferma del prezzo (decisions.md, 2026-09-27).

Leggi docs/spec.md (§4.12, RF-02, RF-04, RF-06..09, RF-52..55, RF-69, RF-70),
docs/usecases/scelta.md (UC-E), docs/decisions.md (2026-09-26 "Scelta v3", "Prezzo effettivo
prima del link", "M21-A Durata"), vela/domain/intent.py, vela/domain/chooser.py,
vela/domain/refine.py, vela/domain/say.py, vela/domain/usecases.py, vela/surfaces/mcp.py,
vela/surfaces/rest.py e docs/roadmap.md M21 (regole comuni) e M21-E.

Obiettivo: il caso UC-E con i suoi test. Parole "in tutto/totale/in total" nel parser; campo
budget_scope su create_intent e reject_proposal; regola 4 di RF-69; budget_scope nei criteri;
frase di RF-70 in ogni say con un budget; docs/rest.md e descrizioni MCP aggiornate.

Decisione aperta della roadmap: dove calcolare la regola 4. La mia preferenza è A)
create_intent, salvata nei criteri, così il say la dichiara subito. Confermamela o proponi di
meglio prima di scrivere codice.

Nessuna chiamata a servizi esterni. I test che fissano comportamenti vecchi si aggiornano senza
indebolire le asserzioni e si elencano in decisions.md. TDD, suite e ruff verdi, commit
piccoli, fermati per il mio OK prima del merge su master.
</pasted_content id="70e2">

## Agente 12:42

I'll read the listed documents and code first, then propose the approach and wait for your OK.

- 🔧 Bash: Count lines of files to read

- 🔧 Bash: Locate spec sections

- 🔧 Bash: Locate roadmap, decisions, use case sections

- 🔧 Bash: Read spec RF-01..09 and §4.11-4.12

- 🔧 Bash: Read UC-E and roadmap M21-E

- 🔧 Bash: Read relevant decisions

Now the code.

- 🔧 Bash: Read intent parser

- 🔧 Bash: Read chooser and refine

- 🔧 Bash: Read usecases and Criteria model

- 🔧 Bash: Read say.py first part

- 🔧 Bash: Find budget usage in say/surfaces/docs/tests

- 🔧 Bash: Check existing per-person tests and REST doc

- 🔧 Bash: Find says with budget and tests fixing phrasing

- 🔧 Bash: Check no_match say, MCP budget param, REST fields, git history

Ho letto spec, UC-E, decisioni, roadmap e il codice. Il branch `task/m21e` è allineato a `master`. Non ho ancora scritto niente.

## Dove calcolare la regola 4: confermo A

Si calcola in `create_intent` e il risultato si salva nei criteri. I motivi:
- **Il `say` è sempre vero.** RF-70 fa sentire la lettura subito ("600 a persona, 1800 in tutto"). Con B la lettura potrebbe cambiare dopo un sync del catalogo senza che il viaggiatore lo senta, e la frase detta all'inizio diventerebbe falsa.
- **Il chooser non cambia.** Resta `budget` come tetto sul totale, come dice la decisione "Lettura del budget".
- **Il viaggiatore corregge in un modo solo:** `reject_proposal(budget_scope=…)`.

Su `reject_proposal` la regola 4 si ricalcola solo quando arriva una cifra nuova, nel motivo o nei campi.

## Approccio

- **Modello.** `Criteria.budget_scope` (`per_person` | `total` | None), messo in fondo come le notti di M21-A. `StructuredFields.budget_scope`. Validazione in `validate_fields`: un valore fuori elenco si scarta e il `say` lo dice. Si salva nel JSON dei criteri, senza migrazione. Gli intenti vecchi hanno None e valgono come `total`.
- **Parser, regole 1-3 e 5.** L'ordine è: campo `budget_scope`, poi le parole "a testa/each/…", poi le parole "in tutto/totale/in totale/complessivi/in total/total/altogether". Con una persona la lettura è `total`. Se il campo e il testo non coincidono vince il campo e il conflitto va nei log.
- **Regola 4.**
  - Una funzione pura in `chooser.py`, `cheapest_total(products, criteria, today, now)`, applica gli stessi filtri duri di `choose` senza prezzo e senza rifiuti. Metto a fattor comune la lista dei filtri, così le due funzioni non divergono.
  - `parse_intent` e `refine` ricevono un `cheapest_total` opzionale (un callable) e restano pure.
  - `usecases` passa il callable letto dal catalogo, e il catalogo si legge solo quando la regola 4 serve.
  - Quando nessun prodotto è compatibile, la lettura è `total`.
- **Campo `budget` senza `budget_scope`.** Passa anche lui dalla regola 4, come nell'esempio di UC-E (`budget=600, pax=3`). È un cambio di comportamento: oggi il campo è sempre un totale. Aggiorno la descrizione MCP e `docs/rest.md`.
- **`say` (RF-70).** La frase di `_describe` diventa "con un budget di 600 euro a persona, 1800 in tutto" oppure "con un budget di 600 euro in tutto" (in inglese "…per person, 1800 in total" / "…in total"). Sostituisce "budget massimo di X" in tutti i `say` di creazione e di rifiuto.
- **Superfici.** `budget_scope` entra in MCP e REST su creazione e rifiuto ed esce nei criteri. Aggiorno le descrizioni MCP di `budget` e `budget_scope`, `docs/rest.md`, `decisions.md` (con l'elenco dei test cambiati) e la riga di stato della spec.
- **Commit** in quest'ordine, ognuno in TDD: modello e validazione, parser, regola 4 in create, rifiuto, `say`, superfici, documenti.

## Tre decisioni che i documenti non coprono

1. **Nel rifiuto cambia il numero di persone e non c'è una cifra nuova, con lettura `per_person`** (es. "600 a testa" in 3, poi "siamo in 4"):
   - **A) Il totale si ricalcola, 600 × 4 = 2400 (raccomandata).** Il viaggiatore ha detto un budget a testa.
   - B) Il tetto resta 1800, come oggi.
2. **"Troppo caro" abbassa il budget all'80% del totale proposto:**
   - **A) La lettura diventa `total` (raccomandata).** La cifra non l'ha detta il viaggiatore e divisa a testa darebbe numeri come "186,67 a persona".
   - B) Resta `per_person`.
3. **`budget_scope` senza nessun budget:**
   - **A) Nessun effetto e niente nel `say` (raccomandata).** Non è un campo invalido, non c'è niente da leggere.
   - B) Si dichiara scartato.
   - Nel rifiuto, se l'intento ha già un budget, `budget_scope` da solo rilegge la cifra e ricalcola il tetto. Questo lo chiede UC-E.

## Una nota sulla forma

Le cifre restano senza separatore delle migliaia ("1800 euro"), come oggi fa `fmt_money`, non "1.800" come nell'esempio di UC-E. Per la voce è meglio. Se vuoi il separatore lo aggiungo, ma cambia tutte le frasi con importi.

Aspetto il tuo OK sulla regola 4 in `create_intent` e sui tre punti.

## Utente 12:44

<pasted_content id="70e2">
OK su tutto: regola 4 in create_intent (A), salvata nei criteri, ricalcolata nel rifiuto solo
con una cifra nuova. OK anche sull'approccio e sull'ordine dei commit.

Le tre decisioni:
1. A: con lettura per_person e numero di persone cambiato senza cifra nuova, il tetto si
   ricalcola (600 × 4 = 2400).
2. A: "troppo caro" porta la lettura a total.
3. A: budget_scope senza budget non ha effetto e non compare nel say; nel rifiuto, se l'intento
   ha già un budget, rilegge quella cifra e ricalcola il tetto, come chiede UC-E.

Precisazioni:
- Cifre senza separatore delle migliaia: ok, ma allinea l'esempio in docs/usecases/scelta.md
  (UC-E, "1.800" → "1800") così caso d'uso e test dicono la stessa cosa.
- Descrizione MCP di budget: l'agente passa la cifra così come l'ha detta il viaggiatore, senza
  moltiplicarla o dividerla per le persone, e passa budget_scope solo se il viaggiatore l'ha
  detto in modo esplicito. Stessa frase in docs/rest.md.
- cheapest_total: usa la stessa lettura del catalogo del chooser (in memoria o in cache), senza
  una query in più per ogni create_intent; se non è possibile, dimmelo prima di procedere.
  Aggiungi un test che dimostri che choose dà gli stessi risultati di prima dopo aver messo i
  filtri a fattor comune.
- Registra le tre decisioni e il cambio di comportamento del campo budget in decisions.md.

Procedi in TDD, fermati prima del merge su master.
</pasted_content id="70e2">

## Agente 12:44

Prima di scrivere codice verifico come il chooser legge il catalogo, perché la precisazione su `cheapest_total` dipende da questo.

- 🔧 Bash: Find product catalog reads and caching

- 🔧 Bash: Read Postgres product repo and decisions on catalog cache

- 🔧 Bash: Check whether an in-memory catalog cache exists

Mi fermo prima di scrivere codice, come mi avevi chiesto: **leggere il catalogo senza una query in più in `create_intent` non è possibile.**

## Cosa ho trovato

- **Non c'è una cache del catalogo.** `PostgresProductRepository.list_all()` (`vela/adapters/repo_postgres.py:77`) fa una `SELECT` a ogni chiamata. Il chooser la chiama a ogni `_propose`, cioè in `get_proposal` e `reject_proposal`. Il "catalogo in memoria per istanza (M14)" citato in `decisions.md` non è mai stato implementato.
- **Oggi `create_intent` non legge i prodotti.** Per la regola 4 serve per forza una lettura del catalogo che prima non c'era.
- **Nel rifiuto la query in più si evita.** `reject_proposal` legge già il catalogo in `_propose`: lo leggo una volta sola e lo passo sia alla regola 4 sia a `choose`.

## Opzioni per `create_intent`

- **A) Leggere il catalogo solo quando serve la regola 4 (raccomandata).** Serve solo con una cifra detta senza lettura esplicita, con più di una persona e senza `budget_scope`. È la stessa `list_all()` del chooser, senza la colonna `raw`, circa 200 righe. Tutti gli altri `create_intent` restano senza query.
- **B) Una cache del catalogo in memoria per ogni processo.** Si invaliderebbe con `last_fetched_at` o con un TTL. È un componente nuovo e cambia anche il chooser. `set_bookable` modifica i prodotti tra un sync e l'altro, quindi la cache andrebbe invalidata anche lì, e c'è il tema di RNF-01. Esce dallo scope di M21-E.
- **C) Il minimo con una query SQL mirata** (`MIN(price)` con i filtri). La scartei: il filtro sulle date passa da `departure()` in Python (finestre, durata, `minDate`/`maxDate`) e in SQL darebbe risultati diversi dal chooser.

Raccomando A: con B risolveremmo un problema di prestazioni che non abbiamo misurato, dentro una task che parla di budget. Se il costo di una `SELECT` in più per questi intenti conta per il load test, B può diventare una task a parte. Con il tuo OK su A la registro in `decisions.md` insieme alle altre tre decisioni e parto in TDD con l'ordine concordato.

## Utente 12:45

<pasted_content id="70e2">
OK su A: il catalogo si legge in create_intent solo quando serve la regola 4; nel rifiuto una
sola lettura condivisa tra regola 4 e choose. Niente cache in M21-E.

Registra in decisions.md, insieme alle altre tre decisioni:
- A e il motivo;
- la correzione: il "catalogo in memoria per istanza (M14)" citato nelle decisioni non esiste,
  list_all() fa una SELECT a ogni _propose; M14 non è stata fatta;
- la cache del catalogo come possibile task separata, da aprire solo se il load test dopo M21-E
  mostra una p95 REST peggiore di quella in loadtest/RESULTS.md.

Parti in TDD con l'ordine concordato e fermati prima del merge su master.
</pasted_content id="70e2">

## Agente 12:45

- 🔧 Skill superpowers:test-driven-development

Baseline suite first.

- 🔧 Bash: Run baseline test suite and lint

Green (1209 tests, 63 skipped without `DATABASE_URL`). Commit 1: model and validation. Let me look at the existing tests to match style.

- 🔧 Bash: Read model tests and intent test header

- 🔧 Bash: Locate validation and say tests

- 🔧 Bash: Read FieldsTest and say discarded tests

M21-A used dedicated test files; I'll follow that with `tests/test_budget_scope.py`. Checking the header style:

- 🔧 Bash: Read M21-A test file style

Now writing the first failing tests: `budget_scope` in the criteria JSON, in the structured fields, and its validation.

- 🔧 Bash: Write failing tests for budget_scope model and validation

Red for the right reasons. Adding the `say_discarded` sentence test too, then the implementation.

- 🔧 Bash: Implement budget_scope in model, validation and discarded say

Green. Full suite and lint, then commit 1.

- 🔧 Bash: Run suite, lint, commit model changes

- 🔧 Bash: Check which UC-E phrasings parse_budget reads today

- 🔧 Bash: Write failing parser tests for rules 1-3 and 5

Import error on `parse_budget_scope`, as expected. Implementing in `intent.py`:

- 🔧 Bash: Implement scope words, figure patterns and read_budget

Green. Full suite and lint:

- 🔧 Bash: Run full suite and lint

No existing test changed. Commit 2:

- 🔧 Bash: Commit parser rules

- 🔧 Bash: Read chooser fixture test and support helpers

- 🔧 Bash: List fixtures and loader

I'll generate the expected table from the current code (before any change to `chooser.py`) over the recorded padel and tennis catalogues, and paste it in as literals.

- 🔧 Bash: Generate choose results on the fixture grid

- 🔧 Bash: Inspect generated table

- 🔧 Bash: Generate full candidate orderings by exhausting rejections

Those five sequences cover 217 choices, every hard filter and both `now` modes. I'll write them into a new test file, which should pass on the current code, then the red `cheapest_total` tests.

- 🔧 Bash: Write characterization test for choose and run it

Pax 20 still finds a product (no `maxPax` on it). I'll use `sport` instead. `pax` and the other filters already have synthetic `NoChoice` tests in `test_chooser.py`; checking that:

- 🔧 Bash: Check existing NoChoice coverage

All eight filter names are already covered synthetically. I'll swap the pax case for sport:

- 🔧 Bash: Fix filter case and rerun characterization test

Green on the current code. I'll commit the safety net separately, before touching `chooser.py`:

- 🔧 Bash: Commit characterization test

Now the red tests for rule 4: `cheapest_total` in the chooser, the rule in `read_budget`, and its use in `create_intent`. Checking how the use-case tests build `Vela`:

- 🔧 Bash: Read use case test setup

- 🔧 Bash: Add failing cheapest_total tests

- 🔧 Bash: Run cheapest_total tests expecting failure

Red (import error, `cheapest_total` doesn't exist yet). Now the chooser refactor:

- 🔧 Bash: Factor out hard filters and add cheapest_total

- 🔧 Bash: Show errors

`support` needs `tests/` on the path; that's how the suite runs (discover with `-s tests`). Rerunning with discover and a pattern:

- 🔧 Bash: Run chooser tests via discover

- 🔧 Bash: Check test Clock

- 🔧 Bash: Add failing rule 4 tests

Red for the expected reasons. Implementing:

- 🔧 Bash: Implement rule 4 in read_budget, parse_intent and create_intent

Green. I'd added a `products` parameter to `_cheapest_total` that only the rejection needs; I'll remove it from this commit and bring it in with the rejection. Then full suite:

- 🔧 Bash: Simplify and run full suite

Green, and no existing test changed. Commit 3b:

- 🔧 Bash: Commit rule 4 in create_intent

Commit 4: the rejection. Tests on `refine` first (the pure function), then the single shared catalogue read in `reject_proposal`. Checking how the refine tests build a proposal:

- 🔧 Bash: Read refine test setup

- 🔧 Bash: Add failing rejection tests

- 🔧 Bash: Summarize failure reasons

- 🔧 Bash: Fix rejection single-read test expectation

Now the implementation in `refine.py` and `usecases.py`:

- 🔧 Bash: Implement budget reading on rejection with shared catalog read

Green. Full suite and lint:

- 🔧 Bash: Run full suite and lint

- 🔧 Bash: Inspect a refine test failure

- 🔧 Bash: Re-read budget only when needed and rerun suite

Green, with all 11 tests unchanged. I'll add a test that pins this case explicitly in the UC-E file, then commit:

- 🔧 Bash: Add regression test and commit rejection changes

Commit 5: the RF-70 sentence. Tests first in `test_say.py`, plus the `say` of `create_intent` and `reject_proposal` in the UC-E file:

- 🔧 Bash: Add failing RF-70 say tests

Red. Implementing in `say.py`:

- 🔧 Bash: Implement RF-70 sentence and run suite

- 🔧 Bash: Update UC7 expectation, run suite, commit say changes

Commit 6: MCP and REST surfaces. Looking at how M21-A tested the contract on both:

- 🔧 Bash: Read MCP and REST duration contract tests

- 🔧 Bash: Read MCP tool descriptions and signatures

Tests for both surfaces first:

- 🔧 Bash: Check imports and helpers in surface tests

- 🔧 Bash: Add failing MCP and REST contract tests

- 🔧 Bash: Fix assertion and show failure reasons

- 🔧 Bash: Make surface tests depend on the field and rerun

All red for the right reasons. Implementing the surfaces, with the `budget` description you specified:

- 🔧 Bash: Add budget_scope to MCP tools and REST body

`DESCRIPTIONS_SMS` inherits the two tool texts. Full suite and lint:

- 🔧 Bash: Run full suite and lint

- 🔧 Bash: Commit surface changes

Commit 7: documentation. Checking how M21-A recorded its status in the spec and roadmap, to do the same:

- 🔧 Bash: See how M21-A updated spec and roadmap

M21-A only updated the §4.12 status line and left the roadmap alone. I'll do the same, plus the RF-52 wording, since the `budget` field now carries the figure as said. Editing the docs:

- 🔧 Bash: Find doc lines to update

- 🔧 Bash: Update use case example and spec status

- 🔧 Bash: Update spec RF-52 and REST docs

- 🔧 Bash: Check load test results and the M14 claim

- 🔧 Bash: Find section containing the M14 claim

- 🔧 Bash: Write decisions section and REST row

- 🔧 Bash: Run suite, commit docs, list branch commits

UC-E è implementato su `task/m21e` in 8 commit, tutti in TDD. Mi fermo qui: niente merge su `master` e niente push finché non mi dai l'OK.

**Verifiche:** 1276 test verdi e ruff pulito. I 63 test Postgres sono saltati perché `DATABASE_URL` non è impostata. Non servono migrazioni (`budget_scope` sta nel JSON dei criteri), ma quei test non li ho eseguiti.

## Cosa fa adesso

- **Lettura del budget.** L'ordine è: campo `budget_scope`, poi le parole "a testa/each" o "in tutto/in total", poi la regola 4, e con una persona il budget è totale. Nei criteri `budget` resta il tetto sul totale, `budget_scope` registra come è stata letta la cifra.
- **Parser.** Legge anche forme che prima perdeva: "budget totale 1.500", "1,800 in total", "600 each". "Siamo 4 in tutto" resta un numero di persone e non diventa una lettura del budget.
- **Regola 4.** Si calcola in `create_intent` e il risultato si salva. Il catalogo si legge solo quando la regola serve, quindi gli altri intenti non fanno query in più (c'è un test che conta le letture). Nel rifiuto la regola 4 e `choose` usano una sola lettura del catalogo.
- **Filtri a fattor comune.** `choose` e il calcolo del viaggio più economico usano gli stessi filtri duri. Prima del refactor ho registrato con il chooser di allora 217 scelte in sequenza su cinque criteri delle fixture. Dopo il refactor sono identiche.
- **Rifiuto.** Le tue tre decisioni sono applicate: 600 a testa in 3 e poi "siamo in 4" dà 2400; "troppo caro" legge il tetto in totale; `budget_scope` senza budget non ha effetto.
- **Frase di RF-70.** Il `say` dice sempre come ha letto il budget, senza separatore delle migliaia: "con un budget di 600 euro a persona, 1800 in tutto" oppure "…di 600 euro in tutto".
- **MCP e REST.** Accettano `budget_scope` su creazione e rifiuto. La descrizione di `budget` usa la tua frase (cifra come detta, mai moltiplicata o divisa per le persone), ripetuta in `docs/rest.md`.
- **Documenti.** In `decisions.md` ci sono la regola 4, la lettura del catalogo, la correzione su M14, la cache come eventuale task separata, le tre decisioni e il cambio di comportamento del campo `budget`. Ho aggiornato anche RF-52, lo stato di §4.12 e l'esempio di UC-E.

**Test esistenti cambiati (elencati in `decisions.md`):**
- `test_models`: il dizionario dei criteri ha una chiave in più.
- `test_usecases_agent_tool` UC7: "budget massimo di 1000 euro" diventa "budget di 1000 euro in tutto". Controlla sempre la frase intera, e ora verifica anche che la regola 4 legga 1000 come totale.

## Decisioni prese strada facendo

- **Cifra senza valuta.** Prima di "in tutto" o "each" vale come budget solo sopra 20, perché "siamo 4 in tutto" parla delle persone.
- **Intenti salvati prima di M21-E.** La lettura assente vale "totale". Un rifiuto che non tocca né il budget né il numero di persone non riscrive i criteri, così un test esistente resta valido.
- **Conflitto tolto.** Se l'agente passa `budget=600` e il testo dice "600 euro a testa", nei log non compare più un conflitto: prima si confrontavano 1800 e 600.
- **Esempio di UC-E.** Ho tolto il separatore dal `say` e dal conto del server. Le frasi del viaggiatore restano con "1.800", che il parser legge.

## Su cosa non sono sicuro

- **Test di caratterizzazione.** Fissa l'ordinamento attuale, quindi M21-B dovrà aggiornare le sequenze (è scritto nel file).
- **"Total" è una parola larga.** In inglese "a total of 3 nights" verrebbe letta come lettura del budget totale. Conta solo se c'è una cifra e se il testo non dice anche "a testa", quindi l'effetto è limitato.
- **Test Postgres.** Se vuoi averli verdi prima del merge, lanciali su un database usa e getta.

## Utente 13:13

no mergia

## Agente 13:13

Non voglio indovinare su un merge: "no mergia" si può leggere in due modi.

- **"No, non mergiare":** lascio `task/m21e` com'è, con gli 8 commit, e non tocco `master`.
- **"No [ai test Postgres], mergia":** faccio il merge locale di `task/m21e` su `master` con un merge commit, come per le task precedenti (es. "Merge branch 'task/m21-durata'"). Poi rilancio suite e ruff su `master`, senza push.

Quale delle due?

## Utente 13:14

non lanciare test, mergia direttamente

## Agente 13:14

- 🔧 Bash: Find where master is checked out

`master` has moved since I branched (it's now at the merge of `doc/m22-hotel`). Checking what's new and that the `master` worktree is clean:

- 🔧 Bash: Check master worktree state and new commits

Worktree is clean. The new commits on `master` are M22 docs plus a probe script, and they may touch `decisions.md` and the spec too. Merging with a merge commit, as for the previous tasks:

- 🔧 Bash: Merge task/m21e into master

- 🔧 Bash: Locate conflict markers in decisions.md

Both branches appended a section at the end of `decisions.md`: M22-a on `master`, M21-E on the branch. No text overlaps. I'll keep both, M22-a first, then M21-E:

- 🔧 Bash: Resolve conflict keeping both sections

Resolved: both sections kept in date order, no markers left. Committing the merge (no tests, as you asked, and no push):

- 🔧 Bash: Commit the merge
