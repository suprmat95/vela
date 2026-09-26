# Task durata viaggio M21

- Sessione: `55017c4c-a8f8-487a-87b0-9a5538c138c1`
- Inizio: 2026-09-26 19:25

## Utente 19:25

<pasted_content id="7e63">
Worktree `task/m21-durata` da `master`. Leggi `docs/usecases/scelta.md` (UC-A), gli RF
corrispondenti in `docs/spec.md` e il task in `docs/roadmap.md` (M21). Un solo task: la
durata del viaggio come criterio morbido. TDD, come sempre.

Cosa deve cambiare:
- `Criteria` (vela/domain/models.py): `duration_min_nights: Optional[int]`,
  `duration_max_nights: Optional[int]`.
- `intent.py`: regole it/en per "weekend" (2-3 notti), "ponte" (3-4), "una settimana" (6-8),
  "due settimane", "N giorni"/"N notti"/"N days"/"N nights", "lungo weekend". Campo
  strutturato dell'agente `duration_min_nights`/`duration_max_nights` che vince sul testo.
- `chooser.py`: la durata NON è un filtro duro. Calcola le notti effettive della finestra
  scelta da `departure` (end - start); `duration_ok` entra nella chiave di ordinamento subito
  dopo "entro budget"; `Choice` porta `nights: int` e `duration_ok: bool`; `_reason` aggiunge
  la frase quando la durata non è rispettata ("Non ho weekend compatibili: questo dura 5
  notti, dal 9 al 14 ottobre" / "I have no weekend trips: this one is 5 nights…").
- `refine.py`: nel rifiuto, "troppo lungo"/"troppo corto"/"too long"/"too short" e le stesse
  espressioni di durata aggiornano i criteri.
- `say`: la ripetizione dell'intento ("Ho capito: …") include la durata quando c'è.
- MCP (`vela/surfaces/mcp.py`) e REST: i due nuovi parametri opzionali su create_intent e
  reject_proposal, con descrizione per l'agente. Aggiorna `docs/api/` e le descrizioni dei
  tool.

Vincoli: nessuna migrazione (i criteri sono già serializzati come JSON? verifica; se serve
una migrazione fermati e chiedi). Non cambiare l'ordine dei filtri esistenti. Tutti i test
attuali devono restare verdi; aggiungi test in tests/ per parser (it/en), chooser
(preferenza, frase, weekend vs 7 notti), refine, MCP e REST usando `assert_single_product`.

Prima di scrivere codice, proponimi l'approccio in poche righe (in particolare la tabella
parola → notti e dove va la frase nel `say`) e aspetta il mio OK. Alla fine: cosa hai fatto,
cosa hai deciso, cosa non ti convince; decisioni in docs/decisions.md; commit piccoli.
</pasted_content id="7e63">

## Agente 19:25

I'll start by reading the use case, the spec, the roadmap and the code involved, then propose the approach.

- 🔧 Bash: Read UC-A use case and M21 roadmap

- 🔧 Bash: Locate spec RFs and file sizes

- 🔧 Bash: Read spec 4.12 and M21 roadmap section

- 🔧 Bash: Read chooser, refine and Criteria

- 🔧 Bash: Scan intent.py and criteria persistence

- 🔧 Bash: Scan say.py and surfaces for duration

- 🔧 Bash: Read say describe/proposal and intent weekend/validation

- 🔧 Bash: Read MCP/REST surfaces, docs/rest.md and test helper

- 🔧 Bash: Check weekend regex, tests and decisions on duration

Ho letto UC-A, spec §4.12 (RF-58/59), roadmap M21-A, `decisions.md` ("Scelta v3") e il codice coinvolto. Prima dell'approccio ci sono tre punti in cui il tuo prompt e i documenti non coincidono: decidili tu.

## Da decidere

**1. Tabella parola → notti.** Il prompt dice weekend 2-3 e ponte 3-4. Spec RF-58, UC-A e `decisions.md` dicono weekend 1..3 e ponte/long weekend 2..4.
Consiglio di seguire i documenti, perché sono già decisioni accettate. Aggiungerei le voci del prompt che mancano:

| Frase (it / en) | min | max |
|---|---|---|
| weekend, fine settimana / weekend | 1 | 3 |
| ponte, lungo weekend, weekend lungo / long weekend | 2 | 4 |
| una settimana / a week, one week | 6 | 8 |
| due settimane / two weeks *(nuova)* | 13 | 15 |
| N giorni / N days | N−1 | N−1 |
| N notti / N nights | N | N |
| N-M notti, N o M notti, da N a M notti / N to M nights | N | M |
| almeno N notti / at least N nights | N | — |

Le regole più specifiche vincono ("lungo weekend" prima di "weekend"). "Prima settimana di ottobre" e "fine settimana" non contano come "una settimana". N si legge con `_to_int`, quindi funziona anche "cinque giorni".

**2. "Weekend" come periodo.** Il prompt non ne parla, ma la roadmap M21-A lo mette nello scope. La regola: "un weekend" / "a weekend" diventa solo durata, mentre "questo/prossimo weekend" e "this/next weekend" restano anche periodo.
- Il test esistente `"padel weekend, x2, 600€"` si aspetta il periodo del prossimo weekend. Consiglio di togliere il periodo solo quando c'è l'articolo indeterminato (anche in "un weekend di padel"), come dice UC-A. Quel test resta verde.

**3. `nights` nella risposta `proposal`.** La roadmap lo prevede, il prompt no. È un campo in più nell'interfaccia pubblica, calcolato da `end_date - start_date`, senza schema. Consiglio di aggiungerlo, ma serve il tuo OK.

