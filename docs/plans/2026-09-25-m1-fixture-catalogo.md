# M1 — Fixture del catalogo in locale `it`: piano di esecuzione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m1`. Destinazione di questo file: `docs/plans/2026-09-25-m1-fixture-catalogo.md`.

**Goal:** uno script `scripts/record_catalog.py` che registra `fixtures/catalog.json` (lista prodotti in locale `it` + dettaglio `extended=true` dei prodotti non archiviati) dall'API reale di House of Journeys, rispettando la quota, senza credenziali nel file, con `--dry-run`; più la fixture stessa committata.

**Architecture:** lo script importa `Client` e `QuotaGuard` da `scripts/api_explore.py` (nessuna modifica a quel file). Il `Client` salva ogni risposta grezza in una cartella **fuori dal repo** (`--raw-dir`); una seconda fase (`build_catalog`) legge quei record e assembla la fixture. Così la fixture si può ricostruire (`--build-only`) senza consumare quota, per esempio dopo aver cambiato la lista di chiavi da scartare. Il dettaglio di ogni prodotto attivo viene salvato in due forme: `catalog` (proiezione ai campi di RF-28, con i nomi dell'API) e `raw` (dettaglio esteso senza le chiavi media).

**Tech Stack:** Python 3 solo stdlib (compatibile 3.7, come `api_explore.py`), `unittest`. Nessuna dipendenza nuova.

**Spec:** `docs/spec.md` (RF-32, RF-28, §6), `docs/roadmap.md` sezione M1 (il file vive sul branch `doc/roadmap`, non mergiato: questo piano è autosufficiente, decisione dell'intervista), `docs/api/products.md`, `docs/api/quota-health.md`, `docs/api/counts.md`.

## Contesto

Vela (docs/spec.md) propone un solo viaggio di padel/tennis alla volta leggendo il catalogo da una copia locale, mai dall'API di HofJ, che ha un limite di 120 richieste al minuto. RF-32 chiede uno snapshot `fixtures/catalog.json` committato: serve alla modalità replay (M2), all'avvio a freddo e alla demo se la quota è esaurita. L'esplorazione precedente (`scripts/api_explore.py`, `docs/api/`) è stata fatta in locale `en`; la spec fissa il catalogo in locale `it`, quindi serve un nuovo giro di chiamate. In `en` la lista ha 123 prodotti in 2 pagine, di cui 92 non archiviati: in `it` i numeri possono differire e vanno verificati a runtime.

## Decisioni prese nell'intervista (da riportare in `docs/decisions.md`, Task 0)

| Decisione | Scelta | Motivo |
|---|---|---|
| Riuso | `record_catalog.py` importa `Client` e `QuotaGuard` da `api_explore.py`; le risposte grezze restano fuori dal repo in `--raw-dir` | Zero modifiche al codice esistente; la fixture si ricostruisce da `--raw-dir` senza quota |
| Contenuto | `products` = item della lista integrali (anche archiviati, così M2 testa l'esclusione); `details[id]` = `{catalog: proiezione RF-28 con nomi API, raw: dettaglio esteso senza chiavi media}` solo per i non archiviati | RF-28 vuole i campi elencati **e** il JSON grezzo; le immagini non servono a Vela e pesano; obiettivo ≈ 1 MB |
| Hotel di default | La proiezione porta `hotels` (= `rawAttributes.hotels` senza media) così com'è; la scelta dell'hotel di default è di M2 | La forma di `rawAttributes.hotels` non è documentata: niente estrazione a indovinare |
| Chiave API | `HOFJ_API_KEY` (spec §6), fallback `API_BEAR_KEY` (già nel `.env`) | Nessun cambio al `.env` esistente, nome finale della spec |
| Brand | `HOFJ_BRAND` opzionale: se assente il parametro non viene inviato (default del server, `weebora.com`) e il file ha `brand: null` | Configurazione da env come in spec §6 |
| Dry-run | Nessuna chiamata; stima dalle dimensioni di una fixture esistente, altrimenti dai numeri di `docs/api/counts.md` (123 / 92) | Il numero esatto di dettagli si conosce solo dopo la lista |
| Cartella grezza | `record` rifiuta una `--raw-dir` non vuota | Evita di mischiare due registrazioni |
| Validazione | `tests/test_catalog_fixture.py` verifica il file committato e si salta se il file manca | RNF-09: suite verde senza servizi esterni |
| Roadmap | `docs/roadmap.md` non viene mergiata su `task/m1` | Il piano è autosufficiente; conflitto banale su `decisions.md` al merge |

## Global Constraints

- Solo stdlib, compatibile con Python 3.7 (come `scripts/api_explore.py`).
- La chiave viene letta solo dall'ambiente; mai stampata, mai salvata, mai nel repo (`.claude/settings.json` nega la lettura di `.env`).
- Chiamate esterne dichiarate prima dell'esecuzione: previste ≈ 96 autenticate (2 liste + ~92 dettagli + 2 sync quota) in 2 finestre da 60 s; se il dry-run ne stima più di 110, fermarsi e chiedere.
- Nessuna chiamata di rete nei test automatici; `python3 -m unittest discover -s tests` deve restare verde.
- Commit piccoli con messaggio chiaro; niente force push; mai `git stash` nudo.
- Struttura di destinazione: `scripts/record_catalog.py`, `tests/test_record_catalog.py`, `tests/test_catalog_fixture.py`, `fixtures/catalog.json`, `docs/fixtures.md`.

## Review Focus

1. La lista in `it` ha un numero di prodotti diverso da `en` (traduzioni mancanti o nuovi prodotti): lo script non deve dipendere da 123/92 (test `test_paginates_and_fetches_details_only_for_active`, Task 3).
2. Un dettaglio risponde 502 `upstream-error` per un prodotto attivo: la registrazione continua, la costruzione fallisce elencando gli id mancanti e non scrive un file parziale (test `test_detail_error_is_recorded_not_fatal`, Task 3, e `test_missing_detail_raises_with_ids`, Task 2).
3. La chiave finisce nei file grezzi, nei log o nella fixture: mai (test `test_key_never_written_or_logged`, Task 3, e `test_no_credentials_or_media`, Task 5).
4. Lo stesso id compare in due pagine (il cursore è un numero di pagina e il catalogo può cambiare durante la registrazione): l'ultimo vince, nessun duplicato (test `test_duplicate_ids_last_wins`, Task 2).
5. `HOFJ_BRAND` sconosciuto: il server risponde 400 sulla lista; lo script si ferma con un messaggio chiaro invece di scaricare 0 dettagli e scrivere una fixture vuota (test `test_list_error_raises`, Task 3).

## Formato di `fixtures/catalog.json`

```json
{
  "recorded_at": "2026-09-25T15:02:11.482000+00:00",
  "locale": "it",
  "brand": null,
  "base_url": "https://api.hofj.com",
  "products": [ { "...item della lista, 32 campi, integrale..." } ],
  "details": {
    "12": {
      "catalog": {
        "id": "12", "title": "...", "slug": "...", "shortDescription": "...",
        "price": 340, "currency": "EUR", "minPax": 2, "maxPax": null,
        "minDate": "2026-09-25", "maxDate": "2027-01-07",
        "availabilities": [ { "status": "Bookable", "startDate": "...", "endDate": "...", "serviceLevels": [] } ],
        "defaultDurationInDays": 3, "updatedAt": "2026-09-25T09:20:18.757Z",
        "category": { "id": "1", "name": "...", "slug": "..." },
        "venue": { "id": "194", "title": "...", "slug": "..." },
        "destination": { "id": "17", "title": "...", "slug": "...", "country": "...", "geohierarchy": "..." },
        "hotels": { "data": [ "...rawAttributes.hotels senza media..." ] }
      },
      "raw": { "...dettaglio extended senza gallery/image/travelProgram e senza chiavi media dentro rawAttributes..." }
    }
  }
}
```

`products` conserva l'ordine dell'API (id crescente). `details` contiene solo i prodotti con `archived: false`, nello stesso ordine. `venue` e `destination` possono essere `null` (5 prodotti su 123 in `en`).

---

### Task 0: Salvare piano e decisioni nel repo

**Files:**
- Create: `docs/plans/2026-09-25-m1-fixture-catalogo.md` (questo file, identico)
- Modify: `docs/decisions.md` (aggiungere una sezione in coda)

- [ ] **Step 1: Copiare il piano** in `docs/plans/2026-09-25-m1-fixture-catalogo.md` (creare la cartella `docs/plans/`).

- [ ] **Step 2: Aggiungere a `docs/decisions.md`** la sezione seguente, in coda al file:

```markdown

## 2026-09-25 — M1: fixture del catalogo in locale `it`

Origine: intervista sulla macro task M1, piano in `docs/plans/2026-09-25-m1-fixture-catalogo.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Riuso | `scripts/record_catalog.py` importa `Client` e `QuotaGuard` da `scripts/api_explore.py`; le risposte grezze restano fuori dal repo in `--raw-dir` | Zero modifiche al codice esistente; la fixture si ricostruisce con `--build-only` senza consumare quota |
| Contenuto della fixture | `products` = item della lista integrali (anche archiviati); `details[id]` = `{catalog: proiezione ai campi di RF-28 con i nomi dell'API, raw: dettaglio esteso senza chiavi media}` solo per i non archiviati | RF-28 vuole i campi elencati e il JSON grezzo; le immagini non servono e pesano; obiettivo ≈ 1 MB |
| Hotel di default | La proiezione porta `hotels` (= `rawAttributes.hotels` senza media) così com'è; la scelta dell'hotel è di M2 | La forma di `rawAttributes.hotels` non è documentata |
| Chiave API | `HOFJ_API_KEY` (spec §6) con fallback `API_BEAR_KEY` | Nome della spec senza cambiare il `.env` esistente |
| Brand | `HOFJ_BRAND` opzionale: se assente il parametro non viene inviato e il file ha `brand: null` | Configurazione da env come in spec §6 |
| Dry-run | Nessuna chiamata; stima dalla fixture esistente, altrimenti da `docs/api/counts.md` (123 prodotti, 92 attivi) | Il numero esatto di dettagli si conosce solo dopo la lista |
| Cartella grezza | La registrazione rifiuta una `--raw-dir` non vuota | Evita di mischiare due registrazioni |
| Validazione | `tests/test_catalog_fixture.py` verifica il file committato e si salta se manca | RNF-09: suite verde senza servizi esterni |
| Roadmap | `docs/roadmap.md` resta sul branch `doc/roadmap`, non mergiata su `task/m1` | Il piano è autosufficiente |
```

- [ ] **Step 3: Commit**

```bash
git add docs/plans/2026-09-25-m1-fixture-catalogo.md docs/decisions.md
git commit -m "Add M1 plan for the catalog fixture and record its decisions"
```

---

### Task 1: `strip_media` e `project_detail` (funzioni pure)

**Files:**
- Create: `scripts/record_catalog.py`
- Create: `tests/test_record_catalog.py`

**Interfaces:**
- Produces: `strip_media(value) -> copia ricorsiva senza le chiavi in MEDIA_KEYS`; `project_detail(detail: dict) -> dict` con le chiavi `id, title, slug, shortDescription, price, currency, minPax, maxPax, minDate, maxDate, availabilities, defaultDurationInDays, updatedAt, category, venue, destination, hotels` (valore `None` se il campo manca); costanti `LOCALE = "it"`, `MEDIA_KEYS`, `CATALOG_FIELDS`.

- [ ] **Step 1: Scrivere il test che fallisce** in `tests/test_record_catalog.py`. Gli helper `item` e `detail_of` restano in cima al file: li usano anche i task successivi.

```python
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import api_explore  # noqa: E402
import record_catalog  # noqa: E402


def item(pid, archived=False, **over):
    """Item della lista /v1/products come lo restituisce l'API (campi principali)."""
    base = {
        "id": str(pid), "slug": "padel-%d" % pid, "title": "Padel %d" % pid,
        "shortDescription": "breve", "description": "**lunga**", "archived": archived,
        "channelId": "1", "venueId": "194", "categoryId": "1", "destinationId": "17",
        "createdAt": "2026-03-09T09:26:05.776Z", "updatedAt": "2026-09-25T09:20:18.757Z",
        "publishedAt": "2026-03-10T11:54:04.217Z", "tripCode": "MKT_%d" % pid,
        "providerID": "t%07d" % pid, "price": 340, "currency": "EUR", "minPax": 2,
        "maxPax": None, "minDate": "2026-09-25", "maxDate": "2027-01-07",
        "defaultDurationInDays": 3, "hotelSelection": False, "locale": "it",
        "availabilities": [] if archived else [
            {"status": "Bookable", "startDate": "2026-09-28", "endDate": "2026-10-01",
             "serviceLevels": []}],
    }
    base.update(over)
    return base


def detail_of(list_item):
    """Dettaglio extended=true dello stesso prodotto, con i campi pesanti da scartare."""
    detail = dict(list_item)
    detail.update({
        "category": {"id": "1", "name": "Padel", "slug": "padel"},
        "venue": {"id": "194", "title": "Club", "slug": "club", "coverUrl": "https://x/v.jpg"},
        "destination": {"id": "17", "title": "Sinalunga", "slug": "sinalunga", "country": "IT",
                        "geohierarchy": "IT_123", "coverUrl": "https://x/d.jpg"},
        "image": {"url": "https://x/i.jpg", "width": 1, "height": 1},
        "gallery": [{"url": "https://x/g1.jpg", "source": "venue"}],
        "travelProgram": {"id": "733", "description": "...", "details": []},
        "rawAttributes": {
            "hotels": {"data": [{"id": 5, "attributes": {"name": "Hotel Uno",
                                                         "gallery": {"data": []}}}]},
            "gallery": {"data": [{"id": 1}]}, "cover": {"data": {"id": 2}},
            "playtomicLevel": "3",
        },
    })
    return detail


class StripMediaTest(unittest.TestCase):
    def test_removes_media_keys_at_any_depth_without_touching_input(self):
        detail = detail_of(item(12))
        out = record_catalog.strip_media(detail)
        for key in ("gallery", "image", "travelProgram"):
            self.assertNotIn(key, out)
        self.assertNotIn("gallery", out["rawAttributes"])
        self.assertNotIn("cover", out["rawAttributes"])
        hotel = out["rawAttributes"]["hotels"]["data"][0]["attributes"]
        self.assertEqual(hotel, {"name": "Hotel Uno"})
        self.assertEqual(out["venue"]["coverUrl"], "https://x/v.jpg")  # una stringa URL resta
        self.assertEqual(out["rawAttributes"]["playtomicLevel"], "3")
        self.assertIn("gallery", detail)  # l'originale non viene modificato

    def test_scalars_and_lists_pass_through(self):
        self.assertEqual(record_catalog.strip_media([1, {"gallery": 1, "a": 2}]), [1, {"a": 2}])
        self.assertIsNone(record_catalog.strip_media(None))


class ProjectDetailTest(unittest.TestCase):
    def test_keeps_rf28_fields_with_api_names(self):
        catalog = record_catalog.project_detail(detail_of(item(12)))
        self.assertEqual(sorted(catalog), sorted([
            "id", "title", "slug", "shortDescription", "price", "currency", "minPax", "maxPax",
            "minDate", "maxDate", "availabilities", "defaultDurationInDays", "updatedAt",
            "category", "venue", "destination", "hotels"]))
        self.assertEqual(catalog["category"]["slug"], "padel")
        self.assertEqual(catalog["destination"]["geohierarchy"], "IT_123")
        self.assertEqual(catalog["hotels"]["data"][0]["attributes"], {"name": "Hotel Uno"})
        self.assertEqual(catalog["price"], 340)

    def test_missing_fields_become_none(self):
        catalog = record_catalog.project_detail({"id": "1"})
        self.assertIsNone(catalog["venue"])
        self.assertIsNone(catalog["hotels"])
        self.assertIsNone(catalog["price"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Eseguire il test e vedere che fallisce**

Run: `python3 -m unittest tests.test_record_catalog -v`
Expected: `ModuleNotFoundError: No module named 'record_catalog'`

- [ ] **Step 3: Scrivere `scripts/record_catalog.py`** con docstring, costanti e le due funzioni.

```python
#!/usr/bin/env python3
"""Registra fixtures/catalog.json dalla House of Journeys API in locale `it`.

Uso:
  record_catalog.py --raw-dir DIR --dry-run     # stampa le chiamate previste, nessuna rete
  record_catalog.py --raw-dir DIR               # registra in DIR (nuova o vuota), scrive la fixture
  record_catalog.py --raw-dir DIR --build-only  # ricostruisce la fixture da DIR senza chiamate

La chiave viene letta SOLO dalle variabili d'ambiente HOFJ_API_KEY (o API_BEAR_KEY) e non
viene mai stampata né salvata. DIR sta FUORI dal repository: contiene le risposte grezze
salvate da api_explore.Client, così la fixture si può ricostruire senza consumare quota.

Solo stdlib, compatibile con Python 3.7.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_explore  # noqa: E402

LOCALE = "it"
PAGE_LIMIT = api_explore.PAGE_LIMIT
KEY_ENVS = ("HOFJ_API_KEY", "API_BEAR_KEY")
BRAND_ENV = "HOFJ_BRAND"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures",
                           "catalog.json")
EXPECTED_TOTAL = 123   # docs/api/counts.md (locale en): stima usata dal dry-run
EXPECTED_ACTIVE = 92
# chiavi scartate a ogni profondità del dettaglio: immagini e programma di viaggio
MEDIA_KEYS = frozenset(["gallery", "image", "images", "cover", "media", "travelProgram"])
# campi di RF-28 presi pari pari dal dettaglio (category, venue, destination, hotels a parte)
CATALOG_FIELDS = ("id", "title", "slug", "shortDescription", "price", "currency", "minPax",
                  "maxPax", "minDate", "maxDate", "availabilities", "defaultDurationInDays",
                  "updatedAt")


def strip_media(value):
    """Copia ricorsiva di `value` senza le chiavi in MEDIA_KEYS. Non modifica l'input."""
    if isinstance(value, dict):
        return {k: strip_media(v) for k, v in value.items() if k not in MEDIA_KEYS}
    if isinstance(value, list):
        return [strip_media(v) for v in value]
    return value


def project_detail(detail):
    """Campi di RF-28 presi dal dettaglio esteso, con i nomi dell'API; None se mancanti."""
    catalog = {k: detail.get(k) for k in CATALOG_FIELDS}
    catalog["category"] = detail.get("category")
    catalog["venue"] = detail.get("venue")
    catalog["destination"] = detail.get("destination")
    raw_attributes = detail.get("rawAttributes") or {}
    catalog["hotels"] = strip_media(raw_attributes.get("hotels"))
    return catalog
```

- [ ] **Step 4: Eseguire i test e vedere che passano**

Run: `python3 -m unittest discover -s tests -v`
Expected: tutti `ok` (i test di `api_explore` e `agents_log` compresi).

- [ ] **Step 5: Commit**

```bash
git add scripts/record_catalog.py tests/test_record_catalog.py
git commit -m "Add strip_media and project_detail for the catalog fixture"
```

---

### Task 2: `build_catalog` dai record grezzi

**Files:**
- Modify: `scripts/record_catalog.py`
- Modify: `tests/test_record_catalog.py`

**Interfaces:**
- Consumes: `api_explore.Client(out_dir, guard, api_key, base_url=, opener=, sleep=, log=, dry_run=)` che salva record `{"path", "params", "status", "body", "requestedAt", ...}` in `out_dir`; `api_explore.load_records(out_dir)` che li rilegge in ordine.
- Produces: `class BuildError(RuntimeError)`; `detail_id(record) -> str | None`; `build_catalog(raw_dir, locale="it", brand=None) -> dict` (formato della sezione "Formato"); `write_catalog(catalog, out_path)`.

- [ ] **Step 1: Aggiungere al test** il server finto (usato anche dal Task 3) e i test di costruzione. Inserire dopo `detail_of` e prima di `StripMediaTest`:

```python
def quota_body(used, remaining, ends="2026-09-25T09:54:47.409Z"):
    return {"data": {"clientId": "c", "limitPerMinute": 120, "usedInWindow": used,
                     "remainingInWindow": remaining, "windowEndsAt": ends,
                     "backend": "firestore"}}


class FakeResponse(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode("utf-8"))
        self.status = status
        self.headers = {"Content-Type": "application/json"}


class FakeHofj:
    """Server finto: /v1/quota, lista paginata per cursore, dettaglio per id.

    Simula il 429 oltre `limit` richieste per finestra; `new_window` azzera il contatore
    (va passato come `sleep` al Client). `broken_ids` rispondono 502 al dettaglio,
    `list_status` diverso da 200 fa fallire la lista.
    """

    def __init__(self, products, limit=120, page_size=100, broken_ids=(), list_status=200):
        self.products = products
        self.limit = limit
        self.page_size = page_size
        self.broken_ids = set(broken_ids)
        self.list_status = list_status
        self.calls = []            # (path, query dict, headers dict)
        self.window_used = 0
        self.max_window_used = 0

    def new_window(self, *_):
        self.window_used = 0

    def __call__(self, req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        query = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((url.path, query, dict(req.header_items())))
        self.window_used += 1
        self.max_window_used = max(self.max_window_used, self.window_used)
        if self.window_used > self.limit:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b"{}"))
        if url.path == "/v1/quota":
            return FakeResponse(200, quota_body(self.window_used, 120 - self.window_used))
        if url.path == "/v1/products":
            if self.list_status != 200:
                return FakeResponse(self.list_status, {"title": "bad request"})
            page = int(query.get("cursor", "p1")[1:])
            start = (page - 1) * self.page_size
            chunk = self.products[start:start + self.page_size]
            more = start + self.page_size < len(self.products)
            return FakeResponse(200, {"data": chunk,
                                      "meta": {"nextCursor": "p%d" % (page + 1) if more else None}})
        match = re.match(r"^/v1/products/(\d+)$", url.path)
        if match:
            pid = match.group(1)
            if pid in self.broken_ids:
                return FakeResponse(502, {"type": "https://api.hofj.com/problems/upstream-error",
                                          "status": 502})
            for product in self.products:
                if product["id"] == pid:
                    return FakeResponse(200, {"data": detail_of(product)})
            return FakeResponse(502, {"title": "upstream-error"})
        return FakeResponse(404, {"title": "not found"})


def make_client(raw_dir, server, logs, cap=90):
    return api_explore.Client(raw_dir, api_explore.QuotaGuard(cap=cap), "SECRET-KEY",
                              base_url="https://api.test", opener=server,
                              sleep=server.new_window, log=logs.append)


def record_pages_and_details(client, products, locale="it"):
    """Simula a mano una registrazione: una pagina di lista e i dettagli indicati."""
    client.get("/v1/products", {"limit": 100, "locale": locale})
    for pid in products:
        client.get("/v1/products/%s" % pid, {"extended": "true", "locale": locale})
```

Poi aggiungere la classe di test (dopo `ProjectDetailTest`):

```python
class BuildCatalogTest(unittest.TestCase):
    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self.logs = []

    def test_builds_products_and_active_details(self):
        server = FakeHofj([item(1), item(2, archived=True), item(3)])
        record_pages_and_details(make_client(self.raw, server, self.logs), ["1", "3"])
        catalog = record_catalog.build_catalog(self.raw)
        self.assertEqual([p["id"] for p in catalog["products"]], ["1", "2", "3"])
        self.assertEqual(list(catalog["details"]), ["1", "3"])
        self.assertEqual(catalog["details"]["1"]["catalog"]["category"]["slug"], "padel")
        self.assertNotIn("gallery", catalog["details"]["1"]["raw"])
        self.assertIn("rawAttributes", catalog["details"]["1"]["raw"])
        self.assertEqual((catalog["locale"], catalog["brand"]), ("it", None))
        self.assertEqual(catalog["base_url"], api_explore.BASE_URL)
        self.assertRegex(catalog["recorded_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertIn("description", catalog["products"][0])  # item della lista integrale

    def test_brand_is_written_as_given(self):
        server = FakeHofj([item(1)])
        record_pages_and_details(make_client(self.raw, server, self.logs), ["1"])
        self.assertEqual(record_catalog.build_catalog(self.raw, brand="weebora.com")["brand"],
                         "weebora.com")

    def test_ignores_other_locales_and_failed_calls(self):
        server = FakeHofj([item(1)], broken_ids=["1"])
        client = make_client(self.raw, server, self.logs)
        client.get("/v1/products", {"limit": 100, "locale": "en"})   # locale sbagliato
        client.get("/v1/products", {"limit": 100, "locale": "it"})
        client.get("/v1/products/1", {"extended": "true", "locale": "it"})  # 502
        with self.assertRaises(record_catalog.BuildError) as ctx:
            record_catalog.build_catalog(self.raw)
        self.assertIn("1", str(ctx.exception))

    def test_missing_detail_raises_with_ids(self):
        server = FakeHofj([item(1), item(3), item(4, archived=True)])
        record_pages_and_details(make_client(self.raw, server, self.logs), ["1"])
        with self.assertRaises(record_catalog.BuildError) as ctx:
            record_catalog.build_catalog(self.raw)
        self.assertIn("3", str(ctx.exception))
        self.assertNotIn("4", str(ctx.exception))  # archiviato: nessun dettaglio atteso

    def test_duplicate_ids_last_wins(self):
        server = FakeHofj([item(1, title="vecchio")])
        client = make_client(self.raw, server, self.logs)
        client.get("/v1/products", {"limit": 100, "locale": "it"})
        server.products = [item(1, title="nuovo")]
        client.get("/v1/products", {"limit": 100, "locale": "it", "cursor": "p1"})
        client.get("/v1/products/1", {"extended": "true", "locale": "it"})
        catalog = record_catalog.build_catalog(self.raw)
        self.assertEqual(len(catalog["products"]), 1)
        self.assertEqual(catalog["products"][0]["title"], "nuovo")

    def test_empty_raw_dir_raises(self):
        with self.assertRaises(record_catalog.BuildError):
            record_catalog.build_catalog(self.raw)

    def test_write_catalog_creates_dir_and_trailing_newline(self):
        out = os.path.join(self.raw, "fixtures", "catalog.json")
        record_catalog.write_catalog({"a": "è"}, out)
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.endswith("}\n"))
        self.assertIn("è", text)  # ensure_ascii=False
```

- [ ] **Step 2: Eseguire il test e vedere che fallisce**

Run: `python3 -m unittest tests.test_record_catalog.BuildCatalogTest -v`
Expected: `AttributeError: module 'record_catalog' has no attribute 'build_catalog'`

- [ ] **Step 3: Implementare** in `scripts/record_catalog.py`, dopo `project_detail`:

```python
class BuildError(RuntimeError):
    """La cartella grezza non basta a costruire una fixture completa."""


def detail_id(record):
    """Id del prodotto se il record è un dettaglio esteso riuscito, altrimenti None."""
    match = re.match(r"^/v1/products/([^/]+)$", record["path"])
    if match and record["params"].get("extended") == "true" and record["status"] == 200:
        return match.group(1)
    return None


def build_catalog(raw_dir, locale=LOCALE, brand=None):
    """Assembla la fixture dai record salvati da api_explore.Client in `raw_dir`.

    Lista: tutti gli item (anche archiviati), l'ultimo record vince a parità di id.
    Dettagli: solo i prodotti non archiviati; se ne manca uno solleva BuildError.
    """
    products, details, stamps = {}, {}, []
    for record in api_explore.load_records(raw_dir):
        body = record["body"] if isinstance(record["body"], dict) else {}
        if record["params"].get("locale") != locale:
            continue
        if record["path"] == "/v1/products" and record["status"] == 200:
            for product in body.get("data") or []:
                products[str(product["id"])] = product
            stamps.append(record["requestedAt"])
        pid = detail_id(record)
        if pid and isinstance(body.get("data"), dict):
            details[pid] = body["data"]
            stamps.append(record["requestedAt"])
    if not products:
        raise BuildError("nessuna pagina di /v1/products (locale %s) in %s" % (locale, raw_dir))
    active = [pid for pid, product in products.items() if not product.get("archived")]
    missing = [pid for pid in active if pid not in details]
    if missing:
        raise BuildError("dettaglio mancante per %d prodotti non archiviati: %s"
                         % (len(missing), ", ".join(missing)))
    return {
        "recorded_at": max(stamps),
        "locale": locale,
        "brand": brand,
        "base_url": api_explore.BASE_URL,
        "products": list(products.values()),
        "details": {pid: {"catalog": project_detail(details[pid]),
                          "raw": strip_media(details[pid])} for pid in active},
    }


def write_catalog(catalog, out_path):
    """Scrive la fixture: indent=1 per contenere la dimensione, UTF-8 non escapato."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
```

Nota: `products` mantiene l'ordine di inserimento (dict ordinati da Python 3.7), quindi l'ordine dell'API; in `test_duplicate_ids_last_wins` l'aggiornamento di una chiave esistente non ne cambia la posizione.

- [ ] **Step 4: Eseguire i test e vedere che passano**

Run: `python3 -m unittest discover -s tests -v`
Expected: tutti `ok`.

- [ ] **Step 5: Commit**

```bash
git add scripts/record_catalog.py tests/test_record_catalog.py
git commit -m "Build catalog.json from recorded HofJ responses"
```

---

### Task 3: `record`: lista paginata e dettagli entro la quota

**Files:**
- Modify: `scripts/record_catalog.py`
- Modify: `tests/test_record_catalog.py`

**Interfaces:**
- Consumes: `api_explore.Client.get(path, params)` (filtra i parametri `None`, sincronizza la quota, attende a fine finestra, solleva `QuotaExceededError` su 429; in `dry_run` accoda a `client.planned` e restituisce `None`); `client.log`.
- Produces: `record(client, locale="it", brand=None, expected=(EXPECTED_TOTAL, EXPECTED_ACTIVE)) -> list | None` (in dry-run pianifica soltanto e restituisce `None`); `call_plan(n_calls, cap=api_explore.CAP_PER_WINDOW) -> (finestre, chiamate_totali_con_sync)`.

- [ ] **Step 1: Aggiungere i test** (dopo `BuildCatalogTest`):

```python
class RecordTest(unittest.TestCase):
    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self.logs = []

    def test_paginates_and_fetches_details_only_for_active(self):
        products = [item(i, archived=(i % 3 == 0)) for i in range(1, 8)]  # 3 e 6 archiviati
        server = FakeHofj(products, page_size=5)
        record_catalog.record(make_client(self.raw, server, self.logs), brand="weebora.com")
        lists = [q for p, q, _ in server.calls if p == "/v1/products"]
        self.assertEqual(len(lists), 2)
        self.assertEqual(lists[0], {"limit": "100", "locale": "it", "brand": "weebora.com"})
        self.assertEqual(lists[1]["cursor"], "p2")
        details = [p for p, _, _ in server.calls if p.startswith("/v1/products/")]
        self.assertEqual(details, ["/v1/products/%d" % i for i in (1, 2, 4, 5, 7)])
        query = [q for p, q, _ in server.calls if p == "/v1/products/1"][0]
        self.assertEqual(query, {"extended": "true", "locale": "it", "brand": "weebora.com"})
        self.assertEqual(server.calls[0][0], "/v1/quota")
        self.assertEqual(server.calls[1][2]["Authorization"], "Bearer SECRET-KEY")

    def test_brand_omitted_when_none(self):
        server = FakeHofj([item(1)])
        record_catalog.record(make_client(self.raw, server, self.logs))
        for path, query, _ in server.calls:
            self.assertNotIn("brand", query, path)

    def test_key_never_written_or_logged(self):
        server = FakeHofj([item(1), item(2)])
        record_catalog.record(make_client(self.raw, server, self.logs))
        dump = "".join(self.logs)
        for name in os.listdir(self.raw):
            with open(os.path.join(self.raw, name), encoding="utf-8") as fh:
                dump += fh.read()
        self.assertNotIn("SECRET-KEY", dump)
        self.assertNotIn("Authorization", dump)

    def test_paces_within_cap_across_windows(self):
        server = FakeHofj([item(i) for i in range(1, 96)])  # 95 attivi
        record_catalog.record(make_client(self.raw, server, self.logs, cap=90))
        quota_calls = [p for p, _, _ in server.calls if p == "/v1/quota"]
        self.assertEqual(len(quota_calls), 2)           # sync iniziale + sync dopo l'attesa
        self.assertLessEqual(server.max_window_used, 90)
        self.assertEqual(len(server.calls), 1 + 95 + 2)  # lista + dettagli + 2 sync

    def test_429_stops_and_keeps_partial_raw(self):
        server = FakeHofj([item(i) for i in range(1, 6)], limit=3)
        with self.assertRaises(api_explore.QuotaExceededError):
            record_catalog.record(make_client(self.raw, server, self.logs))
        self.assertGreaterEqual(len(os.listdir(self.raw)), 2)  # quota + lista salvate

    def test_detail_error_is_recorded_not_fatal(self):
        server = FakeHofj([item(1), item(2)], broken_ids=["1"])
        record_catalog.record(make_client(self.raw, server, self.logs))
        details = [p for p, _, _ in server.calls if p.startswith("/v1/products/")]
        self.assertEqual(details, ["/v1/products/1", "/v1/products/2"])
        with self.assertRaises(record_catalog.BuildError) as ctx:
            record_catalog.build_catalog(self.raw)
        self.assertIn("1", str(ctx.exception))

    def test_list_error_raises(self):
        server = FakeHofj([item(1)], list_status=400)
        with self.assertRaises(RuntimeError) as ctx:
            record_catalog.record(make_client(self.raw, server, self.logs))
        self.assertIn("400", str(ctx.exception))
        self.assertEqual([p for p, _, _ in server.calls if p.startswith("/v1/products/")], [])

    def test_dry_run_plans_from_expected_counts(self):
        server = FakeHofj([])
        client = api_explore.Client(self.raw, api_explore.QuotaGuard(), "", base_url="https://api.test",
                                    opener=server, log=self.logs.append, dry_run=True)
        record_catalog.record(client, expected=(123, 92))
        self.assertEqual(server.calls, [])
        self.assertEqual(os.listdir(self.raw), [])
        lists = [p for p, _, _ in client.planned if p == "/v1/products"]
        self.assertEqual(len(lists), 2)
        self.assertEqual(len(client.planned), 2 + 92)


class CallPlanTest(unittest.TestCase):
    def test_windows_and_total_include_quota_syncs(self):
        self.assertEqual(record_catalog.call_plan(94, cap=90), (2, 96))   # 89 + 5
        self.assertEqual(record_catalog.call_plan(89, cap=90), (1, 90))
        self.assertEqual(record_catalog.call_plan(1, cap=90), (1, 2))
```

- [ ] **Step 2: Eseguire il test e vedere che fallisce**

Run: `python3 -m unittest tests.test_record_catalog.RecordTest tests.test_record_catalog.CallPlanTest -v`
Expected: `AttributeError: module 'record_catalog' has no attribute 'record'`

- [ ] **Step 3: Implementare** in `scripts/record_catalog.py`, dopo `write_catalog`:

```python
def record(client, locale=LOCALE, brand=None, expected=(EXPECTED_TOTAL, EXPECTED_ACTIVE)):
    """Scarica la lista paginata e il dettaglio esteso dei prodotti non archiviati.

    In dry-run non conosce i numeri reali: pianifica dalle stime `expected`
    (prodotti totali, non archiviati) e restituisce None. Un dettaglio che fallisce
    non ferma il giro: sarà build_catalog a segnalare gli id mancanti.
    """
    if client.dry_run:
        total, active = expected
        pages = max(1, -(-total // PAGE_LIMIT))
        for n in range(pages):
            client.get("/v1/products", {"limit": PAGE_LIMIT, "locale": locale, "brand": brand,
                                        "cursor": "pagina-%d" % (n + 1) if n else None})
        for _ in range(active):
            client.get("/v1/products/{id}", {"extended": "true", "locale": locale, "brand": brand})
        return None

    cursor, products = None, []
    while True:
        page = client.get("/v1/products", {"limit": PAGE_LIMIT, "locale": locale,
                                           "brand": brand, "cursor": cursor})
        if page["status"] != 200:
            raise RuntimeError("lista prodotti: HTTP %d %s" % (page["status"],
                                                               json.dumps(page["body"])[:300]))
        products.extend(page["body"].get("data") or [])
        cursor = (page["body"].get("meta") or {}).get("nextCursor")
        if not cursor:
            break
    active = [p for p in products if not p.get("archived")]
    client.log("%d prodotti in lista, %d non archiviati: scarico i dettagli"
               % (len(products), len(active)))
    for product in active:
        client.get("/v1/products/%s" % product["id"],
                   {"extended": "true", "locale": locale, "brand": brand})
    return products


def call_plan(n_calls, cap=api_explore.CAP_PER_WINDOW):
    """(finestre da 60 s, chiamate autenticate totali) per n_calls, contando un sync
    di /v1/quota per finestra: ogni finestra ospita al più cap - 1 chiamate utili."""
    windows = max(1, -(-n_calls // (cap - 1)))
    return windows, n_calls + windows
```

- [ ] **Step 4: Eseguire i test e vedere che passano**

Run: `python3 -m unittest discover -s tests -v`
Expected: tutti `ok`. Se `test_paces_within_cap_across_windows` fallisce sul conteggio, controllare che `make_client` passi `server.new_window` come `sleep` (a fine finestra il server finto riparte da zero).

- [ ] **Step 5: Commit**

```bash
git add scripts/record_catalog.py tests/test_record_catalog.py
git commit -m "Record product list and extended details within the HofJ quota"
```

---

### Task 4: CLI `main` con `--dry-run`, registrazione e `--build-only`

**Files:**
- Modify: `scripts/record_catalog.py`
- Modify: `tests/test_record_catalog.py`

**Interfaces:**
- Consumes: `record`, `call_plan`, `build_catalog`, `write_catalog`, `api_explore.Client`, `api_explore.QuotaGuard`.
- Produces: `expected_counts(out_path) -> (totale, attivi)`; `main(argv=None)`; opzioni `--raw-dir` (obbligatoria), `--out` (default `fixtures/catalog.json`), `--dry-run`, `--build-only`. Uscite con `sys.exit(messaggio)` (codice 1) su chiave assente, cartella non vuota, 429/errore di lista, fixture incompleta.

- [ ] **Step 1: Aggiungere i test** (dopo `CallPlanTest`):

```python
def run_main(argv, env):
    """Esegue main con un ambiente controllato e cattura stdout."""
    out = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
        record_catalog.main(argv)
    return out.getvalue()


class MainTest(unittest.TestCase):
    def setUp(self):
        self.raw = os.path.join(tempfile.mkdtemp(), "raw")
        self.out = os.path.join(tempfile.mkdtemp(), "fixtures", "catalog.json")

    def test_dry_run_needs_no_key_and_makes_no_calls(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("rete usata")):
            text = run_main(["--raw-dir", self.raw, "--out", self.out, "--dry-run"], {})
        self.assertIn("2 liste + 92 dettagli + 2 sync quota = 96 autenticate", text)
        self.assertIn("2 finestre", text)
        self.assertEqual(os.listdir(self.raw), [])
        self.assertFalse(os.path.exists(self.out))

    def test_dry_run_uses_existing_fixture_counts(self):
        record_catalog.write_catalog({"products": [{} for _ in range(10)],
                                      "details": {str(i): {} for i in range(4)}}, self.out)
        text = run_main(["--raw-dir", self.raw, "--out", self.out, "--dry-run"], {})
        self.assertIn("1 liste + 4 dettagli + 1 sync quota = 6 autenticate", text)

    def test_missing_key_exits_before_any_call(self):
        with self.assertRaises(SystemExit) as ctx:
            run_main(["--raw-dir", self.raw, "--out", self.out], {})
        self.assertIn("HOFJ_API_KEY", str(ctx.exception))
        self.assertFalse(os.path.exists(self.out))

    def test_fallback_key_env_is_accepted(self):
        server = FakeHofj([item(1)])
        with mock.patch("urllib.request.urlopen", server):
            run_main(["--raw-dir", self.raw, "--out", self.out], {"API_BEAR_KEY": "SECRET-KEY"})
        self.assertEqual(server.calls[1][2]["Authorization"], "Bearer SECRET-KEY")

    def test_non_empty_raw_dir_is_refused(self):
        os.makedirs(self.raw)
        with open(os.path.join(self.raw, "001-GET-x.json"), "w") as fh:
            fh.write("{}")
        with self.assertRaises(SystemExit) as ctx:
            run_main(["--raw-dir", self.raw, "--out", self.out], {"HOFJ_API_KEY": "SECRET-KEY"})
        self.assertIn("non è vuota", str(ctx.exception))

    def test_full_run_records_and_writes_fixture(self):
        server = FakeHofj([item(1), item(2, archived=True), item(3)])
        with mock.patch("urllib.request.urlopen", server):
            text = run_main(["--raw-dir", self.raw, "--out", self.out],
                            {"HOFJ_API_KEY": "SECRET-KEY", "HOFJ_BRAND": "weebora.com"})
        self.assertIn("richieste autenticate eseguite: 4", text)  # quota + lista + 2 dettagli
        self.assertIn("3 prodotti, 2 dettagli", text)
        with open(self.out, encoding="utf-8") as fh:
            catalog = json.load(fh)
        self.assertEqual(catalog["brand"], "weebora.com")
        self.assertEqual(sorted(catalog["details"]), ["1", "3"])
        self.assertNotIn("SECRET-KEY", text)

    def test_build_only_rebuilds_without_calls(self):
        server = FakeHofj([item(1)])
        record_pages_and_details(make_client(self.raw, server, []), ["1"])
        calls_before = len(server.calls)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("rete usata")):
            text = run_main(["--raw-dir", self.raw, "--out", self.out, "--build-only"], {})
        self.assertEqual(len(server.calls), calls_before)
        self.assertIn("1 prodotti, 1 dettagli", text)
        self.assertTrue(os.path.exists(self.out))

    def test_quota_exceeded_exits_with_stop_and_keeps_raw(self):
        server = FakeHofj([item(i) for i in range(1, 6)], limit=3)
        with mock.patch("urllib.request.urlopen", server):
            with self.assertRaises(SystemExit) as ctx:
                run_main(["--raw-dir", self.raw, "--out", self.out], {"HOFJ_API_KEY": "SECRET-KEY"})
        self.assertIn("STOP", str(ctx.exception))
        self.assertFalse(os.path.exists(self.out))
        self.assertGreaterEqual(len(os.listdir(self.raw)), 2)

    def test_incomplete_raw_does_not_write_fixture(self):
        server = FakeHofj([item(1), item(2)], broken_ids=["2"])
        with mock.patch("urllib.request.urlopen", server):
            with self.assertRaises(SystemExit) as ctx:
                run_main(["--raw-dir", self.raw, "--out", self.out], {"HOFJ_API_KEY": "SECRET-KEY"})
        self.assertIn("fixture non scritta", str(ctx.exception))
        self.assertIn("2", str(ctx.exception))
        self.assertFalse(os.path.exists(self.out))
```

- [ ] **Step 2: Eseguire il test e vedere che fallisce**

Run: `python3 -m unittest tests.test_record_catalog.MainTest -v`
Expected: `AttributeError: module 'record_catalog' has no attribute 'main'`

- [ ] **Step 3: Implementare** in coda a `scripts/record_catalog.py`:

```python
def expected_counts(out_path):
    """Stime per il dry-run: dalla fixture esistente se c'è, altrimenti da docs/api/counts.md."""
    try:
        with open(out_path, encoding="utf-8") as fh:
            catalog = json.load(fh)
        return len(catalog["products"]), len(catalog["details"])
    except (OSError, ValueError, KeyError, TypeError):
        return EXPECTED_TOTAL, EXPECTED_ACTIVE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw-dir", required=True,
                    help="cartella FUORI dal repo per le risposte grezze (nuova o vuota)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="fixture da scrivere (default fixtures/catalog.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="stampa le chiamate previste senza eseguirle")
    ap.add_argument("--build-only", action="store_true",
                    help="ricostruisce la fixture da --raw-dir senza chiamate")
    args = ap.parse_args(argv)
    brand = os.environ.get(BRAND_ENV) or None

    if not args.build_only:
        if not args.dry_run and os.path.isdir(args.raw_dir) and os.listdir(args.raw_dir):
            sys.exit("--raw-dir %s non è vuota: usa una cartella nuova o --build-only"
                     % args.raw_dir)
        api_key = next((os.environ[k] for k in KEY_ENVS if os.environ.get(k)), None)
        if not api_key and not args.dry_run:
            sys.exit("variabile d'ambiente %s assente" % " o ".join(KEY_ENVS))
        client = api_explore.Client(args.raw_dir, api_explore.QuotaGuard(), api_key or "",
                                    dry_run=args.dry_run)
        if args.dry_run:
            total, active = expected_counts(args.out)
            record(client, brand=brand, expected=(total, active))
            lists = sum(1 for path, _, _ in client.planned if path == "/v1/products")
            details = len(client.planned) - lists
            windows, calls = call_plan(len(client.planned))
            print("chiamate previste: %d liste + %d dettagli + %d sync quota = %d autenticate, "
                  "in %d finestre da 60 s (stima: %d prodotti, %d non archiviati)"
                  % (lists, details, windows, calls, windows, total, active))
            return
        try:
            record(client, brand=brand)
        except RuntimeError as e:   # QuotaExceededError o lista fallita
            sys.exit("STOP: %s (risposte parziali in %s)" % (e, args.raw_dir))
        print("richieste autenticate eseguite: %d" % client.guard.total_requests)

    try:
        catalog = build_catalog(args.raw_dir, brand=brand)
    except BuildError as e:
        sys.exit("fixture non scritta: %s" % e)
    write_catalog(catalog, args.out)
    print("scritta %s: %d prodotti, %d dettagli, %d byte"
          % (args.out, len(catalog["products"]), len(catalog["details"]),
             os.path.getsize(args.out)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Eseguire i test e vedere che passano**

Run: `python3 -m unittest discover -s tests -v`
Expected: tutti `ok`.

- [ ] **Step 5: Prova manuale del dry-run (nessuna rete, nessuna chiave)**

Run: `python3 scripts/record_catalog.py --raw-dir /tmp/vela-dry --dry-run`
Expected: una riga `[dry-run] GET ...` per chiamata e in fondo `chiamate previste: 2 liste + 92 dettagli + 2 sync quota = 96 autenticate, in 2 finestre da 60 s (stima: 123 prodotti, 92 non archiviati)`.

- [ ] **Step 6: Commit**

```bash
git add scripts/record_catalog.py tests/test_record_catalog.py
git commit -m "Add record_catalog CLI with dry-run and build-only modes"
```

---

### Task 5: Test di validazione della fixture e `docs/fixtures.md`

**Files:**
- Create: `tests/test_catalog_fixture.py`
- Create: `docs/fixtures.md`

**Interfaces:**
- Consumes: il formato di `fixtures/catalog.json` (sezione "Formato").
- Produces: una suite che si salta finché il file non esiste; dopo il Task 6 deve passare.

- [ ] **Step 1: Scrivere `tests/test_catalog_fixture.py`**

```python
"""Verifica fixtures/catalog.json registrato da scripts/record_catalog.py.

Si salta se il file non esiste (RNF-09: la suite non richiede servizi esterni).
"""
import json
import os
import unittest

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")
MEDIA_KEYS = ("gallery", "image", "images", "cover", "media", "travelProgram")
MAX_BYTES = 1500000


def has_key(value, key):
    if isinstance(value, dict):
        return key in value or any(has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(has_key(v, key) for v in value)
    return False


@unittest.skipUnless(os.path.exists(FIXTURE),
                     "fixtures/catalog.json assente: eseguire scripts/record_catalog.py")
class CatalogFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.catalog = json.loads(cls.text)
        cls.products = cls.catalog["products"]
        cls.details = cls.catalog["details"]

    def test_header(self):
        self.assertEqual(self.catalog["locale"], "it")
        self.assertRegex(self.catalog["recorded_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertIn(type(self.catalog["brand"]), (str, type(None)))
        self.assertTrue(self.catalog["base_url"].startswith("https://"))

    def test_every_active_product_has_a_detail_and_vice_versa(self):
        active = [p["id"] for p in self.products if not p["archived"]]
        self.assertEqual(sorted(active), sorted(self.details))
        self.assertEqual(len(active), len(set(active)))       # nessun duplicato
        self.assertGreaterEqual(len(active), 80)              # atteso ~92 (docs/api/counts.md)

    def test_list_items_have_pricing_and_dates(self):
        for product in self.products:
            for key in ("price", "currency", "minDate", "maxDate", "availabilities", "archived"):
                self.assertIn(key, product, product["id"])
            self.assertEqual(product["locale"], "it", product["id"])
            if not product["archived"]:
                self.assertGreater(product["price"], 0, product["id"])
                self.assertEqual(product["currency"], "EUR", product["id"])

    def test_details_have_rf28_fields_and_no_media(self):
        for pid, detail in self.details.items():
            catalog, raw = detail["catalog"], detail["raw"]
            for key in ("category", "venue", "destination", "hotels", "price", "minDate",
                        "maxDate", "availabilities", "defaultDurationInDays", "updatedAt"):
                self.assertIn(key, catalog, pid)
            self.assertIsInstance(catalog["category"], dict, pid)
            self.assertEqual(catalog["id"], pid)
            self.assertIn("hotels", raw.get("rawAttributes") or {}, pid)
            for key in MEDIA_KEYS:
                self.assertFalse(has_key(raw, key), "%s contiene %s" % (pid, key))

    def test_no_credentials(self):
        self.assertNotIn("Authorization", self.text)
        self.assertNotIn("Bearer ", self.text)
        for env in ("HOFJ_API_KEY", "API_BEAR_KEY"):
            key = os.environ.get(env)
            if key:   # mai stampare la chiave: messaggio senza il valore
                self.assertFalse(key in self.text, "%s presente nella fixture" % env)

    def test_size_within_budget(self):
        self.assertLess(os.path.getsize(FIXTURE), MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Eseguire la suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: i test di `CatalogFixtureTest` risultano `skipped 'fixtures/catalog.json assente...'`, il resto `ok`.

- [ ] **Step 3: Scrivere `docs/fixtures.md`**

````markdown
# Fixture del catalogo (`fixtures/catalog.json`)

Snapshot del catalogo House of Journeys in locale `it` (RF-32): lista `GET /v1/products`
integrale (anche archiviati) più dettaglio `GET /v1/products/{id}?extended=true` dei
prodotti non archiviati. Usato dalla modalità replay, dall'avvio a freddo e dalla demo se
la quota è esaurita. Piano e decisioni: `docs/plans/2026-09-25-m1-fixture-catalogo.md`,
`docs/decisions.md` (2026-09-25, M1).

## Formato

| Chiave | Contenuto |
|---|---|
| `recorded_at` | istante dell'ultima risposta registrata (ISO-8601 UTC) |
| `locale` | `it` |
| `brand` | valore di `HOFJ_BRAND` usato, `null` se omesso (default del server: `weebora.com`) |
| `base_url` | base URL dell'API al momento della costruzione |
| `products` | item della lista così come li restituisce l'API, in ordine di id |
| `details[id].catalog` | campi di RF-28 con i nomi dell'API: `id, title, slug, shortDescription, price, currency, minPax, maxPax, minDate, maxDate, availabilities, defaultDurationInDays, updatedAt, category, venue, destination, hotels` (`hotels` = `rawAttributes.hotels` senza media) |
| `details[id].raw` | dettaglio esteso senza `gallery`, `image`, `images`, `cover`, `media`, `travelProgram` a qualsiasi profondità |

## Rigenerare la fixture

Variabili: `HOFJ_API_KEY` (o `API_BEAR_KEY`), opzionali `HOFJ_BASE_URL`, `HOFJ_BRAND`.
La chiave non viene mai stampata né salvata. Le risposte grezze vanno in una cartella
fuori dal repository e permettono di ricostruire il file senza consumare quota.

```bash
python3 scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-it --dry-run   # solo conteggio
python3 scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-it             # ≈ 96 chiamate, 2 finestre
python3 scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-it --build-only  # ricostruzione
python3 -m unittest tests.test_catalog_fixture -v                               # validazione
```

Pacing: budget per finestra di 60 s = min(`remainingInWindow`, 90 − `usedInWindow`), attesa
fino a `windowEndsAt` + 2 s, stop immediato su 429 (`scripts/api_explore.py`).

## Ultima registrazione

Da compilare al Task 6: data, prodotti totali, non archiviati, chiamate eseguite,
dimensione del file.
````

- [ ] **Step 4: Commit**

```bash
git add tests/test_catalog_fixture.py docs/fixtures.md
git commit -m "Add fixture validation test and docs/fixtures.md"
```

---

### Task 6: Registrazione reale e commit della fixture

**Files:**
- Create: `fixtures/catalog.json`
- Modify: `docs/fixtures.md` (sezione "Ultima registrazione")
- Modify: `docs/decisions.md` (solo se la lista `MEDIA_KEYS` cambia)

Questa task chiama l'API reale: **dichiarare prima le chiamate**. Il piano approvato copre fino a 110 chiamate autenticate; oltre, fermarsi e chiedere.

- [ ] **Step 1: Ambiente.** Caricare la chiave senza aprire il file (decisione 2026-09-25): `set -a; . ./.env; set +a` nella stessa shell del comando. Verificare che esista senza stamparla: `test -n "$HOFJ_API_KEY" -o -n "$API_BEAR_KEY" && echo "chiave presente"`. Se il Python è quello di python.org 3.7 su macOS, aggiungere `SSL_CERT_FILE=/etc/ssl/cert.pem`. Scegliere `RAW=$HOME/vela-raw/catalog-it-$(date +%Y%m%d-%H%M)` (fuori dal repo).

- [ ] **Step 2: Dry-run e dichiarazione.** Eseguire `python3 scripts/record_catalog.py --raw-dir "$RAW" --dry-run` e riportare in chat la riga `chiamate previste: ...`. Se il totale supera 110, fermarsi.

- [ ] **Step 3: Registrazione.** Nella stessa shell dell'ambiente:

```bash
set -a; . ./.env; set +a; python3 scripts/record_catalog.py --raw-dir "$RAW"
```

Expected: log `GET /v1/quota ...`, due `GET /v1/products ...`, la riga `N prodotti in lista, M non archiviati`, poi i dettagli; una sola attesa `budget esaurito: attendo ~60s`; in fondo `richieste autenticate eseguite: ~96` e `scritta .../fixtures/catalog.json: N prodotti, M dettagli, B byte`. Durata circa 2-3 minuti. Se termina con `STOP:` (429), attendere un minuto e ripetere con una `--raw-dir` nuova; annotare l'accaduto in chat.

- [ ] **Step 4: Validare.** `python3 -m unittest discover -s tests -v`: `CatalogFixtureTest` non più saltato, tutto `ok`. Se `test_size_within_budget` fallisce (file > 1,5 MB): elencare le chiavi più pesanti di `raw` con un one-liner (`python3 -c "import json,collections; c=json.load(open('fixtures/catalog.json')); s=collections.Counter(); [s.update({k: len(json.dumps(v))}) for d in c['details'].values() for k,v in d['raw'].get('rawAttributes',{}).items()]; print(s.most_common(10))"`), aggiungere le chiavi media evidenti a `MEDIA_KEYS` (e a `MEDIA_KEYS` del test di validazione), ricostruire con `--build-only`, e registrare la modifica in `docs/decisions.md`. Se il numero di non archiviati è sotto 80, abbassare la soglia del test solo dopo aver verificato il conteggio in chat.

- [ ] **Step 5: Verifica dei segreti** (la chiave si espande nella shell, non appare nel comando né nei log):

```bash
set -a; . ./.env; set +a; K="${HOFJ_API_KEY:-$API_BEAR_KEY}"; if [ -z "$K" ]; then echo "chiave assente dall'ambiente: ripetere"; elif git grep -q -i -F --untracked "$K" -- . ; then echo "TROVATA: rimuovere prima di committare"; else echo "ok: chiave assente dal repo"; fi
```

Expected: `ok: chiave assente dal repo` (`--untracked` include `fixtures/catalog.json` non ancora aggiunto). Se `TROVATA`, non committare e segnalare.

- [ ] **Step 6: Compilare `docs/fixtures.md` › "Ultima registrazione"** con: data (`recorded_at`), prodotti totali, non archiviati, chiamate autenticate eseguite (dall'output), numero di finestre, dimensione del file in byte, differenze notate rispetto ai numeri in `en` (123/92).

- [ ] **Step 7: Commit**

```bash
git add fixtures/catalog.json docs/fixtures.md
git commit -m "Add fixtures/catalog.json recorded in locale it"
```

Se `docs/decisions.md` o `scripts/record_catalog.py` sono cambiati allo Step 4, includerli con un messaggio che lo dica (`Extend MEDIA_KEYS after the first real recording`).

---

## Verifica finale (criteri di completamento M1)

- `python3 -m unittest discover -s tests` verde, con `CatalogFixtureTest` eseguito (non saltato).
- `fixtures/catalog.json` contiene tutti i prodotti non archiviati della lista `it`; ogni item ha `price`, `currency`, `minDate`, `maxDate`, `availabilities`; ogni dettaglio ha `category`, `venue`, `destination` e `rawAttributes.hotels` (in `catalog.hotels` e in `raw`).
- `git grep` della chiave non trova nulla (eseguito senza stamparla).
- `python3 scripts/record_catalog.py --raw-dir /tmp/x --dry-run` stampa il numero di chiamate previste senza farle e senza chiave.
- Chiamate reali eseguite ≈ 96 in 2 finestre, dichiarate prima e annotate in `docs/fixtures.md`.
- Al termine: `git log --oneline master..task/m1` mostra i 7 commit dei task; il merge su `master` resta all'utente (CLAUDE.md).

## Cosa resta fuori (per le task successive)

- La scelta dell'"hotel di default" dentro `hotels` (M2, quando la forma dei dati è visibile).
- Il filtro padel/tennis e la scrittura in Postgres (M2, M10). M10 potrà riusare `strip_media`/`project_detail` o sostituire lo script con `python -m vela.sync --fixture`.
- Il merge di `docs/roadmap.md` su `master`.
