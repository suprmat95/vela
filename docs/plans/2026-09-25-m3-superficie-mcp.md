# M3 — Superficie MCP e primo test da claude.ai: piano di esecuzione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m3`. Destinazione di questo file: `docs/plans/2026-09-25-m3-superficie-mcp.md`.

**Goal:** un connector custom di claude.ai collegato a `https://vela-n506.onrender.com/mcp` (modalità replay) vede cinque tool con i nomi di RF-39 e completa il flusso di spec §10.1: proposta singola, rifiuto con motivo, altra proposta singola, accettazione, link di pagamento, pagamento simulato, stato `confirmed` con codice `R-…`.

**Architecture:** `vela/surfaces/mcp.py` è un adapter sottile sopra i casi d'uso di `Vela` (M2): argomenti piatti → `TravelerProfile` → caso d'uso → `to_dict()` restituito come `structuredContent` e come testo JSON in un `CallToolResult`. Gli errori diventano un `CallToolResult` con `isError=true` e una frase italiana pronta da leggere. Il server è un `MCPServer` dell'SDK `mcp` 2.2.0 con trasporto Streamable HTTP stateless e risposte JSON; le sue route (`/mcp`) sono innestate nel router FastAPI della stessa app e il session manager gira nel lifespan dell'app. Nessuna autenticazione fino a M8.

**Tech Stack:** Python 3.12 (`uv run python`), FastAPI, SDK `mcp` 2.2.0 (già in `uv.lock`), `httpx` (già dipendenza), `unittest` (`IsolatedAsyncioTestCase` per il client MCP in-process). Nessuna dipendenza nuova.

**Spec:** `docs/spec.md` (RF-10, RF-39, RF-41, RF-42, RF-43, §10.1, §10.6), `docs/roadmap.md` sezione M3. Il design approvato nell'intervista è la sezione "Design" qui sotto; le decisioni sono nella tabella "Decisioni prese nell'intervista".

## Contesto

- Esiste già (M2): `vela/domain/usecases.py` con `Vela` e i cinque casi d'uso; `NotFound(kind, id)` con `kind` in `intent`, `proposal`, `order` (definita in `vela/domain/orders.py`, riesportata da `vela/domain/usecases.py`); le risposte con `to_dict()` in `vela/domain/models.py` (contratto nella sezione "Contratto di `to_dict()`" del piano M2); `vela/domain/say.py` con le frasi italiane; `GET /replay/checkout/{order_id}` in `vela/surfaces/replay.py`; `create_app(settings, vela, runner, catalog_loader)` in `vela/app.py`.
- Helper di test esistenti in `tests/support.py`: `NOW`, `make_product`, `FakeHofJ` (codice di prenotazione `R-000001`, `fail_itinerary` per far fallire l'accettazione), `StubPayments` (link `http://pay.test/<order_id>`), `count_products`, `assert_single_product`.
- Verifiche fatte sull'SDK `mcp` 2.2.0 durante l'intervista (spike nello scratchpad, buttati):
  - `from mcp.server.mcpserver import MCPServer`; `from mcp import Client`; `Client(server)` si collega in-process a un `MCPServer`, `Client("https://…/mcp")` via Streamable HTTP.
  - I tool `def` sincroni vengono eseguiti dall'SDK in un thread (`anyio.to_thread.run_sync`): i casi d'uso sincroni vanno bene così.
  - Un tool annotato `-> dict` non produce `structuredContent`; `-> Dict[str, Any]` con `structured_output=True` lo incapsula in `{"result": …}`. Un tool annotato `-> CallToolResult` viene restituito così com'è: è la forma scelta.
  - Un `ToolError` diventa testo `"Error executing tool <nome>: <messaggio>"`; un'eccezione qualsiasi diventa `str(exc)` nel risultato. Per questo il wrapper dei tool intercetta tutte le eccezioni e costruisce da sé il risultato d'errore.
  - Le descrizioni degli argomenti con `Annotated[T, Field(description=…)]` compaiono nello schema.
  - `app.mount("/mcp", …)` con `streamable_http_path="/"` risponde **307** a `POST /mcp`. `app.mount("/", …)` funziona ma trasforma `POST /health` da 405 a 404. Innestare `streamable_http_app(streamable_http_path="/mcp").routes` in `app.router.routes` dà 200 su `/mcp` e lascia intatti 405 e 404.
  - Senza `transport_security` esplicito l'SDK accetta solo host `127.0.0.1`/`localhost` (421 per `testserver` e per l'host di Render). Host rifiutato → 421, Origin rifiutato → 403.
  - Una sottoapp montata non esegue il proprio lifespan: `server.session_manager.run()` va aperto nel lifespan FastAPI. `session_manager` esiste solo dopo `streamable_http_app(…)` ed è avviabile una sola volta per istanza (ogni test crea la propria app).
- **Comportamento noto, non si corregge in M3:** con il chooser di M2 il rifiuto non interpreta il motivo, quindi "troppo caro" produce la proposta successiva per prezzo crescente, cioè **più cara** (sul catalogo replay: 279 € → 300 € → 355 €). La proposta "più economica" di §10.1 arriva con M9. In M3 test e smoke verificano "proposta diversa"; `docs/acceptance.md` registra il criterio 1 in replay come parziale.
- Interprete: i test si eseguono con `uv run python -m unittest …` (Python 3.12); il `python3` di sistema è 3.7.

## Decisioni prese nell'intervista (da riportare in `docs/decisions.md`, Task 0)

| Decisione | Scelta | Motivo |
|---|---|---|
| Trasporto MCP | Streamable HTTP stateless (`stateless_http=True`) con risposte JSON (`json_response=True`) | Nessuna sessione in memoria: regge riavvii e sleep del piano free di Render e client semplici (ElevenLabs). Lo stato vive già in Postgres |
| Montaggio | Le route di `streamable_http_app(streamable_http_path="/mcp")` sono innestate in `app.router.routes`; `session_manager.run()` nel lifespan dell'app | `Mount("/mcp")` risponde 307 a `POST /mcp`; `Mount("/")` trasformerebbe i 405 in 404 |
| Argomenti dei tool | Piatti: `first_name`, `last_name`, `email`, `phone` opzionali, `participants` lista di `{first_name, last_name}`; `create_intent` ha anche `pax` | Schema semplice da compilare per un modello vocale; `accept_proposal` si richiama finché `missing` è vuoto |
| Risultato dei tool | `CallToolResult` con `structuredContent` = `to_dict()` del caso d'uso e lo stesso JSON come testo; nessun `outputSchema`, nessun campo `kind` aggiunto | Contratto di M2 invariato; il modello distingue le varianti dalle chiavi (`question`, `failed_criterion`, `missing`) |
| Errori | `isError=true` con una sola frase italiana: `say_not_found(kind)` per id sconosciuti, `say_unavailable()` senza dominio, `say_error()` per eccezioni inattese (loggate con `logger.exception` su `vela.mcp`, mai nel risultato) | Il modello legge una frase utile invece di uno stack trace; nessun dettaglio interno esce |
| Lingua | Istruzioni del server e descrizioni dei tool in inglese; `say` resta italiano (M2) | I modelli seguono meglio le istruzioni in inglese; giudici anglofoni |
| Protezione DNS rebinding | Attiva. Host ammessi: `localhost`, `127.0.0.1` (con qualunque porta), `testserver`, host di `VELA_PUBLIC_URL`. Origin ammessi: `https://claude.ai`, `http://localhost:*`, `http://127.0.0.1:*`, origin di `VELA_PUBLIC_URL`; richieste senza Origin accettate | Difesa gratuita dell'SDK, nessuna variabile d'ambiente nuova |
| Dominio assente | `/mcp` sempre montato; senza `DATABASE_URL` ogni tool risponde `isError` con `say_unavailable()` | `/mcp` non va mai in crash; stesso comportamento di `/replay/checkout` (503) |
| Deploy e prova | Merge su `master` fatto dall'utente → autodeploy Render; smoke test automatico con `scripts/mcp_smoke.py` contro l'URL live (solo replay, nessun costo); conversazione in claude.ai fatta dall'utente; esiti in `docs/acceptance.md` | Il connector di claude.ai si configura solo dall'account dell'utente |
| "Troppo caro" | Resta a M9: in M3 il rifiuto produce una proposta diversa, non necessariamente più economica; criterio 1 in replay registrato come parziale | M3 resta solo superficie; nessun conflitto con il worktree di M9 su `intent.py`/`usecases.py` |

