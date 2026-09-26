"""App del finto HofJ (M13a) con TestClient: forme reali, quota di HofJ, guasti, registro."""
import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from loadtest.fake_hofj.app import FakeConfig, FakeHofJ, create_app
from loadtest.fake_hofj.faults import parse_fault

KEY = "loadtest-key"
AUTH = {"Authorization": "Bearer " + KEY}
PADEL = {"brand": "weebora.com", "locale": "it"}
PRODUCT = "181"   # fixtures/catalog.json, non archiviato


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t
        self.slept = []

    def __call__(self):
        return self.t

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


def fake(clock=None, **over):
    clock = clock or Clock()
    over.setdefault("latency", "none")
    return FakeHofJ(FakeConfig(**over), clock=clock, sleep=clock.sleep), clock


def client(f):
    return TestClient(create_app(fake=f))


def new_itinerary(c, product=PRODUCT, params=PADEL):
    return c.post("/v1/itineraries", params=params, headers=AUTH, json={
        "productId": int(product), "startDate": "2026-10-10", "adults": 2, "rooms": 1,
        "currency": "EUR"})


class ShapesTest(unittest.TestCase):
    def setUp(self):
        self.f, self.clock = fake()
        self.c = client(self.f)

    def test_without_bearer_401_and_no_quota(self):
        r = self.c.get("/v1/quota")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.f.stats()["calls"], 0)

    def test_quota_counts_itself(self):
        first = self.c.get("/v1/quota", headers=AUTH).json()
        second = self.c.get("/v1/quota", headers=AUTH).json()
        self.assertEqual((first["data"]["usedInWindow"], second["data"]["usedInWindow"]), (1, 2))
        self.assertEqual(first["data"]["limitPerMinute"], 120)
        self.assertIn("now", first["meta"])

    def test_full_cart_and_booking_shapes(self):
        r = new_itinerary(self.c)
        self.assertEqual(r.status_code, 200, r.text)
        iid = r.json()["data"]["itineraryId"]
        self.assertEqual(self.c.put("/v1/itineraries/%s/customer" % iid, params=PADEL, headers=AUTH,
                                    json={"firstName": "Mario", "lastName": "Rossi", "email": "m@x.it",
                                          "phone": "+39", "address": {"street1": "Via", "postalCode": "1",
                                                                      "city": "Milano", "region": "MI",
                                                                      "countryCode": "IT"}}).status_code, 200)
        pax = self.c.get("/v1/itineraries/%s/pax" % iid, params=PADEL, headers=AUTH).json()["data"]
        self.assertEqual([p["refId"] for p in pax], ["pax-1", "pax-2"])
        self.assertEqual(pax[0]["firstName"], "Mario")   # precompilato dal customer
        pax[1].update(firstName="Anna", lastName="Bianchi")
        self.assertEqual(self.c.put("/v1/itineraries/%s/pax" % iid, params=PADEL, headers=AUTH,
                                    json=pax).status_code, 200)
        checkout = self.c.get("/v1/itineraries/%s" % iid, params=PADEL,
                              headers=AUTH).json()["data"]["checkout"]
        self.assertIsInstance(checkout["openAmount"]["amount"], str)
        booking = self.c.post("/v1/bookings", params=PADEL, headers=AUTH,
                              json={"itineraryId": iid, "paymentType": "full"})
        self.assertEqual(booking.json()["data"], iid)
        again = self.c.post("/v1/bookings", params=PADEL, headers=AUTH,
                            json={"itineraryId": iid, "paymentType": "full"})
        self.assertEqual(again.json()["data"], iid)
        self.assertEqual(self.f.bookings, {iid: 2})
        self.assertEqual(self.f.stats()["bookings"], 1)

    def test_unknown_product_is_a_502_upstream_404(self):
        r = new_itinerary(self.c, product="999999")
        self.assertEqual(r.status_code, 502)
        self.assertIn("returned 404", r.json()["detail"])
        self.assertTrue(r.headers["content-type"].startswith("application/json"))

    def test_product_of_another_brand_is_not_found(self):
        r = new_itinerary(self.c, params={"brand": "terrarossa.com", "locale": "it"})
        self.assertEqual(r.status_code, 502)

    def test_products_are_paginated_per_brand(self):
        seen, cursor = [], None
        while True:
            params = dict(PADEL, limit=40, **({"cursor": cursor} if cursor else {}))
            body = self.c.get("/v1/products", params=params, headers=AUTH).json()
            seen += [p["id"] for p in body["data"]]
            cursor = body["meta"].get("nextCursor")
            if not cursor:
                break
        with open(os.path.join(self.f.config.fixtures_dir, "catalog.json"), encoding="utf-8") as fh:
            self.assertEqual(seen, [str(p["id"]) for p in json.load(fh)["products"]])
        detail = self.c.get("/v1/products/%s" % PRODUCT, params=dict(PADEL, extended="true"),
                            headers=AUTH).json()["data"]
        self.assertIn("hotels", detail["rawAttributes"])

    def test_fake_routes_do_not_count(self):
        self.c.get("/_fake/stats")
        self.c.post("/_fake/reset")
        self.c.get("/health")
        self.assertEqual(self.c.get("/v1/quota", headers=AUTH).json()["data"]["usedInWindow"], 1)


