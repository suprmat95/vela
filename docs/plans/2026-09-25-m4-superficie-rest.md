# M4 — Superficie REST: piano di esecuzione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m4`. Destinazione di questo file: `docs/plans/2026-09-25-m4-superficie-rest.md`.

**Goal:** i cinque casi d'uso di RF-39 esposti via REST sotto `/v1` (RF-40) con bearer statico `VELA_API_TOKEN` (RF-43), errori RFC 7807 e `GET /health` arricchito con età del catalogo e quota nota (RNF-06).

**Architecture:** la superficie è un adapter sottile in `vela/surfaces/rest.py`: un `APIRouter` con prefisso `/v1` e due dependency (`require_token`, `get_vela`) che chiama `Vela` e restituisce `{"outcome": ..., **to_dict()}`. Gli errori sono prodotti da `vela/surfaces/problems.py`, i cui exception handler rispondono in `application/problem+json` solo sotto `/v1`. Il dominio non cambia; l'unica modifica a una porta è `ProductRepository.last_fetched_at()`, usata da `/health`.

**Tech Stack:** Python 3.12, FastAPI 0.141 (Pydantic 2.13, Starlette 1.7), SQLAlchemy Core 2, `unittest`. Nessuna dipendenza nuova.

**Spec:** `docs/spec.md` (RF-39, RF-40, RF-42, RF-43, RNF-06, §10.3, §10.6), `docs/roadmap.md` sezione M4, contratto `to_dict()` in `docs/plans/2026-09-25-m2-dominio-replay.md` ("Contratto di `to_dict()`"). Il design approvato nell'intervista è la sezione "Design" qui sotto.

## Contesto

- Esiste già: `Vela` in `vela/domain/usecases.py` con i cinque casi d'uso e `NotFound(kind, id)` (kind `intent`, `proposal`, `order`); le risposte in `vela/domain/models.py` con `to_dict()`; `profile_from_dict`; `vela/app.py` (`create_app(settings, vela, runner, catalog_loader)`, `app.state.vela` è `None` senza `DATABASE_URL`); `vela/surfaces/health.py` (solo stato DB); `vela/surfaces/replay.py` (`GET /replay/checkout/{order_id}`, gestisce da sé il proprio 404); `Settings.vela_api_token` letto da `VELA_API_TOKEN`; `render.yaml` dichiara già `VELA_API_TOKEN` con `sync: false`.
- `tests/support.py` ha `NOW`, `make_product`, `assert_single_product` (RF-10 + `say` senza URL né markdown). `tests/repo_contract.py` è il contratto dei repository eseguito su memoria (sempre) e Postgres (solo con `DATABASE_URL`).
- `tests/test_health.py` usa `Settings(database_url="sqlite://")`: in quel caso `create_app` costruisce `PostgresRepositories` su SQLite senza tabelle, quindi ogni lettura del catalogo solleva `OperationalError`. `/health` deve tollerarlo.
- Interprete: `uv run python` (3.12). Il `python3` di sistema è 3.7. Suite di partenza: 271 test, 11 skipped, verde.
- M3 (MCP) gira in parallelo e modifica anch'essa `vela/app.py` (un `include_router`/mount in più) e crea `docs/acceptance.md`: chi arriva secondo fa rebase.
- Comportamenti di FastAPI verificati in una sonda prima di scrivere il piano: le dependency del router vengono eseguite prima della validazione del body (401 prima di 422); `HTTPBearer(auto_error=False)` restituisce `None` per schemi diversi da Bearer; un handler per `Exception` produce la risposta 500 (con `TestClient(..., raise_server_exceptions=False)`); una route sconosciuta sotto `/v1` arriva all'handler di `HTTPException` con `request.url.path`; i campi extra del body sono ignorati; JSON malformato → `RequestValidationError`.

## Decisioni prese nell'intervista (da riportare in `docs/decisions.md`, Task 0)

