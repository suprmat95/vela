"""Router del carrello per brand (M10, RF-56): ogni chiamata usa il brand del prodotto dell'ordine."""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, make_product
from vela.adapters.hofj_router import BrandRouter, SingleClientRouter
from vela.adapters.repo_memory import MemoryRepositories
from vela.config import DEFAULT_TRAVELER
from vela.domain.booking import BookingJob
from vela.domain.models import (Criteria, Intent, Job, JobKind, JobStatus, NoMatch, Order,
                                OrderStatus, Proposal, TravelerProfile)
from vela.domain.purchase import PurchaseJob
from vela.ports.hofj import ConfigError, UpstreamError

BRANDS = {"padel": "weebora.com", "tennis": "terrarossa.com"}
NEXT_WINDOW = NOW + timedelta(seconds=45)
TRAVELER = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", 2)


def router():
    weebora, terrarossa = FakeHofJ(), FakeHofJ(code="R-TENNIS")
    return BrandRouter({"weebora.com": weebora, "terrarossa.com": terrarossa}, BRANDS), weebora, terrarossa


class BrandRouterTest(unittest.TestCase):
    def test_client_by_brand(self):
        r, weebora, terrarossa = router()
        self.assertIs(r.client("weebora.com"), weebora)
        self.assertIs(r.client("terrarossa.com"), terrarossa)

    def test_unknown_brand_is_a_config_error(self):
        r, _, _ = router()
        with self.assertRaises(ConfigError):
            r.client("altro.com")

    def test_client_for_uses_the_product_brand(self):
        r, _, terrarossa = router()
        self.assertIs(r.client_for(make_product(1, sport="padel", brand="terrarossa.com")), terrarossa)

    def test_product_without_brand_uses_the_brand_of_its_sport(self):
        r, weebora, terrarossa = router()
        self.assertIs(r.client_for(make_product(1, sport="tennis")), terrarossa)
        self.assertIs(r.client_for(make_product(2, sport="padel")), weebora)

    def test_no_brand_for_the_product_is_a_config_error(self):
        r = BrandRouter({"weebora.com": FakeHofJ()}, {"padel": "weebora.com"})
        for product in (make_product(1, sport="tennis"), None):
            with self.subTest(product=product), self.assertRaises(ConfigError):
                r.client_for(product)

    def test_quota_is_read_from_any_client(self):
        r, weebora, _ = router()
        r.get_quota()
        self.assertEqual(weebora.calls[-1][0], "get_quota")

    def test_single_client_router_always_returns_the_same_client(self):
        fake = FakeHofJ()
        r = SingleClientRouter(fake)
        self.assertIs(r.client("x"), fake)
        self.assertIs(r.client_for(None), fake)
        r.get_quota()
        self.assertEqual(fake.calls[-1][0], "get_quota")


class TennisOrderTest(unittest.TestCase):
    """Un ordine su un prodotto Terrarossa: carrello e prenotazione passano tutti da Terrarossa."""

    def setUp(self):
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many([make_product(11, sport="tennis", brand="terrarossa.com")])
        self.repos.intents.add(Intent("i1", "tennis", Criteria(sport="tennis"), TRAVELER, NOW))
        self.repos.proposals.add(Proposal("p1", "i1", "11", date(2026, 10, 1), date(2026, 10, 4), 2,
                                          Decimal("500"), "EUR", "Motivo.", NOW))
        self.repos.orders.add(Order("o1", "p1", "i1", "11", OrderStatus.QUEUED, 2, Decimal("500"),
                                    None, "EUR", TRAVELER, NOW, NOW, enqueued_at=NOW))

    def purchase(self, r):
        job = PurchaseJob(self.repos, r, StubPayments(), lambda intent: NoMatch("i1", "x", "x"),
                          DEFAULT_TRAVELER, now=lambda: NOW)
        self.repos.jobs.enqueue(Job("j1", JobKind.PURCHASE, "o1", JobStatus.PENDING, NOW, NOW))
        return job.run(replace(self.repos.jobs.get("j1"), status=JobStatus.RUNNING), NEXT_WINDOW)

    def book(self, r):
        job = BookingJob(self.repos, r, now=lambda: NOW)
        self.repos.jobs.enqueue(Job("b1", JobKind.BOOKING, "o1", JobStatus.PENDING, NOW, NOW))
        return job.run(replace(self.repos.jobs.get("b1"), status=JobStatus.RUNNING), NEXT_WINDOW)

    def pay(self):
        order = self.repos.orders.get("o1")
        self.repos.orders.save(replace(order, status=OrderStatus.PAID_PENDING_BOOKING, payment_ref="pi_1"))

    def test_every_cart_call_goes_to_terrarossa(self):
        r, weebora, terrarossa = router()
        self.purchase(r)
        self.assertEqual(self.repos.orders.get("o1").status, OrderStatus.AWAITING_CONFIRMATION)
        self.assertEqual([c[0] for c in terrarossa.calls],
                         ["create_itinerary", "set_customer", "get_pax", "set_pax", "get_itinerary"])
        self.assertEqual(weebora.calls, [])

    def test_booking_retry_after_a_restart_still_uses_terrarossa(self):
        r, _, _ = router()
        self.purchase(r)
        self.pay()
        # riavvio: nuovo router e nuovi client, stesso DB; il primo tentativo cade sulla rete
        r2, weebora2, terrarossa2 = router()
        terrarossa2.fail_at = {"create_booking": [UpstreamError("rete")]}
        self.book(r2)
        r3, weebora3, terrarossa3 = router()
        job = BookingJob(self.repos, r3, now=lambda: NOW)
        job.run(replace(self.repos.jobs.get("b1"), status=JobStatus.RUNNING), NEXT_WINDOW)
        self.assertEqual(self.repos.orders.get("o1").booking_code, "R-TENNIS")
        self.assertEqual([c[0] for c in terrarossa2.calls + terrarossa3.calls],
                         ["create_booking", "create_booking"])
        self.assertEqual(weebora2.calls + weebora3.calls, [])

    def test_pre_m10_tennis_product_without_brand_uses_terrarossa(self):
        self.repos.products.upsert_many([make_product(11, sport="tennis", brand=None)])
        r, weebora, terrarossa = router()
        self.purchase(r)
        self.assertTrue(terrarossa.calls)
        self.assertEqual(weebora.calls, [])


if __name__ == "__main__":
    unittest.main()
