# m5-hofj-async-purchase-booking

- Sessione: `4e77c5e2-1cbd-49a4-a46b-71f152659842`
- Inizio: 2026-09-25 17:56

## Utente 17:56

Leggi la task m8 in docs/roadmap.md. Obiettivo: intervistami e scrivi il
          piano di esecuzione in un file in docs/plans/ Il piano dovrà indicare i microtask e i test che
      coprono il codice prodotto. Dopodiché lancerò l'esecuzione del piano

Leggi la task m5 in docs/roadmap.md. Obiettivo: intervistami e scrivi il
          piano di esecuzione in un file in docs/plans/ Il piano dovrà indicare i microtask e i test che
      coprono il codice prodotto. Dopodiché lancerò l'esecuzione del piano

## Agente 17:56

- 🔧 Bash: Read M5 task in roadmap and list docs

- 🔧 Bash: Read rest of M5 and repo overview

- 🔧 Agent: Summarize M5 spec requirements

- 🔧 Agent: Map current domain code

- 🔧 Agent: Study previous plan format

Ho letto M5 nella roadmap e ho avviato tre esplorazioni in parallelo: requisiti di spec e decisioni, codice attuale del dominio, formato dei piani precedenti. Ti intervisto appena tornano i risultati.

## Utente 17:57

/superpowers:brainstorming: ❯ Leggi la task m5 in docs/roadmap.md. Obiettivo: intervistami e scrivi il
            piano di esecuzione in un file in docs/plans/ Il piano dovrà indicare i microtask e i test che
        coprono il codice prodotto. Dopodiché lancerò l'esecuzione del piano

## Agente 17:57

Sto usando il brainstorming per condurre l'intervista su M5.

**Classificazione: architetturale.** M5 cambia il contratto di `accept_proposal` (da sincrono ad asincrono), aggiunge una migrazione (`0003`, tabella `jobs` e contatori della quota), sostituisce `BookingRunner` con un worker e introduce l'adapter HTTP verso HofJ. Quindi farò il percorso completo: domande una alla volta, 2-3 approcci con una raccomandazione, design a sezioni. Poi scrivo il piano con microtask e test in `docs/plans/`, come i piani M0–M4 e M11, invece di una spec separata.

Le tre esplorazioni sono ancora in corso: requisiti di spec e decisioni, codice attuale, formato dei piani precedenti. Faccio la prima domanda quando tornano, così parte dai documenti e dal codice reali.

## Utente 17:58

<task-notification>
<task-id>a10800cc5ebcd28bc</task-id>
<tool-use-id>toolu_01LvWdviJiTaD5iYiG7NCZS3</tool-use-id>
<output-file>/private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-task-m5/4e77c5e2-1cbd-49a4-a46b-71f152659842/tasks/a10800cc5ebcd28bc.output</output-file>
<status>completed</status>
<summary>Agent "Study previous plan format" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>The three plans (M2, M3, M4) share one template. They are written in Italian, and only the code, commit messages and the agent header line are in English. Each plan includes the full code and the full tests, lists test names, and ends every task with a literal commit step.

## Commits and whether they touched decisions.md

| Plan | Commit | Files in that commit | Touched `docs/decisions.md`? |
|---|---|---|---|
| M2 `2026-09-25-m2-dominio-replay.md` (4299 lines) | `bc1335d` 16:06 "Add the M2 execution plan: domain, use cases and replay mode" | plan + agent-log `.md`/`.jsonl` | **No**. The decisions were added separately in `71c5770` 16:10 "Record the M2 interview decisions". |
| M3 `2026-09-25-m3-superficie-mcp.md` (1184 lines) | `d5da128` 16:59 "Add the M3 execution plan and record the interview decisions" | plan + decisions.md (+17) + agent-log `.md`/`.jsonl` | **Yes** |
| M4 `2026-09-25-m4-superficie-rest.md` (1312 lines) | `73ae0bf` 16:56 "Add the M4 execution plan and record the interview decisions" | plan + decisions.md (+17) + agent-log `.md`/`.jsonl` | **Yes** |

The agent-log files are named `agent-log/…-superpowers-brainstorming-leggi-la-task.{md,jsonl}` and were probably added to the commit by the hook. The M2 plan's own Task 0 says to commit the plan and decisions.md together, but that isn't what happened. M3 and M4 follow their Task 0. The M2 trailer is `Co-Authored-By: Claude Fable 5.1`, while M3 and M4 use `Claude Opus 5.5`.

## Plan skeleton

```markdown
# M&lt;N&gt; — &lt;Titolo&gt;: piano di esecuzione

&gt; **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m&lt;N&gt;`. Destinazione di questo file: `docs/plans/2026-09-25-m&lt;N&gt;-&lt;slug&gt;.md`.

**Goal:** &lt;una frase: cosa funziona alla fine, con i RF citati&gt;

**Architecture:** &lt;paragrafo: file/moduli nuovi, come si collegano, cosa NON cambia&gt;

**Tech Stack:** Python 3.12 (`uv run python`), ..., `unittest`. Nessuna dipendenza nuova.

**Spec:** `docs/spec.md` (RF-.., §..), `docs/roadmap.md` sezione M&lt;N&gt;, &lt;altri piani/doc&gt;. Il design approvato nell'intervista è la sezione "Design" qui sotto.

## Contesto
- Esiste già: ... (classi, funzioni, helper di test con i nomi esatti)
- Verifiche/sonde fatte prima del piano (comportamenti di librerie verificati)
- Interprete: `uv run python` (3.12). Il `python3` di sistema è 3.7. Suite di partenza: N test, K skipped, verde.
- Task parallele che toccano gli stessi file → chi arriva secondo fa rebase.

## Decisioni prese nell'intervista (da riportare in `docs/decisions.md`, Task 0)
| Decisione | Scelta | Motivo |
|---|---|---|
| ... | ... | ... |

## Global Constraints
- Nessuna dipendenza nuova in `pyproject.toml`; nessuna modifica a `uv.lock`. Nessuna variabile d'ambiente nuova (spec §6).
- `uv run python -m unittest discover -s tests` verde senza servizi esterni e senza `DATABASE_URL`.
- Mai aprire, stampare o loggare `.env`, chiavi o token.
- &lt;invarianti di dominio: RF-10, to_dict() invariato, ecc.&gt;
- Commit piccoli, uno per task, messaggio imperativo in inglese come nella storia del repo, con `Co-Authored-By: ...`. Nessun force push.

## Review Focus
1. &lt;caso limite concreto&gt;. Test in Task X (`test_nome_esatto`).
2. ...

---

## Design
### Struttura dei file      (code block: path  + / NUOVO: descrizione)
### Contratto / Flusso dei dati / &lt;sottosezioni specifiche&gt;   (tabelle, JSON attesi)

---

### Task 0: Piano e decisioni nel repo
**Files:**
- Create: `docs/plans/...` (questo file)
- Modify: `docs/decisions.md` (in coda)
- [ ] **Step 1: Aggiungere in coda a `docs/decisions.md`** una sezione `## 2026-09-25 — M&lt;N&gt;: &lt;titolo&gt;` con la frase di origine (`Origine: intervista sulla macro task M&lt;N&gt;, piano in docs/plans/....`) e la tabella "Decisioni prese nell'intervista" di questo piano, copiata integralmente.
- [ ] **Step 2: Commit**   (bash block: git add ... ; git commit -m "Add the M&lt;N&gt; execution plan and record the interview decisions\n\nCo-Authored-By: ...")

---

### Task K: &lt;titolo&gt;
**Files:**
- Create/Modify: `...`
- Test: `tests/...`
**Interfaces:**
- Consumes: &lt;firme esatte usate da task precedenti&gt;
- Produces: &lt;firme esatte usate dai task successivi&gt;
- [ ] **Step 1: Scrivere il test (che fallisce)** ... (full python code)
- [ ] **Step 2: Eseguire e vedere il fallimento**
      Run: `uv run python -m unittest discover -s tests -p "test_x.py"`
      Expected: FAIL con `&lt;errore esatto&gt;`
- [ ] **Step 3: Implementare.** ... (full python code, exact insertion points)
- [ ] **Step 4: Eseguire i test**  Run: ... poi suite intera. Expected: PASS (...)
- [ ] **Step 5: Commit**  (bash block with git add &lt;file espliciti&gt; + messaggio inglese + Co-Authored-By)

---

### Task N-1: Documentazione, decisioni e verifica finale
  (README, doc della superficie, sezione "## 2026-09-25 — M&lt;N&gt;: decisioni prese durante l'esecuzione" in decisions.md con "Nessuna deviazione dal piano" + numero di test se nessuna; verifica finale: suite, suite con .env, git grep di import proibiti nel dominio, git diff master su domain/pyproject/uv.lock, git status)

### Task N (manuale, con l'utente, dopo il merge su `master`): &lt;criterio §10.x&gt;
  (Step (utente): ...; registrare esito in `docs/acceptance.md`; commit)

## Copertura dei test di completamento della roadmap M&lt;N&gt;
| Test di completamento (roadmap) | Dove |       (Task + nomi test/classi)

## Requisiti coperti
RF-.. (Task ..), RNF-.. (Task ..), §10.x (...).

## Fuori scope (task successive)
- &lt;cosa&gt; (M&lt;x&gt;): ...
```

Differences between the plans:
- **M3** calls its steps "Scrivere il test che fallisce" and "Eseguire e verificare che fallisca/passi". It uses "## Copertura" instead of the longer coverage heading, and adds "Flusso dei dati" and "Istruzioni e descrizioni" under Design.
- **M2** adds "Contratto di `to_dict()` (consumato da M3 e M4)" under Design. It has 13 tasks and separates code blocks with section-divider comments.
- **M4** also has "Contratto HTTP" tables and a "Flusso di una richiesta" section.

## Verbatim microtask excerpt (M4 Task 1, lines 158-228)

````markdown
### Task 1: `ProductRepository.last_fetched_at()`

**Files:**
- Modify: `vela/ports/repositories.py`, `vela/adapters/repo_memory.py`, `vela/adapters/repo_postgres.py`
- Test: `tests/repo_contract.py` (eseguito da `tests/test_repo_memory.py` sempre e da `tests/test_repo_postgres.py` con `DATABASE_URL`)

**Interfaces:**
- Consumes: `Product.fetched_at: datetime` (aware, UTC); `products_t.c.fetched_at` (`DateTime(timezone=True)`).
- Produces: `ProductRepository.last_fetched_at(self) -&gt; Optional[datetime]`: il `fetched_at` più recente, `None` con catalogo vuoto. Implementato da `MemoryProducts` e `PostgresProducts`.

- [ ] **Step 1: Scrivere il test nel contratto.** In `tests/repo_contract.py`, nella classe `RepositoryContract`, subito dopo `test_products_empty`, aggiungere:

```python
    def test_products_last_fetched_at(self):
        self.assertIsNone(self.repos.products.last_fetched_at())
        later = NOW + timedelta(hours=1)
        self.repos.products.upsert_many([make_product(1), replace(make_product(2), fetched_at=later)])
        self.assertEqual(self.repos.products.last_fetched_at(), later)
```

(`replace`, `timedelta`, `NOW` e `make_product` sono già importati nel file.)

- [ ] **Step 2: Eseguire e vedere il fallimento**

Run: `uv run python -m unittest discover -s tests -p "test_repo_memory.py" -k last_fetched_at`
Expected: FAIL con `AttributeError: 'MemoryProducts' object has no attribute 'last_fetched_at'`

- [ ] **Step 3: Implementare.** In `vela/ports/repositories.py` aggiungere `from datetime import datetime` ...
  [full code blocks for the port, memory and postgres implementations]

- [ ] **Step 4: Eseguire i test**

Run: `uv run python -m unittest discover -s tests -p "test_repo_*.py"`
Expected: PASS (Postgres skipped senza `DATABASE_URL`). ...

- [ ] **Step 5: Commit**

```bash
git add vela/ports/repositories.py vela/adapters/repo_memory.py vela/adapters/repo_postgres.py tests/repo_contract.py
git commit -m "Add last_fetched_at to the product repositories

Co-Authored-By: Claude Opus 5.5 &lt;noreply@anthropic.com&gt;"
```
````

## How decisions are recorded

**In the plan:** the section `## Decisioni prese nell'intervista (da riportare in \`docs/decisions.md\`, Task 0)` holds a three-column table, `| Decisione | Scelta | Motivo |`. Task 0 copies that table unchanged into decisions.md. Decisions made while carrying out the plan go into a second section, written in the last documentation task.

**In `docs/decisions.md`:** the file starts with `# Decisioni` and the line "Registro delle decisioni accettate. Formato: data, decisione, motivo." New sections are always added at the end. The format of one entry:

```markdown
## 2026-09-25 — M4: superficie REST

Origine: intervista sulla macro task M4, piano in `docs/plans/2026-09-25-m4-superficie-rest.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| `VELA_API_TOKEN` assente | L'app parte; ogni `/v1/*` risponde 503 `rest-not-configured` (7807). `/health` e `/replay` restano disponibili | Fail closed senza accesso aperto per errore, diagnosi chiara su Render, i test esistenti non cambiano |
| Endpoint sincroni | `def`, non `async def` | Il dominio è sincrono; FastAPI li esegue nel threadpool |
```

The execution section that follows looks like this:

```markdown
## 2026-09-25 — M4: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m4-superficie-rest.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| Suite finale | 319 test, 12 saltati (Postgres), verde (erano 271 a inizio M4) | — |
```

- **Heading:** `## YYYY-MM-DD — &lt;Mx&gt;: &lt;titolo&gt;`, with an em dash.
- **Origine line:** optional, and the M3 execution section has none.
- **Formatting inconsistency:** at line 231 of decisions.md, the M4 execution heading comes straight after the table with no blank line.

## Relevant files
- `/Users/matteodospina/orca/workspaces/vela/task-m5/docs/plans/2026-09-25-m4-superficie-rest.md`
- `/Users/matteodospina/orca/workspaces/vela/task-m5/docs/plans/2026-09-25-m3-superficie-mcp.md`
- `/Users/matteodospina/orca/workspaces/vela/task-m5/docs/plans/2026-09-25-m2-dominio-replay.md`
- `/Users/matteodospina/orca/workspaces/vela/task-m5/docs/decisions.md`</result>
<usage><subagent_tokens>84415</subagent_tokens><tool_uses>11</tool_uses><duration_ms>73371</duration_ms></usage>
</task-notification>

## Agente 17:58

Il formato dei piani precedenti è chiaro. Aspetto ancora le due esplorazioni sui requisiti e sul codice.

## Utente 17:59

<task-notification>
<task-id>a702c1b7bb64297d5</task-id>
<tool-use-id>toolu_01Fphsiry6vHsvCSoBUyHjw3</tool-use-id>
<output-file>/private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-task-m5/4e77c5e2-1cbd-49a4-a46b-71f152659842/tasks/a702c1b7bb64297d5.output</output-file>
<status>completed</status>
<summary>Agent "Map current domain code" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>Everything below is from the current worktree (HEAD `103908d Merge branch 'task/m11'`, working tree clean). Paths are relative to `/Users/matteodospina/orca/workspaces/vela/task-m5/`.

**Things that differ from what you expected**
- There is no `BookingRunner` in `vela/domain/orders.py`. It lives in `vela/adapters/background.py`, next to `InlineRunner`.
- There is no clock port. Time is injected as `now: Callable[[], datetime]`, and ids as `new_id: Callable[[], str]`.
- There is no checkout port. The replay "checkout" is a REST route, `GET /replay/checkout/{order_id}`.
- There is no errors module. The errors are `NotFound` (in `domain/orders.py`), `DuplicateOrder` (in `ports/repositories.py`), the `HofJError` family (in `ports/hofj.py`) and `Problem` (in `surfaces/problems.py`).
- `ProductRepository` has no method to mark a product non-bookable. The `bookable` fields exist, but only `upsert_many` writes them.
- The tests use `unittest`, not pytest. `CLAUDE.md` says to run them with `python3 -m unittest discover -s tests`, and pytest is not in the dependencies.
- `CLAUDE.md` asks for a proposed approach and an OK before implementing. It also asks you to check before changing public interfaces, the DB schema or core architecture. M5 touches all three.

---

## 1. Domain (`vela/domain`)

### `orders.py` (61 lines)
- Docstring (L1-6): `awaiting_payment` → `paid_pending_booking` (`mark_paid`) → `confirmed` | `booking_failed` (`complete_booking`). A transition from an unexpected state leaves the order unchanged. It says "Retry con backoff: M5".
- `class NotFound(Exception)` (L16-20): `__init__(self, kind: str, id: str)`, sets `.kind` and `.id`. It is re-exported by `usecases`.
- `class OrderService` (L23):
  - `__init__(self, repos: Repositories, hofj: HofJPort, now: Callable[[], datetime])` (L24)
  - `get(order_id) -&gt; Order`, raises `NotFound("order", …)` (L29)
  - `mark_paid(order_id, payment_ref) -&gt; Order`: only acts on `AWAITING_PAYMENT`; sets `payment_ref`, `paid_at` and `updated_at` (L35-43)
  - `complete_booking(order_id) -&gt; Order` (L45-58): only acts on `PAID_PENDING_BOOKING`. There is no retry or backoff: any `HofJError` goes straight to `BOOKING_FAILED`.
    ```python
    proof = PaymentProof(order.payment_ref or "", "succeeded")
    try:
        code = self.hofj.create_booking(order.itinerary_id, proof)
        order = replace(order, status=OrderStatus.CONFIRMED, booking_code=code, updated_at=self.now())
    except HofJError as exc:
        order = replace(order, status=OrderStatus.BOOKING_FAILED, failure_reason=str(exc), ...)
    ```
  - `pending_booking_ids() -&gt; List[str]` calls `repos.orders.ids_with_status(PAID_PENDING_BOOKING)` (L60)

### `vela/adapters/background.py` (the runners, 53 lines)
- `InlineRunner(orders)` (L15): `submit(order_id)` runs synchronously, `resume() -&gt; List[str]`, `shutdown(wait=True)` does nothing.
- `BookingRunner(orders, max_workers=2)` (L32): `ThreadPoolExecutor(thread_name_prefix="booking")`. `_run` logs and swallows exceptions, which leaves the order in `PAID_PENDING_BOOKING`. `resume()` submits every pending id. `shutdown(wait)`.

### `usecases.py` (158 lines): `class Vela`
- `__init__(self, repos, hofj: HofJPort, payments: PaymentsPort, defaults=None, now=None, new_id=None)` (L39). Defaults are `utcnow` and `random_id` (uuid4). It creates `self.orders = OrderService(repos, hofj, self.now)`.
- `create_intent(text, profile=None) -&gt; IntentCreated | IntentQuestion` (L52)
- `get_proposal(intent_id)` (L64) and `reject_proposal(proposal_id, reason)` (L70) both return `ProposalMade | NoMatch` and use `_propose` (L79).
  - Reject does not look at orders today. RF-49 (reject on a `queued` order cancels it) has to be added here.
- `_propose` (L79-95): reuses the last open, non-rejected proposal. Otherwise it calls `choose(products.list_all(), criteria, rejected_products, today=...)`.
- **`accept_proposal(proposal_id, traveler=None) -&gt; AcceptResponse | MissingTravelerData`** (L104-143). Current synchronous flow:
  1. Loads the proposal, or raises `NotFound`. If `orders.get_by_proposal` finds an existing order, returns `_accepted(existing)` (idempotent).
  2. Merges `intent.profile.merged_with(traveler)`. If `missing_fields(pax)` is non-empty, returns `MissingTravelerData`.
  3. Calls `hofj.create_itinerary(product, start_date, pax, 1, currency)`, then `set_customer(Customer(... + TravelerDefaults))`, then `get_pax`, then fills the names and calls `set_pax`.
  4. Builds `Order(... AWAITING_PAYMENT ..., itinerary_id=itinerary.id)` and calls `repos.orders.add`. On `DuplicateOrder` it returns the existing order.
  5. Calls `payments.create_payment_link(order)`, then saves with `payment_url` and `payment_ref`.
- `_accepted(order)` (L145-150): `estimate = price_from * pax`, `differs = total != estimate`, and the `say` comes from `say_accept`.
- `get_order_status(order_id) -&gt; OrderStatusResponse` (L154-158): returns `(id, status, booking_code, say_status(...))`.

### `models.py` (348 lines)
- **Intent side**
  - `Area`, `Period`, `Criteria(sport, area, period, pax, budget, language="it")` (L22-43), plus `criteria_to_dict` and `criteria_from_dict`.
  - `TravelerProfile(first_name, last_name, email, phone, pax, participants: tuple)` (L83), with `merged_with` and `missing_fields(pax)`, plus `profile_to_dict` and `profile_from_dict`.
  - `Intent(id, text, criteria, profile, created_at)` (L133).
- **`Product`** (L150-175) ends with:
  ```python
  bookable: bool = True
  bookable_checked_at: Optional[datetime] = None
  archived: bool = False
  provider_id: Optional[str] = None
  ```
- **`Proposal`** `(id, intent_id, product_id, start_date, end_date, pax, price_from, currency, reason, created_at)` (L181), with a `total_from` property.
- **`OrderStatus(str, Enum)`** (L198-203): `AWAITING_PAYMENT`, `PAID_PENDING_BOOKING`, `CONFIRMED`, `BOOKING_FAILED`, `EXPIRED`. There is no `queued`, `replaced`, `cancelled` or `failed` yet.
- **`Order`** (L207-225): `id, proposal_id, intent_id, product_id, status, pax, price_from, total, currency, traveler, created_at, updated_at`, then optional `itinerary_id, payment_url, payment_ref, booking_code, failure_reason, paid_at`.
  - Note that `total` is required. Under async accept it will not be known when the order is created.
- `Rejection` (L229) and `TravelerDefaults` (L238, a fixed street/city/IT address).
- **Response classes (`to_dict`)**
  - `AcceptResponse(order_id, status, total, currency, price_from_total, total_differs, payment_url, say)` (L310-325)
  - `MissingTravelerData(proposal_id, missing, say)` (L329)
  - `OrderStatusResponse(order_id, status, booking_code, say)` (L339-347)
  - `ProposalMade(proposal, product, say, replaced=False)` (L283). The `replaced` flag already exists.
  - `IntentCreated`, `IntentQuestion`, `NoMatch`
  - `money_str()` (L16) formats money as `"700.00"`.

### `say.py` (155 lines)
- Helpers: `fmt_date`, `on_date`, `fmt_money` (`"700 euro"`), `_people`, `_join`.
- Sentence builders:
  - `say_intent_created`, `say_proposal`, `say_no_match(criterion, criteria)` (uses the `_NO_MATCH` dict, which already covers `"bookable"`), `say_missing`
  - `say_accept(total, price_from_total, total_differs)` (L113) promises the payment link
  - `say_status(status, booking_code, failure_reason)` (L121-131): one branch per current status, with `EXPIRED` as the fall-through
  - `say_paid`, `say_not_found(kind)`, `say_unavailable`, `say_error`
- Rules (module docstring): no markdown and no URLs. The tests check that `"http"` and `"**"` never appear in `say`.

### Other domain modules
- `chooser.py`: `choose(products, criteria, rejected_ids, today) -&gt; Choice | NoChoice` (L154). The filter order is `archived`, `bookable` (`lambda p: p.bookable`), `trip`, `sport`, `dates`, `pax`, `rejected`. There is no 24-hour re-enable logic (RF-34).
- `catalog.py`: `load_fixture(path, fetched_at=None) -&gt; list[Product]` (L75). It always sets `bookable=True` and `bookable_checked_at=None` (L68-69). It also has `is_trip`.
- `intent.py`: `parse_intent(text, profile, today)` (L170) and `QUESTION_PAX`.

---

## 2. Ports (`vela/ports`)

### `hofj.py`
- Errors (L10-23): `HofJError`, with subclasses `ProductError` (RF-17), `QuotaError` (RF-37) and `UpstreamError` (network, timeout, 5xx).
- Dataclasses:
  - `Itinerary(id, total: Decimal, currency)`
  - `Customer(first_name, last_name, email, phone, street1, postal_code, city, region, country_code)`
  - `Pax(ref_id, first_name=None, last_name=None)`
  - `PaymentProof(payment_intent_id, payment_status, payment_type="full")`
- Protocol (L60-66):
  ```python
  class HofJPort(Protocol):
      def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int, currency: str) -&gt; Itinerary: ...
      def set_customer(self, itinerary_id: str, customer: Customer) -&gt; None: ...
      def get_pax(self, itinerary_id: str) -&gt; List[Pax]: ...
      def set_pax(self, itinerary_id: str, pax: List[Pax]) -&gt; None: ...
      def create_booking(self, itinerary_id: str, proof: PaymentProof) -&gt; str: ...
  ```
  There is no separate "read the real total" call. The total comes back from `create_itinerary`, but RF-46 lists reading the total as its own step. There are no quota or `get_quota` methods either.

### `payments.py`
- `PaymentLink(url, expires_at: datetime, reference)` and `PaymentsPort.create_payment_link(self, order: Order) -&gt; PaymentLink`.