## Global Constraints

- Nessuna dipendenza nuova in `pyproject.toml`; nessuna modifica a `uv.lock`.
- `uv run python -m unittest discover -s tests` verde senza servizi esterni e senza `DATABASE_URL`.
- Mai aprire, stampare o loggare `.env`, chiavi o token.
- Nessuna variabile d'ambiente nuova oltre quelle di spec §6.
- `vela/domain` non importa `mcp`, `fastapi`, `pydantic`, `httpx`: l'unico file di dominio toccato è `vela/domain/say.py`.
- Nessuna modifica al contratto `to_dict()` di M2 né ai casi d'uso.
- Nessuna risposta contiene più di un prodotto (RF-10): ogni `structuredContent` passa `assert_single_product`.
- `say` e i testi d'errore senza markdown e senza URL (RF-42); l'URL sta solo in `payment_url`.
- Ogni descrizione di tool contiene la frase `Never list` e il riferimento `` `say` `` (RF-41).
- Nomi dei tool esattamente: `create_intent`, `get_proposal`, `reject_proposal`, `accept_proposal`, `get_order_status`.
- `/mcp` senza autenticazione (RF-43, ponte fino a M8).
- Commit piccoli, uno per task, messaggio imperativo in inglese come nella storia del repo, con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nessun force push, nessun merge o push senza OK dell'utente.

## Review Focus

1. `POST /mcp` senza slash finale deve rispondere 200, non 307: claude.ai non ripete un POST dopo un redirect. Test in Task 3 (`test_post_mcp_is_not_redirected`).
2. `VELA_PUBLIC_URL` scritta con slash o percorso finale (`https://vela-n506.onrender.com/`) deve comunque ammettere l'host di Render; senza, ogni chiamata da claude.ai riceve 421. Test in Task 3 (`test_public_url_host_is_accepted`, `test_allowed_hosts_from_public_url`).
3. Un errore inatteso dentro un caso d'uso (per esempio un fallimento dell'itinerario) non deve far uscire il messaggio interno verso il modello. Test in Task 2 (`test_unexpected_error_is_generic_and_logged`).
4. `accept_proposal` chiamato prima con dati parziali e poi con tutti i dati: la prima chiamata non crea ordini, la seconda crea l'ordine, una terza restituisce lo stesso ordine. Con `participants: []` e 2 persone i dati del secondo partecipante risultano mancanti. Test in Task 2 (`test_full_flow_section_10_1`, `test_empty_participants_are_missing`).
5. Argomenti mancanti o di tipo sbagliato (`create_intent` senza `text`) devono dare un risultato `isError`, non un errore HTTP 500. Test in Task 2 (`test_invalid_arguments_are_a_tool_error`).

---

## Design

### Struttura dei file

```
vela/domain/say.py            + say_not_found(kind), say_unavailable(), say_error()
vela/surfaces/mcp.py          INSTRUCTIONS, DESCRIPTIONS, TOOL_NAMES, build_mcp(get_vela),
                              allowed_hosts, allowed_origins, mcp_routes(server, public_url)
vela/app.py                   app.state.mcp; route /mcp innestate; session manager nel lifespan
scripts/mcp_smoke.py          run_flow(client, open_url, …) e main(argv): flusso §10.1 contro un URL
docs/acceptance.md            tabella dei 7 criteri di §10
README.md                     sezione "Collegare Claude (connector MCP)"
docs/decisions.md             decisioni di M3
tests/test_say.py             + NotFoundSayTest
tests/test_mcp_tools.py       tool in-process: elenco, schema, flusso, errori, RF-10
tests/test_mcp_http.py        /mcp nell'app FastAPI: JSON stateless, host/origin, altre route
tests/test_mcp_smoke.py       run_flow contro l'app replay in-process
```

### Flusso dei dati

1. claude.ai → `POST /mcp` (JSON-RPC) → route innestata → `TransportSecurityMiddleware` (Host/Origin) → `MCPServer` → tool `def` in un thread.
2. Tool → `run(name, use_case)`: `get_vela()` è `None` → `say_unavailable()`; altrimenti caso d'uso → `ok(response)` = `CallToolResult(structuredContent=response.to_dict(), content=[TextContent(json)])`.
3. `NotFound` → `fail(say_not_found(exc.kind))`; qualunque altra eccezione → `log.exception` + `fail(say_error())`.
4. `accept_proposal` restituisce `payment_url` = `<VELA_PUBLIC_URL>/replay/checkout/<order_id>`: l'utente lo apre dalla chat, `GET /replay/checkout` (M2) segna il pagamento e prenota; `get_order_status` restituisce `confirmed` e il codice.

### Istruzioni e descrizioni

Testo definitivo nel codice di Task 2 (`INSTRUCTIONS`, `DESCRIPTIONS`). Regole: una sola proposta alla volta, mai elencare o confrontare alternative, leggere `say` alla lettera nella lingua dell'utente, mai leggere gli URL ad alta voce, mostrare `payment_url` come link, chiamare `get_proposal` subito dopo `create_intent`, `accept_proposal` solo dopo un "sì" esplicito.

---

### Task 0: Piano e decisioni nel repo

**Files:**
- Create: `docs/plans/2026-09-25-m3-superficie-mcp.md` (questo file)
- Modify: `docs/decisions.md` (in coda)

- [ ] **Step 1: Aggiungere in coda a `docs/decisions.md`** una sezione `## 2026-09-25 — M3: superficie MCP` con la riga di origine `Origine: intervista sulla macro task M3, piano in docs/plans/2026-09-25-m3-superficie-mcp.md.` e la tabella "Decisioni prese nell'intervista" di questo piano, copiata integralmente.

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-09-25-m3-superficie-mcp.md docs/decisions.md
git commit -m "Add the M3 execution plan and record the interview decisions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Frasi d'errore in `say.py`

**Files:**
- Modify: `vela/domain/say.py` (in coda)
- Test: `tests/test_say.py` (nuova classe in coda)

**Interfaces:**
- Produces: `say_not_found(kind: str) -> str` (`kind` ∈ `intent`, `proposal`, `order`, altrimenti frase generica), `say_unavailable() -> str`, `say_error() -> str`.

- [ ] **Step 1: Scrivere il test che fallisce** in coda a `tests/test_say.py`:

