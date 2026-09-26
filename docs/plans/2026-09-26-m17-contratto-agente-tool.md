# M17 — Contratto agente-tool e sinonimi dello sport

## Contesto

Il 2026-09-26, in claude.ai, un viaggiatore ha rifiutato una proposta ("troppo caldo, vorrei un
posto più freddo"). L'agente ha chiamato un nuovo `create_intent` invece di `reject_proposal`, e
il chooser deterministico ha riproposto lo stesso prodotto. Nessuno ha mai chiesto lo sport.
M17 fa questo:
- aggiunge campi strutturati a `create_intent`/`reject_proposal` (MCP e REST);
- applica la precedenza campo > parser > Haiku;
- chiede sempre lo sport, e `any` vale come risposta;
- fa ripetere al `say` i criteri capiti;
- corregge le descrizioni dei tool;
- aggiunge i sinonimi dello sport.

Fonti: `docs/spec.md` §4.11 (RF-52..55), RF-01..04, RF-08, RF-09, RF-39..42;
`docs/usecases/agente-tool.md` (UC1-UC9); `docs/decisions.md` 2026-09-26; roadmap M17.

**Stato del branch:** `task/m17` non ha commit propri. È 10 commit dietro `master`, e i documenti
di M17 (72dff4f) sono solo su `master`. Primo passo: `git merge --ff-only master`, che non
riscrive la storia.

**Vincoli:** non toccare i file di M10: sync, `hofj*`, `schema.py`, fixture, migrazioni. Nessuna
chiamata ad Anthropic, né nei test (client finto) né altrove: **0 chiamate Haiku reali
previste**. Una sola task alla volta, con un resoconto alla fine di ciascuna.

## Decisioni chiuse nel brainstorm (da registrare in `docs/decisions.md`)

| Tema | Scelta |
|---|---|
| Sinonimi | Dizionario fisso in `intent.py`: "terra rossa", "terrarossa", "clay" → tennis; "paddle", "pádel", "weebora" → padel. Haiku resta la riserva quando lo sport manca ancora, e il suo prompt conosce gli stessi sinonimi |
| "padel e tennis" | Entrambi gli sport nel testo → `any`. Frasi di indifferenza ("indifferente", "tutti e due", "entrambi", "non importa", "either", "both sports", "doesn't matter") → `any` |
| beach/paddle tennis | Esclusioni controllate prima dei sinonimi → sport non riconosciuto → domanda. Anche il prompt di Haiku dice di restituire null per questi casi |
| Tornei | Fuori da M17. Li risolve l'agente con il campo `sport`, e Haiku fa da riserva |
| "più fresco/freddo", "cooler" / "più caldo", "warmer" | `refine.py` li traduce in north/south (rete di sicurezza per i client solo testo) |
| id dopo `no_match` da rifiuto | Nuovo campo `rejected_proposal_id` in `NoMatch`, presente solo quando il no_match arriva da `reject_proposal` |

Decisioni di dettaglio che prendo io (da registrare, correggibili):
- **Tipi dei campi:** `sport`, `area`, `direction`, `period_*` sono stringhe libere nello schema
  MCP/REST, non `Literal`. Un valore invalido viene scartato e dichiarato (RF-53), invece di
  diventare un errore di validazione. `pax` è un intero e `budget` un numero; un tipo JSON
  sbagliato resta un 422 o un errore MCP.
- **Periodo:** servono sia `period_start` sia `period_end`. Una sola delle due date → periodo
  scartato e dichiarato. Validazione come l'attuale `_llm_overrides`: inizio ≤ fine, fine ≥ oggi.
- **`pax` MCP:** l'argomento `pax` di `create_intent` esiste già e oggi va nel profilo. Diventa il
  campo strutturato di RF-52, quindi vince sul testo. Su REST `profile.pax` resta il default più
  basso e `pax` al primo livello è il campo.
- **Haiku:** parte quando manca lo sport dopo campi e parser (RF-03, non più "sport e periodo").
  Riempie solo i criteri ancora vuoti; oggi invece sovrascrive quelli del parser.
- **`say` del rifiuto:** [annullato ordine] + [campi scartati] + [motivo non traducibile, solo
  se il motivo non è vuoto e nulla è cambiato] + "Ho capito: …." + proposta o no_match.
- **Frasi di no_match:** "prova a riformulare la richiesta" diventa "dimmi cosa vuoi cambiare"
  (it/en), per non spingere l'agente verso un nuovo `create_intent` (RF-09).

## Progetto

### Dominio
- **`vela/domain/models.py`**
  - Nuovo `StructuredFields` (frozen): `sport`, `area`, `period_start`, `period_end`, `pax`,
    `budget`, `direction`, tutti opzionali e grezzi.
  - `NoMatch.rejected_proposal_id: Optional[str] = None`, emesso in `to_dict` solo se presente.
- **`vela/domain/intent.py`**
  - `parse_sport`: prima le esclusioni (beach/paddle tennis), poi le frasi di indifferenza e i
    due sport → `any`, poi i sinonimi, poi `padel|tennis`. `refine` lo importa già, quindi
    anche i rifiuti ereditano sinonimi e `any`.
  - `_llm_overrides` diventa `validate_fields(raw, today) -> (valid: dict, discarded: list)`,
    usata sia dai campi strutturati sia da Haiku (con `any` ammesso). È il riuso dell'attuale
    validatore.
  - `parse_intent(text, profile, today, extractor, fields=None)` segue questo ordine:
    1. parser;
    2. campi validi sovrascrivono, con conflitti raccolti;
    3. Haiku solo se `sport` è None, e riempie solo i None;
    4. pax = campo > testo > `profile.pax`.
  - `ParseResult` guadagna `discarded` e `conflicts`.
  - Domande: `QUESTION_SPORT` = "Padel o tennis?" / "Padel or tennis?", poi `QUESTION_PAX`.
    Rimossi `QUESTION_SPORT_OR_PERIOD(_EN)`.
- **`vela/domain/refine.py`**
  - `_NORTH`/`_SOUTH` più "più fresco/freddo", "cooler/colder", "più caldo", "warmer/hotter".
  - `refine(..., fields=None, direction=None)` restituisce un `Refinement(criteria, discarded,
    conflicts, understood)`. Ordine: regole del testo, poi `direction` del campo (sostituisce
    quella del testo; se `geo.move` restituisce None la direzione è scartata), poi `area` del
    campo (vince su `direction`, con conflitto), poi gli altri campi.
- **`vela/domain/chooser.py`**: una riga, `criteria.sport in (None, "any")`. M10 non tocca
  questo file.
- **`vela/domain/say.py`**
  - `_describe(c)` estratto da `say_intent_created`, con `any` → "padel o tennis" / "padel or
    tennis".
  - Nuove `say_understood(c)`, `say_discarded(items, lang)` (frase per campo, es. "Non conosco
    il luogo Atlantide, cerco ovunque.") e `say_untranslatable(lang)`.
  - Testi di no_match aggiornati.
- **`vela/domain/usecases.py`**
  - `create_intent(text, profile, fields=None)`: logga i conflitti con l'id dell'intento
    (logger `vela.domain.usecases`, mai il testo) e mette gli scartati nel `say`.
  - `reject_proposal(proposal_id, reason, fields=None, direction=None)`: il doppio rifiuto è già
    un no-op. Nel repository in memoria `setdefault`, su Postgres `on_conflict_do_nothing`: non
    cambia niente, lo copre un test. Il `NoMatch` porta `rejected_proposal_id=proposal.id`.

### Superfici
- **`vela/adapters/haiku.py`**: enum `sport` con `"any"`. Il SYSTEM aggiunge sinonimi, `any` e
  l'esclusione di beach/paddle tennis.
- **`vela/surfaces/mcp.py`**
  - Argomenti nuovi, con descrizione: `create_intent` +sport, area, period_start, period_end,
    budget (pax già c'è); `reject_proposal` +tutti i campi e direction.
  - `INSTRUCTIONS` e `DESCRIPTIONS` riscritti per RF-41:
    - chiedere lo sport prima di `create_intent`;
    - passare i campi capiti;
    - dopo una proposta, ogni cambiamento va su `reject_proposal`;
    - "più fresco" → north, "più caldo" → south;
    - no_match con `rejected_proposal_id` → `reject_proposal` su quell'id;
    - nessun invito a riformulare.
- **`vela/surfaces/rest.py`**: `IntentIn` e `RejectIn` con gli stessi campi.
- **`docs/rest.md`**: aggiornato con il contratto.

## Task (TDD, un commit per task, resoconto dopo ciascuna)

0. `git merge --ff-only master`, poi `docs/plans/2026-09-26-m17-contratto-agente-tool.md` (questo
   piano) e le decisioni in `docs/decisions.md`. Commit.
1. Parser dello sport: esclusioni, `any`, sinonimi (tabelle in `tests/test_intent.py`).
2. `validate_fields` + nuova RF-04 + precedenza campo > parser > Haiku (client finto). I test
   "sport oppure periodo" vengono aggiornati ed elencati in `decisions.md`.
3. `refine`: cooler/warmer, `direction` e campi, `Refinement` (`tests/test_refine.py`).
4. `chooser` `any` + `say` (`_describe`, understood, discarded, untranslatable, no_match).
5. `usecases`: campi, log dei conflitti (`assertLogs`), `rejected_proposal_id`, secondo rifiuto.
   UC1-UC9 in `tests/test_usecases_agent_tool.py` con repository in memoria e prodotti costruiti
   nel test (nessuna fixture toccata).
6. Haiku: schema `any` e prompt (`tests/test_haiku.py`, client finto).
7. MCP: argomenti, descrizioni, UC1/UC4/UC7/UC8 in `test_mcp_tools`, e un test che nessuna
   descrizione inviti a riformulare con `create_intent`.
8. REST: modelli, UC1/UC4/UC7/UC8 in `test_rest`, `docs/rest.md`.
9. Chiusura: suite completa, riga in `docs/acceptance.md` per il test manuale UC4 in claude.ai
   (lo esegui tu), decisioni prese durante l'esecuzione in `docs/decisions.md`.

## Verifica
- `python3 -m unittest discover -s tests`: verde. I test Postgres vengono saltati senza
  `DATABASE_URL`, come nelle task precedenti.
- UC4: dopo "troppo caldo" con `direction=north`, stesso `intent_id` e prodotto diverso da quello
  rifiutato.
- Manuale (tuo): il dialogo del 2026-09-26 ripetuto in replay da claude.ai.

## Dubbi aperti (da segnalare, non bloccanti)
- `usecases.py` è un file che M10 potrebbe toccare: possibile conflitto al merge.
- Il fallback Haiku parte più spesso (ogni volta che manca lo sport): più latenza e più costo in
  live. L'interruttore di RNF-12 resta com'è.
- Un "indifferente" riferito ad altro ("la data è indifferente") diventa `any`. Il `say` lo
  rende visibile e il viaggiatore può correggere.
- Rifiutare una proposta vecchia mentre ne esiste una più recente aperta restituisce quella
  aperta: caso fuori da RF-55, non lo cambio.