### `repositories.py`
```python
class DuplicateOrder(Exception)
class ProductRepository(Protocol):   upsert_many(products: Iterable[Product]) -&gt; None; count() -&gt; int; list_all() -&gt; List[Product]; get(product_id) -&gt; Optional[Product]; last_fetched_at() -&gt; Optional[datetime]
class IntentRepository(Protocol):    add(intent) -&gt; None; get(intent_id) -&gt; Optional[Intent]
class ProposalRepository(Protocol):  add(proposal); get(proposal_id); list_for_intent(intent_id) -&gt; List[Proposal]
class OrderRepository(Protocol):     add(order); get(order_id); get_by_proposal(proposal_id); save(order); ids_with_status(status: OrderStatus) -&gt; List[str]
class RejectionRepository(Protocol): add(rejection); product_ids_for_intent(intent_id) -&gt; Set[str]; proposal_ids_for_intent(intent_id) -&gt; Set[str]
class Repositories(Protocol): products, intents, proposals, orders, rejections
```
There are no jobs or quota repositories.

---

## 3. Adapters (`vela/adapters`)

### `hofj_replay.py`: `ReplayHofJ(catalog_path=FIXTURE_PATH, rng=None)`
- `load_catalog()` calls `load_fixture`.
- Itineraries are held in memory as `it-replay-&lt;hex&gt;`, with `total = price * adults`.
- `_get` raises `UpstreamError` for an unknown itinerary.
- `create_booking` accepts any id that starts with `it-replay-`, even after a restart. The code is `R-%06d`, idempotent per itinerary (`_codes`).
- There is no simulated latency or quota yet. The roadmap asks for both, configurable and defaulting to zero and unlimited.

### `stripe_fake.py`: `FakePayments(public_url=None, now=None)`
- The link is `{base}/replay/checkout/{order.id}`, expires after `LINK_TTL = 24h`, with reference `pi_replay_{id}`.

### `repo_memory.py`: `MemoryRepositories`
- Has a `clear()`.
- `MemoryOrders` uses a `threading.Lock`; `add` raises `DuplicateOrder` when the same `proposal_id` already has an order.
- `ids_with_status` returns sorted ids.

### `repo_postgres.py`: `PostgresRepositories(engine)`
- SQLAlchemy Core with one transaction per method.
- `PostgresProducts.upsert_many` uses `pg_insert().on_conflict_do_update` (Postgres-only). `list_all` leaves out `raw`; `get` includes it.
- `PostgresOrders.add` (L156) maps an `IntegrityError` whose message contains `"uq_orders_proposal_id"` to `DuplicateOrder`. `save` does an `UPDATE` of every column except `id`.
- `ids_with_status` is ordered by id.
- `PostgresRejections.add` uses `on_conflict_do_nothing(proposal_id)`.
- Row mappers: `_product_row` and `_product`, `_order_row` and `_order`, `_proposal`.

### `schema.py`
Tables are declared on the shared `metadata` from `db.py`. Column types are kept neutral (JSON, Numeric) so the migrations also run on SQLite:
- `products_t`: includes `bookable` (Boolean, default True), `bookable_checked_at`, `archived`
- `intents_t`
- `proposals_t`: FKs to intents and products
- `orders_t`: `status` is `String(24)` with an index; `UniqueConstraint("proposal_id", name="uq_orders_proposal_id")`
- `rejections_t`

### `db.py`
- `metadata = MetaData()`
- `make_engine(url)`: `pool_pre_ping`; on Postgres, `connect_timeout=3` and `pool_timeout=3`
- `check_db(engine) -&gt; bool`

### How the catalog bootstrap works (`vela/app.py`)
- `bootstrap(vela, runner, catalog_loader)` (L45-51): if `products.count() == 0`, it calls `upsert_many(catalog_loader())`.
- It returns `{"catalog_loaded": n, "resumed": runner.resume()}`, which is stored on `app.state.bootstrap`.

---

## 4. Migrations and DB tables
- `alembic/versions/0001_initial.py`: empty; only creates `alembic_version`.
- `alembic/versions/0002_domain_tables.py` (down_revision `"0001"`) creates:
  - `products`, `intents`, `proposals` (+ `ix_proposals_intent_id`), `orders` (+ `uq_orders_proposal_id`, `ix_orders_status`), `rejections` (+ `uq_rejections_proposal_id`, `ix_rejections_intent_id`)
  - `downgrade` drops all of them.
- `alembic/env.py`: the URL comes from `Settings.from_env().database_url` and raises `RuntimeError` if it is missing. It imports `vela.adapters.schema` to register the tables and uses `NullPool` online.
- Next revision: `0003` (the roadmap names it) for `jobs`, the quota counter, and order columns such as queue position and job step.
- Tests that hard-code `"0002"`, all in `tests/test_migrations.py`:
  - L32: `heads == ["0002"]`
  - L39: `"0002" in stdout`
  - L48: `versions(url) == ["0002"]` (SQLite upgrade then downgrade)
  - L65: the Postgres idempotence check
- The container runs `alembic upgrade head` in `docker-entrypoint.sh` before starting uvicorn.

---

## 5. App wiring and config

### `vela/config.py`
- `Settings` is a frozen dataclass: `database_url, hofj_api_key, hofj_base_url, hofj_brand, stripe_secret_key, stripe_webhook_secret, vela_api_token, vela_upstream_mode="replay", anthropic_api_key, vela_public_url`.
- `Settings.from_env(environ=None)` reads `DATABASE_URL` (normalised to `postgresql+psycopg://`), `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND`, `STRIPE_*`, `VELA_API_TOKEN`, `VELA_UPSTREAM_MODE`, `ANTHROPIC_API_KEY` and `VELA_PUBLIC_URL`.
- `DEFAULT_TRAVELER = TravelerDefaults()` (L59).
- There are no settings yet for worker concurrency, quota limit, booking reserve or replay latency.
- `tests/test_config.py` asserts every field one by one (L22-45) and never reads files (`NoDotenvTest`).

### `vela/app.py`
- `REPLAY = "replay"`
- `build_vela(settings, engine) -&gt; (Vela, BookingRunner, CatalogLoader)` (L35-42) raises for any mode other than replay:
  ```python
  raise RuntimeError("VELA_UPSTREAM_MODE=%s non disponibile prima di M5: usare replay" % ...)
  ```
  Otherwise it builds `ReplayHofJ()`, `Vela(PostgresRepositories(engine), hofj, FakePayments(public_url), DEFAULT_TRAVELER)` and `BookingRunner(vela.orders)`.
- `create_app(settings=None, vela=None, runner=None, catalog_loader=None)` (L54). Tests inject `vela` and `runner`. Without `database_url`, `app.state.vela` is `None`.
- `lifespan` (L61-68): inside `mcp.session_manager.run()`, it calls `bootstrap(...)` and later `runner.shutdown(wait=False)`. This is where a worker pool would start and stop.
- State set on the app: `settings, engine, vela, runner, catalog_loader, bootstrap, mcp`.
- The replay router is mounted only when `vela_upstream_mode == "replay"`.
- `render.yaml` sets `VELA_UPSTREAM_MODE: replay`.

### `vela/surfaces/health.py`
- The body has `"quota": None` hard-coded (L38). Its docstring says quota "resta null finché il guardiano della quota non esiste (M5)".

---

## 6. Surfaces

### MCP (`vela/surfaces/mcp.py`)
- Tools are registered in `build_mcp(get_vela)` (L109).
- `run()` maps `NotFound` to `fail(say_not_found(kind))` and any other exception to `say_error()`. `ok()` returns `structured_content = to_dict()` plus the same JSON as text.
- `DESCRIPTIONS["accept_proposal"]` (L58-65) still describes synchronous accept:
  &gt; "...On success the result has `order_id`, the real `total` and `payment_url`: show `payment_url` as a clickable link in the chat and never read it aloud." + `_VOICE`
- `DESCRIPTIONS["get_order_status"]` (L66-69):
  &gt; "Check an order when the user says they paid or asks how it is going. Returns `status` (awaiting_payment, paid_pending_booking, confirmed, booking_failed, expired) and, when confirmed, `booking_code`." + `_VOICE`
- `INSTRUCTIONS` (L30) also talk about the payment link.
- The `accept_proposal` tool (L142-147) takes `proposal_id` plus the flat traveler fields `first_name`, `last_name`, `email`, `phone` and `participants`.
- Current return shapes:
  - Order: `{order_id, status, total, currency, price_from_total, total_differs, payment_url, say}`
  - Missing data: `{proposal_id, missing[], say}`
  - `get_order_status`: `{order_id, status, booking_code, say}`

### REST (`vela/surfaces/rest.py`, prefix `/v1`, Bearer `VELA_API_TOKEN`)
- `OUTCOMES` (L24) maps each response type to an outcome name, e.g. `AcceptResponse: "order"`, `MissingTravelerData: "missing_traveler_data"`, `OrderStatusResponse: "order_status"`.
- `CREATED = (IntentCreated, AcceptResponse)` means HTTP 201.
- `reply()` returns `{"outcome": ..., **to_dict()}`.
- `POST /v1/proposals/{proposal_id}/accept` (L102) takes body `AcceptIn{traveler: ProfileIn?}` and returns 201 `order` or 200 `missing_traveler_data`.
- `GET /v1/orders/{order_id}` (L109) returns 200 `order_status`.
- Errors are RFC 7807 via `surfaces/problems.py`: `Problem`, `not_found`, `domain_unavailable`, `rest_not_configured`, `unauthorized`, and a 500 `internal-error`. `NotFound` becomes a 404 problem.
- `docs/rest.md` documents this surface.

### Replay checkout (`vela/surfaces/replay.py`)
- `GET /replay/checkout/{order_id}` calls `vela.orders.mark_paid(order_id, "pi_replay_"+id)`.
- If the order is now `PAID_PENDING_BOOKING`, it calls `request.app.state.runner.submit(order_id)`. This is the booking trigger that would become a `booking` job.
- It returns `{order_id, status, say}`: 404 for an unknown order, 503 with no domain.

---

## 7. Tests (`tests/`, unittest)
- **Running them:** `python3 -m unittest discover -s tests`. Modules import the helpers directly (`from support import ...`, `from repo_contract import ...`).
- **Naming:** files are `test_&lt;area&gt;.py`, classes are `&lt;Thing&gt;Test(unittest.TestCase)`, methods are `test_&lt;behaviour_in_snake_case&gt;`. MCP tests use `unittest.IsolatedAsyncioTestCase` with `mcp.Client(server)`.
- **`tests/support.py`**
  - `NOW = 2026-09-25 12:00 UTC`, `TODAY`
  - `make_product(pid, price, sport, country, destination, windows, ..., archived, bookable, hotel, title)`
  - `count_products` and `assert_single_product(tc, d)` (RF-10, checks for no `http` or `**` in `say`)
  - `FakeHofJ(total=None, fail_itinerary=None, fail_booking=None, code="R-000001")` records `.calls`, `.customers`, `.pax` and `.bookings`. Itinerary ids are `it-&lt;product_id&gt;`.
  - `StubPayments(base="http://pay.test")` records `.links`, with reference `pi_&lt;order_id&gt;`.
  - `assert_problem(tc, response, status, slug)`
- **Fake clock:** each test file defines its own `Clock` class; nothing is shared.
  ```python
  class Clock:
      def __init__(self): self.at = NOW
      def __call__(self): self.at += timedelta(seconds=1); return self.at
  ```
  Copies are in `test_usecases.py:15` (takes an `at=` argument), `test_mcp_tools.py:27`, `test_rest.py:25` and `test_app_replay.py:22`. `test_orders.py` and `test_health.py` use `now=lambda: ...`. Ids are made deterministic with `new_id=lambda: next(iter("id%d"...))`.
- **Postgres tests are skipped without `DATABASE_URL`**
  - The decorator is `@unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")`. It is used in `test_repo_postgres.py:20` (class), `test_migrations.py:60` and `test_db.py:49`.
  - `test_repo_postgres.py` creates schema `vela_test` and appends `options=-csearch_path%3Dvela_test` to the URL. It runs `alembic upgrade head` in `setUpClass` and deletes from all tables in `make_repos()` (FK order: rejections, orders, proposals, intents, products).
  - `tests/repo_contract.py` holds `RepositoryContract`, a mixin shared by `test_repo_memory.py` and `test_repo_postgres.py`. Its builders are `intent()`, `proposal()` and `order()`, and `seed()` creates the FK targets. New repositories (jobs, quota) would fit this pattern.
- **Tests tied to today's synchronous contract:**
  - `test_usecases.py`: `AcceptProposalTest` L155-220 (expects `AWAITING_PAYMENT`, a `payment_url`, and the itinerary/customer/pax call order), `OrderStatusTest` L223, `FullReplayFlowTest` L238-286.
  - `test_orders.py`: `CompleteBookingTest` L49 (a failure goes straight to `BOOKING_FAILED`), `RunnerTest` L84.
  - `test_mcp_tools.py`: `FlowTest.test_full_flow_section_10_1` L94 (expects `"awaiting_payment"` and a `payment_url`); `test_descriptions_are_written_for_voice` L75 requires `"Never list"` and `` "`say`" `` in every description.
  - `test_rest.py`: L225-258 (accept returns 201 `order` with `payment_url`; order status is `awaiting_payment`) and `FullFlowTest` L291.
  - `test_app_replay.py`: `ModeTest.test_live_with_database_is_refused` L116 asserts `"M5"` in the `RuntimeError`. The bootstrap and resume tests are at L48-67.
  - `test_migrations.py`: the `"0002"` checks listed in section 4.
