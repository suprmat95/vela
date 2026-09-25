"""Contratto dei repository: eseguito su MemoryRepositories (sempre) e PostgresRepositories (con DATABASE_URL)."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.domain.models import (Criteria, Intent, Order, OrderStatus, Participant, Period,
                                Proposal, Rejection, TravelerProfile)
from vela.ports.repositories import DuplicateOrder

CRITERIA = Criteria(sport="padel", period=Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"),
                    pax=2, budget=Decimal("800"))
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", 2, (Participant("Bo", "Bi"),))


def intent(iid="i1"):
    return Intent(iid, "padel a ottobre per due", CRITERIA, PROFILE, NOW)


def proposal(pid="p1", iid="i1", product_id="1", created_at=NOW):
    return Proposal(pid, iid, product_id, date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("500"),
                    "EUR", "Motivo.", created_at)


def order(oid="o1", pid="p1"):
    return Order(oid, pid, "i1", "1", OrderStatus.AWAITING_PAYMENT, 2, Decimal("500"),
                 Decimal("1000"), "EUR", PROFILE, NOW, NOW, itinerary_id="it-1")


class RepositoryContract:
    def make_repos(self):
        raise NotImplementedError

    def setUp(self):
        self.repos = self.make_repos()

    # prodotti
    def test_products_upsert_is_idempotent_and_updates(self):
        self.repos.products.upsert_many([make_product(1, price=500), make_product(2, archived=True)])
        self.repos.products.upsert_many([make_product(1, price=550)])
        self.assertEqual(self.repos.products.count(), 2)
        self.assertEqual(self.repos.products.get("1").price, Decimal("550"))
        self.assertEqual(sorted(p.id for p in self.repos.products.list_all()), ["1", "2"])
        self.assertTrue(self.repos.products.get("2").archived)
        self.assertIsNone(self.repos.products.get("999"))

    def test_products_fields_round_trip(self):
        p = make_product(7, min_pax=2, max_pax=0, hotel=None, windows=(("2026-10-01", "2026-10-04"),
                                                                        ("2026-11-05", "2026-11-08")))
        p = replace(p, raw={"rawAttributes": {"k": [1, 2]}}, bookable=False, bookable_checked_at=NOW)
        self.repos.products.upsert_many([p])
        got = self.repos.products.get("7")
        self.assertEqual(got, p)

    def test_products_empty(self):
        self.assertEqual(self.repos.products.count(), 0)
        self.assertEqual(self.repos.products.list_all(), [])
        self.repos.products.upsert_many([])

    # intenti
    def test_intents_round_trip(self):
        self.repos.intents.add(intent())
        self.assertEqual(self.repos.intents.get("i1"), intent())
        self.assertIsNone(self.repos.intents.get("nope"))

    def seed(self):
        """Prodotti e intento a cui proposte, ordini e rifiuti fanno riferimento (foreign key su Postgres)."""
        self.repos.products.upsert_many([make_product(1), make_product(2)])
        self.repos.intents.add(intent())

    # proposte
    def test_proposals_ordered_by_created_at(self):
        self.seed()
        self.repos.proposals.add(proposal("p2", created_at=NOW + timedelta(seconds=5)))
        self.repos.proposals.add(proposal("p1"))
        self.assertEqual([p.id for p in self.repos.proposals.list_for_intent("i1")], ["p1", "p2"])
        self.assertEqual(self.repos.proposals.get("p2"), proposal("p2", created_at=NOW + timedelta(seconds=5)))
        self.assertIsNone(self.repos.proposals.get("nope"))
        self.assertEqual(self.repos.proposals.list_for_intent("other"), [])

    # ordini
    def test_orders_add_get_save_and_duplicate(self):
        self.seed()
        self.repos.proposals.add(proposal())
        self.repos.orders.add(order())
        self.assertEqual(self.repos.orders.get("o1"), order())
        self.assertEqual(self.repos.orders.get_by_proposal("p1").id, "o1")
        with self.assertRaises(DuplicateOrder):
            self.repos.orders.add(order("o2", "p1"))
        self.assertIsNone(self.repos.orders.get("o2"))
        updated = replace(order(), status=OrderStatus.CONFIRMED, booking_code="R-1",
                          payment_url="http://x", payment_ref="pi", paid_at=NOW,
                          updated_at=NOW + timedelta(seconds=1))
        self.repos.orders.save(updated)
        self.assertEqual(self.repos.orders.get("o1"), updated)
        self.assertEqual(self.repos.orders.ids_with_status(OrderStatus.CONFIRMED), ["o1"])
        self.assertEqual(self.repos.orders.ids_with_status(OrderStatus.AWAITING_PAYMENT), [])
        self.assertIsNone(self.repos.orders.get_by_proposal("nope"))

    # rifiuti
    def test_rejections(self):
        self.seed()
        self.repos.proposals.add(proposal("p1", product_id="1"))
        self.repos.proposals.add(proposal("p2", product_id="2"))
        self.repos.rejections.add(Rejection("i1", "p1", "1", "troppo caro", NOW))
        self.repos.rejections.add(Rejection("i1", "p1", "1", "di nuovo", NOW))
        self.repos.rejections.add(Rejection("i1", "p2", "2", "", NOW))
        self.assertEqual(self.repos.rejections.product_ids_for_intent("i1"), {"1", "2"})
        self.assertEqual(self.repos.rejections.proposal_ids_for_intent("i1"), {"p1", "p2"})
        self.assertEqual(self.repos.rejections.product_ids_for_intent("other"), set())