```python
class NotFoundSayTest(unittest.TestCase):
    def test_each_kind_has_its_own_sentence(self):
        sentences = {kind: say.say_not_found(kind) for kind in ("intent", "proposal", "order")}
        self.assertEqual(len(set(sentences.values())), 3)
        self.assertIn("proposta", sentences["proposal"])
        self.assertIn("ordine", sentences["order"])
        self.assertIn("richiesta", sentences["intent"])

    def test_unknown_kind_is_generic(self):
        self.assertTrue(say.say_not_found("boh"))
        self.assertNotIn(say.say_not_found("boh"), [say.say_not_found("order")])

    def test_error_sentences_are_speakable(self):
        for s in (say.say_not_found("intent"), say.say_not_found("proposal"),
                  say.say_not_found("order"), say.say_not_found("x"),
                  say.say_unavailable(), say.say_error()):
            self.assertNotIn("http", s)
            self.assertNotIn("**", s)
            self.assertNotIn("`", s)
            self.assertTrue(s.endswith("."))
```

- [ ] **Step 2: Eseguire e verificare che fallisca**

Run: `uv run python -m unittest discover -s tests -p test_say.py -v`
Expected: FAIL con `AttributeError: module 'vela.domain.say' has no attribute 'say_not_found'`

- [ ] **Step 3: Implementare** in coda a `vela/domain/say.py`:

```python
_NOT_FOUND = {
    "intent": "Non ritrovo questa richiesta di viaggio: dimmi di nuovo che viaggio hai in mente e riparto da lì.",
    "proposal": "Non ritrovo questa proposta: dimmi di nuovo che viaggio hai in mente e te ne preparo una.",
    "order": ("Non ritrovo questo ordine: controlla il link di pagamento che ti ho mandato, "
              "oppure ripartiamo dal viaggio che hai in mente."),
}


def say_not_found(kind: str) -> str:
    return _NOT_FOUND.get(kind, "Non ritrovo quello che mi chiedi: ripartiamo dal viaggio che hai in mente.")


def say_unavailable() -> str:
    return "Vela non è disponibile in questo momento: riprova tra qualche minuto."


def say_error() -> str:
    return "Qualcosa non ha funzionato dalla mia parte: riprova tra poco."
```

- [ ] **Step 4: Eseguire e verificare che passi**

Run: `uv run python -m unittest discover -s tests -p test_say.py -v`
Expected: PASS (tutti i test di `test_say.py`)

- [ ] **Step 5: Commit**

```bash
git add vela/domain/say.py tests/test_say.py
git commit -m "Add the spoken sentences for unknown ids, unavailable service and errors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Server MCP con i cinque tool

**Files:**
- Create: `vela/surfaces/mcp.py`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `Vela` e `NotFound` da `vela.domain.usecases`; `TravelerProfile`, `Participant` da `vela.domain.models`; `say.say_not_found/say_unavailable/say_error` (Task 1).
- Produces:
  - `TOOL_NAMES: tuple[str, ...]` = `("create_intent", "get_proposal", "reject_proposal", "accept_proposal", "get_order_status")`
  - `INSTRUCTIONS: str`, `DESCRIPTIONS: dict[str, str]`
  - `build_mcp(get_vela: Callable[[], Optional[Vela]]) -> MCPServer`
  - `allowed_hosts(public_url: Optional[str]) -> list[str]`, `allowed_origins(public_url: Optional[str]) -> list[str]`
  - `mcp_routes(server: MCPServer, public_url: Optional[str]) -> list` (route Starlette da innestare; usata in Task 3)
  - `MCP_PATH = "/mcp"`

- [ ] **Step 1: Scrivere i test che falliscono** in `tests/test_mcp_tools.py`:

```python
"""Tool MCP in-process (RF-39, RF-41, RF-10): client dell'SDK collegato al server senza HTTP."""
import json
import unittest
from datetime import timedelta

from mcp import Client

from support import NOW, FakeHofJ, StubPayments, assert_single_product, make_product
from vela.adapters.background import InlineRunner
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain import say
from vela.domain.intent import QUESTION_PAX
from vela.domain.usecases import Vela
from vela.surfaces.mcp import DESCRIPTIONS, TOOL_NAMES, build_mcp

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
TRAVELER = {"first_name": "Anna", "last_name": "Rossi", "email": "anna@x.it", "phone": "+390000",
            "participants": [{"first_name": "Bo", "last_name": "Bi"}]}
PRODUCTS = [
    make_product(1, price=300, country="IT", destination="Riccione"),
    make_product(2, price=450, country="ES", destination="Madrid"),
    make_product(3, price=350, country="ES", destination="Valencia"),
    make_product(4, price=390, country="ES", destination="Lanzarote"),
]


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_vela(products=None, hofj=None):
    repos = MemoryRepositories()
    repos.products.upsert_many(PRODUCTS if products is None else products)
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, hofj or FakeHofJ(), StubPayments(), now=Clock(), new_id=lambda: next(ids))


class McpCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.vela = make_vela()
        self.server = build_mcp(lambda: self.vela)

    async def call(self, name, **args):
        async with Client(self.server) as client:
            return await client.call_tool(name, args)

    async def ok(self, name, **args):
        r = await self.call(name, **args)
        self.assertFalse(r.is_error, r.content[0].text if r.content else r)
        assert_single_product(self, r.structured_content)
        return r.structured_content

    async def error_text(self, name, **args):
        r = await self.call(name, **args)
        self.assertTrue(r.is_error)
        self.assertIsNone(r.structured_content)
        return r.content[0].text


class ListToolsTest(McpCase):
    async def tools(self):
        async with Client(self.server) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    async def test_five_tools_named_as_rf39(self):
        self.assertEqual(set(await self.tools()), {"create_intent", "get_proposal", "reject_proposal",
                                                   "accept_proposal", "get_order_status"})
        self.assertEqual(set(TOOL_NAMES), set(await self.tools()))

    async def test_descriptions_are_written_for_voice(self):
        for name, tool in (await self.tools()).items():
            self.assertEqual(tool.description, DESCRIPTIONS[name])
            self.assertIn("Never list", tool.description, name)
            self.assertIn("`say`", tool.description, name)

    async def test_traveler_arguments_are_flat(self):
        tools = await self.tools()
        accept = tools["accept_proposal"].input_schema
        self.assertEqual(accept["required"], ["proposal_id"])
        for field in ("first_name", "last_name", "email", "phone", "participants"):
            self.assertIn(field, accept["properties"])
        self.assertEqual(accept["properties"]["participants"]["anyOf"][0]["type"], "array")
        intent = tools["create_intent"].input_schema
        self.assertEqual(intent["required"], ["text"])
        self.assertIn("pax", intent["properties"])


class FlowTest(McpCase):
    async def test_full_flow_section_10_1(self):
        intent = await self.ok("create_intent", text=INTENT)
        self.assertEqual(intent["intent_id"], "id1")
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        second = await self.ok("reject_proposal", proposal_id=first["proposal_id"], reason="troppo caro")
        self.assertNotEqual(second["product"]["product_id"], first["product"]["product_id"])

        partial = await self.ok("accept_proposal", proposal_id=second["proposal_id"], first_name="Anna")
        self.assertIn("last_name", partial["missing"])
        self.assertIsNone(self.vela.repos.orders.get_by_proposal(second["proposal_id"]))

        accepted = await self.ok("accept_proposal", proposal_id=second["proposal_id"], **TRAVELER)
        self.assertEqual(accepted["status"], "awaiting_payment")
        self.assertTrue(accepted["payment_url"].startswith("http://pay.test/"))
        again = await self.ok("accept_proposal", proposal_id=second["proposal_id"], **TRAVELER)
        self.assertEqual(again["order_id"], accepted["order_id"])

        self.vela.orders.mark_paid(accepted["order_id"], "pi_test")
        InlineRunner(self.vela.orders).submit(accepted["order_id"])
        status = await self.ok("get_order_status", order_id=accepted["order_id"])
        self.assertEqual(status["status"], "confirmed")
        self.assertEqual(status["booking_code"], "R-000001")
        self.assertIn("R-000001", status["say"])

    async def test_question_persists_nothing(self):
        d = await self.ok("create_intent", text="padel a ottobre")
        self.assertEqual(d, {"question": QUESTION_PAX, "say": QUESTION_PAX})
        self.assertIsNone(self.vela.repos.intents.get("id1"))

    async def test_profile_arguments_reach_the_intent(self):
        d = await self.ok("create_intent", text="padel a ottobre", first_name="Anna", pax=2)
        profile = self.vela.repos.intents.get(d["intent_id"]).profile
        self.assertEqual((profile.first_name, profile.pax), ("Anna", 2))

    async def test_empty_participants_are_missing(self):
        intent = await self.ok("create_intent", text=INTENT)
        proposal = await self.ok("get_proposal", intent_id=intent["intent_id"])
        args = dict(TRAVELER, participants=[])
        d = await self.ok("accept_proposal", proposal_id=proposal["proposal_id"], **args)
        self.assertEqual(d["missing"], ["participants[0].first_name", "participants[0].last_name"])

    async def test_no_match_names_the_criterion(self):
        self.vela = make_vela(products=[])
        intent = await self.ok("create_intent", text=INTENT)
        d = await self.ok("get_proposal", intent_id=intent["intent_id"])
        self.assertIn("failed_criterion", d)

    async def test_text_content_mirrors_structured_content(self):
        r = await self.call("create_intent", text=INTENT)
        self.assertEqual(json.loads(r.content[0].text), r.structured_content)


class ErrorsTest(McpCase):
    async def test_unknown_ids_read_a_sentence(self):
        cases = [("get_proposal", {"intent_id": "nope"}, "intent"),
                 ("reject_proposal", {"proposal_id": "nope", "reason": "no"}, "proposal"),
                 ("accept_proposal", {"proposal_id": "nope"}, "proposal"),
                 ("get_order_status", {"order_id": "nope"}, "order")]
        for name, args, kind in cases:
            with self.subTest(name):
                self.assertEqual(await self.error_text(name, **args), say.say_not_found(kind))

    async def test_unexpected_error_is_generic_and_logged(self):
        self.vela = make_vela(hofj=FakeHofJ(fail_itinerary=RuntimeError("segreto interno")))
        intent = await self.ok("create_intent", text=INTENT)
        proposal = await self.ok("get_proposal", intent_id=intent["intent_id"])
        with self.assertLogs("vela.mcp", "ERROR") as logs:
            text = await self.error_text("accept_proposal", proposal_id=proposal["proposal_id"], **TRAVELER)
        self.assertEqual(text, say.say_error())
        self.assertNotIn("segreto", text)
        self.assertIn("accept_proposal", logs.output[0])

    async def test_domain_unavailable(self):
        self.server = build_mcp(lambda: None)
        self.assertEqual(await self.error_text("get_order_status", order_id="x"), say.say_unavailable())

    async def test_invalid_arguments_are_a_tool_error(self):
        r = await self.call("create_intent")
        self.assertTrue(r.is_error)


class AllowedHostsTest(unittest.TestCase):
    def test_allowed_hosts_from_public_url(self):
        from vela.surfaces.mcp import allowed_hosts
        self.assertIn("vela-n506.onrender.com", allowed_hosts("https://vela-n506.onrender.com/"))
        self.assertIn("vela-n506.onrender.com", allowed_hosts("https://vela-n506.onrender.com/x/y"))
        self.assertIn("localhost:8000", allowed_hosts("http://localhost:8000"))
        self.assertEqual(allowed_hosts(None), ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*",
                                               "testserver"])

    def test_allowed_origins_from_public_url(self):
        from vela.surfaces.mcp import allowed_origins
        origins = allowed_origins("https://vela-n506.onrender.com/")
        self.assertIn("https://claude.ai", origins)
        self.assertIn("https://vela-n506.onrender.com", origins)
        self.assertEqual(allowed_origins(None), ["https://claude.ai", "http://localhost:*",
                                                 "http://127.0.0.1:*"])
```

- [ ] **Step 2: Eseguire e verificare che fallisca**

Run: `uv run python -m unittest discover -s tests -p test_mcp_tools.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'vela.surfaces.mcp'`

- [ ] **Step 3: Implementare** `vela/surfaces/mcp.py`:

```python
"""Superficie MCP (RF-41): i cinque casi d'uso di RF-39 come tool Streamable HTTP su ``/mcp``.

Adapter sottile: argomenti piatti → ``TravelerProfile`` → caso d'uso → ``to_dict()``, restituito
come ``structuredContent`` e come testo JSON. Gli errori diventano un risultato ``isError`` con
una frase italiana pronta da leggere, mai un messaggio interno. Trasporto stateless con risposte
JSON; nessuna autenticazione fino a M8 (RF-43). Le istruzioni sono in inglese, ``say`` in italiano.
"""
import json
import logging
from typing import Annotated, Callable, List, Optional
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from vela.domain import say
from vela.domain.models import Participant, TravelerProfile
from vela.domain.usecases import NotFound, Vela

log = logging.getLogger("vela.mcp")

MCP_PATH = "/mcp"
TOOL_NAMES = ("create_intent", "get_proposal", "reject_proposal", "accept_proposal", "get_order_status")
LOCAL_HOSTS = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "testserver"]
LOCAL_ORIGINS = ["http://localhost:*", "http://127.0.0.1:*"]
CLAUDE_ORIGIN = "https://claude.ai"

INSTRUCTIONS = (
    "Vela books a padel or tennis trip with hotel from one sentence of the user. "
    "Always propose exactly ONE option at a time: never list, compare or invent alternatives, "
    "and never search or suggest trips yourself. After every tool call, speak the `say` field "
    "to the user verbatim, in the user's language. Never read URLs aloud: when there is a "
    "payment link, tell the user it is in the chat. Call get_proposal right after create_intent "
    "returns an intent_id."
)

_VOICE = (" Speak the `say` field verbatim. Never list alternatives, never compare options, "
          "never mention other trips.")

DESCRIPTIONS = {
    "create_intent": (
        "Start a trip request from the user's own words (sport, place, period, number of people, "
        "budget). Pass the user's sentence verbatim in `text`; add traveler details only if the "
        "user already gave them. Returns either `intent_id` (then call get_proposal immediately) "
        "or `question` (ask the user exactly that question, then call create_intent again with "
        "the original sentence plus the answer)." + _VOICE),
    "get_proposal": (
        "Get the single trip Vela proposes for an intent. Returns one proposal (`proposal_id`, "
        "`product`, dates, price from) or, when nothing fits, `failed_criterion`: then ask the "
        "user to rephrase the request. After speaking the proposal, ask if the user likes it."
        + _VOICE),
    "reject_proposal": (
        "The user said no to the current proposal. Pass the user's reason in their own words "
        "(e.g. 'troppo caro', 'preferisco il mare'). Returns the next single proposal, or "
        "`failed_criterion` when nothing else fits." + _VOICE),
    "accept_proposal": (
        "Call only after the user explicitly says yes to the current proposal. Pass the details "
        "the user gave you: first_name, last_name, email and phone of the main traveler, plus "
        "first and last name of every other participant. If the result has `missing`, ask the "
        "user only for those details and call accept_proposal again with everything you have: "
        "calling it again never creates a second order. On success the result has `order_id`, "
        "the real `total` and `payment_url`: show `payment_url` as a clickable link in the chat "
        "and never read it aloud." + _VOICE),
    "get_order_status": (
        "Check an order when the user says they paid or asks how it is going. Returns `status` "
        "(awaiting_payment, paid_pending_booking, confirmed, booking_failed, expired) and, when "
        "confirmed, `booking_code`." + _VOICE),
}


class ParticipantArg(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


Text = Annotated[str, Field(description="The user's request, verbatim, in their own words.")]
FirstName = Annotated[Optional[str], Field(description="Main traveler's first name, only if the user said it.")]
LastName = Annotated[Optional[str], Field(description="Main traveler's last name, only if the user said it.")]
Email = Annotated[Optional[str], Field(description="Main traveler's email, only if the user said it.")]
Phone = Annotated[Optional[str], Field(description="Main traveler's phone number, only if the user said it.")]
Pax = Annotated[Optional[int], Field(description="Number of travelers, only if the user said it.")]
Participants = Annotated[Optional[List[ParticipantArg]],
                         Field(description="First and last name of each traveler other than the main one.")]
IntentId = Annotated[str, Field(description="The intent_id returned by create_intent.")]
ProposalId = Annotated[str, Field(description="The proposal_id of the current proposal.")]
Reason = Annotated[str, Field(description="Why the user said no, in their own words.")]
OrderId = Annotated[str, Field(description="The order_id returned by accept_proposal.")]


def traveler_profile(first_name=None, last_name=None, email=None, phone=None, pax=None,
                     participants=None) -> TravelerProfile:
    return TravelerProfile(first_name=first_name, last_name=last_name, email=email, phone=phone,
                           pax=pax, participants=tuple(Participant(p.first_name, p.last_name)
                                                       for p in participants or ()))


def ok(response) -> CallToolResult:
    d = response.to_dict()
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(d, ensure_ascii=False))],
                          structured_content=d)


def fail(sentence: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=sentence)], is_error=True)


def build_mcp(get_vela: Callable[[], Optional[Vela]]) -> MCPServer:
    """Server MCP con i cinque tool. ``get_vela`` è letto a ogni chiamata: l'app lo imposta dopo."""
    server = MCPServer("vela", title="Vela", instructions=INSTRUCTIONS, version="0.1.0")

    def run(name: str, use_case: Callable[[Vela], object]) -> CallToolResult:
        vela = get_vela()
        if vela is None:
            return fail(say.say_unavailable())
        try:
            return ok(use_case(vela))
        except NotFound as exc:
            return fail(say.say_not_found(exc.kind))
        except Exception:   # noqa: BLE001 - nessun dettaglio interno verso il modello
            log.exception("tool MCP %s fallito", name)
            return fail(say.say_error())

    @server.tool(description=DESCRIPTIONS["create_intent"])
    def create_intent(text: Text, first_name: FirstName = None, last_name: LastName = None,
                      email: Email = None, phone: Phone = None, pax: Pax = None,
                      participants: Participants = None) -> CallToolResult:
        profile = traveler_profile(first_name, last_name, email, phone, pax, participants)
        return run("create_intent", lambda v: v.create_intent(text, profile))

    @server.tool(description=DESCRIPTIONS["get_proposal"])
    def get_proposal(intent_id: IntentId) -> CallToolResult:
        return run("get_proposal", lambda v: v.get_proposal(intent_id))

    @server.tool(description=DESCRIPTIONS["reject_proposal"])
    def reject_proposal(proposal_id: ProposalId, reason: Reason = "") -> CallToolResult:
        return run("reject_proposal", lambda v: v.reject_proposal(proposal_id, reason))

    @server.tool(description=DESCRIPTIONS["accept_proposal"])
    def accept_proposal(proposal_id: ProposalId, first_name: FirstName = None,
                        last_name: LastName = None, email: Email = None, phone: Phone = None,
                        participants: Participants = None) -> CallToolResult:
        profile = traveler_profile(first_name, last_name, email, phone, None, participants)
        return run("accept_proposal", lambda v: v.accept_proposal(proposal_id, profile))

    @server.tool(description=DESCRIPTIONS["get_order_status"])
    def get_order_status(order_id: OrderId) -> CallToolResult:
        return run("get_order_status", lambda v: v.get_order_status(order_id))

    return server


def allowed_hosts(public_url: Optional[str]) -> List[str]:
    hosts = list(LOCAL_HOSTS)
    netloc = urlparse(public_url).netloc if public_url else ""
    if netloc and netloc not in hosts:
        hosts.append(netloc)
    return hosts


def allowed_origins(public_url: Optional[str]) -> List[str]:
    origins = [CLAUDE_ORIGIN] + LOCAL_ORIGINS
    parsed = urlparse(public_url) if public_url else None
    if parsed is not None and parsed.scheme and parsed.netloc:
        origins.append("%s://%s" % (parsed.scheme, parsed.netloc))
    return origins


def mcp_routes(server: MCPServer, public_url: Optional[str]) -> list:
    """Route Streamable HTTP su ``/mcp`` da innestare nel router FastAPI.

    Innestate e non montate: ``Mount("/mcp")`` risponde 307 a ``POST /mcp`` e ``Mount("/")``
    trasformerebbe i 405 dell'app in 404. ``server.session_manager.run()`` va aperto nel
    lifespan dell'app, perché le route innestate non eseguono il lifespan della sottoapp.
    """
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                         allowed_hosts=allowed_hosts(public_url),
                                         allowed_origins=allowed_origins(public_url))
    http = server.streamable_http_app(streamable_http_path=MCP_PATH, json_response=True,
                                      stateless_http=True, transport_security=security)
    return list(http.routes)
```

- [ ] **Step 4: Eseguire e verificare che passi**

Run: `uv run python -m unittest discover -s tests -p test_mcp_tools.py -v`
Expected: PASS (15 test). Se `test_traveler_arguments_are_flat` fallisce solo per la forma di `participants` nello schema (per esempio `$ref` al posto di `anyOf`), stampare lo schema, adeguare l'asserzione alla forma reale mantenendo il controllo "array di oggetti", e annotarlo nel riepilogo del task.

- [ ] **Step 5: Commit**

```bash
git add vela/surfaces/mcp.py tests/test_mcp_tools.py
git commit -m "Add the MCP server with the five voice-ready tools

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `/mcp` nell'app FastAPI

**Files:**
- Modify: `vela/app.py` (`create_app` e il suo lifespan; docstring del modulo)
- Test: `tests/test_mcp_http.py`

**Interfaces:**
- Consumes: `build_mcp`, `mcp_routes` (Task 2); `create_app(settings, vela, runner, catalog_loader)` (M2).
- Produces: `app.state.mcp: MCPServer`; `POST /mcp` Streamable HTTP stateless con risposte JSON in ogni modalità (`replay` o no, con o senza dominio).

- [ ] **Step 1: Scrivere i test che falliscono** in `tests/test_mcp_http.py`:

```python
"""`/mcp` montato nell'app FastAPI: JSON-RPC su HTTP, stateless, protezione Host/Origin."""
import unittest

from fastapi.testclient import TestClient

