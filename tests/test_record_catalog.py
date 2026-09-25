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


if __name__ == "__main__":
    unittest.main()
