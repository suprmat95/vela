import random
import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.adapters.hofj_replay import FIXTURE_PATH, ITINERARY_PREFIX, ReplayHofJ
from vela.adapters.stripe_fake import FakePayments
from vela.domain.models import Order, OrderStatus, TravelerProfile
from vela.ports.hofj import (ConfigError, Customer, HofJError, Pax, PaymentProof, QuotaError,
                             UpstreamError)

CUSTOMER = Customer("Anna", "Rossi", "a@x.it", "+39", "Via 1", "20100", "Milano", "MI", "IT")


class ReplayHofJTest(unittest.TestCase):
    def setUp(self):
        self.hofj = ReplayHofJ(rng=random.Random(42))

    def test_load_catalog_reads_the_fixture(self):
        products = self.hofj.load_catalog()
        self.assertEqual(len(products), 110)
        self.assertEqual(len([p for p in products if not p.archived]), 77)

    def test_create_itinerary_returns_only_the_id(self):
        iid = self.hofj.create_itinerary(make_product(1, price=578), date(2026, 10, 1), 2, 1, "EUR")
        self.assertIsInstance(iid, str)
        self.assertTrue(iid.startswith(ITINERARY_PREFIX))

    def test_get_itinerary_returns_the_amount_to_pay(self):
        iid = self.hofj.create_itinerary(make_product(1, price=578), date(2026, 10, 1), 2, 1, "EUR")
        it = self.hofj.get_itinerary(iid)
        self.assertEqual((it.id, it.total, it.currency), (iid, Decimal("1156"), "EUR"))
        with self.assertRaises(UpstreamError):
            self.hofj.get_itinerary("it-replay-nope")

    def test_customer_and_pax_round_trip_preserving_ref_ids(self):
        iid = self.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        self.hofj.set_customer(iid, CUSTOMER)
        slots = self.hofj.get_pax(iid)
        self.assertEqual([s.ref_id for s in slots], ["pax-1", "pax-2"])
        self.assertTrue(all(s.first_name is None for s in slots))
        self.hofj.set_pax(iid, [Pax("pax-1", "Anna", "Rossi"), Pax("pax-2", "Bo", "Bi")])
        self.assertEqual(self.hofj.get_pax(iid)[1], Pax("pax-2", "Bo", "Bi"))

    def test_unknown_itinerary_is_upstream_error(self):
        with self.assertRaises(UpstreamError):
            self.hofj.get_pax("it-replay-nope")
        with self.assertRaises(UpstreamError):
            self.hofj.set_customer("it-replay-nope", CUSTOMER)

    def test_booking_code_format_and_idempotence(self):
        iid = self.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        proof = PaymentProof("pi_1", "succeeded")
        code = self.hofj.create_booking(iid, proof)
        self.assertRegex(code, r"^R-\d{6}$")
        self.assertEqual(self.hofj.create_booking(iid, proof), code)

    def test_booking_survives_a_restart(self):
        # dopo un riavvio l'itinerario non è più in memoria: in replay la prenotazione riesce comunque (RF-27)
        code = ReplayHofJ(rng=random.Random(1)).create_booking("it-replay-abc", PaymentProof("pi", "succeeded"))
        self.assertRegex(code, r"^R-\d{6}$")

    def test_booking_rejects_foreign_itinerary(self):
        with self.assertRaises(UpstreamError):
            self.hofj.create_booking("real-123", PaymentProof("pi", "succeeded"))



class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at


class ReplaySimulationTest(unittest.TestCase):
    """Latenza e quota simulate (roadmap M5): default zero e illimitata; M13 impone 120/min e 2-6 s."""

    def call(self, hofj):
        return hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")

    def test_quota_unlimited_by_default(self):
        hofj = ReplayHofJ(rng=random.Random(1))
        for _ in range(500):
            self.call(hofj)

    def test_limit_raises_429_after_limit_in_window(self):
        clock = Clock()
        hofj = ReplayHofJ(rng=random.Random(1), limit=3, now=clock)
        for _ in range(3):
            self.call(hofj)
        with self.assertRaises(QuotaError):
            self.call(hofj)
        clock.at = NOW + timedelta(seconds=59)
        with self.assertRaises(QuotaError):
            self.call(hofj)
        clock.at = NOW + timedelta(seconds=60)
        self.call(hofj)

    def test_every_hofj_call_counts_towards_the_limit(self):
        hofj = ReplayHofJ(rng=random.Random(1), limit=6, now=Clock())
        iid = self.call(hofj)
        hofj.set_customer(iid, CUSTOMER)
        hofj.set_pax(iid, hofj.get_pax(iid))
        hofj.get_itinerary(iid)
        hofj.create_booking(iid, PaymentProof("pi", "succeeded"))
        with self.assertRaises(QuotaError):
            hofj.get_quota()

    def test_latency_uses_injected_sleep(self):
        slept = []
        hofj = ReplayHofJ(rng=random.Random(1), latency=(2.0, 6.0), sleep=slept.append)
        iid = self.call(hofj)
        hofj.get_itinerary(iid)
        self.assertEqual(len(slept), 2)
        self.assertTrue(all(2.0 <= s <= 6.0 for s in slept))

    def test_no_sleep_without_latency(self):
        slept = []
        self.call(ReplayHofJ(rng=random.Random(1), sleep=slept.append))
        self.assertEqual(slept, [])

    def test_get_quota_snapshot_counts_calls_including_itself(self):
        clock = Clock()
        hofj = ReplayHofJ(rng=random.Random(1), limit=120, now=clock)
        self.call(hofj)
        clock.at = NOW + timedelta(seconds=5)
        snap = hofj.get_quota()
        self.assertEqual((snap.limit_per_minute, snap.used_in_window), (120, 2))
        self.assertEqual((snap.window_started_at, snap.window_ends_at), (NOW, NOW + timedelta(seconds=60)))

    def test_unlimited_quota_reports_hofj_default_limit(self):
        self.assertEqual(ReplayHofJ(rng=random.Random(1), now=Clock()).get_quota().limit_per_minute, 120)


class PortErrorsTest(unittest.TestCase):
    def test_quota_error_carries_retry_after(self):
        self.assertEqual(QuotaError("429", retry_after=12.5).retry_after, 12.5)
        self.assertIsNone(QuotaError("429").retry_after)

    def test_config_error_is_a_hofj_error(self):
        self.assertTrue(issubclass(ConfigError, HofJError))

class FakePaymentsTest(unittest.TestCase):
    def order(self):
        return Order("o1", "p1", "i1", "1", OrderStatus.AWAITING_PAYMENT, 2, Decimal("500"),
                     Decimal("1000"), "EUR", TravelerProfile(), NOW, NOW)

    def test_link_points_to_replay_checkout(self):
        link = FakePayments("https://vela.test/", now=lambda: NOW).create_payment_link(self.order(), "Padel")
        self.assertEqual(link.url, "https://vela.test/replay/checkout/o1")
        self.assertEqual(link.reference, "pi_replay_o1")
        self.assertEqual(link.expires_at, NOW + timedelta(hours=24))

    def test_default_public_url(self):
        link = FakePayments(None).create_payment_link(self.order(), "Padel")
        self.assertEqual(link.url, "http://localhost:8000/replay/checkout/o1")


class FixturePathTest(unittest.TestCase):
    def test_path_is_absolute_and_exists(self):
        import os
        self.assertTrue(os.path.isabs(FIXTURE_PATH))
        self.assertTrue(FIXTURE_PATH.endswith(os.path.join("fixtures", "catalog.json")))