## Approccio (TDD, un commit per passo)

1. **`models.py` e `intent.py`**
   - `Criteria` riceve `duration_min_nights` e `duration_max_nights`.
   - `criteria_to_dict` / `from_dict` usano `.get`. `intents.criteria` è una colonna `JSON`, quindi **non serve una migrazione** e le righe vecchie si leggono con `None`.
   - `StructuredFields` riceve i due campi.
   - `validate_fields` accetta interi da 1 a 30 con min ≤ max, anche uno solo. Un valore invalido scarta la coppia come `("duration", (min, max))` e va nel `say` (RF-53). Il campo vince sul testo e il conflitto finisce nei log.
2. **`chooser.py`**
   - I filtri restano identici.
   - Notti = `(end - start).days` della finestra calcolata da `departure`.
   - `duration_ok`: vero se non è chiesta una durata, altrimenti se le notti cadono in [min, max].
   - La chiave di ordinamento diventa `(-area, not within_budget, not duration_ok, price, id)`.
   - `Choice` riceve `nights` e `duration_ok`.
   - Prodotti senza `duration_days`: le notti sono la lunghezza della finestra (opzione A della roadmap). Nelle fixture comunque non ce ne sono.
3. **Frase in `_reason`**: si aggiunge tra la frase dell'area e quella di date/budget, solo quando `duration_ok` è falso.
   - it: "Non ho weekend compatibili: questo dura 5 notti, dal 9 al 14 ottobre."
   - en: "I have no weekend trips: this one is 5 nights, from 9 to 14 October."
   - Il nome del viaggio dipende dall'intervallo: 1..3 → "weekend", 6..8 → "viaggi di una settimana", altrimenti "viaggi da N a M notti", "di N notti" o "di almeno N notti".
4. **`say` "Ho capito"**: la durata va subito dopo il periodo e prima delle persone, come nell'esempio di UC-A: "…in Spagna a ottobre, da 1 a 3 notti, per 2 persone".
   - Forme: "3 notti", "almeno 3 notti", "al massimo 3 notti".
   - en: "1 to 3 nights", "at least…", "at most…".
5. **`refine.py`**
   - Le espressioni di durata nel motivo aggiornano i criteri, e i campi strutturati vincono.
   - "troppo lungo" / "too long" con n notti proposte: max = n−1, e il min si abbassa se serve (non sotto 1).
   - "troppo corto" / "too short": min = n+1, e il max si alza se serve (non sopra 30).
   - Una durata letta così conta come `understood`.
6. **MCP e REST**
   - `duration_min_nights` e `duration_max_nights`, opzionali, su `create_intent` e `reject_proposal`.
   - Descrizione per l'agente: "weekend = 1..3, a week = 6..8, N days = N−1 nights".
   - Su REST un tipo sbagliato dà 422.
   - Test con `assert_single_product`.
7. **Documenti**
   - Il prompt dice `docs/api/`, ma quella cartella documenta l'API di HofJ. Il contratto REST sta in `docs/rest.md`, quindi aggiorno quello, più le descrizioni MCP.
   - Le decisioni vanno in `docs/decisions.md`.

Per iniziare creo il worktree `task/m21-durata` da `master`. Nessuna chiamata a servizi esterni.

Mi servono le tue risposte su 1, 2 e 3, e l'OK per partire.

## Utente 19:27

si a tutte e tre vai

## Agente 19:27

- 🔧 Skill superpowers:test-driven-development

- 🔧 Bash: Create worktree and run baseline tests

Baseline green (1129 tests, 63 skipped). Step 1: parser and criteria. Let me read the rest of `intent.py` and the models.

- 🔧 Bash: Read intent.py head and models

- 🔧 Bash: Inspect test_intent and test_models structure

Starting with the test for criteria serialization, then the parser. First the tests (RED):

- 🔧 Bash: Read criteria round-trip tests

- 🔧 Bash: Add criteria duration round-trip tests and run

RED as expected. Now the parser tests (it/en), in a new file:

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/m21-durata/tests/test_intent_duration.py

- 🔧 Bash: Run new parser tests expecting failure

RED (`parse_duration` doesn't exist). Implementation: models first.

- 🔧 Bash: Add duration fields to Criteria and StructuredFields

- 🔧 Bash: Check positional uses of Criteria/StructuredFields

One test builds `Criteria` positionally with `language` sixth: I'll put the new fields after `language`, so positional calls stay compatible.

- 🔧 Bash: Reorder Criteria fields and run model tests

Now `intent.py`: `parse_duration`, weekend with an article no longer a period, "N nights/days" no longer read as people, validation of the fields.

- 🔧 Bash: Implement duration parsing in intent.py and run tests

Parser green. Full suite and lint before the first commit:

- 🔧 Bash: Run full test suite and ruff

- 🔧 Bash: Commit parser and criteria changes

Step 2: chooser. Let me look at the helpers in the existing tests.

- 🔧 Bash: Read chooser tests and Product model

- 🔧 Bash: Read make_product helper and reason tests

- 🔧 Bash: Read say.py date helpers and reason tests

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/m21-durata/tests/test_chooser_duration.py

- 🔧 Bash: Run chooser duration tests expecting failures

- 🔧 Bash: Show the import error

Parser committed; I'm on the chooser tests now (the error was just how the module is launched: `support` only resolves with `discover -s tests`).

- 🔧 Bash: Run chooser duration tests via discover

RED for the right reasons. Implementing: date/night formatting in `say.py` (where the date helpers already live), preference and reason sentence in `chooser.py`.

- 🔧 Bash: Implement duration preference and reason in chooser

- 🔧 Bash: Fix wording in test, simplify label, run suite