from support import NOW, FakeHofJ, StubPayments, make_product
from vela.adapters.background import InlineRunner
from vela.adapters.repo_memory import MemoryRepositories
from vela.app import create_app
from vela.config import Settings
from vela.domain import say
from vela.domain.usecases import Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"}}


def make_app(public_url="http://test", with_domain=True):
    vela = None
    runner = None
    if with_domain:
        repos = MemoryRepositories()
        repos.products.upsert_many([make_product(3, price=350, country="ES", destination="Valencia")])
        vela = Vela(repos, FakeHofJ(), StubPayments(), now=lambda: NOW)
        runner = InlineRunner(vela.orders)
    return create_app(Settings(vela_upstream_mode="replay", vela_public_url=public_url),
                      vela=vela, runner=runner, catalog_loader=None)


def rpc(client, method, params=None, **headers):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=dict(HEADERS, **headers), follow_redirects=False)


class McpHttpTest(unittest.TestCase):
    def test_post_mcp_is_not_redirected(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "initialize", INIT)
        self.assertEqual(r.status_code, 200)

    def test_initialize_is_stateless_json(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "initialize", INIT)
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        self.assertNotIn("mcp-session-id", r.headers)
        result = r.json()["result"]
        self.assertEqual(result["serverInfo"]["name"], "vela")
        self.assertIn("exactly ONE", result["instructions"])

    def test_tools_list_over_http(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "tools/list", **{"MCP-Protocol-Version": "2025-06-18"})
        names = {t["name"] for t in r.json()["result"]["tools"]}
        self.assertEqual(names, {"create_intent", "get_proposal", "reject_proposal",
                                 "accept_proposal", "get_order_status"})

    def test_tool_call_over_http(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "tools/call", {"name": "create_intent", "arguments": {"text": INTENT}},
                    **{"MCP-Protocol-Version": "2025-06-18"})
        result = r.json()["result"]
        self.assertFalse(result.get("isError", False))
        self.assertIn("intent_id", result["structuredContent"])

    def test_without_domain_tools_say_unavailable(self):
        with TestClient(create_app(Settings())) as c:
            r = rpc(c, "tools/call", {"name": "get_order_status", "arguments": {"order_id": "x"}},
                    **{"MCP-Protocol-Version": "2025-06-18"})
        result = r.json()["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], say.say_unavailable())


class McpSecurityTest(unittest.TestCase):
    def test_unknown_host_is_421(self):
        with TestClient(make_app()) as c:
            self.assertEqual(rpc(c, "initialize", INIT, Host="evil.example").status_code, 421)

    def test_public_url_host_is_accepted(self):
        with TestClient(make_app(public_url="https://vela-n506.onrender.com/")) as c:
            r = rpc(c, "initialize", INIT, Host="vela-n506.onrender.com")
        self.assertEqual(r.status_code, 200)

    def test_foreign_origin_is_403(self):
        with TestClient(make_app()) as c:
            self.assertEqual(rpc(c, "initialize", INIT, Origin="https://evil.example").status_code, 403)

    def test_claude_origin_is_accepted(self):
        with TestClient(make_app()) as c:
            self.assertEqual(rpc(c, "initialize", INIT, Origin="https://claude.ai").status_code, 200)


class OtherRoutesTest(unittest.TestCase):
    def test_other_routes_are_unchanged(self):
        with TestClient(make_app()) as c:
            self.assertEqual(c.post("/health").status_code, 405)
            self.assertEqual(c.get("/nope").status_code, 404)
            self.assertEqual(c.get("/replay/checkout/nope").status_code, 404)
            self.assertIn(c.get("/health").status_code, (200, 503))

    def test_mcp_route_is_present_in_every_mode(self):
        for settings in (Settings(), Settings(vela_upstream_mode="live")):
            paths = [getattr(r, "path", None) for r in create_app(settings).routes]
            self.assertIn("/mcp", paths)
```

- [ ] **Step 2: Eseguire e verificare che fallisca**

Run: `uv run python -m unittest discover -s tests -p test_mcp_http.py -v`
Expected: FAIL (`/mcp` risponde 404; `test_mcp_route_is_present_in_every_mode` fallisce con `'/mcp' not found`)

- [ ] **Step 3: Implementare** in `vela/app.py`.

Aggiungere l'import:

```python
from vela.surfaces.mcp import build_mcp, mcp_routes
```

Nella docstring del modulo, dopo la prima frase, aggiungere: ``La superficie MCP (M3) è innestata su ``/mcp`` in ogni modalità; il suo session manager gira nel lifespan.``

Sostituire il lifespan e il fondo di `create_app` con:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with app.state.mcp.session_manager.run():
            if app.state.vela is not None:
                app.state.bootstrap = bootstrap(app.state.vela, app.state.runner, app.state.catalog_loader)
            yield
            if app.state.runner is not None:
                app.state.runner.shutdown(wait=False)

    app = FastAPI(title="Vela", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.vela = vela
    app.state.runner = runner
    app.state.catalog_loader = catalog_loader
    app.state.bootstrap = None
    app.state.mcp = build_mcp(lambda: app.state.vela)
    app.include_router(health_router)
    if settings.vela_upstream_mode == REPLAY:
        app.include_router(replay_router)
    app.router.routes.extend(mcp_routes(app.state.mcp, settings.vela_public_url))
    return app
```

- [ ] **Step 4: Eseguire e verificare che passi, poi la suite completa**

Run: `uv run python -m unittest discover -s tests -p test_mcp_http.py -v`
Expected: PASS (11 test)

Run: `uv run python -m unittest discover -s tests`
Expected: OK (i test Postgres `skipped` senza `DATABASE_URL`); in particolare `test_app_replay.py` e `test_health.py` restano verdi.

- [ ] **Step 5: Commit**

```bash
git add vela/app.py tests/test_mcp_http.py
git commit -m "Serve the MCP surface on /mcp as stateless JSON with host and origin checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Smoke test del flusso §10.1 contro un URL

**Files:**
- Create: `scripts/mcp_smoke.py`
- Test: `tests/test_mcp_smoke.py`

**Interfaces:**
- Consumes: `app.state.mcp` (Task 3), `GET /replay/checkout/{order_id}` (M2).
- Produces: `run_flow(client, open_url, expected_base=None, attempts=10, delay=1.0) -> dict` (chiavi `first`, `second`, `order_id`, `total`, `booking_code`); `SmokeFailure`; `base_of(mcp_url) -> str`; `main(argv) -> int` (0 ok, 1 fallito, 2 uso errato).

- [ ] **Step 1: Scrivere i test che falliscono** in `tests/test_mcp_smoke.py`:

```python
"""Smoke test MCP (scripts/mcp_smoke.py) contro l'app replay in-process, catalogo della fixture."""
import os
import random
import sys
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from mcp import Client

from support import NOW
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.usecases import Vela

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_smoke  # noqa: E402


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_app(preload=True):
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    if preload:
        repos.products.upsert_many(hofj.load_catalog())
    vela = Vela(repos, hofj, FakePayments("http://test"), DEFAULT_TRAVELER, now=Clock())
    app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://test"),
                     vela=vela, runner=InlineRunner(vela.orders), catalog_loader=None)
    return app


class SmokeFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_flow_passes_against_the_replay_app(self):
        app = make_app()
        opened = []
        with TestClient(app) as tc:
            def open_url(url):
                opened.append(url)
                self.assertEqual(tc.get(urlparse(url).path).status_code, 200)

            async with Client(app.state.mcp) as client:
                summary = await mcp_smoke.run_flow(client, open_url, expected_base="http://test", delay=0)
        self.assertRegex(summary["booking_code"], r"^R-\d{6}$")
        self.assertNotEqual(summary["first"], summary["second"])
        self.assertEqual(len(opened), 1)

    async def test_payment_link_on_another_host_fails(self):
        app = make_app()
        with TestClient(app):
            async with Client(app.state.mcp) as client:
                with self.assertRaises(mcp_smoke.SmokeFailure) as ctx:
                    await mcp_smoke.run_flow(client, lambda url: None,
                                             expected_base="https://elsewhere.example", delay=0)
        self.assertIn("VELA_PUBLIC_URL", str(ctx.exception))

    async def test_empty_catalog_fails_at_get_proposal(self):
        app = make_app(preload=False)
        async with Client(app.state.mcp) as client:
            with self.assertRaises(mcp_smoke.SmokeFailure) as ctx:
                await mcp_smoke.run_flow(client, lambda url: None, delay=0)
        self.assertIn("get_proposal", str(ctx.exception))

    async def test_unpaid_order_is_reported(self):
        app = make_app()
        async with Client(app.state.mcp) as client:
            with self.assertRaises(mcp_smoke.SmokeFailure) as ctx:
                await mcp_smoke.run_flow(client, lambda url: None, attempts=2, delay=0)
        self.assertIn("awaiting_payment", str(ctx.exception))


class SmokeCliTest(unittest.TestCase):
    def test_usage(self):
        self.assertEqual(mcp_smoke.main([]), 2)

    def test_base_of(self):
        self.assertEqual(mcp_smoke.base_of("https://vela-n506.onrender.com/mcp"),
                         "https://vela-n506.onrender.com")

    def test_count_products(self):
        self.assertEqual(mcp_smoke.count_products({"a": [{"product_id": 1}, {"product_id": 2}]}), 2)
```

- [ ] **Step 2: Eseguire e verificare che fallisca**

Run: `uv run python -m unittest discover -s tests -p test_mcp_smoke.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'mcp_smoke'`

- [ ] **Step 3: Implementare** `scripts/mcp_smoke.py`:

```python
"""Smoke test della superficie MCP (M3): il flusso di spec §10.1 contro un server MCP.

Uso: uv run python scripts/mcp_smoke.py https://vela-n506.onrender.com/mcp

Solo per la modalità replay: il "pagamento" è la visita del link /replay/checkout/{order_id}.
Nessuna chiamata a HofJ né a Stripe; sul server restano un intento e un ordine di prova.
Richiede Python 3.12 (`uv run`), non il python3 di sistema. Il rifiuto "troppo caro" produce una
proposta diversa, non necessariamente più economica: l'interpretazione del motivo arriva con M9.
"""
import asyncio
import sys
from typing import Callable, Optional

import httpx
from mcp import Client

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
TRAVELER = {"first_name": "Prova", "last_name": "Smoke", "email": "smoke@example.com",
            "phone": "+390000000000",
            "participants": [{"first_name": "Seconda", "last_name": "Smoke"}]}
TOOL_NAMES = {"create_intent", "get_proposal", "reject_proposal", "accept_proposal",
              "get_order_status"}


class SmokeFailure(Exception):
    pass