| Decisione | Scelta | Motivo |
|---|---|---|
| `VELA_API_TOKEN` assente | L'app parte; ogni `/v1/*` risponde 503 `rest-not-configured` (7807). `/health` e `/replay` restano disponibili | Fail closed senza accesso aperto per errore, diagnosi chiara su Render, i test esistenti non cambiano |
| Esiti previsti dei casi d'uso | Sempre 2xx con `{"outcome": ..., **to_dict()}`. 201 per `intent_created` e `order` (anche al secondo accept idempotente), 200 per `question`, `proposal`, `no_match`, `missing_traveler_data`, `order_status` | Domanda, "niente di compatibile" e dati mancanti sono risposte di dominio che l'agente legge (`say`), non errori. `to_dict()` resta invariato per M3 |
| `/health` | Nuovo `ProductRepository.last_fetched_at()` (memoria + Postgres `MAX(fetched_at)`); risposta con `catalog: {products, fetched_at, age_seconds}` (`null` senza dominio o con lettura fallita) e `quota: null` fino a M5; il codice di stato dipende solo dal DB | RNF-06 senza anticipare il guardiano della quota; il controllo di salute di Render non cambia comportamento |
| RFC 7807 | `type` = `/problems/<slug>` (`unauthorized`, `not-found`, `method-not-allowed`, `invalid-request`, `rest-not-configured`, `domain-unavailable`, `internal-error`, `http-error`), più `title`, `status`, `detail`, `instance` e `say` in italiano. Solo sotto `/v1`; `/health`, `/replay`, `/docs` mantengono il formato predefinito | Slug leggibili da un client; `say` permette all'agente di dire qualcosa al viaggiatore anche sull'errore |
| Test manuale §10.3 | Nessuno script: i comandi `curl` del flusso stanno in `docs/rest.md`; l'esecuzione contro Render avviene dopo il merge e l'esito va in `docs/acceptance.md` (creato se M3 non l'ha ancora creato) | Scelta dell'utente |
| Corpi delle richieste | Modelli Pydantic; campi extra ignorati; `text` ripulito dagli spazi, lunghezza 1-1000; `pax` ≥ 1; `profile`/`traveler` con la forma di `profile_to_dict` | Un agente che manda un campo in più non riceve un errore; testo vuoto e pax 0 sono errori del client |
| Autenticazione | `HTTPBearer(auto_error=False)` + `hmac.compare_digest`; schema `Bearer` case-insensitive; auth prima della validazione e del dominio; il token ricevuto non compare mai nella risposta | RFC 6750; niente oracle di validazione per chi non ha il token |
| OpenAPI | `/docs` e `/openapi.json` restano pubblici e includono lo schema Bearer | Utili a chi integra; non espongono dati |
| Endpoint sincroni | `def`, non `async def` | Il dominio è sincrono; FastAPI li esegue nel threadpool |
| Nessuna route per modalità | Il router REST è montato sempre, in replay e in live | La superficie non dipende dall'upstream |

## Global Constraints

- Nessuna dipendenza nuova in `pyproject.toml`; nessuna modifica a `uv.lock`. Nessuna variabile d'ambiente nuova (spec §6).
- `uv run python -m unittest discover -s tests` verde senza servizi esterni e senza `DATABASE_URL`; i test Postgres restano sotto `@unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")`.
- Mai aprire, stampare o loggare `.env`, chiavi o token. Con Postgres: `set -a; . ./.env; set +a; uv run python -m unittest discover -s tests` in una sola riga.
- `vela/domain` non cambia, e nemmeno i `to_dict()`. Unica modifica di interfaccia: `ProductRepository.last_fetched_at() -> Optional[datetime]`.
- Nessuna risposta contiene più di un prodotto (RF-10): `assert_single_product` su ogni corpo di successo nei test REST.
- Ogni errore sotto `/v1` è `application/problem+json` con `type`, `title`, `status`, `detail`, `instance`, `say`; mai traceback, messaggi di eccezione interni o il token ricevuto nel corpo.
- `/health` resta pubblico e il suo codice di stato dipende solo dal DB.
- Commit piccoli, uno per task, messaggio imperativo in inglese come nella storia del repo, con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nessun force push.

## Review Focus

1. Richiesta senza token con body non valido, o senza token con dominio assente: deve rispondere 401, non 422 o 503 (nessuna informazione a chi non è autorizzato). Test in Task 4 (`test_auth_is_checked_before_validation`, `test_auth_is_checked_before_domain`).
2. Header `Authorization: bearer <token>` in minuscolo (lo mandano alcuni client): deve essere accettato; `Basic ...` o token sbagliato → 401 con `WWW-Authenticate: Bearer` e senza il token nella risposta. Test in Task 4 (`test_scheme_is_case_insensitive`, `test_wrong_token_is_not_echoed`).
3. Id sconosciuti su ognuno dei quattro endpoint con id (proposta per intento, reject, accept, ordine): 404 `not-found` con il tipo di risorsa nel `detail`, mai 500. Test in Task 4 (`test_unknown_intent_is_404`) e Task 5 (`test_unknown_ids_are_404`).
4. `POST .../reject` e `POST .../accept` senza alcun body (come fa `curl -X POST`): devono funzionare, non dare 422. Test in Task 5 (`test_reject_without_body`, `test_double_accept_returns_same_order`).
5. Errore inatteso nel dominio: 500 `internal-error` in 7807 senza il messaggio dell'eccezione; fuori da `/v1` resta il 500 predefinito in testo. Test in Task 3 (`test_unexpected_error_is_500_without_leak`, `test_other_paths_keep_default_format`) e Task 5 (`test_unexpected_domain_error_is_500_problem`).

---

## Design

### Struttura dei file

```
vela/ports/repositories.py      + ProductRepository.last_fetched_at()
vela/adapters/repo_memory.py    + MemoryProducts.last_fetched_at()
vela/adapters/repo_postgres.py  + PostgresProducts.last_fetched_at()  (SELECT MAX(fetched_at))
vela/surfaces/health.py         + catalog, quota
vela/surfaces/problems.py       NUOVO: Problem, costruttori, handler 7807 limitati a /v1
vela/surfaces/rest.py           NUOVO: router /v1, auth, corpi Pydantic, 5 endpoint, outcome
vela/app.py                     + install_problem_handlers(app), include_router(rest_router)
tests/support.py                + PROBLEM_JSON, assert_problem
tests/repo_contract.py          + test_products_last_fetched_at
tests/test_health.py            corpi attesi aggiornati + CatalogHealthTest
tests/test_problems.py          NUOVO
tests/test_rest.py              NUOVO
docs/rest.md                    NUOVO: contratto e comandi curl del flusso §10.3
docs/decisions.md, README.md    aggiornati
docs/acceptance.md              creato o aggiornato nel Task 7 (manuale)
```

### Contratto HTTP

Tutti gli endpoint richiedono `Authorization: Bearer <VELA_API_TOKEN>`.

| Endpoint | Body | Esiti |
|---|---|---|
| `POST /v1/intents` | `{"text": str, "profile"?: Profile}` | 201 `intent_created`, 200 `question` |
| `GET /v1/intents/{intent_id}/proposal` | — | 200 `proposal`, 200 `no_match` |
| `POST /v1/proposals/{proposal_id}/reject` | opzionale `{"reason"?: str}` | 200 `proposal`, 200 `no_match` |
| `POST /v1/proposals/{proposal_id}/accept` | opzionale `{"traveler"?: Profile}` | 201 `order`, 200 `missing_traveler_data` |
| `GET /v1/orders/{order_id}` | — | 200 `order_status` |

`Profile` = `{"first_name"?, "last_name"?, "email"?, "phone"?, "pax"? (≥ 1), "participants"?: [{"first_name"?, "last_name"?}]}`.

Corpo di successo = `{"outcome": <esito>, ...chiavi di to_dict()}`:

| Risposta del dominio | `outcome` | HTTP |
|---|---|---|
| `IntentCreated` | `intent_created` | 201 |
| `IntentQuestion` | `question` | 200 |
| `ProposalMade` | `proposal` | 200 |
| `NoMatch` | `no_match` | 200 |
| `AcceptResponse` | `order` | 201 |
| `MissingTravelerData` | `missing_traveler_data` | 200 |
| `OrderStatusResponse` | `order_status` | 200 |

Errori (`application/problem+json`, solo sotto `/v1`):

| HTTP | `type` | Quando |
|---|---|---|
| 401 | `/problems/unauthorized` | token mancante, sbagliato o schema non Bearer; header `WWW-Authenticate: Bearer` |
| 404 | `/problems/not-found` | `NotFound` del dominio (detail `Id sconosciuto (<intento/proposta/ordine>): <id>`) o route sconosciuta sotto `/v1` |
| 405 | `/problems/method-not-allowed` | metodo sbagliato su una route esistente; header `Allow` preservato |
| 422 | `/problems/invalid-request` | validazione di body/parametri o JSON malformato; campo `errors: [{"loc": [...], "msg": str}]` |
| 503 | `/problems/rest-not-configured` | `VELA_API_TOKEN` non impostata |
| 503 | `/problems/domain-unavailable` | `app.state.vela is None` (manca `DATABASE_URL`) |
| 500 | `/problems/internal-error` | eccezione inattesa; detail fisso, niente messaggio dell'eccezione |

Ordine dei controlli: token configurato (503) → token valido (401) → validazione (422) → dominio disponibile (503) → caso d'uso (404 / esito).

### `/health`

```json
200 {"status": "ok", "db": "ok",
     "catalog": {"products": 110, "fetched_at": "2026-09-25T12:00:00+00:00", "age_seconds": 3600},
     "quota": null}
503 {"status": "degraded", "db": "error", "catalog": null, "quota": null}
```

`catalog` è `null` se il DB non risponde, se non c'è dominio o se la lettura solleva `SQLAlchemyError`. Con catalogo vuoto: `{"products": 0, "fetched_at": null, "age_seconds": null}`. L'età si calcola con `vela.now()` (orologio iniettabile).

### Flusso di una richiesta

`HTTPBearer` → `require_token` (503/401) → validazione Pydantic (422) → `get_vela` (503) → metodo di `Vela` → `reply(result)` → JSON con `outcome`. `NotFound` e le eccezioni inattese risalgono agli handler di `problems.py`.

---

### Task 0: Piano e decisioni nel repo

**Files:**
- Create: `docs/plans/2026-09-25-m4-superficie-rest.md` (questo file)
- Modify: `docs/decisions.md` (in coda)

- [ ] **Step 1: Aggiungere in coda a `docs/decisions.md`** una sezione `## 2026-09-25 — M4: superficie REST` con la frase di origine (`Origine: intervista sulla macro task M4, piano in docs/plans/2026-09-25-m4-superficie-rest.md.`) e la tabella "Decisioni prese nell'intervista" di questo piano, copiata integralmente.

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-09-25-m4-superficie-rest.md docs/decisions.md
git commit -m "Add the M4 execution plan and record the interview decisions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 1: `ProductRepository.last_fetched_at()`

**Files:**
- Modify: `vela/ports/repositories.py`, `vela/adapters/repo_memory.py`, `vela/adapters/repo_postgres.py`
- Test: `tests/repo_contract.py` (eseguito da `tests/test_repo_memory.py` sempre e da `tests/test_repo_postgres.py` con `DATABASE_URL`)

**Interfaces:**
- Consumes: `Product.fetched_at: datetime` (aware, UTC); `products_t.c.fetched_at` (`DateTime(timezone=True)`).
- Produces: `ProductRepository.last_fetched_at(self) -> Optional[datetime]`: il `fetched_at` più recente, `None` con catalogo vuoto. Implementato da `MemoryProducts` e `PostgresProducts`.

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

- [ ] **Step 3: Implementare.** In `vela/ports/repositories.py` aggiungere `from datetime import datetime` prima di `from typing import ...`, e il metodo alla `ProductRepository`:

```python
from datetime import datetime
from typing import Iterable, List, Optional, Protocol, Set
```

```python
class ProductRepository(Protocol):
    def upsert_many(self, products: Iterable[Product]) -> None: ...
    def count(self) -> int: ...
    def list_all(self) -> List[Product]: ...
    def get(self, product_id: str) -> Optional[Product]: ...
    def last_fetched_at(self) -> Optional[datetime]: ...
```

In `vela/adapters/repo_memory.py` aggiungere `from datetime import datetime` agli import e a `MemoryProducts`:

```python
    def last_fetched_at(self) -> Optional[datetime]:
        return max((p.fetched_at for p in self._items.values()), default=None)
```

In `vela/adapters/repo_postgres.py` cambiare `from datetime import date` in `from datetime import date, datetime` e aggiungere a `PostgresProducts`, dopo `get`:

```python
    def last_fetched_at(self) -> Optional[datetime]:
        with self.engine.connect() as conn:
            return conn.execute(select(func.max(products_t.c.fetched_at))).scalar_one()
```

- [ ] **Step 4: Eseguire i test**

Run: `uv run python -m unittest discover -s tests -p "test_repo_*.py"`
Expected: PASS (Postgres skipped senza `DATABASE_URL`). Poi, se l'ambiente lo consente: `set -a; . ./.env; set +a; uv run python -m unittest discover -s tests -p "test_repo_postgres.py"` → PASS senza skip.

- [ ] **Step 5: Commit**

```bash
git add vela/ports/repositories.py vela/adapters/repo_memory.py vela/adapters/repo_postgres.py tests/repo_contract.py
git commit -m "Add last_fetched_at to the product repositories

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `/health` con età del catalogo e quota nota (RNF-06)

**Files:**
- Modify: `vela/surfaces/health.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: `ProductRepository.count()`, `ProductRepository.last_fetched_at()` (Task 1), `Vela.now()`, `app.state.vela`, `app.state.engine`, `check_db`.
- Produces: corpo `{"status", "db", "catalog", "quota"}` come in "Design / `/health`". Nessun'altra funzione pubblica usata da task successivi.

- [ ] **Step 1: Aggiornare i test esistenti e scriverne di nuovi.** In `tests/test_health.py`:

sostituire le asserzioni esatte di `test_no_database_configured_is_503` e `test_reachable_database_is_200` con:

```python
    def test_no_database_configured_is_503(self):
        r = client(None).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json(), {"status": "degraded", "db": "error", "catalog": None, "quota": None})

    def test_reachable_database_is_200(self):
        # SQLite senza tabelle: il catalogo non si legge, ma la salute dipende solo dal DB.
        r = client("sqlite://").get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok", "db": "ok", "catalog": None, "quota": None})
```

poi aggiungere questi import in testa al file, dopo quelli esistenti, e il resto in fondo:

```python
from dataclasses import replace
from datetime import timedelta

from support import NOW, make_product
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.usecases import Vela


def catalog_client(products, database_url="sqlite://", now=NOW + timedelta(hours=1)):
    repos = MemoryRepositories()
    repos.products.upsert_many(products)
    vela = Vela(repos, ReplayHofJ(), FakePayments("http://test"), DEFAULT_TRAVELER, now=lambda: now)
    app = create_app(Settings(database_url=database_url), vela=vela, runner=InlineRunner(vela.orders))
    return TestClient(app)


class CatalogHealthTest(unittest.TestCase):
    def test_reports_catalog_size_and_age(self):
        older = replace(make_product(2), fetched_at=NOW - timedelta(days=1))
        r = catalog_client([make_product(1), older]).get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["catalog"], {"products": 2, "fetched_at": NOW.isoformat(),
                                               "age_seconds": 3600})
        self.assertIsNone(r.json()["quota"])

    def test_empty_catalog(self):
        r = catalog_client([]).get("/health")
        self.assertEqual(r.json()["catalog"], {"products": 0, "fetched_at": None, "age_seconds": None})

    def test_age_is_never_negative(self):
        r = catalog_client([make_product(1)], now=NOW - timedelta(minutes=5)).get("/health")
        self.assertEqual(r.json()["catalog"]["age_seconds"], 0)

    def test_no_catalog_when_database_is_down(self):
        r = catalog_client([make_product(1)], database_url=UNREACHABLE).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertIsNone(r.json()["catalog"])

    def test_health_needs_no_token(self):
        app = create_app(Settings(database_url="sqlite://", vela_api_token="tok"))
        self.assertEqual(TestClient(app).get("/health").status_code, 200)
```

- [ ] **Step 2: Eseguire e vedere il fallimento**

Run: `uv run python -m unittest discover -s tests -p "test_health.py"`
Expected: FAIL: `KeyError: 'catalog'` e differenze di dizionario (`catalog`, `quota` mancanti).

- [ ] **Step 3: Implementare.** Sostituire interamente `vela/surfaces/health.py` con:

```python
"""``GET /health``: pubblico; stato del DB, età del catalogo e quota nota (RNF-06).

Il codice di stato dipende solo dal DB (è il controllo di salute di Render). ``catalog`` è
``null`` con il DB irraggiungibile, senza dominio o se la lettura fallisce; ``quota`` resta
``null`` finché il guardiano della quota non esiste (M5).
"""
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from vela.adapters.db import check_db

router = APIRouter()


def catalog_info(vela) -> Optional[dict]:
    if vela is None:
        return None
    try:
        count = vela.repos.products.count()
        fetched_at = vela.repos.products.last_fetched_at()
    except SQLAlchemyError:
        return None
    if fetched_at is None:
        return {"products": count, "fetched_at": None, "age_seconds": None}
    age = max(int((vela.now() - fetched_at).total_seconds()), 0)
    return {"products": count, "fetched_at": fetched_at.isoformat(), "age_seconds": age}


@router.get("/health")
def health(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    db_ok = engine is not None and check_db(engine)
    body = {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error",
            "catalog": catalog_info(request.app.state.vela) if db_ok else None,
            "quota": None}
    return JSONResponse(body, status_code=200 if db_ok else 503)
```

- [ ] **Step 4: Eseguire i test**

Run: `uv run python -m unittest discover -s tests -p "test_health.py"` poi `uv run python -m unittest discover -s tests`
Expected: PASS; la suite intera resta verde (`tests/test_app_replay.py::test_health_still_works` si aspetta ancora 503 senza engine).

- [ ] **Step 5: Commit**

```bash
git add vela/surfaces/health.py tests/test_health.py
git commit -m "Report catalog age and the known quota on /health

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Errori RFC 7807 sotto `/v1`

**Files:**
- Create: `vela/surfaces/problems.py`
- Modify: `tests/support.py` (in coda)
- Test: `tests/test_problems.py`

**Interfaces:**
- Consumes: `vela.domain.orders.NotFound` (attributi `kind`, `id`).
- Produces (usati dal Task 4 e 5):
  - `PROBLEM_JSON = "application/problem+json"`
  - `class Problem(Exception)` con `__init__(self, status: int, slug: str, title: str, detail: str, say: str, headers: Optional[dict] = None, extra: Optional[dict] = None)`
  - `unauthorized() -> Problem`, `rest_not_configured() -> Problem`, `domain_unavailable() -> Problem`, `not_found(kind: str, id: str) -> Problem`
  - `install_problem_handlers(app: FastAPI) -> None`
  - in `tests/support.py`: `PROBLEM_JSON`, `assert_problem(testcase, response, status: int, slug: str) -> dict`

- [ ] **Step 1: Aggiungere l'helper di test.** In coda a `tests/support.py`:

```python
PROBLEM_JSON = "application/problem+json"


def assert_problem(testcase, response, status, slug):
    """Risposta RFC 7807 completa con `say` leggibile; restituisce il corpo."""
    testcase.assertEqual(response.status_code, status, response.text)
    testcase.assertTrue(response.headers["content-type"].startswith(PROBLEM_JSON),
                        response.headers["content-type"])
    body = response.json()
    testcase.assertEqual(body["type"], "/problems/" + slug)
    testcase.assertEqual(body["status"], status)
    for key in ("title", "detail", "instance", "say"):
        testcase.assertTrue(body.get(key), "campo 7807 mancante: %s" % key)
    testcase.assertNotIn("http", body["say"])
    return body
```

- [ ] **Step 2: Scrivere i test.** Creare `tests/test_problems.py`:

```python
"""Errori RFC 7807 della superficie REST: solo sotto /v1, mai dettagli interni."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from support import assert_problem
from vela.domain.orders import NotFound
from vela.surfaces.problems import install_problem_handlers, not_found, unauthorized


class Body(BaseModel):
    text: str


def make_client():
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/v1/problem")
    def problem():
        raise unauthorized()

    @app.get("/v1/missing")
    def missing():
        raise NotFound("order", "o-1")

    @app.get("/v1/boom")
    def boom():
        raise RuntimeError("segreto interno")

    @app.post("/v1/echo")
    def echo(body: Body):
        return {"text": body.text}

    @app.post("/other/echo")
    def other_echo(body: Body):
        return {"text": body.text}

    @app.get("/other/boom")
    def other_boom():
        raise RuntimeError("segreto interno")

    return TestClient(app, raise_server_exceptions=False)


class ProblemTest(unittest.TestCase):
    def setUp(self):
        self.c = make_client()

    def test_problem_exception_is_7807(self):
        r = self.c.get("/v1/problem")
        body = assert_problem(self, r, 401, "unauthorized")
        self.assertEqual(body["instance"], "/v1/problem")
        self.assertEqual(r.headers["www-authenticate"], "Bearer")

    def test_domain_not_found_is_404(self):
        body = assert_problem(self, self.c.get("/v1/missing"), 404, "not-found")
        self.assertIn("ordine", body["detail"])
        self.assertIn("o-1", body["detail"])

    def test_not_found_labels_every_kind(self):
        self.assertIn("intento", not_found("intent", "x").detail)
        self.assertIn("proposta", not_found("proposal", "x").detail)

    def test_unknown_route_under_v1_is_404_problem(self):
        assert_problem(self, self.c.get("/v1/nope"), 404, "not-found")

    def test_method_not_allowed_keeps_allow_header(self):
        r = self.c.get("/v1/echo")
        assert_problem(self, r, 405, "method-not-allowed")
        self.assertEqual(r.headers["allow"], "POST")

    def test_validation_error_is_invalid_request(self):
        body = assert_problem(self, self.c.post("/v1/echo", json={}), 422, "invalid-request")
        self.assertEqual(body["errors"][0]["loc"], ["body", "text"])
        self.assertTrue(body["errors"][0]["msg"])

    def test_malformed_json_is_invalid_request(self):
        r = self.c.post("/v1/echo", content="{non json", headers={"content-type": "application/json"})
        assert_problem(self, r, 422, "invalid-request")

    def test_unexpected_error_is_500_without_leak(self):
        r = self.c.get("/v1/boom")
        assert_problem(self, r, 500, "internal-error")
        self.assertNotIn("segreto", r.text)
        self.assertNotIn("Traceback", r.text)

    def test_other_paths_keep_default_format(self):
        r = self.c.get("/other/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {"detail": "Not Found"})
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        r = self.c.post("/other/echo", json={})
        self.assertEqual(r.status_code, 422)
        self.assertIsInstance(r.json()["detail"], list)
        r = self.c.get("/other/boom")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.text, "Internal Server Error")

    def test_prefix_match_is_exact(self):
        r = self.c.get("/v1x/nope")
        self.assertEqual(r.json(), {"detail": "Not Found"})
```

- [ ] **Step 3: Eseguire e vedere il fallimento**

Run: `uv run python -m unittest discover -s tests -p "test_problems.py"`
Expected: FAIL con `ModuleNotFoundError: No module named 'vela.surfaces.problems'`

- [ ] **Step 4: Implementare.** Creare `vela/surfaces/problems.py`:

```python
"""Errori RFC 7807 della superficie REST (RF-40).

Solo i path sotto ``/v1`` rispondono ``application/problem+json``; ``/health``, ``/replay`` e
le pagine di FastAPI tengono il formato predefinito. ``type`` è uno slug relativo
(``/problems/<slug>``); ``say`` è la frase italiana che un agente può leggere al viaggiatore
(RF-42). Il corpo non contiene mai messaggi di eccezioni interne né il token ricevuto.
"""
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (http_exception_handler,
                                        request_validation_exception_handler)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException

from vela.domain.orders import NotFound

PROBLEM_JSON = "application/problem+json"
REST_PREFIX = "/v1"
KINDS_IT = {"intent": "intento", "proposal": "proposta", "order": "ordine"}
HTTP_PROBLEMS = {404: ("not-found", "Risorsa non trovata"),
                 405: ("method-not-allowed", "Metodo non consentito")}
SAY_NOT_FOUND = "Non trovo più questa richiesta. Ripartiamo dalla tua idea di viaggio?"
SAY_HTTP = "La richiesta non è andata a buon fine. Riproviamo?"
SAY_INVALID = "La richiesta non è completa. Riproviamo descrivendo di nuovo il viaggio."
SAY_RETRY = "Qualcosa è andato storto da parte mia. Riprova tra un minuto."


class Problem(Exception):
    def __init__(self, status: int, slug: str, title: str, detail: str, say: str,
                 headers: Optional[dict] = None, extra: Optional[dict] = None):
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.say = say
        self.headers = headers or {}
        self.extra = extra or {}


def unauthorized() -> Problem:
    return Problem(401, "unauthorized", "Token mancante o non valido",
                   "Serve l'header Authorization: Bearer con il token di Vela.",
                   "Non sono autorizzato a usare il servizio di prenotazione.",
                   headers={"WWW-Authenticate": "Bearer"})


def rest_not_configured() -> Problem:
    return Problem(503, "rest-not-configured", "Superficie REST non configurata",
                   "VELA_API_TOKEN non è impostata: la superficie REST è chiusa.",
                   "Il servizio di prenotazione non è ancora configurato. Riprova più tardi.")


def domain_unavailable() -> Problem:
    return Problem(503, "domain-unavailable", "Dominio non disponibile",
                   "DATABASE_URL non è impostata: i casi d'uso non sono disponibili.",
                   "Il servizio di prenotazione non è disponibile in questo momento. Riprova tra poco.")


def not_found(kind: str, id: str) -> Problem:
    return Problem(404, "not-found", "Risorsa non trovata",
                   "Id sconosciuto (%s): %s" % (KINDS_IT.get(kind, kind), id), SAY_NOT_FOUND)


def is_rest(request: Request) -> bool:
    path = request.url.path
    return path == REST_PREFIX or path.startswith(REST_PREFIX + "/")


def problem_response(request: Request, problem: Problem) -> JSONResponse:
    body = {"type": "/problems/" + problem.slug, "title": problem.title,
            "status": problem.status, "detail": problem.detail,
            "instance": request.url.path, "say": problem.say}
    body.update(problem.extra)
    return JSONResponse(body, status_code=problem.status, headers=problem.headers,
                        media_type=PROBLEM_JSON)


def install_problem_handlers(app: FastAPI) -> None:
    async def on_problem(request: Request, exc: Problem):
        return problem_response(request, exc)

    async def on_not_found(request: Request, exc: NotFound):
        return problem_response(request, not_found(exc.kind, exc.id))

    async def on_http(request: Request, exc: HTTPException):
        if not is_rest(request):
            return await http_exception_handler(request, exc)
        slug, title = HTTP_PROBLEMS.get(exc.status_code, ("http-error", "Errore HTTP"))
        say = SAY_NOT_FOUND if exc.status_code == 404 else SAY_HTTP
        return problem_response(request, Problem(exc.status_code, slug, title, str(exc.detail),
                                                 say, headers=dict(exc.headers or {})))

    async def on_validation(request: Request, exc: RequestValidationError):
        if not is_rest(request):
            return await request_validation_exception_handler(request, exc)
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem_response(request, Problem(
            422, "invalid-request", "Richiesta non valida",
            "Il corpo o i parametri non rispettano il formato atteso.", SAY_INVALID,
            extra={"errors": errors}))

    async def on_error(request: Request, exc: Exception):
        if not is_rest(request):
            return PlainTextResponse("Internal Server Error", status_code=500)
        return problem_response(request, Problem(
            500, "internal-error", "Errore interno",
            "Errore inatteso: il dettaglio è nei log del server.", SAY_RETRY))

    app.add_exception_handler(Problem, on_problem)
    app.add_exception_handler(NotFound, on_not_found)
    app.add_exception_handler(HTTPException, on_http)
    app.add_exception_handler(RequestValidationError, on_validation)
    app.add_exception_handler(Exception, on_error)
```

- [ ] **Step 5: Eseguire i test**

Run: `uv run python -m unittest discover -s tests -p "test_problems.py"`
Expected: PASS (11 test).

- [ ] **Step 6: Commit**

```bash
git add vela/surfaces/problems.py tests/support.py tests/test_problems.py
git commit -m "Add RFC 7807 problem responses scoped to the /v1 surface

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Router `/v1`, autenticazione, intenti e proposta

**Files:**
- Create: `vela/surfaces/rest.py`
- Modify: `vela/app.py`
- Test: `tests/test_rest.py`

**Interfaces:**
- Consumes: `Problem`, `unauthorized`, `rest_not_configured`, `domain_unavailable`, `install_problem_handlers` (Task 3); `Vela.create_intent(text, profile)`, `Vela.get_proposal(intent_id)`; `profile_from_dict`; `app.state.settings.vela_api_token`, `app.state.vela`.
- Produces (usati dal Task 5): in `vela/surfaces/rest.py`: `router` (`APIRouter(prefix="/v1")`), `require_token`, `get_vela(request) -> Vela`, `ProfileIn`, `to_profile(p: Optional[ProfileIn]) -> Optional[TravelerProfile]`, `reply(result) -> JSONResponse`, `OUTCOMES`. In `tests/test_rest.py`: `TOKEN`, `AUTH`, `INTENT`, `FULL`, `make_client(products=None, token=TOKEN) -> (TestClient, Vela)`, `new_intent(c, text=INTENT, profile=FULL) -> dict`.

- [ ] **Step 1: Scrivere i test.** Creare `tests/test_rest.py`:

```python
"""Superficie REST (RF-40, RF-43): auth, esiti, errori RFC 7807, flusso completo in replay, RF-10."""
import random
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from support import NOW, assert_problem, assert_single_product, make_product
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.usecases import Vela

TOKEN = "tok-test"
AUTH = {"Authorization": "Bearer " + TOKEN}
INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
FULL = {"first_name": "Anna", "last_name": "Rossi", "email": "anna@x.it", "phone": "+390000",
        "participants": [{"first_name": "Bo", "last_name": "Bi"}]}


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_client(products=None, token=TOKEN):
    """App con repository in memoria, adapter replay e runner sincrono. `products=None` = fixture."""
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    repos.products.upsert_many(hofj.load_catalog() if products is None else products)
    vela = Vela(repos, hofj, FakePayments("http://test"), DEFAULT_TRAVELER, now=Clock())
    settings = Settings(vela_upstream_mode="replay", vela_public_url="http://test",
                        vela_api_token=token)
    app = create_app(settings, vela=vela, runner=InlineRunner(vela.orders))
    return TestClient(app, raise_server_exceptions=False), vela


def new_intent(c, text=INTENT, profile=FULL):
    body = {"text": text}
    if profile is not None:
        body["profile"] = profile
    r = c.post("/v1/intents", json=body, headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.c, _ = make_client()

    def test_missing_token_is_401(self):
        r = self.c.post("/v1/intents", json={"text": INTENT})
        assert_problem(self, r, 401, "unauthorized")
        self.assertEqual(r.headers["www-authenticate"], "Bearer")

    def test_wrong_token_is_not_echoed(self):
        r = self.c.post("/v1/intents", json={"text": INTENT},
                        headers={"Authorization": "Bearer sbagliato-123"})
        assert_problem(self, r, 401, "unauthorized")
        self.assertNotIn("sbagliato-123", r.text)

    def test_non_bearer_scheme_is_401(self):
        r = self.c.post("/v1/intents", json={"text": INTENT},
                        headers={"Authorization": "Basic " + TOKEN})
        assert_problem(self, r, 401, "unauthorized")

    def test_scheme_is_case_insensitive(self):
        r = self.c.post("/v1/intents", json={"text": INTENT},
                        headers={"Authorization": "bearer " + TOKEN})
        self.assertEqual(r.status_code, 201, r.text)

    def test_unconfigured_token_is_503(self):
        c, _ = make_client(token=None)
        assert_problem(self, c.post("/v1/intents", json={"text": INTENT}), 503, "rest-not-configured")
        r = c.post("/v1/intents", json={"text": INTENT}, headers=AUTH)
        assert_problem(self, r, 503, "rest-not-configured")

    def test_auth_is_checked_before_validation(self):
        assert_problem(self, self.c.post("/v1/intents", json={}), 401, "unauthorized")

    def test_auth_is_checked_before_domain(self):
        c = TestClient(create_app(Settings(vela_api_token=TOKEN)))   # nessun DATABASE_URL
        assert_problem(self, c.post("/v1/intents", json={"text": INTENT}), 401, "unauthorized")
        r = c.post("/v1/intents", json={"text": INTENT}, headers=AUTH)
        assert_problem(self, r, 503, "domain-unavailable")

    def test_health_and_replay_need_no_token(self):
        self.assertNotEqual(self.c.get("/health").status_code, 401)
        self.assertEqual(self.c.get("/replay/checkout/nope").status_code, 404)


class IntentEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.c, self.vela = make_client()

    def test_create_intent_is_201_intent_created(self):
        r = self.c.post("/v1/intents", json={"text": INTENT, "profile": FULL}, headers=AUTH)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        body = r.json()
        self.assertEqual(body["outcome"], "intent_created")
        self.assertTrue(body["intent_id"])
        self.assertEqual(body["criteria"]["sport"], "padel")
        self.assertEqual(body["criteria"]["pax"], 2)
        self.assertEqual(body["criteria"]["budget"], "800.00")
        assert_single_product(self, body)

    def test_question_is_200_and_persists_nothing(self):
        r = self.c.post("/v1/intents", json={"text": "ciao"}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "question")
        self.assertNotIn("intent_id", body)
        self.assertEqual(body["say"], body["question"])

    def test_profile_is_passed_to_the_domain(self):
        body = new_intent(self.c, text="padel a ottobre", profile={"pax": 3})
        self.assertEqual(body["criteria"]["pax"], 3)

    def test_blank_text_is_422(self):
        r = self.c.post("/v1/intents", json={"text": "   "}, headers=AUTH)
        body = assert_problem(self, r, 422, "invalid-request")
        self.assertEqual(body["errors"][0]["loc"], ["body", "text"])

    def test_zero_pax_is_422(self):
        r = self.c.post("/v1/intents", json={"text": INTENT, "profile": {"pax": 0}}, headers=AUTH)
        assert_problem(self, r, 422, "invalid-request")

    def test_missing_body_is_422(self):
        assert_problem(self, self.c.post("/v1/intents", headers=AUTH), 422, "invalid-request")

    def test_extra_fields_are_ignored(self):
        r = self.c.post("/v1/intents", json={"text": INTENT, "channel": "voce"}, headers=AUTH)
        self.assertEqual(r.status_code, 201)

    def test_get_proposal_is_a_single_product(self):
        iid = new_intent(self.c)["intent_id"]
        r = self.c.get("/v1/intents/%s/proposal" % iid, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "proposal")
        self.assertEqual(body["intent_id"], iid)
        self.assertTrue(body["product"]["product_id"])
        assert_single_product(self, body)
        again = self.c.get("/v1/intents/%s/proposal" % iid, headers=AUTH).json()
        self.assertEqual(again["proposal_id"], body["proposal_id"])

    def test_no_match_is_200(self):
        c, _ = make_client(products=[make_product(1, sport="tennis")])
        iid = new_intent(c, text="padel a ottobre, siamo in due")["intent_id"]
        r = c.get("/v1/intents/%s/proposal" % iid, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "no_match")
        self.assertEqual(body["failed_criterion"], "sport")
        assert_single_product(self, body)

    def test_unknown_intent_is_404(self):
        body = assert_problem(self, self.c.get("/v1/intents/nope/proposal", headers=AUTH),
                              404, "not-found")
        self.assertIn("intento", body["detail"])
        self.assertIn("nope", body["detail"])
```

(Gli import `urlparse` servono al Task 5, che aggiunge classi a questo file.)

- [ ] **Step 2: Eseguire e vedere il fallimento**

Run: `uv run python -m unittest discover -s tests -p "test_rest.py"`
Expected: FAIL: le richieste a `/v1/...` rispondono 404 `{"detail":"Not Found"}` (router assente), quindi `assert_problem` e gli status 201 falliscono.

- [ ] **Step 3: Implementare il router.** Creare `vela/surfaces/rest.py`:

```python
"""Superficie REST (RF-40, RF-43): i cinque casi d'uso di RF-39 sotto ``/v1``.

Bearer statico ``VELA_API_TOKEN``; senza token configurato ogni endpoint risponde 503. Ogni
risposta di successo è ``{"outcome": ..., **to_dict()}``: gli esiti previsti (domanda, niente di
compatibile, dati mancanti) sono 200, non errori. Gli errori sono RFC 7807
(``vela/surfaces/problems.py``). Ordine dei controlli: token, validazione, dominio.
"""
import hmac
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, StringConstraints

from vela.domain.models import (AcceptResponse, IntentCreated, IntentQuestion,
                                MissingTravelerData, NoMatch, OrderStatusResponse, ProposalMade,
                                TravelerProfile, profile_from_dict)
from vela.domain.usecases import Vela
from vela.surfaces.problems import domain_unavailable, rest_not_configured, unauthorized

bearer = HTTPBearer(auto_error=False)

OUTCOMES = {IntentCreated: "intent_created", IntentQuestion: "question",
            ProposalMade: "proposal", NoMatch: "no_match", AcceptResponse: "order",
            MissingTravelerData: "missing_traveler_data", OrderStatusResponse: "order_status"}
CREATED = (IntentCreated, AcceptResponse)


def require_token(request: Request,
                  creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> None:
    expected = request.app.state.settings.vela_api_token
    if not expected:
        raise rest_not_configured()
    if creds is None or not hmac.compare_digest(creds.credentials.encode(), expected.encode()):
        raise unauthorized()


def get_vela(request: Request) -> Vela:
    vela = request.app.state.vela
    if vela is None:
        raise domain_unavailable()
    return vela


def reply(result) -> JSONResponse:
    status = 201 if isinstance(result, CREATED) else 200
    return JSONResponse({"outcome": OUTCOMES[type(result)], **result.to_dict()}, status_code=status)


class ParticipantIn(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ProfileIn(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pax: Optional[int] = Field(default=None, ge=1)
    participants: List[ParticipantIn] = []


def to_profile(p: Optional[ProfileIn]) -> Optional[TravelerProfile]:
    return None if p is None else profile_from_dict(p.model_dump())


class IntentIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    profile: Optional[ProfileIn] = None


router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(require_token)])


@router.post("/intents")
def create_intent(body: IntentIn, vela: Vela = Depends(get_vela)) -> JSONResponse:
    return reply(vela.create_intent(body.text, to_profile(body.profile)))


@router.get("/intents/{intent_id}/proposal")
def get_proposal(intent_id: str, vela: Vela = Depends(get_vela)) -> JSONResponse:
    return reply(vela.get_proposal(intent_id))
```

- [ ] **Step 4: Collegare all'app.** In `vela/app.py` aggiungere gli import:

```python
from vela.surfaces.problems import install_problem_handlers
from vela.surfaces.rest import router as rest_router
```

e in `create_app`, subito dopo `app.include_router(health_router)`:

```python
    install_problem_handlers(app)
    app.include_router(rest_router)
```

Aggiornare la docstring del modulo: la prima riga resta, aggiungere dopo la seconda frase `La superficie REST (/v1) è sempre montata; gli errori sotto /v1 sono RFC 7807.`

- [ ] **Step 5: Eseguire i test**

Run: `uv run python -m unittest discover -s tests -p "test_rest.py"` poi `uv run python -m unittest discover -s tests`
Expected: PASS; suite intera verde. (Il test che copre il token su tutti e cinque gli endpoint arriva nel Task 5, quando esistono.)

- [ ] **Step 6: Commit**

```bash
git add vela/surfaces/rest.py vela/app.py tests/test_rest.py
git commit -m "Add the /v1 REST router with bearer auth, intents and proposals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Rifiuto, accettazione, stato dell'ordine e flusso completo

**Files:**
- Modify: `vela/surfaces/rest.py`
- Test: `tests/test_rest.py` (classi nuove in coda)

**Interfaces:**
- Consumes: da Task 4 `router`, `get_vela`, `ProfileIn`, `to_profile`, `reply`; `Vela.reject_proposal(proposal_id, reason)`, `Vela.accept_proposal(proposal_id, traveler)`, `Vela.get_order_status(order_id)`; in test `make_client`, `new_intent`, `AUTH`, `FULL`.
- Produces: `POST /v1/proposals/{proposal_id}/reject`, `POST /v1/proposals/{proposal_id}/accept`, `GET /v1/orders/{order_id}`; `RejectIn`, `AcceptIn`.

- [ ] **Step 1: Scrivere i test.** In coda a `tests/test_rest.py`:

```python
ENDPOINTS = [("post", "/v1/intents"), ("get", "/v1/intents/i/proposal"),
             ("post", "/v1/proposals/p/reject"), ("post", "/v1/proposals/p/accept"),
             ("get", "/v1/orders/o")]


class EveryEndpointAuthTest(unittest.TestCase):
    def test_every_endpoint_requires_token(self):
        c, _ = make_client()
        for method, path in ENDPOINTS:
            with self.subTest(path=path):
                assert_problem(self, getattr(c, method)(path), 401, "unauthorized")


def proposal_for(c, iid):
    r = c.get("/v1/intents/%s/proposal" % iid, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


class ProposalEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.c, self.vela = make_client()
        self.iid = new_intent(self.c)["intent_id"]
        self.first = proposal_for(self.c, self.iid)

    def test_reject_returns_a_different_product(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"],
                        json={"reason": "troppo caro"}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "proposal")
        self.assertNotEqual(body["product"]["product_id"], self.first["product"]["product_id"])
        assert_single_product(self, body)

    def test_reject_without_body(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"], headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["outcome"], "proposal")

    def test_reject_with_null_reason(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"],
                        json={"reason": None}, headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)

    def test_reject_until_no_match(self):
        c, _ = make_client(products=[make_product(1)])
        iid = new_intent(c, text="padel a ottobre, siamo in due")["intent_id"]
        pid = proposal_for(c, iid)["proposal_id"]
        body = c.post("/v1/proposals/%s/reject" % pid, headers=AUTH).json()
        self.assertEqual(body["outcome"], "no_match")
        self.assertEqual(body["failed_criterion"], "rejected")

    def test_double_accept_returns_same_order(self):
        path = "/v1/proposals/%s/accept" % self.first["proposal_id"]
        r1 = self.c.post(path, json={}, headers=AUTH)
        r2 = self.c.post(path, headers=AUTH)
        self.assertEqual((r1.status_code, r2.status_code), (201, 201))
        self.assertEqual(r1.json()["outcome"], "order")
        self.assertEqual(r1.json()["order_id"], r2.json()["order_id"])
        self.assertTrue(r1.json()["payment_url"].startswith("http://test/replay/checkout/"))
        self.assertNotIn("http", r1.json()["say"])

    def test_missing_traveler_data_then_complete(self):
        iid = new_intent(self.c, profile=None)["intent_id"]
        path = "/v1/proposals/%s/accept" % proposal_for(self.c, iid)["proposal_id"]
        r = self.c.post(path, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "missing_traveler_data")
        self.assertIn("email", body["missing"])
        self.assertIn("participants[0].last_name", body["missing"])
        assert_single_product(self, body)
        r = self.c.post(path, json={"traveler": FULL}, headers=AUTH)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["outcome"], "order")

    def test_order_status(self):
        order = self.c.post("/v1/proposals/%s/accept" % self.first["proposal_id"],
                            headers=AUTH).json()
        r = self.c.get("/v1/orders/%s" % order["order_id"], headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "order_status")
        self.assertEqual(body["status"], "awaiting_payment")
        self.assertIsNone(body["booking_code"])
        assert_single_product(self, body)

    def test_unknown_ids_are_404(self):
        cases = [("post", "/v1/proposals/nope/reject", "proposta"),
                 ("post", "/v1/proposals/nope/accept", "proposta"),
                 ("get", "/v1/orders/nope", "ordine")]
        for method, path, label in cases:
            with self.subTest(path=path):
                body = assert_problem(self, getattr(self.c, method)(path, headers=AUTH),
                                      404, "not-found")
                self.assertIn(label, body["detail"])

    def test_invalid_traveler_is_422(self):
        r = self.c.post("/v1/proposals/%s/accept" % self.first["proposal_id"],
                        json={"traveler": {"participants": "Bo"}}, headers=AUTH)
        assert_problem(self, r, 422, "invalid-request")

    def test_unexpected_domain_error_is_500_problem(self):
        def boom(order_id):
            raise RuntimeError("segreto interno")
        self.vela.get_order_status = boom
        r = self.c.get("/v1/orders/x", headers=AUTH)
        assert_problem(self, r, 500, "internal-error")
        self.assertNotIn("segreto", r.text)

    def test_openapi_lists_the_five_endpoints(self):
        paths = self.c.get("/openapi.json").json()["paths"]
        for path in ("/v1/intents", "/v1/intents/{intent_id}/proposal",
                     "/v1/proposals/{proposal_id}/reject", "/v1/proposals/{proposal_id}/accept",
                     "/v1/orders/{order_id}"):
            self.assertIn(path, paths)


class FullFlowTest(unittest.TestCase):
    def test_intent_to_confirmed_over_rest(self):
        """§10.3 in replay: intento → proposta → rifiuto → altra → accetta ×2 → checkout → confirmed."""
        c, vela = make_client()
        bodies = []

        def call(method, path, expected, **kw):
            r = getattr(c, method)(path, headers=AUTH, **kw)
            self.assertEqual(r.status_code, expected, r.text)
            bodies.append(r.json())
            return r.json()

        intent = call("post", "/v1/intents", 201, json={"text": INTENT, "profile": FULL})
        first = call("get", "/v1/intents/%s/proposal" % intent["intent_id"], 200)
        second = call("post", "/v1/proposals/%s/reject" % first["proposal_id"], 200,
                      json={"reason": "troppo caro"})
        self.assertNotEqual(second["product"]["product_id"], first["product"]["product_id"])
        order = call("post", "/v1/proposals/%s/accept" % second["proposal_id"], 201)
        again = call("post", "/v1/proposals/%s/accept" % second["proposal_id"], 201)
        self.assertEqual(again["order_id"], order["order_id"])
        status = call("get", "/v1/orders/%s" % order["order_id"], 200)
        self.assertEqual(status["status"], "awaiting_payment")

        paid = c.get(urlparse(order["payment_url"]).path)   # checkout replay: nessun token
        self.assertEqual(paid.status_code, 200)

        final = call("get", "/v1/orders/%s" % order["order_id"], 200)
        self.assertEqual(final["status"], "confirmed")
        self.assertRegex(final["booking_code"], r"^R-\d{6}$")
        self.assertIn(final["booking_code"], final["say"])
        for body in bodies:                                   # RF-10 su ogni risposta
            assert_single_product(self, body)
```

- [ ] **Step 2: Eseguire e vedere il fallimento**

Run: `uv run python -m unittest discover -s tests -p "test_rest.py"`
Expected: FAIL: le route `reject`, `accept`, `orders` rispondono 404 `not-found` (route sconosciuta), quindi gli status 200/201 attesi falliscono.

- [ ] **Step 3: Implementare.** In `vela/surfaces/rest.py`, dopo `class IntentIn`, aggiungere:

```python
class RejectIn(BaseModel):
    reason: Optional[str] = None


class AcceptIn(BaseModel):
    traveler: Optional[ProfileIn] = None
```

e in coda al file:

```python
@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, body: Optional[RejectIn] = None,
                    vela: Vela = Depends(get_vela)) -> JSONResponse:
    reason = body.reason if body is not None else None
    return reply(vela.reject_proposal(proposal_id, reason or ""))


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str, body: Optional[AcceptIn] = None,
                    vela: Vela = Depends(get_vela)) -> JSONResponse:
    traveler = to_profile(body.traveler) if body is not None else None
    return reply(vela.accept_proposal(proposal_id, traveler))


@router.get("/orders/{order_id}")
def get_order_status(order_id: str, vela: Vela = Depends(get_vela)) -> JSONResponse:
    return reply(vela.get_order_status(order_id))
```

- [ ] **Step 4: Eseguire i test**

Run: `uv run python -m unittest discover -s tests -p "test_rest.py"` poi `uv run python -m unittest discover -s tests`
Expected: PASS, incluso `EveryEndpointAuthTest`. Suite intera verde.

- [ ] **Step 5: Commit**

```bash
git add vela/surfaces/rest.py tests/test_rest.py
git commit -m "Add reject, accept and order status to the REST surface with the full replay flow test

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Documentazione, decisioni e verifica finale

**Files:**
- Create: `docs/rest.md`
- Modify: `README.md`, `docs/decisions.md`

- [ ] **Step 1: Creare `docs/rest.md`** con: (a) una frase introduttiva (superficie REST di RF-40, bearer `VELA_API_TOKEN`); (b) le tabelle "Contratto HTTP" (endpoint, `outcome`, errori) della sezione Design di questo piano, copiate; (c) il blocco del flusso §10.3 qui sotto. Richiede `curl` e `jq`; il token si legge da una variabile già esportata e non va mai scritto nel comando né stampato.

```bash
# Prerequisiti: export VELA_URL=https://vela-n506.onrender.com  e  VELA_API_TOKEN nell'ambiente.
H="Authorization: Bearer $VELA_API_TOKEN"

curl -s "$VELA_URL/health" | jq

INTENT=$(curl -s -X POST "$VELA_URL/v1/intents" -H "$H" -H 'content-type: application/json' \
  -d '{"text":"un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro",
       "profile":{"first_name":"Anna","last_name":"Rossi","email":"anna@example.com",
                  "phone":"+390000000000","participants":[{"first_name":"Bo","last_name":"Bi"}]}}')
echo "$INTENT" | jq '{outcome, intent_id, say}'
IID=$(echo "$INTENT" | jq -r .intent_id)

P1=$(curl -s "$VELA_URL/v1/intents/$IID/proposal" -H "$H")
echo "$P1" | jq '{outcome, proposal_id, product, total_from, say}'

P2=$(curl -s -X POST "$VELA_URL/v1/proposals/$(echo "$P1" | jq -r .proposal_id)/reject" -H "$H" \
  -H 'content-type: application/json' -d '{"reason":"troppo caro"}')
echo "$P2" | jq '{outcome, proposal_id, product, total_from, say}'

ORDER=$(curl -s -X POST "$VELA_URL/v1/proposals/$(echo "$P2" | jq -r .proposal_id)/accept" -H "$H")
echo "$ORDER" | jq '{outcome, order_id, total, payment_url, say}'
OID=$(echo "$ORDER" | jq -r .order_id)

curl -s "$(echo "$ORDER" | jq -r .payment_url)" | jq      # replay: simula il pagamento
sleep 2
curl -s "$VELA_URL/v1/orders/$OID" -H "$H" | jq          # atteso: confirmed, booking_code R-xxxxxx
```

Aggiungere sotto: "In replay nessuna chiamata va a HofJ o Stripe. In `live` (da M7) il link di pagamento è Stripe: si paga con `4242 4242 4242 4242` e si interroga lo stato finché diventa `confirmed`."

- [ ] **Step 2: Aggiornare `README.md`.**
  - Riga "Stato": sostituire con `Stato: M4 (superficie REST). L'app espone GET /health, la superficie REST sotto /v1 (bearer VELA_API_TOKEN, contratto in docs/rest.md) e, in replay, GET /replay/checkout/{order_id} (pagamento simulato).` mantenendo la frase successiva sui cinque casi d'uso, con "arrivano su MCP (M3) e REST (M4)" → "sono esposti via REST (M4) e arrivano su MCP (M3)".
  - Nella sezione Deploy, riga 5: il corpo atteso di `/health` diventa `{"status":"ok","db":"ok","catalog":{...},"quota":null}`.
  - Tabella variabili, `VELA_API_TOKEN`: `| VELA_API_TOKEN | per usare /v1 | Bearer token statico della superficie REST (e del token statico MCP da M8). Senza, /v1/* risponde 503. |`
  - Struttura: `vela/surfaces   health.py, replay.py (M2), rest.py e problems.py (M4), MCP (M3), webhook (M6)`.

- [ ] **Step 3: Aggiornare `docs/decisions.md`.** In coda una sezione `## 2026-09-25 — M4: decisioni prese durante l'esecuzione` con una tabella `| Decisione | Scelta | Motivo |` che contenga ogni scelta dell'esecutore che devia da questo piano o lo precisa (se nessuna, una riga "Nessuna deviazione dal piano" con il numero di test della suite finale).

- [ ] **Step 4: Verifica finale.** Eseguire, in quest'ordine, e riportare l'esito nel messaggio di chiusura:

```bash
uv run python -m unittest discover -s tests                                        # verde, Postgres skipped
set -a; . ./.env; set +a; uv run python -m unittest discover -s tests              # verde, repository Postgres senza skip
git grep -n -E "fastapi|sqlalchemy|httpx" -- vela/domain vela/ports                # nessun risultato
git diff master --stat -- vela/domain                                              # nessuna modifica al dominio
git diff master -- pyproject.toml uv.lock                                          # vuoto
git status --short                                                                 # pulito
```

- [ ] **Step 5: Commit**

```bash
git add docs/rest.md README.md docs/decisions.md
git commit -m "Document the REST surface and the M4 decisions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7 (manuale, con l'utente, dopo il merge su `master`): criterio §10.3 in replay su Render

Nessuna chiamata a HofJ o Stripe: Render è in `replay`. Chiamate previste: 1 `/health` + 7 al flusso di `docs/rest.md`, tutte verso Vela.

- [ ] **Step 1 (utente):** impostare `VELA_API_TOKEN` nella dashboard di Render (valore generato, es. `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`, mai incollato in chat né nel repo) e verificare che `VELA_PUBLIC_URL=https://vela-n506.onrender.com`. Attendere il redeploy.
- [ ] **Step 2 (utente, nel proprio terminale):** esportare `VELA_URL` e `VELA_API_TOKEN` ed eseguire i comandi di `docs/rest.md`. Controllare anche: `curl -s -o /dev/null -w '%{http_code}' -X POST "$VELA_URL/v1/intents"` → `401`.
- [ ] **Step 3:** registrare l'esito in `docs/acceptance.md`. Se il file non esiste (M3 non ancora mergiata), crearlo con:

```markdown
# Criteri di accettazione (spec §10)

| Criterio | Data | Modalità | Esito | Note |
|---|---|---|---|---|
```

e aggiungere la riga `| 3 — flusso via REST con curl e token (RF-43) | <data> | replay, Render | <ok/ko> | codice R-xxxxxx; 401 senza token; /health catalog.products = 110 |`. Se esiste, aggiungere solo la riga.
- [ ] **Step 4: Commit** su un branch dedicato (es. `task/m4-acceptance`) o direttamente come concordato con l'utente:

```bash
git add docs/acceptance.md
git commit -m "Record acceptance criterion 3 over REST in replay on Render

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Copertura dei test di completamento della roadmap M4

| Test di completamento (roadmap) | Dove |
|---|---|
| TestClient: 401 senza token | Task 4 `AuthTest` (`test_missing_token_is_401`, `test_wrong_token_is_not_echoed`, `test_non_bearer_scheme_is_401`); Task 5 `EveryEndpointAuthTest` |
| Flusso completo in replay con token | Task 5 `FullFlowTest::test_intent_to_confirmed_over_rest` |
| Forma RFC 7807 | Task 3 `tests/test_problems.py` (401, 404, 405, 422, 500, formato predefinito fuori da `/v1`); Task 4-5 `assert_problem` su 401, 404, 422, 503, 500 |
| Invariante RF-10 | `assert_single_product` su ogni corpo di successo (Task 4, 5) e su tutte le risposte del flusso completo |
| `/health` con età catalogo e quota | Task 1 contratto `test_products_last_fetched_at` (memoria + Postgres); Task 2 `CatalogHealthTest` |
| Manuale: §10.3 in replay con `curl` su Render | Task 7, esito in `docs/acceptance.md` |

## Requisiti coperti

RF-40 (Task 3, 4, 5), RF-43 parte REST (Task 4), RF-10 sulla superficie REST (Task 4, 5), RF-42 (`say` anche negli errori, Task 3), RNF-06 parte `/health` (Task 1, 2), §10.3 in replay (Task 5 automatico, Task 7 manuale), §10.6 per REST (Task 5).

## Fuori scope (task successive)

- Quota residua reale in `/health` (M5, guardiano della quota): oggi `quota: null`.
- Log JSON con id intento/ordine (M14).
- Token statico su `/mcp` e OAuth (M8); OAuth per REST è un "prossimo passo" di M15.
- Frasi `say` in inglese, anche per gli errori (M9).
- Webhook Stripe e link reali (M6); §10.3 in `live` (M7).
- Rate limiting della superficie REST: non richiesto dalla spec.
