"""Contratto: il vero `HofJHttp` contro il finto HofJ (M13a). Se il finto cambiasse forma o
errori rispetto a quanto l'adapter si aspetta da HofJ, qui si romperebbe."""
import socket
import threading
import time
import unittest
from datetime import date

import uvicorn

from loadtest.fake_hofj.app import FakeConfig, FakeHofJ, create_app
from loadtest.fake_hofj.faults import parse_fault
from support import asgi_transport
from vela.adapters.hofj_http import HofJHttp
from vela.adapters.hofj_replay import FIXTURES_DIR
from vela.domain.catalog import load_fixture
from vela.ports.hofj import (ConfigError, Customer, PaymentProof, ProductError, QuotaError,
                             UpstreamError)

KEY = "loadtest-key"
CUSTOMER = Customer("Mario", "Rossi", "m@example.com", "+390200000000", "Via Roma 1", "20121",
                    "Milano", "MI", "IT")
PADEL = [p for p in load_fixture(FIXTURES_DIR + "/catalog.json") if not p.archived][0]
TENNIS = [p for p in load_fixture(FIXTURES_DIR + "/catalog-tennis.json") if not p.archived][0]


def adapter(brand="weebora.com", key=KEY, **config):
    config.setdefault("latency", "none")
    fake = FakeHofJ(FakeConfig(**config))
    return HofJHttp("http://fake-hofj:8001", key, brand, locale="it",
                    transport=asgi_transport(create_app(fake=fake))), fake


class ContractTest(unittest.TestCase):
    def test_cart_booking_and_quota(self):
        hofj, fake = adapter()
        iid = hofj.create_itinerary(PADEL, date(2026, 10, 10), 2, 1, "EUR")
        hofj.set_customer(iid, CUSTOMER)
        pax = hofj.get_pax(iid)
        self.assertEqual(pax[0].first_name, "Mario")
        hofj.set_pax(iid, pax)
        itinerary = hofj.get_itinerary(iid)
        self.assertEqual(itinerary.total, PADEL.price * 2)
        proof = PaymentProof("pi_replay_o1", "succeeded")
        self.assertEqual(hofj.create_booking(iid, proof), iid)
        self.assertEqual(hofj.create_booking(iid, proof), iid)   # upsert
        quota = hofj.get_quota()
        self.assertEqual((quota.limit_per_minute, quota.used_in_window), (120, 8))
        self.assertEqual((quota.window_ends_at - quota.window_started_at).total_seconds(), 60)
        self.assertEqual(fake.stats()["booking_posts_max_per_itinerary"], 2)

    def test_catalog_source_for_each_brand(self):
        hofj, _ = adapter()
        for brand in ("weebora.com", "terrarossa.com"):
            items, cursor = hofj.list_page(brand, None)
            self.assertTrue(items)
            detail = hofj.detail(brand, str(next(i for i in items if not i.get("archived"))["id"]))
            self.assertIn("rawAttributes", detail)

    def test_tennis_product_needs_the_tennis_brand(self):
        padel, _ = adapter()
        with self.assertRaises(ProductError):
            padel.create_itinerary(TENNIS, date(2026, 10, 10), 2, 1, "EUR")
        tennis, _ = adapter(brand="terrarossa.com")
        self.assertTrue(tennis.create_itinerary(TENNIS, date(2026, 10, 10), 2, 1, "EUR"))

    def test_errors_map_like_hofj(self):
        hofj, _ = adapter(limit=1)
        hofj.get_quota()
        with self.assertRaises(QuotaError) as ctx:
            hofj.get_quota()
        self.assertGreater(ctx.exception.retry_after, 0)
        with self.assertRaises(ConfigError):
            adapter(key="wrong")[0].get_quota()
        broken, _ = adapter(faults=(parse_fault("GET /v1/quota=5xx:1"),))
        with self.assertRaises(UpstreamError):
            broken.get_quota()
        product, _ = adapter(faults=(parse_fault("POST /v1/itineraries=product_502:1"),))
        with self.assertRaises(ProductError):
            product.create_itinerary(PADEL, date(2026, 10, 10), 2, 1, "EUR")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TimeoutTest(unittest.TestCase):
    """Server vero su localhost: il timeout del client scatta mentre il finto è appeso."""

    def setUp(self):
        self.fake = FakeHofJ(FakeConfig(latency="none", hang_seconds=1.0,
                                        faults=(parse_fault("POST /v1/bookings=hang_then_execute:0.5"),),
                                        seed=3))
        self.port = free_port()
        config = uvicorn.Config(create_app(fake=self.fake), host="127.0.0.1", port=self.port,
                                log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 5
        while not self.server.started and time.time() < deadline:
            time.sleep(0.02)

    def tearDown(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def test_timeout_after_execution_then_retry_gives_one_booking(self):
        hofj = HofJHttp("http://127.0.0.1:%d" % self.port, KEY, "weebora.com", timeout=0.3)
        iid = hofj.create_itinerary(PADEL, date(2026, 10, 10), 2, 1, "EUR")
        proof = PaymentProof("pi_replay_o1", "succeeded")
        outcomes = []
        for _ in range(6):   # come BookingJob: si ripete la stessa POST finché non risponde
            try:
                outcomes.append(hofj.create_booking(iid, proof))
                break
            except UpstreamError:
                outcomes.append("timeout")
        self.assertIn("timeout", outcomes)
        self.assertEqual(outcomes[-1], iid)
        self.assertEqual(list(self.fake.bookings), [iid])   # un solo codice, una prenotazione


if __name__ == "__main__":
    unittest.main()