def count_products(obj) -> int:
    """Dizionari con chiave `product_id` a qualunque profondità (RF-10)."""
    if isinstance(obj, dict):
        return (1 if "product_id" in obj else 0) + sum(count_products(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(count_products(v) for v in obj)
    return 0


async def call(client, name: str, args: dict, need: str) -> dict:
    r = await client.call_tool(name, args)
    if r.is_error:
        text = r.content[0].text if r.content else "?"
        raise SmokeFailure("%s ha risposto con un errore: %s" % (name, text))
    d = r.structured_content or {}
    if count_products(d) > 1:
        raise SmokeFailure("%s: più di un prodotto nella risposta (RF-10)" % name)
    if need not in d:
        raise SmokeFailure("%s: manca %r nella risposta: %s" % (name, need, d.get("say", d)))
    return d


async def run_flow(client, open_url: Callable[[str], None], expected_base: Optional[str] = None,
                   attempts: int = 10, delay: float = 1.0) -> dict:
    names = {t.name for t in (await client.list_tools()).tools}
    if names != TOOL_NAMES:
        raise SmokeFailure("tool attesi %s, trovati %s" % (sorted(TOOL_NAMES), sorted(names)))
    intent = await call(client, "create_intent", {"text": INTENT}, "intent_id")
    first = await call(client, "get_proposal", {"intent_id": intent["intent_id"]}, "proposal_id")
    second = await call(client, "reject_proposal",
                        {"proposal_id": first["proposal_id"], "reason": "troppo caro"}, "proposal_id")
    if second["product"]["product_id"] == first["product"]["product_id"]:
        raise SmokeFailure("reject_proposal ha riproposto lo stesso prodotto")
    accepted = await call(client, "accept_proposal",
                          dict(TRAVELER, proposal_id=second["proposal_id"]), "payment_url")
    url = accepted["payment_url"]
    if expected_base and not url.startswith(expected_base.rstrip("/") + "/"):
        raise SmokeFailure("il link di pagamento %s non punta a %s: VELA_PUBLIC_URL è impostata?"
                           % (url, expected_base))
    open_url(url)
    status = {}
    for _ in range(attempts):
        status = await call(client, "get_order_status", {"order_id": accepted["order_id"]}, "status")
        if status["status"] == "confirmed":
            return {"first": first["product"]["title"], "second": second["product"]["title"],
                    "order_id": accepted["order_id"], "total": accepted["total"],
                    "booking_code": status["booking_code"]}
        await asyncio.sleep(delay)
    raise SmokeFailure("ordine %s non confermato: stato %s"
                       % (accepted["order_id"], status.get("status")))


def open_with_httpx(url: str) -> None:
    httpx.get(url, timeout=30).raise_for_status()


def base_of(mcp_url: str) -> str:
    return mcp_url.rstrip("/").rsplit("/mcp", 1)[0]


async def main_async(url: str) -> dict:
    async with Client(url) as client:
        return await run_flow(client, open_with_httpx, expected_base=base_of(url))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: uv run python scripts/mcp_smoke.py <url>/mcp", file=sys.stderr)
        return 2
    try:
        summary = asyncio.run(main_async(argv[0]))
    except SmokeFailure as exc:
        print("FALLITO: %s" % exc, file=sys.stderr)
        return 1
    for key, value in summary.items():
        print("%s: %s" % (key, value))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Eseguire e verificare che passi**

Run: `uv run python -m unittest discover -s tests -p test_mcp_smoke.py -v`
Expected: PASS (7 test)

Run: `uv run python -m unittest discover -s tests`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add scripts/mcp_smoke.py tests/test_mcp_smoke.py
git commit -m "Add the MCP smoke test that runs the section 10.1 flow against a URL

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `docs/acceptance.md` e README

**Files:**
- Create: `docs/acceptance.md`
- Modify: `README.md` (nuova sezione dopo "Deploy su Render"; riga `vela/surfaces` in "Struttura")

**Interfaces:**
- Produces: la tabella che M4, M7, M12, M13, M14 e M15 aggiornano.

- [ ] **Step 1: Creare `docs/acceptance.md`** con questo contenuto:

```markdown
# Vela — criteri di accettazione (spec §10)

Una riga per ogni esecuzione di un criterio. Modalità: `replay` (HofJ e Stripe finti) o `live`.
Esito: `ok`, `parziale` (con il motivo nelle note), `fallito`, `da eseguire`.

| # | Criterio (spec §10) | Data | Modalità | Superficie | Esito | Note |
|---|---|---|---|---|---|---|
| 1 | Flusso da Claude via MCP: proposta singola, "troppo caro" → altra singola più economica, "sì" → link, pagamento, `confirmed` con codice | — | replay | MCP (claude.ai) | da eseguire | M3. In replay il rifiuto non interpreta il motivo (M9): la seconda proposta è diversa ma può essere più cara |
| 1 | idem | — | live | MCP (claude.ai) | da eseguire | M7 |
| 2 | Flusso da agente vocale ElevenLabs, link per testo | — | live | MCP (ElevenLabs) | da eseguire | M12 |
| 3 | Flusso via REST con `curl` e token | — | replay | REST | da eseguire | M4 |
| 3 | idem | — | live | REST | da eseguire | M7 |
| 4 | Prodotto che fallisce al carrello sostituito senza errore visibile | — | live | MCP/REST | da eseguire | M5, M7 |
| 5 | Suite verde e load test in replay, quota HofJ invariata | — | replay | REST | da eseguire | M13 |
| 6 | Nessuna risposta con più di un prodotto, su nessuna superficie | — | replay | MCP | da eseguire | M3: test automatici `tests/test_mcp_tools.py` e smoke `scripts/mcp_smoke.py`; REST in M4 |
| 7 | Nessuna chiave nel repo, `.env` mai letto dagli agenti | — | — | — | da eseguire | M14 |

## Registro delle esecuzioni

Per ogni esecuzione manuale: data, chi, comando o conversazione, esito, riferimenti (id ordine,
codice di prenotazione). Mai incollare token, chiavi o dati personali reali.
```

- [ ] **Step 2: Aggiungere a `README.md`** dopo la sezione "Deploy su Render":

````markdown
## Collegare Claude (connector MCP)

La superficie MCP è su `https://<servizio>.onrender.com/mcp` (Streamable HTTP, stateless, senza
autenticazione fino a M8). Su Render `VELA_PUBLIC_URL` deve essere l'URL pubblico del servizio:
serve al link di checkout replay ed è l'host che `/mcp` accetta (gli altri ricevono 421).

1. Verifica il servizio: `curl https://<servizio>.onrender.com/health`.
2. Smoke test del flusso di spec §10.1 (solo replay, nessuna chiamata a HofJ o Stripe; lascia un
   ordine di prova nel DB):
   `uv run python scripts/mcp_smoke.py https://<servizio>.onrender.com/mcp`
3. In claude.ai: Settings → Connectors → Add custom connector, nome `Vela`, URL
   `https://<servizio>.onrender.com/mcp`, nessuna autenticazione.
4. In una chat nuova, con il connector attivo: "Vorrei un weekend di padel in Spagna a ottobre,
   siamo in due, massimo 800 euro". Il pagamento in replay si simula aprendo il link ricevuto.

In replay "troppo caro" produce una proposta diversa ma non necessariamente più economica:
l'interpretazione del motivo del rifiuto arriva con M9.
````

Nella sezione "Struttura" sostituire la riga di `vela/surfaces` con:

```
vela/surfaces   health.py, replay.py (M2), mcp.py (M3), REST (M4), webhook (M6)
```

- [ ] **Step 3: Verificare** che la suite resti verde (`tests/test_docker_files.py` o test simili potrebbero leggere il README):

Run: `uv run python -m unittest discover -s tests`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add docs/acceptance.md README.md
git commit -m "Add the acceptance table and the guide to connect Claude to the MCP surface

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Deploy, smoke live e prova da claude.ai (manuale, guidato)

Nessun codice nuovo. Ogni passo che tocca `master`, Render o claude.ai si fa solo con l'OK esplicito dell'utente.

- [ ] **Step 1: Verifica finale del branch**

Run: `uv run python -m unittest discover -s tests`
Expected: OK. Riportare all'utente il numero di test e di `skipped`.

- [ ] **Step 2: Merge e deploy (utente).** Chiedere all'utente di fare il merge di `task/m3` su `master` e il push, come per M2 (Render fa l'autodeploy da `master`). Chiedere anche di verificare nella dashboard di Render che `VELA_PUBLIC_URL` sia `https://vela-n506.onrender.com`. Non fare merge né push senza OK.

- [ ] **Step 3: Health (1 chiamata a Render, nessun costo)**

Run: `curl -s https://vela-n506.onrender.com/health`
Expected: `{"status":"ok","db":"ok"}`. Il piano free può impiegare circa un minuto a svegliarsi.

- [ ] **Step 4: Smoke live.** Dichiarare prima all'utente: "una sessione MCP con 7 chiamate di tool e 1 GET di checkout contro Render, in replay; nessuna chiamata a HofJ o Stripe; lascia un intento e un ordine di prova nel DB di Render".

Run: `uv run python scripts/mcp_smoke.py https://vela-n506.onrender.com/mcp`
Expected: righe `first`, `second`, `order_id`, `total`, `booking_code: R-xxxxxx`, poi `OK`. Con 421 o `VELA_PUBLIC_URL` nel messaggio: la variabile su Render manca o è sbagliata. Correggerla (utente) e ripetere.

- [ ] **Step 5: Conversazione in claude.ai (utente).** Dare all'utente i passi 3-4 della sezione README "Collegare Claude". Chiedere che riporti:
  - (a) se claude.ai vede i 5 tool;
  - (b) se ogni risposta del modello propone un solo viaggio, senza elenchi;
  - (c) se dopo "troppo caro" arriva un'altra proposta;
  - (d) se dopo "sì" e i dati arriva il link;
  - (e) dopo aver aperto il link, lo stato `confirmed` e il codice.

- [ ] **Step 6: Registrare gli esiti** in `docs/acceptance.md`:
  - aggiornare le righe 1 (replay, MCP) e 6 con data, esito e note: "parziale" per il criterio 1 se la seconda proposta non è più economica, citando M9;
  - aggiungere una voce in "Registro delle esecuzioni" con la data, il comando smoke e il suo esito (id ordine e codice `R-…`), e la conversazione claude.ai riassunta senza dati personali.

  Aggiungere in coda a `docs/decisions.md` una sezione `## 2026-09-25 — M3: decisioni prese durante l'esecuzione`, solo se durante l'esecuzione sono emerse decisioni.

- [ ] **Step 7: Commit (sul branch indicato dall'utente)**

```bash
git add docs/acceptance.md docs/decisions.md
git commit -m "Record the M3 acceptance run from claude.ai in replay

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Copertura

| Requisito | Dove |
|---|---|
| RF-39 (cinque casi d'uso, stessi nomi) | Task 2 `test_five_tools_named_as_rf39`, Task 3 `test_tools_list_over_http` |
| RF-41 (Streamable HTTP su `/mcp`, descrizioni vocali) | Task 2 `test_descriptions_are_written_for_voice`, Task 3 `McpHttpTest`, Task 6 |
| RF-42 (`say` senza URL né markdown) | Task 1 `test_error_sentences_are_speakable`, `assert_single_product` in ogni test di Task 2 |
| RF-43 (`/mcp` senza auth fino a M8) | Task 3 (nessun header di auth nei test) |
| RF-10 / §10.6 (un solo prodotto) | Task 2 `McpCase.ok`, Task 4 `call` dello smoke |
| §10.1 in replay | Task 2 `test_full_flow_section_10_1`, Task 4, Task 6 |