class QuotaTest(unittest.TestCase):
    def test_over_the_limit_429_with_retry_after_in_body_only(self):
        f, clock = fake(limit=2)
        c = client(f)
        c.get("/v1/quota", headers=AUTH)
        clock.t += 10
        c.get("/v1/quota", headers=AUTH)
        r = c.get("/v1/quota", headers=AUTH)
        self.assertEqual(r.status_code, 429)
        self.assertAlmostEqual(r.json()["retryAfterSeconds"], 50, places=3)
        self.assertNotIn("retry-after", r.headers)
        stats = f.stats()
        self.assertEqual((stats["calls"], stats["status_429"]), (3, 1))

    def test_anchored_window_resets_at_the_first_call_after_expiry(self):
        f, clock = fake(limit=1)
        c = client(f)
        c.get("/v1/quota", headers=AUTH)
        clock.t += 63.8
        r = c.get("/v1/quota", headers=AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["usedInWindow"], 1)

    def test_background_consumes_the_same_key(self):
        f, clock = fake(limit=3, background_rpm=120)
        client(f)
        self.assertEqual(f.tick_background(), 1)
        clock.t += 1.0
        self.assertEqual(f.tick_background(), 2)
        self.assertEqual(client(f).get("/v1/quota", headers=AUTH).status_code, 429)
        self.assertEqual(f.stats()["calls_vela"], 1)


class FaultsTest(unittest.TestCase):
    def booking_after(self, fault):
        f, clock = fake(faults=(parse_fault(fault),), hang_seconds=20)
        c = client(f)
        iid = new_itinerary(c).json()["data"]["itineraryId"]
        clock.slept.clear()
        r = c.post("/v1/bookings", params=PADEL, headers=AUTH, json={"itineraryId": iid})
        return f, clock, iid, r

    def test_hang_then_execute_books_and_hangs(self):
        f, clock, iid, r = self.booking_after("POST /v1/bookings=hang_then_execute:1")
        self.assertEqual(f.bookings, {iid: 1})
        self.assertEqual(clock.slept[-1], 20)
        self.assertEqual(r.json()["data"], iid)

    def test_hang_does_not_execute(self):
        f, clock, iid, r = self.booking_after("POST /v1/bookings=hang:1")
        self.assertEqual(f.bookings, {})
        self.assertEqual(clock.slept[-1], 20)
        self.assertEqual(r.status_code, 502)

    def test_5xx_does_not_execute(self):
        f, _, _, r = self.booking_after("POST /v1/bookings=5xx:1")
        self.assertEqual((r.status_code, f.bookings), (503, {}))

    def test_product_502_on_itineraries(self):
        f, _ = fake(faults=(parse_fault("POST /v1/itineraries=product_502:1"),))
        r = new_itinerary(client(f))
        self.assertEqual(r.status_code, 502)
        self.assertIn("returned 404", r.json()["detail"])
        self.assertEqual(f.stats()["itineraries"], 0)

    def test_same_seed_same_faults(self):
        def sequence(seed):
            f, _ = fake(seed=seed, faults=(parse_fault("GET /v1/quota=5xx:0.5"),))
            c = client(f)
            return [c.get("/v1/quota", headers=AUTH).status_code for _ in range(20)]
        self.assertEqual(sequence(7), sequence(7))
        self.assertIn(503, sequence(7))

    def test_bad_fault_text(self):
        for text in ("POST /v1/bookings=explode:1", "POST /v1/bookings=hang:2", "nonsense"):
            with self.assertRaises(ValueError):
                parse_fault(text)


class LogTest(unittest.TestCase):
    def test_every_call_is_a_json_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calls.jsonl")
            f, _ = fake(log_path=path, limit=1)
            c = client(f)
            c.get("/v1/quota", headers=AUTH)
            c.get("/v1/quota", headers=AUTH)
            c.get("/v1/quota")
            f.log.close()
            with open(path, encoding="utf-8") as fh:
                lines = [json.loads(line) for line in fh]
        self.assertEqual([line["status"] for line in lines], [200, 429, 401])
        self.assertEqual([line["counted"] for line in lines], [True, True, False])
        self.assertEqual(lines[0]["endpoint"], "GET /v1/quota")


if __name__ == "__main__":
    unittest.main()


class CliTest(unittest.TestCase):
    def test_arguments_become_the_config(self):
        from loadtest.fake_hofj.__main__ import config_from, parse_args
        config = config_from(parse_args(env={}, argv=["--window", "rolling", "--background-rpm", "12",
                                         "--latency", "pessimistic", "--seed", "5",
                                         "--fault", "POST /v1/bookings=hang:0.1"]))
        self.assertEqual((config.window, config.background_rpm, config.latency, config.seed),
                         ("rolling", 12.0, "pessimistic", 5))
        self.assertEqual(config.faults[0].kind, "hang")

    def test_environment_defaults_for_compose(self):
        from loadtest.fake_hofj.__main__ import config_from, parse_args
        env = {"FAKE_HOFJ_LATENCY": "pessimistic", "FAKE_HOFJ_BACKGROUND_RPM": "12",
               "FAKE_HOFJ_FAULTS": "POST /v1/bookings=hang_then_execute:0.05; POST /v1/itineraries=hang:0.02"}
        config = config_from(parse_args([], env=env))
        self.assertEqual((config.latency, config.background_rpm, config.window), ("pessimistic", 12.0, "anchored"))
        self.assertEqual([(f.endpoint, f.kind) for f in config.faults],
                         [("POST /v1/bookings", "hang_then_execute"), ("POST /v1/itineraries", "hang")])