- Other test files that exist: `test_replay_adapters.py`, `test_health.py`, `test_say.py`, `test_chooser*.py`, `test_render_yaml.py`, `test_docker_files.py`.

---

## 8. Dependencies (`pyproject.toml`)
- Runtime: `fastapi&gt;=0.115`, `uvicorn[standard]&gt;=0.30`, `sqlalchemy&gt;=2.0`, `psycopg[binary]&gt;=3.2`, `alembic&gt;=1.13`, `httpx&gt;=0.27`, `mcp&gt;=1.2`, `stripe&gt;=10`. There is also a `uv.lock`.
- Dev group: `locust&gt;=2.30`.
- `requires-python &gt;=3.12`.
- `httpx` is already there, so an HTTP adapter and `httpx.MockTransport` tests need no new dependency.
- Existing HofJ HTTP code to look at: `scripts/api_explore.py` has a urllib-based `Client` (L99, `Authorization: Bearer`, `BASE_URL` from `HOFJ_BASE_URL`) and a `QuotaGuard` (L38) with `sync`, `can_request`, `wait_seconds` and `record`. `scripts/record_catalog.py` reuses both.

---

## Reference docs for M5
- `docs/roadmap.md` L231-291: the M5 scope, the completion tests and the prompt. It lists a `jobs` table with `FOR UPDATE SKIP LOCKED`, migration `0003`, `vela/adapters/hofj_http.py`, and replacing `BookingRunner` with `booking` jobs.
- `docs/spec.md`:
  - §4.10 RF-45..51 (L236-271)
  - RF-25 states (L142-148): `queued, awaiting_payment, paid_pending_booking, confirmed, replaced, cancelled, failed, …`
  - RF-14..17 (L99-113), RF-23/24/27 (L136-155), RF-33..38 (L176-198), RNF-04 (15 s timeout, L282)
  - The use-case table (L209-210)
- `docs/decisions.md` L172-185 ("Twist"): Postgres queue, a worker in every instance, an atomic quota counter, and accept that is always async.
- API notes: `docs/api/internal-checkout.md`, `docs/api/quota-health.md`, `docs/api/differences.md`.</result>
<usage><subagent_tokens>139909</subagent_tokens><tool_uses>50</tool_uses><duration_ms>170217</duration_ms></usage>
</task-notification>

## Agente 17:59

Ho la mappa del codice. Resta l'esplorazione su spec e decisioni, poi comincio l'intervista.

## Utente 18:00

<task-notification>
<task-id>a8ae8f7ce9734b22f</task-id>
<tool-use-id>toolu_01RNVdednYSfKL6VJejb21D2</tool-use-id>
<output-file>/private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-task-m5/4e77c5e2-1cbd-49a4-a46b-71f152659842/tasks/a8ae8f7ce9734b22f.output</output-file>
<status>completed</status>
<summary>Agent "Summarize M5 spec requirements" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>I've read everything you listed. Section headings in `docs/decisions.md` are "Roadmap in macro task" and "Twist: 50.000 viaggiatori in dieci minuti". Quotes are from the Italian source, translated into English. I also read `docs/roadmap.md` M5, `docs/easter-eggs.md` (the only record of real cart calls) and the current port/config/say code, because those show gaps you'll hit.

`docs/api/` contains: `README.md`, `articles.md`, `categories.md`, `counts.md`, `destinations.md`, `differences.md`, `distribution-channels.md`, `internal-checkout.md`, `locales.md`, `pages.md`, `products.md`, `quota-health.md`, `recommendations.md`, `venues.md`.

## 1. HofJ endpoints M5 needs

`internal-checkout.md` opens by saying none of these routes has been verified: they come only from the OpenAPI contract and the docs site.

**Requirements for every call:**
- The client must be `profile=internal`, with `allowedEntities` including `itineraries` and `bookings`.
- `?brand=` and `locale` go on every call (`locale` is `it|en|es|fr`).
- Upstream timeout is 15 s.
- Auth is `Authorization: Bearer &lt;api_key&gt;`.

| Step | Call | Request | Response `data` |
|---|---|---|---|
| Create itinerary | `POST /v1/itineraries?brand=&amp;locale=` | `{productId (numeric id or tripCode/providerID), startDate YYYY-MM-DD, adults, rooms, affiliateId?, currency? EUR\|USD\|GBP}` | `{itineraryId}` only, no total |
| Customer | `PUT /v1/itineraries/{id}/customer` | `CustomerData {firstName, lastName, email, phone, taxNumber?, marketingOptIn?, address: {street1, postalCode, city, region, countryCode}}` | `CustomerData` |
| Pax read | `GET /v1/itineraries/{id}/pax` | none | `Pax[]` |
| Pax write | `PUT /v1/itineraries/{id}/pax` | `Pax[]`, "every element must keep `refId`". `Pax {refId, firstName?, lastName?, birthDate?, age?, gender?: Female\|Male, nationalityCountryCode?, marketingOptIn?}` | none |
| Real total | `GET /v1/itineraries/{id}` | none | `Itinerary`: `checkout {openAmount, total, originalTotal: Money, status, refId}`, `totalPrice`, `accommodation {…totalPrice: Money…}` |
| Booking | `POST /v1/bookings` | contract says `CreateBookingRequest {itineraryId, paymentType?, planIndex?}` | a string code, e.g. `R-789012`. "Idempotent upsert per `itineraryId`." |
| Quota | `GET /v1/quota` | none | `{clientId, backend, limitPerMinute:120, usedInWindow, remainingInWindow, windowStartedAt, windowEndsAt}` |

