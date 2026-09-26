"""Contratto dei repository: eseguito su MemoryRepositories (sempre) e PostgresRepositories (con DATABASE_URL)."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.domain.models import (Area, Criteria, Intent, Job, JobKind, JobStatus, Order,
                                OrderStatus, Participant, Period, Proposal, Rejection,
                                TravelerProfile)
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


def job(jid, oid, kind=JobKind.PURCHASE, enqueued_at=NOW, run_after=NOW, **kw):
    return Job(jid, kind, oid, JobStatus.PENDING, enqueued_at, run_after, **kw)


LEASE = 120


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
        p = replace(p, raw={"rawAttributes": {"k": [1, 2]}}, bookable=False, bookable_checked_at=NOW,
                    brand="terrarossa.com")
        self.repos.products.upsert_many([p])
        got = self.repos.products.get("7")
        self.assertEqual(got, p)

    def test_products_empty(self):
        self.assertEqual(self.repos.products.count(), 0)
        self.assertEqual(self.repos.products.list_all(), [])
        self.repos.products.upsert_many([])

    def test_products_last_fetched_at(self):
        self.assertIsNone(self.repos.products.last_fetched_at())
        later = NOW + timedelta(hours=1)
        self.repos.products.upsert_many([make_product(1), replace(make_product(2), fetched_at=later)])
        self.assertEqual(self.repos.products.last_fetched_at(), later)

    def test_products_archive_missing_archives_only_active_products_not_kept(self):
        self.repos.products.upsert_many([make_product(1), make_product(2), make_product(3),
                                         make_product(4, archived=True)])
        self.assertEqual(self.repos.products.archive_missing(["1", "999"]), 2)
        archived = {p.id: p.archived for p in self.repos.products.list_all()}
        self.assertEqual(archived, {"1": False, "2": True, "3": True, "4": True})
        self.assertEqual(self.repos.products.get("2").price, Decimal("500"))   # nessun altro campo

    def test_products_archive_missing_with_nothing_to_keep_archives_everything(self):
        self.repos.products.upsert_many([make_product(1), make_product(2)])
        self.assertEqual(self.repos.products.archive_missing([]), 2)
        self.assertEqual(self.repos.products.archive_missing([]), 0)
        self.assertEqual(self.repos.products.count(), 2)

    def test_products_archive_missing_by_brand_touches_only_that_brand(self):
        self.repos.products.upsert_many([make_product(1, brand="a.com"), make_product(2, brand="a.com"),
                                         make_product(3, brand="b.com"), make_product(4)])
        self.assertEqual(self.repos.products.archive_missing(["1"], brand="a.com"), 1)
        archived = {p.id: p.archived for p in self.repos.products.list_all()}
        self.assertEqual(archived, {"1": False, "2": True, "3": False, "4": False})

    def test_products_sync_state(self):
        self.repos.products.upsert_many([make_product(1, brand="a.com", updated_at="u1"),
                                         make_product(2, updated_at="u2")])
        self.assertEqual(self.repos.products.sync_state(["1", "2", "9"]),
                         {"1": ("a.com", "u1"), "2": (None, "u2")})
        self.assertEqual(self.repos.products.sync_state([]), {})

    def test_products_set_brand(self):
        self.repos.products.upsert_many([make_product(1), make_product(2), make_product(3)])
        self.repos.products.set_brand(["1", "2"], "t.com", "tennis")
        got = {p.id: (p.brand, p.sport) for p in self.repos.products.list_all()}
        self.assertEqual(got, {"1": ("t.com", "tennis"), "2": ("t.com", "tennis"),
                               "3": (None, "padel")})
        self.assertEqual(self.repos.products.get("1").price, Decimal("500"))
        self.repos.products.set_brand([], "t.com", "tennis")

    # intenti
    def test_intents_round_trip(self):
        self.repos.intents.add(intent())
        self.assertEqual(self.repos.intents.get("i1"), intent())
        self.assertIsNone(self.repos.intents.get("nope"))

    def test_intents_update_criteria(self):
        self.repos.intents.add(intent())
        new = replace(CRITERIA, budget=Decimal("560.00"), area=Area("city", "Alicante", "ES"),
                      language="en")
        self.repos.intents.update_criteria("i1", new)
        got = self.repos.intents.get("i1")
        self.assertEqual(got.criteria, new)
        self.assertEqual((got.id, got.text, got.profile, got.created_at),
                         ("i1", intent().text, PROFILE, NOW))
        self.repos.intents.update_criteria("nope", new)   # nessun effetto, nessun errore
        self.assertIsNone(self.repos.intents.get("nope"))

    def seed(self):
        """Prodotti e intento a cui proposte, ordini e rifiuti fanno riferimento (foreign key su Postgres)."""
        self.repos.products.upsert_many([make_product(1), make_product(2)])
        self.repos.intents.add(intent())

    def test_set_bookable_roundtrip(self):
        """RF-33: marcato non prenotabile con l'ora del controllo; riabilitato più tardi (RF-34)."""
        self.repos.products.upsert_many([make_product(1), make_product(2)])
        self.repos.products.set_bookable("1", False, NOW)
        p = self.repos.products.get("1")
        self.assertEqual((p.bookable, p.bookable_checked_at), (False, NOW))
        listed = {q.id: q for q in self.repos.products.list_all()}
        self.assertEqual((listed["1"].bookable, listed["1"].bookable_checked_at), (False, NOW))
        self.assertTrue(listed["2"].bookable)
        later = NOW + timedelta(hours=25)
        self.repos.products.set_bookable("1", True, later)
        p = self.repos.products.get("1")
        self.assertEqual((p.bookable, p.bookable_checked_at), (True, later))
        self.repos.products.set_bookable("nope", False, NOW)     # nessun effetto, nessun errore

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

    def test_order_roundtrip_with_queue_fields(self):
        """Ordine in coda (M5): totale ancora ignoto, posizione e sostituzione salvate."""
        self.seed()
        self.repos.proposals.add(proposal())
        queued = replace(order(), status=OrderStatus.QUEUED, total=None, itinerary_id=None,
                         enqueued_at=NOW - timedelta(minutes=3), replacement_proposal_id=None)
        self.repos.orders.add(queued)
        self.assertEqual(self.repos.orders.get("o1"), queued)
        replaced = replace(queued, status=OrderStatus.REPLACED, replacement_proposal_id="p9",
                           failure_reason="prodotto non prenotabile")
        self.repos.orders.save(replaced)
        self.assertEqual(self.repos.orders.get("o1"), replaced)
        self.assertEqual(self.repos.orders.ids_with_status(OrderStatus.REPLACED), ["o1"])
        self.assertEqual(self.repos.orders.get_by_replacement("p9"), replaced)
        self.assertIsNone(self.repos.orders.get_by_replacement("p1"))

    # job (RF-27, RF-50)
    def seed_orders(self, n):
        self.seed()
        for i in range(1, n + 1):
            self.repos.proposals.add(proposal("p%d" % i))
            self.repos.orders.add(order("o%d" % i, "p%d" % i))

    def test_job_roundtrip(self):
        self.seed_orders(1)
        j = job("j1", "o1", step=2, attempts=1, last_error="timeout")
        self.repos.jobs.enqueue(j)
        self.assertEqual(self.repos.jobs.get("j1"), j)
        done = replace(j, status=JobStatus.DONE, step=5, locked_at=NOW)
        self.repos.jobs.save(done)
        self.assertEqual(self.repos.jobs.get("j1"), done)
        self.assertIsNone(self.repos.jobs.get("nope"))

    def test_claim_marks_running_with_lock_time(self):
        self.seed_orders(1)
        self.repos.jobs.enqueue(job("j1", "o1"))
        claimed = self.repos.jobs.claim(NOW, LEASE)
        self.assertEqual((claimed.id, claimed.status, claimed.locked_at), ("j1", JobStatus.RUNNING, NOW))
        self.assertEqual(self.repos.jobs.get("j1"), claimed)

    def test_claim_prefers_booking_then_payment_check_then_purchase(self):
        self.seed_orders(3)
        self.repos.jobs.enqueue(job("j-p", "o1", enqueued_at=NOW - timedelta(minutes=9)))
        self.repos.jobs.enqueue(job("j-c", "o2", JobKind.PAYMENT_CHECK, enqueued_at=NOW - timedelta(minutes=5)))
        self.repos.jobs.enqueue(job("j-b", "o3", JobKind.BOOKING))
        order_of_claims = [self.repos.jobs.claim(NOW, LEASE).id for _ in range(3)]
        self.assertEqual(order_of_claims, ["j-b", "j-c", "j-p"])
        self.assertIsNone(self.repos.jobs.claim(NOW, LEASE))

    def test_claim_purchase_fifo_by_enqueued_at(self):
        self.seed_orders(3)
        self.repos.jobs.enqueue(job("j2", "o2", enqueued_at=NOW - timedelta(seconds=10)))
        self.repos.jobs.enqueue(job("j3", "o3", enqueued_at=NOW - timedelta(seconds=5)))
        self.repos.jobs.enqueue(job("j1", "o1", enqueued_at=NOW - timedelta(seconds=30)))
        self.assertEqual([self.repos.jobs.claim(NOW, LEASE).id for _ in range(3)], ["j1", "j2", "j3"])

    def test_claim_respects_run_after(self):
        self.seed_orders(2)
        self.repos.jobs.enqueue(job("j1", "o1", enqueued_at=NOW - timedelta(minutes=1),
                                    run_after=NOW + timedelta(seconds=30)))
        self.repos.jobs.enqueue(job("j2", "o2"))
        self.assertEqual(self.repos.jobs.claim(NOW, LEASE).id, "j2")
        self.assertIsNone(self.repos.jobs.claim(NOW, LEASE))
        self.assertEqual(self.repos.jobs.claim(NOW + timedelta(seconds=30), LEASE).id, "j1")

    def test_claimed_job_not_claimed_twice(self):
        self.seed_orders(1)
        self.repos.jobs.enqueue(job("j1", "o1"))
        self.assertIsNotNone(self.repos.jobs.claim(NOW, LEASE))
        self.assertIsNone(self.repos.jobs.claim(NOW + timedelta(seconds=LEASE - 1), LEASE))

    def test_expired_lease_is_reclaimed(self):
        self.seed_orders(1)
        self.repos.jobs.enqueue(job("j1", "o1", step=3))
        self.repos.jobs.claim(NOW, LEASE)
        later = NOW + timedelta(seconds=LEASE)
        again = self.repos.jobs.claim(later, LEASE)
        self.assertEqual((again.id, again.step, again.locked_at), ("j1", 3, later))

    def test_done_and_dead_jobs_are_never_claimed(self):
        self.seed_orders(2)
        self.repos.jobs.enqueue(replace(job("j1", "o1"), status=JobStatus.DONE))
        self.repos.jobs.enqueue(replace(job("j2", "o2"), status=JobStatus.DEAD))
        self.assertIsNone(self.repos.jobs.claim(NOW + timedelta(hours=1), LEASE))

    def test_active_for_order(self):
        self.seed_orders(1)
        self.repos.jobs.enqueue(replace(job("j0", "o1"), status=JobStatus.DONE))
        self.assertIsNone(self.repos.jobs.active_for_order("o1", JobKind.PURCHASE))
        self.repos.jobs.enqueue(job("j1", "o1"))
        self.assertEqual(self.repos.jobs.active_for_order("o1", JobKind.PURCHASE).id, "j1")
        self.repos.jobs.claim(NOW, LEASE)
        self.assertEqual(self.repos.jobs.active_for_order("o1", JobKind.PURCHASE).id, "j1")
        self.assertIsNone(self.repos.jobs.active_for_order("o1", JobKind.BOOKING))

    def test_position_counts_only_pending_purchases_before(self):
        self.seed_orders(4)
        self.repos.jobs.enqueue(job("j1", "o1", enqueued_at=NOW - timedelta(seconds=40)))
        self.repos.jobs.enqueue(job("j2", "o2", enqueued_at=NOW - timedelta(seconds=30)))
        self.repos.jobs.enqueue(job("j3", "o3", enqueued_at=NOW - timedelta(seconds=20)))
        self.repos.jobs.enqueue(job("jb", "o4", JobKind.BOOKING, enqueued_at=NOW - timedelta(minutes=5)))
        self.assertEqual(self.repos.jobs.queued_purchase_position("o3"), 3)
        self.repos.jobs.claim(NOW, LEASE)                    # booking
        self.repos.jobs.claim(NOW, LEASE)                    # j1 in lavorazione: non conta più
        self.assertEqual(self.repos.jobs.queued_purchase_position("o3"), 2)
        self.assertEqual(self.repos.jobs.queued_purchase_position("o2"), 1)

    def test_position_none_when_not_queued(self):
        self.seed_orders(2)
        self.repos.jobs.enqueue(job("j1", "o1"))
        self.repos.jobs.claim(NOW, LEASE)
        self.assertIsNone(self.repos.jobs.queued_purchase_position("o1"))    # in lavorazione
        self.assertIsNone(self.repos.jobs.queued_purchase_position("o2"))    # nessun job

    def test_purchase_waiting(self):
        self.seed_orders(2)
        self.assertFalse(self.repos.jobs.purchase_waiting())
        self.repos.jobs.enqueue(job("jb", "o2", JobKind.BOOKING))
        self.assertFalse(self.repos.jobs.purchase_waiting())
        self.repos.jobs.enqueue(job("j1", "o1", run_after=NOW + timedelta(minutes=1)))
        self.assertTrue(self.repos.jobs.purchase_waiting())

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
        reasons = {r.proposal_id: r.reason for r in self.repos.rejections.list_for_intent("i1")}
        self.assertEqual(reasons, {"p1": "troppo caro", "p2": ""})   # il primo motivo resta
        self.assertEqual(self.repos.rejections.list_for_intent("other"), [])
