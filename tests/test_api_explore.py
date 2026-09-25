import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import api_explore  # noqa: E402


def quota_body(used, remaining, ends="2026-09-25T09:54:47.409Z"):
    return {"data": {"clientId": "c", "limitPerMinute": 120, "usedInWindow": used,
                     "remainingInWindow": remaining, "windowEndsAt": ends,
                     "backend": "firestore"}}


class FakeResponse(io.BytesIO):
    def __init__(self, status, body, headers=None):
        super().__init__(json.dumps(body).encode("utf-8"))
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}


class FakeServer:
    """Risponde alle GET registrando gli header ricevuti; simula il 429 oltre il limite."""

    def __init__(self, routes, limit=120):
        self.routes = routes
        self.limit = limit
        self.calls = []
        self.window_used = 0

    def new_window(self, *_):
        self.window_used = 0

    def __call__(self, req, timeout=None):
        self.calls.append((req.full_url, dict(req.header_items())))
        self.window_used += 1
        used = self.window_used
        if used > self.limit:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b"{}"))
        path = req.full_url.split("?")[0].replace("https://api.test", "")
        if path == "/v1/quota":
            return FakeResponse(200, quota_body(used, 120 - used))
        status, body = self.routes.get(path, (404, {"title": "not found"}))
        return FakeResponse(status, body)


class QuotaGuardTest(unittest.TestCase):
    def test_budget_is_min_of_remaining_and_cap_minus_used(self):
        g = api_explore.QuotaGuard(cap=90)
        g.sync(quota_body(3, 117)["data"])
        self.assertEqual(g.budget, 87)
        g.sync(quota_body(100, 20)["data"])
        self.assertEqual(g.budget, 0)
        self.assertFalse(g.can_request())

    def test_wait_seconds_targets_window_end_plus_margin(self):
        ends = api_explore.parse_iso("2026-09-25T09:54:47.409Z")
        g = api_explore.QuotaGuard(margin=2.0, now=lambda: ends - 10)
        g.sync(quota_body(90, 30)["data"])
        self.assertAlmostEqual(g.wait_seconds(), 12.0, places=3)

    def test_record_decrements(self):
        g = api_explore.QuotaGuard(cap=90)
        g.sync(quota_body(0, 120)["data"])
        g.record()
        self.assertEqual((g.budget, g.total_requests), (89, 1))


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.logs = []
        self.sleeps = []

    def make(self, server):
        def sleep(seconds):          # a fine finestra il finto server riparte da zero
            self.sleeps.append(seconds)
            server.new_window()
        return api_explore.Client(self.tmp, api_explore.QuotaGuard(cap=90), "SECRET-KEY",
                                  base_url="https://api.test", opener=server,
                                  sleep=sleep, log=self.logs.append)

    def test_first_auth_call_syncs_quota_and_saves_files_without_key(self):
        server = FakeServer({"/v1/locales": (200, {"data": [{"code": "it"}]})})
        c = self.make(server)
        rec = c.get("/v1/locales")
        self.assertEqual(rec["status"], 200)
        self.assertEqual([u.split("api.test")[1] for u, _ in server.calls],
                         ["/v1/quota", "/v1/locales"])
        self.assertEqual(server.calls[1][1]["Authorization"], "Bearer SECRET-KEY")
        files = sorted(os.listdir(self.tmp))
        self.assertEqual(files, ["001-GET-v1_quota.json", "002-GET-v1_locales.json"])
        with open(os.path.join(self.tmp, files[0])) as fh:
            dump = fh.read() + "".join(self.logs)
        self.assertNotIn("SECRET-KEY", dump)

    def test_public_call_does_not_use_quota(self):
        server = FakeServer({"/health": (200, {"status": "ok"})})
        c = self.make(server)
        c.get("/health", auth=False)
        self.assertEqual(len(server.calls), 1)
        self.assertNotIn("Authorization", server.calls[0][1])
        self.assertEqual(c.guard.total_requests, 0)

    def test_never_exceeds_cap_waits_then_resyncs(self):
        server = FakeServer({"/v1/locales": (200, {"data": []})}, limit=120)
        c = self.make(server)
        for _ in range(95):
            c.get("/v1/locales")
        # 1 sync + 89 richieste = 90 nella prima finestra, poi attesa e nuovo sync
        self.assertEqual(len(self.sleeps), 1)
        quota_calls = [u for u, _ in server.calls if u.endswith("/v1/quota")]
        self.assertEqual(len(quota_calls), 2)
        # prima finestra: 1 sync + 89 richieste = 90 chiamate, la 91esima e' il nuovo sync
        self.assertEqual(server.calls[90][0].split("api.test")[1], "/v1/quota")
        self.assertLessEqual(server.window_used, 90)

    def test_429_stops_immediately(self):
        server = FakeServer({"/v1/locales": (200, {"data": []})}, limit=2)
        c = self.make(server)
        c.get("/v1/locales")  # quota + locales = 2 chiamate consentite dal finto server
        with self.assertRaises(api_explore.QuotaExceededError):
            c.get("/v1/locales")

    def test_dry_run_makes_no_network_calls(self):
        server = FakeServer({})
        c = api_explore.Client(self.tmp, api_explore.QuotaGuard(), "", base_url="https://api.test",
                               opener=server, log=self.logs.append, dry_run=True)
        api_explore.phase_fixed(c)
        self.assertEqual(server.calls, [])
        self.assertEqual(os.listdir(self.tmp), [])
        # health, quota, channels, locales, 6 liste, 4 casi limite (nessun id o canale disponibile)
        self.assertEqual(len(c.planned), 14)


class PaginationTest(unittest.TestCase):
    def test_last_cursor_reads_saved_pages(self):
        tmp = tempfile.mkdtemp()
        server = FakeServer({"/v1/venues": (200, {"data": [{"id": 1}], "meta": {"nextCursor": "c2"}})})
        c = api_explore.Client(tmp, api_explore.QuotaGuard(), "k", base_url="https://api.test",
                               opener=server, log=lambda *_: None)
        c.get("/v1/venues", {"limit": 100})
        c.get("/v1/venues", {"limit": 1, "brand": "x"})  # ignorata: ha filtri
        self.assertEqual(api_explore.last_cursor(tmp, "venues"), ("c2", 1))
        self.assertEqual(api_explore.last_cursor(tmp, "pages"), (None, 0))


if __name__ == "__main__":
    unittest.main()