- **`Money`** is `{amount: string, currency: string}`. The catalog `price` is a number (differences #10).
- **Declared errors:** 400, 401, 403, 404, 429, 502.
- `GET .../payment` has side effects (it creates a payment intent). Don't call it.

**What was actually observed on staging** (`easter-eggs.md`, host `https://staging.api.hofj.com`, brand `staging.weebora.com`, client `test-dev-2`):
- `POST /v1/itineraries` with `{"productId":118,"startDate":"2026-12-08","adults":2,"rooms":1,"currency":"EUR"}` returned 200 with `itineraryId` `awp8bacduowd`.
- `GET /v1/itineraries/{id}` returned a total of 351.00 EUR with a preselected hotel.
- A start date before `minDate` still worked (200). A date after `maxDate` returned **502, upstream 400 `RESERVATION_PERIOD_ERROR`**, with the body wrapped in `detail`.
- Accommodations sometimes returned "502 upstream timeout" and succeeded on the next call.

## 2. Envelope and error format

- **Success:** `{data, meta}`. Lists use `meta: {nextCursor}`. The docs site says checkout routes return `meta: {now: &lt;epoch ms&gt;}`, but the contract declares an empty `meta` object (differences #21). Not verified.
- **Errors:** RFC 7807 `{type, title, status, detail, instance}`, where `type` is `https://api.hofj.com/problems/&lt;slug&gt;` (`bad-request`, `upstream-error`) and `instance` is a correlation UUID.
  - Content-type is `application/json; charset=utf-8`, not `application/problem+json`, so don't filter on media type (#4).
  - A zod validation `detail` is a string containing a JSON array (#5).
- **A wrong product id gives 502 `upstream-error`, not 404:** "`detail: "Upstream get failed: 500"`. Un id sbagliato è indistinguibile da un guasto upstream" (a wrong id can't be told apart from an upstream failure, #2). The roadmap asks the adapter to handle this.
- **Customer address:** use the contract's `Address {street1, postalCode, city, region, countryCode}`, all required. The docs-site examples (`line1, country`) would fail validation (#20). The roadmap says "indirizzo `Address` da OAS non da DOCS" (use the contract's address, not the docs site's). The existing `Customer` port already matches.
- **Vela's own REST errors** (M4 decision): RFC 7807 with `type=/problems/&lt;slug&gt;` plus `title`, `status`, `detail`, `instance` and `say`.

## 3. Quota

- **Limit:** 120 requests per minute per client. `/v1/quota` itself costs 1 request.
- **Window:** "Finestra **fissa di 60 s ancorata alla prima richiesta**" (a fixed 60 s window anchored at the first request). The contract calls it "rolling 60s window" (#8). There's no `Retry-After` or `X-RateLimit-*` header. The docs site mentions `retryAfterSeconds` in the 429 body, but that's unverified because no 429 has been generated.
- **RF-36:** "contatore condiviso in Postgres per finestra mobile di 60 secondi, inizializzato da `GET /v1/quota` all'avvio e aggiornato a ogni chiamata (inclusa quella di quota)" (a shared Postgres counter per rolling 60 s window, initialised from `/v1/quota` at startup and updated on every call, including the quota call).
- **RF-37:** "nessuna chiamata a HofJ parte senza un blocco di budget prenotato nella finestra corrente… il sync gira solo a coda vuota e sopra la soglia. Nessuna chiamata del viaggiatore fallisce per quota esaurita" (no HofJ call starts without a budget block reserved in the current window; sync runs only with an empty queue and above the threshold; no traveller call fails for lack of quota).
- **RF-38:** "Una risposta 429 da HofJ aggiorna il contatore e non viene mai ripetuta immediatamente" (a 429 updates the counter and is never retried immediately).
- **RF-47, the scheduler:**
  - One scheduler per cluster, with a 60 s counter in Postgres and three classes:
    - `booking`: "riserva garantita del 20% della finestra, configurabile" (guaranteed reserve of 20% of the window, configurable).
    - `purchase`: the rest of the window, FIFO.
    - `sync`: "solo a coda `purchase` vuota e sopra la soglia di RF-37" (only when the purchase queue is empty and above RF-37's threshold).
  - "Un job prenota atomicamente il blocco di chiamate che gli serve (5 per un acquisto, 1 per una prenotazione) oppure attende la finestra successiva" (a job atomically reserves the block of calls it needs, 5 per purchase and 1 per booking, or waits for the next window).
  - "Una risposta 429 azzera il budget residuo della finestra" (a 429 zeroes the window's remaining budget).
  - "`GET /v1/quota` si chiama al boot e dopo un 429, mai in ciclo" (called at boot and after a 429, never in a loop).
- **Margin used elsewhere:** the exploration script used `min(remainingInWindow, 90 − usedInWindow)` and waited until `windowEndsAt` + 2 s. That's a 30-call margin. The spec doesn't carry it over.

## 4. Estimated wait (RF-48, RF-45)

- **RF-48:** "Attesa stimata = posizione in coda × 60 s ÷ acquisti per finestra, con acquisti per finestra = (limite − riserva `booking`) ÷ 5. Ricalcolata a ogni `get_order_status`. Non esiste un tetto" (wait = queue position × 60 s ÷ purchases per window, where purchases per window = (limit − booking reserve) ÷ 5; recomputed on every status call; no cap).
- With 120 and 20%: (120 − 24) / 5 = 19.2 purchases per window.
- **RF-45:** accept "risponde senza chiamare HofJ né Stripe. La frase `say` dichiara l'attesa in minuti, arrotondata per eccesso" (responds without calling HofJ or Stripe; `say` states the wait in minutes, rounded up).

## 5. Purchase job, states, retries

- **RF-46 steps, in order:** create itinerary → customer → read pax → write pax → read the real total → create the payment link → `awaiting_payment`.
  - "Ogni passo salva il proprio esito (`itineraryId` compreso)" (each step saves its result, including `itineraryId`).
  - "Un passo fallito per rete, timeout o 5xx viene ripetuto fino a tre volte nelle finestre successive; poi l'ordine passa a `failed` con un motivo leggibile. Un errore del prodotto segue RF-17" (a step failing on network, timeout or 5xx is retried up to three times in later windows, then the order goes to `failed` with a readable reason; product errors follow RF-17).
- **RF-14:** `POST /v1/itineraries` with product, start date, adults, rooms and currency EUR; `PUT customer`; `GET pax`; `PUT pax` "preservando ogni `refId`" (keeping every `refId`).
- **RF-15:** accept the default accommodation, with no alternative hotels and no activities.
- **RF-16:** if the real total differs from the "from" price, the status response "lo dichiara esplicitamente prima del link di pagamento. Il link porta sempre il totale reale" (says so explicitly before the payment link; the link always carries the real total).
- **RF-17, product error** ("4xx/5xx da HofJ riconducibile al prodotto, non alla quota o alla rete", i.e. caused by the product, not quota or network):
  - Mark the product unbookable, pick the next proposal, set the order to `replaced`.
  - `get_order_status` returns the new proposal in the RF-06 shape plus a `proposal_changed` flag, "senza esporre l'errore" (without exposing the error).
  - "Un nuovo `accept_proposal` sulla proposta sostitutiva crea un ordine che entra in testa alla coda (posizione ereditata dall'ordine sostituito)" (a new accept on the replacement enters at the head of the queue, inheriting the replaced order's position).
- **RF-25 states:** `queued`, `awaiting_payment`, `paid_pending_booking`, `confirmed`, `replaced`, `cancelled`, `failed`, `booking_failed`, `expired`. The status response carries:
  - the wait if `queued`;
  - link and amount if `awaiting_payment`;
  - the replacement proposal if `replaced`;
  - the code if `confirmed`;
  - a readable reason if `failed` or `booking_failed`;
  - always a `say`.

  The current `OrderStatus` enum in `vela/domain/models.py` lacks `queued`, `replaced`, `cancelled` and `failed`.
- **RF-19:** the accept response contains "solo id ordine, stato `queued`, attesa stimata e frase" (only order id, `queued`, estimated wait and the phrase). RF-39 also lists "posizione" (position).
- **RF-23:** `POST /v1/bookings` with `itineraryId`, `paymentType: "full"`, `paymentIntentId` and `paymentStatus` from Stripe. Save the code and move to `confirmed`.
- **RF-24:** retry "su errore di rete o 5xx con backoff, fino a un numero massimo configurato, poi marca l'ordine `booking_failed` con il motivo" (on network error or 5xx with backoff, up to a configured maximum, then `booking_failed` with the reason). **No numbers are given.**
- **RF-27:** at boot, resume `paid_pending_booking` orders, and resume `queued` jobs "dal primo passo non completato… senza ricreare itinerari già creati" (from the first unfinished step, without recreating itineraries).
- **RF-49:** reject on a `queued` order's proposal → `cancelled`, removed from the queue, next proposal returned.
- **RF-50:** a worker runs in every instance, taking jobs with `FOR UPDATE SKIP LOCKED`; "concorrenza per istanza configurabile (default 4)" (per-instance concurrency, configurable, default 4).
- **RF-51:** "Un ordine pagato viene prenotato entro la finestra successiva al webhook" (a paid order is booked within the window after the webhook), barring RF-24 errors.
- **Roadmap M5:** a `jobs` table and migration `0003`, replacing M2's `BookingRunner`. The replay adapter gets configurable simulated latency and quota (default zero and unlimited). `/health` should report quota (M4 left `quota: null` "fino a M5", until M5).
- **RNF-04:** "Le chiamate a HofJ hanno timeout di 15 secondi. Nessun caso d'uso aspetta HofJ: il job d'acquisto (RF-46) assorbe i 2-6 secondi della ricerca di disponibilità live e i timeout" (15 s timeout on HofJ calls; no use case waits on HofJ; the purchase job absorbs the 2–6 s live availability search and the timeouts).

## 6. Unbookable products (RF-33..35)

- **RF-33:** `bookable=false` "al primo fallimento di `POST /v1/itineraries` riconducibile al prodotto… per tutti gli intenti" (on the first product-caused failure of `POST /v1/itineraries`, for all intents).
- **RF-34:** "Dopo 24 ore dal `bookable_checked_at` il prodotto torna candidato: il primo nuovo tentativo lo riconferma o lo riabilita" (24 h after `bookable_checked_at` the product is a candidate again; the next attempt either re-confirms it as unbookable or re-enables it).
- **RF-35:** no pre-emptive check of the whole catalog.

## 7. Say phrases M5 must add or change

- **Wait:** in minutes, rounded up (RF-45).
- **Replacement:** reads the new proposal without mentioning the error (RF-17).
- **Failure:** a readable reason (RF-46, RF-25).
- **Price change:** the real total differs, stated before the link (RF-16).
- **Cancellation:** RF-49.
- **Unchanged:** `booking_failed` and `confirmed` ("La tua prenotazione è confermata, codice R-789012", "Your booking is confirmed, code R-789012") already exist.
- **Rule for all of them (RF-42):** in the intent's language, no markdown, no URL read out.
  - Currently `say` is Italian only (M2 decision); English templates come in M9.
  - The existing `say_accept` in `vela/domain/say.py` assumes the link comes at accept time, so it has to change.
- **RF-41:** the `accept_proposal` tool description must say "la risposta è un'attesa, non un link, e che il link va letto con `get_order_status` dopo l'attesa dichiarata o quando il viaggiatore lo chiede" (the answer is a wait, not a link; get the link from `get_order_status` after the stated wait or when the traveller asks).

## 8. Environment variables (spec §6, a closed list)

`HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND`, `DATABASE_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `VELA_API_TOKEN`, `VELA_UPSTREAM_MODE` (`replay` by default, or `live`), `ANTHROPIC_API_KEY` (optional), `VELA_PUBLIC_URL`.

- M2 decision: `create_app` raises `RuntimeError("VELA_UPSTREAM_MODE=live non disponibile prima di M5")` (live mode not available before M5). M5 removes this.
- M1 decision: `HOFJ_API_KEY` falls back to `API_BEAR_KEY`, but only in the recording script. `vela/config.py` doesn't have that fallback.

## 9. Spec §8 checks (M5's first step)

- **Spec §8:** "con al massimo cinque chiamate a HofJ e nessuna a Stripe oltre la creazione di un link di test" (at most five HofJ calls and no Stripe calls beyond creating a test link).
- **Checks to run:**
  - `GET /v1/quota` plus `POST /v1/itineraries` on `t0054825`. If that returns 403, ask for the internal key.
  - List and detail calls for catalog size.
  - `POST /v1/bookings` with our own `paymentIntentId`. If HofJ rejects it, the fallback is a minimal Stripe.js page that confirms the `client_secret` from HofJ's `POST .../payment`.
  - Read `limitPerMinute`.
  - Test ElevenLabs with the link.
- **Roadmap M5:** "dichiarare ≤ 8 chiamate" (declare at most 8 calls): quota, itinerary, customer, pax read/write, and booking "con un `paymentIntentId` di un Checkout di test creato a mano" (with a `paymentIntentId` from a Checkout made by hand). Record the result and fallback in `decisions.md`.

## 10. Contradictions and open questions for the user

1. **Call budget for §8:** the spec says at most 5 HofJ calls; the roadmap says at most 8. The roadmap list (quota, itinerary, customer, GET pax, PUT pax, GET itinerary, booking) is 7 or more calls.
2. **Booking request shape (the biggest risk):** RF-23 sends `paymentIntentId` and `paymentStatus`, but the contract's `CreateBookingRequest` is only `{itineraryId, paymentType?, planIndex?}`. This is exactly §8 risk row 3, and the fallback (Stripe.js page on HofJ's `client_secret`) would change M6. The test also needs a hand-made Stripe Checkout, and M6 owns Stripe. Ask who creates it, and whether a real booking on production is acceptable: it creates a real reservation, and there's no cancellation in scope.
3. **Which environment and brand?** Production is `api.hofj.com` (channels `weebora.com`, `terrarossa.com`, `booking.hofj.com`). Staging is `staging.api.hofj.com` (`staging.weebora.com`, the only one where carts were verified). Sandbox appears only in the contract.
   - The `it` fixture ids (181–1093) are production. The §8 product `t0054825` looks like a tripCode, which `productId` accepts. The staging product 118 is a different catalog.
   - Ask what `HOFJ_BASE_URL` and `HOFJ_BRAND` should be for the §8 checks and for M7.
4. **Calls per purchase:**
   - RF-46 has five HofJ calls. POST itinerary doesn't return a total, so the extra GET itinerary is needed, and the port's `create_itinerary` currently returns `Itinerary(total)`.
   - Twist math: 120/6 = 20/min (5 + 1 booking). RF-48 gives (120 − 24)/5 = 19.2 purchases per window, while RNF-10 expects about 20.
   - Step retries cost 1 call, not 5. It's unspecified how many calls a resumed or partially done job reserves.
5. **Window model:** RF-36 says "rolling", RF-47 says a 60 s counter, and the observed behaviour is a fixed window anchored at the first request.
   - Unspecified: whether our window follows HofJ's `windowStartedAt`/`windowEndsAt` or our own clock, and whether to keep a safety margin like the script's 30. Other scripts and clients may share the `test-dev-2` key.
   - There's a clock-skew risk.
6. **Sync threshold:** RF-37 and RF-47 cite "la soglia di RF-37" (RF-37's threshold), but RF-37 defines no number. Sync itself is M10.
7. **After a 429:** RF-47 calls `/v1/quota` after a 429, but that call consumes quota and could itself 429. It's also undecided whether to honour `retryAfterSeconds` (unverified).
8. **What counts as a product error:**
   - 502 `upstream-error` covers a wrong id, a wrapped upstream 400 (`RESERVATION_PERIOD_ERROR`) and "upstream timeout". A rule is needed: parse `detail`? Treat 404 and 400 as product errors, 502 with an upstream 4xx as product, 502 timeout as network?
   - A date error isn't really the product's fault: should it make the product unbookable for 24 h?
   - 401/403 are client or config errors and must not mark the product.
9. **Booking retry numbers:** RF-24's backoff and maximum attempts aren't set. They also need reconciling with RF-51's "entro la finestra successiva" (within the next window).
10. **Where the new settings live:** the reserve (20%), per-instance concurrency (4), booking max retries and backoff, and replay latency/quota are all "configurabile", but spec §6 and the M2 decision say the env-var list "resta chiuso" (stays closed). Settings constants, or new env vars?
11. **Replacement queue position:** "in testa alla coda (posizione ereditata)" is either the head of the queue or the replaced order's original position. These differ.
12. **Queue position details:** does it start at 0 or 1? And does the wait formula count in-flight jobs? One purchase takes about 5 × 2–6 s ≈ 10–30 s.
13. **Throughput vs concurrency:** with the default concurrency of 4 and about 20 s per purchase, one instance manages about 12 purchases/min, below the 19–20 quota ceiling. Should the default be higher, or will there be several instances?
14. **Rejecting after the queue:** RF-49 covers only `queued`. What should `reject_proposal` do on an order that's in progress (itinerary already created), `awaiting_payment` or `replaced`?
15. **Accept response and payment step:**
    - RF-19 lists the accept fields without "position", RF-39 includes it. Which is it?
    - The job's last step creates the payment link, but Stripe is M6, running in parallel. In M5, use the fake payments port and let whoever merges second adapt, as the roadmap says for the booking trigger?
16. **Migration numbering:** M5 plans `0003`. M6's webhook-events table may also need a migration, so the number could clash.
17. **`meta.now` and content-type:** the parser should tolerate `meta` being absent or empty, and shouldn't rely on the `problem+json` content-type.</result>
<usage><subagent_tokens>86277</subagent_tokens><tool_uses>11</tool_uses><duration_ms>209361</duration_ms></usage>
</task-notification>

## Agente 18:00

Prima dell'intervista, ecco cosa ho capito.

**Obiettivo di M5.** Il flusso con l'accettazione asincrona diventa reale, e il picco di 50.000 viaggiatori si trasforma in attesa dichiarata invece che in errori:

- `accept_proposal` risponde subito `queued` con l'attesa stimata.
- Un job d'acquisto, a passi ripartibili, crea l'itinerario su HofJ e produce il link di pagamento.
- Uno scheduler in Postgres divide la quota da 120 al minuto in tre classi: `booking` con una riserva, `purchase` in ordine di arrivo, `sync`.
- Un worker gira in ogni istanza.
- L'adapter HTTP verso HofJ è quello vero.

**Vincoli che ho trovato nel repo:**

- Suite `unittest` verde anche senza `DATABASE_URL`.
- Nessuna dipendenza nuova: `httpx` c'è già.
- L'elenco delle variabili d'ambiente è chiuso (spec §6).
- M6 (Stripe) gira in parallelo e tocca `orders.py`.

**Cosa cambia per forza:**

- `OrderStatus`, con gli stati nuovi `queued`, `replaced`, `cancelled` e `failed`.
- `Order.total`, che oggi è obbligatorio ma al momento dell'accettazione non è ancora noto.
- `HofJPort`: la POST dell'itinerario non restituisce il totale, quindi serve un passo `get_itinerary`.
- Una migrazione `0003`.
- Le superfici MCP e REST.
- Una ventina di test legati al contratto sincrono.

Nella spec restano diverse zone scoperte. Te le chiedo a gruppi tematici, cominciando dalle verifiche di §8, perché possono cambiare il design della prenotazione.

- 🔧 AskUserQuestion

Per ora ho annotato due risposte: ambiente **staging** e Checkout di test **creato da me con una chiamata Stripe in modalità test**. Ecco le altre due spiegate meglio.

**1. Budget di chiamate per le verifiche di §8**

Prima di scrivere l'adapter HTTP vogliamo vedere con risposte vere che il flusso d'acquisto funziona su HofJ. Ogni chiamata consuma la quota (120 al minuto, condivisa con chiunque usi la stessa chiave), quindi i documenti fissano un tetto. Il problema è che si contraddicono:

- la spec §8 dice «al massimo cinque chiamate a HofJ»;
- la roadmap M5 dice «dichiarare ≤ 8 chiamate».

Il flusso che il job dovrà eseguire richiede 7 chiamate:

| # | Chiamata | Cosa verifichiamo |
|---|---|---|
| 1 | `GET /v1/quota` | limite reale e finestra |
| 2 | `POST /v1/itineraries` | la chiave ha i permessi `internal`, il formato dell'id prodotto |
| 3 | `PUT …/customer` | che l'indirizzo nel formato OAS (`street1`, `postalCode`…) sia accettato |
| 4 | `GET …/pax` | forma dei `refId` |
| 5 | `PUT …/pax` | scrittura dei nomi |
| 6 | `GET /v1/itineraries/{id}` | dove sta il totale reale (`checkout.total`?) |
| 7 | `POST /v1/bookings` | **il rischio principale**: accetta il nostro `paymentIntentId`? |

- **Opzione A, ≤ 8:** facciamo tutte e 7 le chiamate più una di margine per un eventuale errore da ripetere. Vediamo ogni forma reale.
- **Opzione B, ≤ 5:** saltiamo la 3, la 4 e la 5 (customer e pax), perché in `docs/easter-eggs.md` risultano già provate su staging. Consumiamo meno quota, ma quei tre passi verrebbero scritti solo sulla base di note precedenti.

Consiglio A: sono chiamate su staging e il costo è trascurabile.

**2. Quando fare le verifiche**

Le verifiche sono manuali: le chiamate le lancio io, ma servono le tue chiavi nell'ambiente e la tua approvazione. Il resto di M5 si può invece scrivere e testare tutto con finti in memoria (coda, scheduler, worker, stati, frasi). L'unica parte che dipende dalle risposte reali è l'adapter HTTP: nomi dei campi, dove sta il totale, come arrivano gli errori.

- **Task 1 del piano:** chi esegue il piano si ferma al primo task e fa le chiamate con te. L'adapter HTTP, scritto più avanti, parte dalle forme reali.
- **Ora:** le faccio prima di scrivere il piano, così il piano stesso contiene le forme reali. Serve però che le chiavi siano già disponibili adesso.
- **In fondo:** tutto il codice viene scritto sulle forme del contratto OAS e la verifica reale è l'ultimo task, con il rischio di dover correggere l'adapter a fine lavoro.

Consiglio il Task 1: le forme reali arrivano prima dell'adapter e non blocca l'intervista di adesso.

- 🔧 AskUserQuestion

Su cosa vuoi chiarimenti? Il budget di chiamate, il momento delle verifiche, o qualcos'altro, per esempio perché servono verifiche reali prima dell'adapter?

## Utente 18:04

spiegami meglio cosa indica §8 e perche il budget è fissato ad 8

## Agente 18:04

- 🔧 Bash: Read spec section 8 and budget references

**Cos'è §8.** La sezione 8 della spec si intitola «Rischi e verifiche della prima ora». Elenca cinque ipotesi su cui poggia il progetto e che nessuno ha ancora provato con HofJ reale. Per ognuna dice come verificarla e cosa fare se si rivela falsa:

| # | Rischio | Verifica | Se fallisce | Dove si fa |
|---|---|---|---|---|
| 1 | La chiave non è di profilo `internal`: niente carrelli (403) | `GET /v1/quota` + `POST /v1/itineraries` su `t0054825` | chiedere la chiave interna, intanto si resta in replay | **M5** |
| 2 | Catalogo grande o povero di campi | lista + dettaglio prodotti | ridurre i campi | già coperta da M1 (catalogo registrato) |
| 3 | HofJ non accetta un pagamento fatto sul **nostro** Stripe (`paymentIntentId` rifiutato o ignorato) | un booking completo su un itinerario di test, dopo un Checkout di test | pagina Stripe.js sul `client_secret` di HofJ, che cambia M6 | **M5** |
| 4 | Il limite di quota è molto basso | leggere `limitPerMinute` | alzare le soglie | **M5** (stessa chiamata della riga 1) |
| 5 | ElevenLabs non regge il link | prova vocale | link via testo | M12 |

La riga 3 è la più pericolosa: se HofJ rifiuta il nostro pagamento, cambia il modo in cui paghiamo e quindi il design di M6.

**Perché 5 nella spec.** Il tetto vale per tutte e cinque le righe e la spec lo prevedeva «prima di scrivere il dominio». All'epoca bastava un conto grezzo: quota, itinerario, lista e dettaglio prodotti, booking.

**Perché 8 nella roadmap.** Nei documenti non c'è una motivazione scritta: il valore compare solo nella roadmap e non in `decisions.md`. La mia ricostruzione è questa:

- le verifiche sono state spostate dentro M5 (decisione in `decisions.md:66`);
- la riga 2 non serve più, perché M1 ha già registrato il catalogo;
- la riga 3 chiede un **booking completo**, e su HofJ un booking richiede prima il carrello compilato. Il conto sale così a 7 chiamate: quota, creazione itinerario, customer, lettura pax, scrittura pax, lettura del totale, booking;
- 7 + 1 di margine fanno 8.

In sostanza il tetto serve a due cose: non consumare quota condivisa (120 al minuto per chiave) e rendere dichiarato e contato ciò che tocca un servizio esterno, come chiede `CLAUDE.md`.

Su staging le 7 chiamate costano poco. La scelta vera è se verificare anche customer e pax dal vivo (7 chiamate) o fidarsi delle note di `easter-eggs.md` (4 chiamate). Con 4 però il booking potrebbe fallire perché il carrello è incompleto, e la risposta alla riga 3 resterebbe ambigua.

- 🔧 AskUserQuestion

Registrato: fino a 8 chiamate e verifiche nel Task 1. Il prossimo gruppo di domande riguarda lo scheduler della quota e la configurazione.

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

Ho tutte le risposte che servono. Ti presento il design in due sezioni. Questa è la prima: architettura e dati.

## Design, sezione 1: architettura e dati

**Moduli nuovi**
```
vela/domain/quota.py      NUOVO  regole pure: tetti per classe, limite effettivo (−10%), riserva, attesa stimata
vela/domain/purchase.py   NUOVO  PurchaseJob: 5 passi HofJ + link, ripartibili, classificazione errori → retry/replaced/failed
vela/domain/booking.py    NUOVO  BookingJob: 1 chiamata, 5 tentativi con backoff 5-10-20-40 s (prende il posto di complete_booking)
vela/domain/jobs.py       NUOVO  JobProcessor: preleva un job, prenota il blocco di quota, esegue, salva l'esito
vela/ports/jobs.py        NUOVO  JobRepository (enqueue, claim con lease, complete, reschedule, cancel, queued_position)
vela/ports/quota.py       NUOVO  QuotaStore (acquire(cls, n) atomico, on_429, sync_from_snapshot, snapshot)
vela/adapters/worker.py   NUOVO  Worker a thread (default 4), polling di 1 s; sostituisce BookingRunner/InlineRunner
vela/adapters/hofj_http.py NUOVO httpx, timeout 15 s, envelope, RFC 7807, mappatura errori
vela/adapters/{repo_memory,repo_postgres}.py  + jobs e quota (contratto condiviso in tests/)
alembic/versions/0003_jobs_quota.py
```

**Porta HofJ.** `create_itinerary` restituisce solo l'id. Si aggiungono `get_itinerary(id) -> Itinerary(total)`, cioè il quinto passo, e `get_quota() -> QuotaSnapshot`. Il 429 diventa `QuotaError`.

**Migrazione 0003**
- La tabella `jobs` contiene: id, kind (`purchase`/`booking`), order_id, status (`pending`/`running`/`done`/`dead`), step, attempts, run_after, enqueued_at, locked_at, last_error.
- Il prelievo è `FOR UPDATE SKIP LOCKED`: prima i `booking`, poi i `purchase` per `enqueued_at`.
- Un job `running` con `locked_at` più vecchio di 2 minuti torna prelevabile. Questo copre RF-27 anche con più istanze, senza logica speciale al boot.
- La tabella `quota_window`, a riga unica, contiene window_start, window_end, limit, used.
- Su `orders`: `total` diventa nullable e si aggiungono `enqueued_at` e `replacement_proposal_id`.
- Su `products`: si usano `bookable` e `bookable_checked_at`, che esistono già, più un nuovo `ProductRepository.set_bookable`.

**Scheduler della quota**
- `acquire` è un solo `UPDATE … WHERE used + n <= tetto(classe) RETURNING`. Se la finestra è scaduta, la stessa istruzione la fa avanzare di un multiplo di 60 s e riporta `used` a 0.
- Limite effettivo: 108. Tetto `purchase` e `sync`: 108 − 21 = 87. Tetto `booking`: 108, quindi la riserva di 21 è garantita.
- `sync` passa solo quando non ci sono `purchase` in coda. Il sync vero arriva in M10.
- Un 429 porta `used` al tetto. `/v1/quota` si chiama al boot e alla prima occasione dopo un 429, prenotando una chiamata. Mai in un ciclo.

**Configurazione.** In `Settings` entrano solo campi con default, senza variabili d'ambiente nuove:
- `worker_concurrency=4`, `quota_margin=0.10`, `booking_reserve=0.20`
- `booking_max_attempts=5`, `purchase_max_attempts=3`
- `replay_latency=(0, 0)`, `replay_limit=None`

Il replay simula latenza e 429 con questi valori.

**Modalità live.** Costruisce `HofJHttp`, ma `build_vela` si ferma con un `RuntimeError` che dice di attendere M6 per i pagamenti.

- 🔧 AskUserQuestion

## Design, sezione 2: flusso, stati e contratto

**Accettazione (RF-45, RF-19).** `accept_proposal` non chiama né HofJ né Stripe. Nell'ordine:

1. Se la proposta ha già un ordine, restituisce quello (doppio accept → stesso ordine).
2. Se mancano dati del viaggiatore, risponde `MissingTravelerData`, come oggi.
3. Altrimenti crea l'`Order` in stato `queued`. `enqueued_at` è l'ora attuale, oppure quella dell'ordine sostituito se la proposta è una sostitutiva (RF-17).
4. Accoda un job `purchase` e risponde `{order_id, status:"queued", position, wait_seconds, say}`.

**Job d'acquisto (RF-46).** Passi numerati 0–5:

| # | Passo |
|---|---|
| 0 | creazione itinerario |
| 1 | customer |
| 2 | lettura pax |
| 3 | scrittura pax |
| 4 | lettura del totale |
| 5 | link di pagamento |

- Prima di ogni passo il job rilegge l'ordine: se è `cancelled`, si ferma.
- Ogni passo salva il proprio esito: `itinerary_id` e `total` sull'ordine, `step` sul job. Una ripresa riparte dal primo passo non completato.
- Il job prenota `5 − passi_HofJ_completati` chiamate. Se non ci sono, aspetta la finestra successiva.

**Esiti degli errori:**

| Errore | Esito |
|---|---|
| rete, timeout, 5xx | `attempts + 1`, `run_after` = finestra successiva; al terzo → ordine `failed` con motivo leggibile |
| 429 | budget azzerato, riprova nella finestra successiva, non conta come tentativo |
| errore del prodotto, solo al passo 0 | prodotto `bookable=false`; nuova proposta con `_propose`; ordine `replaced` con `replacement_proposal_id` |
| 401 / 403 | `failed` (configurazione), prodotto non marcato |

- Un prodotto marcato torna candidato dopo 24 ore: `choose` riceve `now` e lo lascia passare se `bookable_checked_at` è più vecchio di 24 ore.
- Una creazione d'itinerario riuscita lo riabilita.

**Prenotazione (RF-23, RF-24, RF-51).** Il checkout replay e, dopo M6, il webhook di Stripe fanno `mark_paid` e accodano un job `booking`.

- Il job prenota 1 chiamata di classe `booking`, poi `create_booking` → `confirmed`.
- Su rete o 5xx ci sono 5 tentativi, con attese di 5, 10, 20 e 40 s tra un tentativo e l'altro, poi `booking_failed`. Un 4xx porta subito a `booking_failed`.
- Al boot gli ordini `paid_pending_booking` senza un job attivo ne ricevono uno (RF-27).

**Rinuncia (RF-49).** Un `reject_proposal` su una proposta con ordine `queued`, in lavorazione o `awaiting_payment` porta l'ordine a `cancelled` e restituisce la proposta successiva. Dopo il pagamento l'ordine non si tocca.

**Posizione e attesa (RF-48).** La posizione è `1 + purchase in stato pending con enqueued_at precedente`. L'attesa è `ceil(posizione × 60 ÷ ((108 − 21) ÷ 5))` secondi e si ricalcola a ogni `get_order_status`.

**Contratto di `get_order_status`.** Campi sempre presenti, `null` quando non pertinenti: `order_id, status, position, wait_seconds, total, currency, price_from_total, total_differs, payment_url, booking_code, failure_reason, proposal_changed, proposal, say`. Il campo `proposal` ha la forma RF-06 solo se lo stato è `replaced`. MCP e REST usano lo stesso `to_dict`.

**Frasi `say`, in italiano:**

| Stato | Frase |
|---|---|
| `queued` | «Ti ho messo in coda: tra circa N minuti il link di pagamento sarà pronto. Chiedimi a che punto è quando vuoi.» |
| `awaiting_payment` | se il totale differisce, lo dice prima («Il totale reale è 720 euro invece di 700»), poi «il link di pagamento è in chat» |
| `replaced` | la nuova proposta, introdotta da «Quel viaggio non è più disponibile, ti propongo…», senza citare l'errore |
| `cancelled` / `failed` | frase propria; per `failed` con il motivo |

**Superfici**
- Descrizioni MCP di `accept_proposal` e `get_order_status` aggiornate (RF-41: la risposta è un'attesa e il link si legge con `get_order_status`).
- `/health` riporta la quota da `QuotaStore.snapshot()`.
- REST: vedi la domanda qui sotto.

**Test.** Ogni microtask è in TDD con `unittest`:
- finti in memoria e un `Clock` avanzabile a mano;
- un contratto condiviso da `MemoryJobs`/`PostgresJobs` e `MemoryQuota`/`PostgresQuota`;
- un test Postgres con due thread sullo stesso contatore che non superano mai il limite (saltato senza `DATABASE_URL`);
- `hofj_http` testato con `httpx.MockTransport`;
- `Worker.drain()` sincrono per i test di flusso.

- 🔧 AskUserQuestion

- 🔧 Write /Users/matteodospina/.claude/plans/leggi-la-task-m8-frolicking-snowflake.md

- 🔧 ToolSearch

- 🔧 ExitPlanMode

- 🔧 Bash: Copy plan into docs and append decisions

- 🔧 Bash: Commit the M5 plan and decisions

Il piano di esecuzione per M5 è in `docs/plans/2026-09-25-m5-hofj-reale.md` e le decisioni dell'intervista sono state aggiunte in fondo a `docs/decisions.md`. Tutto è committato sul branch `task/m5`; non ho ancora scritto codice né lanciato test.

**Come è organizzato.** Venti microtask, dal Task 0 al Task 19. Ognuno in TDD, con i file da toccare, le interfacce che usa e che produce, i nomi dei test e un commit. In fondo c'è una tabella che collega ogni test di completamento della roadmap ai task e ai test che lo coprono.

**Le decisioni principali dell'intervista:**
- **Verifiche di §8:** su staging, al massimo 8 chiamate HofJ più 1 chiamata Stripe in modalità test per ottenere il `paymentIntentId`.
- **Quota:** finestra fissa di 60 s allineata a HofJ, margine del 10% sul limite (quindi 108 chiamate utili) e riserva di 21 per le prenotazioni.
- **Worker:** thread dentro ogni processo, 4 per istanza, che prelevano i job dalla tabella con `FOR UPDATE SKIP LOCKED`.
- **Accettazione via REST:** risponde 202 con posizione e attesa. Le risposte di accettazione e di stato hanno una forma fissa, con `null` sui campi non pertinenti.
- **Modalità `live`:** si ferma all'avvio finché M6 non porta Stripe. Questo si discosta dalla roadmap ed è annotato in `docs/decisions.md`.

**Quando lanci l'esecuzione, il Task 1 non procede da solo.** Il piano lo segna come manuale: prima di fare chiamate reali ti dichiaro quali e quante, e aspetto il tuo OK. Servono `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND` e `STRIPE_SECRET_KEY` nell'ambiente. Se HofJ rifiuta il nostro `paymentIntentId`, l'esecuzione si ferma e ti chiedo come procedere, perché cambia il design di M6.

**Cosa non mi convince del tutto:**
- Il criterio che distingue un errore del prodotto da un guasto di rete legge il testo del campo `detail` nei 502 di HofJ. È fragile, e va confermato con le risposte reali del Task 1.
- Con 4 thread e acquisti da circa 20 secondi, una singola istanza fa circa 12 acquisti al minuto, sotto i 17,4 che la quota permetterebbe. Quindi, con una sola istanza, la stima di attesa sarà ottimistica. Lo vedremo nel load test di M13.
- Se M6 aggiunge anch'essa una migrazione `0003`, chi mergia per secondo deve rinumerare la propria.

Il log di sessione che l'hook ha aggiunto al commit ha "m8" nel nome, perché lo prende dal titolo della sessione. Il contenuto riguarda M5.

## Utente 18:20

aspetta pero continuo a non capire perche il massimo dell 8 chiamate,

## Agente 18:21

- 🔧 Bash: Trace origin of the 8-call limit

- 🔧 Bash: Search session logs for the 8-call rationale

Non c'è una ragione documentata per il numero 8. Il valore compare solo alla riga 240 di `docs/roadmap.md`, entrato con il commit `3c7d152`, lo stesso che ha creato la roadmap. Non ha una motivazione in `docs/decisions.md` né nei log di sessione in `agent-log/`. La spiegazione che ti ho dato prima, cioè 7 chiamate necessarie più 1 di margine, era una mia ricostruzione, non una decisione registrata da qualche parte.

Di tecnico c'è solo questo:
- **Un tetto serve.** `CLAUDE.md` chiede di dichiarare quante chiamate si fanno verso servizi esterni. Inoltre la quota di HofJ è di 120 chiamate al minuto ed è condivisa con chiunque usi la stessa chiave.
- **Il numero giusto dipende da cosa si vuole verificare.** Per rispondere alla domanda principale di §8, cioè se HofJ accetta un pagamento fatto sul nostro Stripe, serve un booking su un carrello completo:

| # | Chiamata | Perché serve |
|---|---|---|
| 1 | `GET /v1/quota` | limite reale |
| 2 | `POST /v1/itineraries` | la chiave può creare carrelli? |
| 3 | `PUT …/customer` | il carrello va completato prima del booking |
| 4 | `GET …/pax` | servono i `refId` per il passo 5 |
| 5 | `PUT …/pax` | completa il carrello |
| 6 | `GET /v1/itineraries/{id}` | dove sta il totale reale |
| 7 | `POST /v1/bookings` | la risposta a §8 riga 3 |

Quindi il minimo è 7. Tutto il resto è margine per eventuali ripetizioni, per esempio un 502 da timeout che su staging è già capitato. Che il tetto sia 8, 9 o 10 è una scelta, non un calcolo. Rispetto alle 120 chiamate al minuto della quota la differenza è trascurabile.

Nella riga che ho scritto in `docs/decisions.md` la motivazione suona più solida di quanto sia. La correggo così: «7 chiamate necessarie + N di margine per ripetizioni; il valore 8 della roadmap non ha una motivazione registrata». Scegli tu N, oppure tengo 8 come nella roadmap (1 di margine).

## Utente 18:22

/superpowers:test-driven-development: docs/plans/2026-09-25-m5-hofj-reale.md

## Agente 18:22

- 🔧 Bash: Run baseline suite and check env vars presence

Ho seguito il piano con TDD. Il Task 0 era già fatto (piano e decisioni committati). La suite di partenza è verde: 390 test, 12 saltati perché manca `DATABASE_URL`.

Il Task 1 (verifiche di §8 su staging) però non può partire: nell'ambiente di questa sessione mancano `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND` e `STRIPE_SECRET_KEY`. Ho controllato solo che ci fossero, senza leggerne il valore.

Per le verifiche ti propongo di fare 7 chiamate a HofJ più 1 di margine, cioè tenere l'8 della roadmap, e 1 chiamata a Stripe in modalità test. Non mi hai ancora detto quanto margine vuoi: se non indichi altro resto su 8 e correggo la motivazione in `docs/decisions.md` come ti ho detto.

Vedo due strade:

1. **Mi dai le chiavi e faccio il Task 1 adesso.** Il modo più semplice è esportarle nel profilo della shell (per esempio `~/.zshrc`) e riavviare la sessione, perché ogni comando che lancio parte da lì. Prima di ogni chiamata ti chiedo comunque l'OK.
2. **Rimando il Task 1 e passo al Task 2.** Dal Task 2 al Task 14 il lavoro non dipende da HofJ reale e si testa con finti in memoria. Solo l'adapter HTTP (Task 15) ha bisogno delle forme reali, quindi farei il Task 1 appena prima.

Ti consiglio la seconda, così non resti bloccato sulle chiavi. `CLAUDE.md` chiede un task alla volta: quale scegli? Se scegli la seconda parto dal Task 2 (i nuovi parametri in `Settings`) e mi fermo a riferirti dopo quel task.

## Utente 18:30

cos'è HOFJ_BRAND?

## Agente 18:30

- 🔧 Bash: Find documentation of HOFJ_BRAND

- 🔧 Bash: Read brand parameter docs

`HOFJ_BRAND` dice a HofJ **per quale sito di vendita stiamo lavorando**. HofJ serve più siti di viaggi, che chiama "distribution channel" o "brand", e ognuno ha il proprio catalogo e i propri prezzi. Il valore finisce nel parametro `?brand=` che l'adapter aggiunge a ogni chiamata.

**I brand che esistono** (da `docs/api/distribution-channels.md`):

| Ambiente | Brand disponibili |
|---|---|
| Produzione (`api.hofj.com`) | `weebora.com` (padel, il default se il parametro manca), `terrarossa.com`, `booking.hofj.com` |
| Staging (`staging.api.hofj.com`) | `staging.weebora.com`, `staging.tennis.weebora.com`, `staging.hofj.com` |

- **Si può usare il nome o il dominio.** HofJ accetta sia il nome (`Weebora`) sia il dominio (`weebora.com`).
- **Un brand sconosciuto dà 400.** HofJ risponde con un messaggio esplicito.
- **In replay non serve.** Nel README risulta obbligatorio solo in modalità `live`.

**Per noi:**

- **Valore per il Task 1:** `HOFJ_BRAND=staging.weebora.com`, cioè il brand che abbiamo scelto per le verifiche su staging (`docs/decisions.md:279`).
- **Non è un segreto,** a differenza di `HOFJ_API_KEY`. È un nome pubblico, quindi puoi scriverlo anche in chiaro qui in chat.
- **Va abbinato all'host giusto:** `HOFJ_BASE_URL=https://staging.api.hofj.com`. Un brand di staging su un host di produzione darebbe 400.

Di segreti restano quindi solo `HOFJ_API_KEY` e `STRIPE_SECRET_KEY`, che devono arrivare dall'ambiente e non dalla chat.

La domanda di prima resta aperta: faccio il Task 1 adesso, dopo che hai impostato le chiavi, oppure lo rimando a prima del Task 15 e parto dal Task 2?

## Utente 18:32

invece la HOFJ_API_KEY non è VELA_API_TOKEN?

## Agente 18:32

No, sono due chiavi diverse che vanno in direzioni opposte:

| | `HOFJ_API_KEY` | `VELA_API_TOKEN` |
|---|---|---|
| Direzione | **in uscita**: Vela → HofJ | **in entrata**: client → Vela |
| Chi la rilascia | HofJ (è la chiave del brief, profilo `internal`) | la scegliamo noi, è un segreto qualsiasi |
| Dove si usa | `Authorization: Bearer …` su ogni chiamata a `api.hofj.com`/`staging.api.hofj.com`, dentro l'adapter HTTP | i client la devono presentare per chiamare la nostra REST `/v1/*` (M4); se manca, `/v1/*` risponde 503 `rest-not-configured` |
| Serve per il Task 1 | **sì** | no |

In pratica `HOFJ_API_KEY` è il nostro badge per entrare in HofJ, mentre `VELA_API_TOKEN` è il badge che chiediamo a chi vuole entrare da noi. Se usassimo lo stesso valore per tutte e due, chiunque abbia accesso alla nostra REST potrebbe chiamare HofJ a nostro nome e consumarci la quota.

Una cosa utile da sapere: in M1 gli script di registrazione del catalogo leggevano la chiave HofJ anche da `API_BEAR_KEY`, se `HOFJ_API_KEY` mancava (`docs/decisions.md`). Se nel tuo ambiente la chiave HofJ si chiama così, è quella giusta per il Task 1. L'app però legge solo `HOFJ_API_KEY`.

## Utente 18:33

ok ho messo le chiavi, dimmi se va

## Agente 18:33

- 🔧 Bash: Check which keys are set without printing secrets

- 🔧 Bash: Check .env existence and zsh profile vars without values

- 🔧 Bash: Look for precedent on loading .env

- 🔧 Bash: Check how M1 ran scripts with the key

C'è un precedente in M1: le variabili si caricano con `set -a; . ./.env; set +a` nella stessa shell del comando, senza mai aprire né stampare il file. Controllo che ci siano.

- 🔧 Bash: Load .env silently and report which keys are present

Le chiavi ci sono tutte. Le ho caricate dal `.env` con `set -a; . ./.env; set +a`, come in M1, senza aprire né stampare il file. Ho mostrato solo i due valori che non sono segreti.

| Variabile | Esito |
|---|---|
| `HOFJ_API_KEY` | presente |
| `STRIPE_SECRET_KEY` | presente, **chiave di test** (`sk_test_…`) ✓ |
| `HOFJ_BASE_URL` | `api.hofj.com/v1/` ⚠️ |
| `HOFJ_BRAND` | `Weebora` ⚠️ |

**Due problemi prima del Task 1:**

1. **L'ambiente è produzione, non staging.** `api.hofj.com` con il brand `Weebora` è il sito vero. Nell'intervista abbiamo deciso staging perché lì un booking non crea una prenotazione reale. Con questi valori il `POST /v1/bookings` rischierebbe una prenotazione vera. Per staging servono:
   ```
   HOFJ_BASE_URL=https://staging.api.hofj.com
   HOFJ_BRAND=staging.weebora.com
   ```
   Resta un'incognita: non so se la tua chiave vale anche su staging. Una decisione precedente (`docs/decisions.md:78`) prevedeva di tornare a produzione se staging non accettava la chiave.

2. **Il formato di `HOFJ_BASE_URL`.** Manca lo schema `https://` e c'è già `/v1/` in fondo. L'adapter aggiunge i percorsi completi (`/v1/itineraries` e simili), quindi uscirebbe `api.hofj.com/v1//v1/itineraries`. Il formato atteso è solo `https://host`. Anche lo script di M1 (`scripts/api_explore.py`) costruisce gli URL così.

Non ho fatto nessuna chiamata. Come vuoi procedere?
- **Correggi il `.env` per staging** con i due valori sopra, e poi ti dichiaro le chiamate.
- **Resti su produzione.** In questo caso propongo di fermarmi prima del booking, cioè 6 chiamate. La verifica della riga 3 di §8 si farebbe su staging o in M7, e andrebbe registrata come modifica della decisione.

## Utente 18:35

cambiato

## Agente 18:35

- 🔧 Bash: Reload .env and verify corrected values

Ricaricato, ma nel `.env` i valori non sono ancora quelli giusti:

| Variabile | Adesso | Serve |
|---|---|---|
| `HOFJ_BASE_URL` | `https://staging.hofj.com/` | `https://staging.api.hofj.com` |
| `HOFJ_BRAND` | `Weebora` | `staging.weebora.com` |

- **`staging.hofj.com` non è l'host delle API.** Nei documenti compare come brand, cioè il sito di vendita di staging di House of Journey, non come host. Le API rispondono su `staging.api.hofj.com`, che è l'host dove sono stati verificati i carrelli (`docs/easter-eggs.md`). Va bene anche con la `/` finale: la tolgo io nell'adapter.
- **`Weebora` è il brand di produzione.** Su staging il brand verificato è `staging.weebora.com`. Con `Weebora` staging potrebbe rispondere 400 «brand sconosciuto», oppure usare un catalogo diverso da quello di prova.

Quando hai corretto il file dimmelo e ricontrollo. Finché i valori non tornano non faccio nessuna chiamata.

## Utente 18:35

fartto

## Agente 18:35

- 🔧 Bash: Reload .env and verify corrected values

Ora il brand è giusto (`staging.weebora.com`). `HOFJ_BASE_URL` invece è ancora `https://staging.hofj.com/`: forse la riga non è stata salvata.

Deve essere:
```
HOFJ_BASE_URL=https://staging.api.hofj.com
```
Nota il `.api.` in mezzo al nome. Senza, le chiamate andrebbero al sito di vendita e non alle API.

## Utente 18:36

fartto

## Agente 18:36

- 🔧 Bash: Reload .env and verify corrected values

Adesso è tutto a posto:

| Variabile | Valore |
|---|---|
| `HOFJ_BASE_URL` | `https://staging.api.hofj.com` ✓ |
| `HOFJ_BRAND` | `staging.weebora.com` ✓ |
| `HOFJ_API_KEY` | presente ✓ |
| `STRIPE_SECRET_KEY` | chiave di test ✓ |

## Task 1: le chiamate che farei

**Su HofJ staging, 7 chiamate più al massimo 1 ripetizione (8 in tutto):**

| # | Chiamata | Dati |
|---|---|---|
| 1 | `GET /v1/quota` | — |
| 2 | `POST /v1/itineraries?brand=staging.weebora.com&locale=it` | `{"productId":118,"startDate":"2026-12-08","adults":2,"rooms":1,"currency":"EUR"}`, la stessa combinazione già riuscita su staging (`docs/easter-eggs.md`) |
| 3 | `PUT …/customer` | un cliente di prova con dati finti (Mario Rossi, email `test@example.com`) e l'indirizzo nel formato del contratto OAS: `street1`, `postalCode`, `city`, `region`, `countryCode` |
| 4 | `GET …/pax` | — |
| 5 | `PUT …/pax` | nomi finti, `refId` invariati |
| 6 | `GET /v1/itineraries/{id}` | lettura del totale reale |
| 7 | `POST /v1/bookings` | `{itineraryId, paymentType:"full", paymentIntentId, paymentStatus:"succeeded"}` |
| (8) | una sola ripetizione | solo se una chiamata risponde 502 per timeout; altrimenti non la faccio |

**Su Stripe, 1 chiamata in modalità test**, tra la 6 e la 7:
- Crea un `PaymentIntent` per il totale letto alla chiamata 6, confermato con la carta di prova `pm_card_visa`.
- Non si muove denaro vero.

**Come le eseguo:**
- Uno script temporaneo nella cartella di lavoro della sessione (scratchpad), fuori dal repo. Carica le chiavi dal `.env` con `set -a` e non stampa mai chiavi né token.
- Mi fermo alla prima risposta inattesa: un 403 sulla chiamata 2 o un booking rifiutato.
- Salvo per ogni chiamata lo stato HTTP e la forma della risposta, poi ti riporto l'esito prima di scrivere in `docs/`.

Il booking crea una prenotazione sull'ambiente di staging (non reale) e non abbiamo un modo per cancellarla. Procedo?

## Utente 18:37

vai

## Agente 18:37

- 🔧 Write /private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-task-m5/4e77c5e2-1cbd-49a4-a46b-71f152659842/scratchpad/s8_checks.py

- 🔧 Bash: Run the section 8 checks against HofJ staging

- 🔧 Bash: Check the earlier successful staging itinerary call

Mi sono fermato alla seconda chiamata, come previsto per una risposta inattesa. Finora ho usato **2 chiamate HofJ su 8 e 0 Stripe**.

| # | Chiamata | Esito |
|---|---|---|
| 1 | `GET /v1/quota` | 200: `limitPerMinute` 120, client `test-dev-2`, finestra di 60 s con inizio e fine (`windowStartedAt`/`windowEndsAt`), come abbiamo modellato |
| 2 | `POST /v1/itineraries` (prodotto 118, `locale=it`) | **502** `upstream-error`, con `detail`: `Brand "staging.weebora.com" POST /itinerary returned 404 … NOT_FOUND_ERROR … {"productId":118,"locale":"it"}` |

**Perché è fallita.** Il carrello riuscito in `docs/easter-eggs.md` usava `locale=en`, noi abbiamo mandato `locale=it`. Su staging il prodotto 118 sembra esistere solo in inglese: la chiave, il brand e il profilo interno funzionano (niente 403), manca il prodotto nella lingua richiesta.

**Cosa ci dice già questo errore:**
- **Riga 1 di §8:** probabilmente superata, visto che non è arrivato un 403. Lo confermerà un carrello creato.
- **Errore del prodotto:** è un caso reale del criterio che abbiamo deciso: un 502 il cui `detail` riporta un 404 upstream va trattato come errore del prodotto. Userò questo testo nei test dell'adapter (Task 15).
- **La lingua conta nella creazione del carrello.** L'app usa `it`, quindi un prodotto non tradotto fallirebbe al passo 0. In produzione il catalogo `it` di M1 esiste, ma è un rischio da annotare.

**Per continuare** rifarei la stessa chiamata con `locale=en`. Il conto diventa esattamente 8: le 2 già fatte, il nuovo tentativo e le 5 che restano (customer, lettura pax, scrittura pax, lettura del totale, booking), più 1 chiamata Stripe. Non resta margine: se qualcosa va in timeout mi fermo e ti chiedo.

Scegli tu:
1. **Riprovo con `locale=en`**, con budget fisso a 8. Ti consiglio questa: è la combinazione già verificata.
2. **Alzo il budget a 9**, per avere di nuovo 1 ripetizione di margine.
3. **Mi fermo qui** e registro l'esito parziale.

## Utente 18:39

riprova con en

## Agente 18:39

- 🔧 Bash: Prepare rerun with locale en and carried-over call count

- 🔧 Bash: Rerun section 8 checks with locale en

- 🔧 Bash: Inspect recorded response shapes

Il flusso completo è passato su staging. Ho usato **8 chiamate HofJ su 8** e **1 Stripe**.

| # | Chiamata | Esito |
|---|---|---|
| 1 | `GET /v1/quota` | 200: limite 120, finestra fissa di 60 s |
| 2 | `POST /v1/itineraries` con `locale=it` | 502: il prodotto 118 non esiste in italiano su staging |
| 3 | `POST /v1/itineraries` con `locale=en` | 200: `itineraryId` `dlp5lyj338uf`, `meta: {now}` |
| 4 | `PUT …/customer` (indirizzo nel formato OAS) | 200: `data: {now}`, `meta: {}` |
| 5 | `GET …/pax` | 200: `refId` `pax-1`, `pax-2`. **Il primo passeggero è già compilato dai dati del cliente** |
| 6 | `PUT …/pax` | 200 |
| 7 | `GET /v1/itineraries/{id}` | 200 (dettagli sotto) |
| — | Stripe `PaymentIntent` di test | `succeeded`, 368,00 € |
| 8 | `POST /v1/bookings` con `paymentIntentId` | **200**: `{"data": "dlp5lyj338uf", "meta": {"now": …}}` |

**Tre cose che cambiano le nostre ipotesi:**

1. **Il booking non restituisce un codice `R-…`.** Restituisce lo stesso `itineraryId`. Il nostro `booking_code` sarà quindi quell'id. La frase «La tua prenotazione è confermata, codice R-789012» leggerebbe una stringa come `dlp5lyj338uf`. Si può fare, ma al telefono va scandita lettera per lettera.

2. **Non sappiamo ancora se HofJ controlla il pagamento.** La risposta 200 dice che il booking è stato accettato, ma non se HofJ ha verificato il `paymentIntentId` o lo ha ignorato. La riga 3 di §8 chiede proprio questo: «rifiuta **o ignora**». Per saperlo servirebbero:
   - 1 chiamata in più, `GET /v1/itineraries/{id}`, per vedere se `checkout.status` passa da `BookingInitiated` a uno stato pagato o confermato;
   - oppure un secondo booking con un `paymentIntentId` inventato: se risponde 200 anche quello, il campo viene ignorato.

3. **Il totale non è univoco.** `checkout` contiene tre importi:

   | Campo | Importo |
   |---|---|
   | `total` | 368 € |
   | `totalPrice` | 368,00 € |
   | `originalTotal` | 337 € |
   | `openAmount` | 337 € |

   Il pagamento di prova è stato di 368 €. Non so da cosa venga la differenza di 31 € (commissioni? un supplemento sull'hotel preselezionato, che nel carrello vale 157 €?). Per il link di pagamento propongo `checkout.total`, perché coincide con `totalPrice`.

**Cosa ti propongo adesso:**
- **Per sciogliere il punto 2:** alzare il budget di 1 o 2 chiamate. Consiglio la sola lettura dell'itinerario dopo il booking, che costa 1 chiamata e non crea nulla.
- **Poi:** registrare tutto in `docs/decisions.md` e `docs/api/internal-checkout.md` e fare il commit del Task 1, annotando anche la questione della lingua (`it` contro `en`) e il fatto che il `booking_code` è l'`itineraryId`.

Faccio la chiamata di controllo in più?

## Utente 18:42

si alza il budget e per annota

## Agente 18:42

- 🔧 Bash: One extra call: read itinerary state after booking

- 🔧 Bash: Read internal-checkout doc structure

Nessuna novità dopo il booking: `checkout.status` è ancora `BookingInitiated` e `openAmount` resta a 337 €. Registro tutto nei documenti.

- 🔧 Bash: Record section 8 results in docs

- 🔧 Bash: Commit Task 1 results
