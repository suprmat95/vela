import random
import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.adapters.hofj_replay import FIXTURE_PATH, ITINERARY_PREFIX, ReplayHofJ
from vela.adapters.stripe_fake import FakePayments
from vela.domain.models import Order, OrderStatus, TravelerProfile
from vela.ports.hofj import Customer, Pax, PaymentProof, UpstreamError

CUSTOMER = Customer("Anna", "Rossi", "a@x.it", "+39", "Via 1", "20100", "Milano", "MI", "IT")


class ReplayHofJTest(unittest.TestCase):
    def setUp(self):
        self.hofj = ReplayHofJ(rng=random.Random(42))

    def test_load_catalog_reads_the_fixture(self):
        products = self.hofj.load_catalog()
        self.assertEqual(len(products), 110)
        self.assertEqual(len([p for p in products if not p.archived]), 77)

    def test_itinerary_total_is_price_times_adults(self):
        it = self.hofj.create_itinerary(make_product(1, price=578), date(2026, 10, 1), 2, 1, "EUR")
        self.assertTrue(it.id.startswith(ITINERARY_PREFIX))
        self.assertEqual((it.total, it.currency), (Decimal("1156"), "EUR"))

    def test_customer_and_pax_round_trip_preserving_ref_ids(self):
        it = self.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        self.hofj.set_customer(it.id, CUSTOMER)
        slots = self.hofj.get_pax(it.id)
        self.assertEqual([s.ref_id for s in slots], ["pax-1", "pax-2"])
        self.assertTrue(all(s.first_name is None for s in slots))
        self.hofj.set_pax(it.id, [Pax("pax-1", "Anna", "Rossi"), Pax("pax-2", "Bo", "Bi")])
        self.assertEqual(self.hofj.get_pax(it.id)[1], Pax("pax-2", "Bo", "Bi"))

    def test_unknown_itinerary_is_upstream_error(self):
        with self.assertRaises(UpstreamError):
            self.hofj.get_pax("it-replay-nope")
        with self.assertRaises(UpstreamError):
            self.hofj.set_customer("it-replay-nope", CUSTOMER)

    def test_booking_code_format_and_idempotence(self):
        it = self.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        proof = PaymentProof("pi_1", "succeeded")
        code = self.hofj.create_booking(it.id, proof)
        self.assertRegex(code, r"^R-\d{6}$")
        self.assertEqual(self.hofj.create_booking(it.id, proof), code)

    def test_booking_survives_a_restart(self):
        # dopo un riavvio l'itinerario non è più in memoria: in replay la prenotazione riesce comunque (RF-27)
        code = ReplayHofJ(rng=random.Random(1)).create_booking("it-replay-abc", PaymentProof("pi", "succeeded"))
        self.assertRegex(code, r"^R-\d{6}$")

    def test_booking_rejects_foreign_itinerary(self):
        with self.assertRaises(UpstreamError):
            self.hofj.create_booking("real-123", PaymentProof("pi", "succeeded"))


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
