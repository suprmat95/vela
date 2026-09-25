"""Processore dei job sotto lo scheduler della quota (RF-36..38, RF-47, RF-50, RF-51).

Limite 120, margine 10%, riserva 20%: 108 effettive, 87 per gli acquisti. Orologio manuale.
"""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.config import DEFAULT_TRAVELER
from vela.domain.booking import BookingJob
from vela.domain.jobs import JobProcessor
from vela.domain.models import (Area, Criteria, Intent, Job, JobKind, JobStatus, NoMatch, Order,
                                OrderStatus, Participant, Period, Proposal, QuotaClass,
                                TravelerProfile)
from vela.domain.purchase import PurchaseJob
from vela.ports.hofj import QuotaError, QuotaSnapshot, UpstreamError

CRITERIA = Criteria("padel", Area("country", "Spagna", "ES"),
                    Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", 2, (Participant("Bo", "Bi"),))


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


class World:
    def __init__(self, hofj=None, quota=None):
        self.clock = Clock()
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many([make_product(i, price=300 + i) for i in range(1, 6)])
        self.repos.intents.add(Intent("i1", "padel", CRITERIA, PROFILE, NOW))
        self.hofj = hofj or FakeHofJ(quota=quota or QuotaSnapshot(120, 1, NOW, NOW + timedelta(seconds=60)))
        purchase = PurchaseJob(self.repos, self.hofj, StubPayments(), lambda intent: NoMatch("i1", "x", "x"),
                               DEFAULT_TRAVELER, now=self.clock, max_attempts=3)
        booking = BookingJob(self.repos, self.hofj, now=self.clock)
        self.processor = JobProcessor(self.repos, self.hofj, {JobKind.PURCHASE: purchase,
                                                              JobKind.BOOKING: booking},
                                      now=self.clock, lease_seconds=120)

    def purchase(self, n, seconds_ago=0):
        oid, pid = "o%d" % n, "p%d" % n
        self.repos.proposals.add(Proposal(pid, "i1", str(n), date(2026, 10, 1), date(2026, 10, 4), 2,
                                          Decimal("300"), "EUR", "Motivo.", NOW))
        at = NOW - timedelta(seconds=seconds_ago)
        self.repos.orders.add(Order(oid, pid, "i1", str(n), OrderStatus.QUEUED, 2, Decimal("300"), None,
                                    "EUR", PROFILE, at, at, enqueued_at=at))
        self.repos.jobs.enqueue(Job("j%d" % n, JobKind.PURCHASE, oid, JobStatus.PENDING, at, at))

    def booking(self, n):
        oid, pid = "o%d" % n, "p%d" % n
        self.repos.proposals.add(Proposal(pid, "i1", str(n), date(2026, 10, 1), date(2026, 10, 4), 2,
                                          Decimal("300"), "EUR", "Motivo.", NOW))
        self.repos.orders.add(Order(oid, pid, "i1", str(n), OrderStatus.PAID_PENDING_BOOKING, 2,
                                    Decimal("300"), Decimal("600"), "EUR", PROFILE, NOW, NOW,
                                    itinerary_id="it-%d" % n, payment_ref="pi"))
        self.repos.jobs.enqueue(Job("b%d" % n, JobKind.BOOKING, oid, JobStatus.PENDING, NOW, NOW))

    def boot(self):
        self.processor.refresh_quota()
        self.hofj.calls.clear()

    def fill(self, cls, calls):
        for _ in range(calls):
            assert self.repos.quota.acquire(cls, 1, self.clock())

    def hofj_methods(self):
        return [c[0] for c in self.hofj.calls]

    def status(self, n):
        return self.repos.orders.get("o%d" % n).status


class SchedulingTest(unittest.TestCase):
    def test_idle_returns_false(self):
        w = World()
        w.boot()
        self.assertFalse(w.processor.run_once())

    def test_purchase_runs_all_steps_under_one_block(self):
        w = World()
        w.boot()
        w.purchase(1)
        self.assertTrue(w.processor.run_once())
        self.assertEqual(w.status(1), OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(w.repos.quota.snapshot(w.clock())["used"], 1 + 5)   # quota + acquisto

    def test_no_hofj_call_without_acquired_block(self):
        w = World()
        w.boot()
        w.fill(QuotaClass.PURCHASE, 86)
        w.purchase(1)
        self.assertTrue(w.processor.run_once())
        self.assertEqual(w.hofj_methods(), [])
        job = w.repos.jobs.get("j1")
        self.assertEqual((job.status, job.attempts, job.step), (JobStatus.PENDING, 0, 0))
        self.assertEqual(job.run_after, NOW + timedelta(seconds=60))

    def test_job_waits_next_window_when_budget_short(self):
        w = World()
        w.boot()
        w.fill(QuotaClass.PURCHASE, 86)
        w.purchase(1)
        w.processor.run_once()
        w.clock.advance(59)
        self.assertFalse(w.processor.run_once())
        w.clock.advance(1)
        self.assertTrue(w.processor.run_once())
        self.assertEqual(w.status(1), OrderStatus.AWAITING_PAYMENT)

    def test_booking_reserve_respected_with_full_window(self):
        w = World()
        w.boot()
        w.fill(QuotaClass.PURCHASE, 86)
        w.purchase(1)
        w.booking(2)
        w.processor.run_once()                         # booking prima, dalla riserva
        self.assertEqual(w.status(2), OrderStatus.CONFIRMED)
        w.processor.run_once()                         # purchase: 87 + 5 > 87, rinviato
        self.assertEqual(w.status(1), OrderStatus.QUEUED)

    def test_purchase_fifo(self):
        w = World()
        w.boot()
        w.purchase(2, seconds_ago=5)
        w.purchase(1, seconds_ago=10)
        w.purchase(3, seconds_ago=1)
        for _ in range(3):
            w.processor.run_once()
        created = [c[1] for c in w.hofj.calls if c[0] == "create_itinerary"]
        self.assertEqual(created, ["1", "2", "3"])

    def test_resumed_purchase_reserves_only_the_remaining_calls(self):
        w = World()
        w.boot()
        w.purchase(1)
        w.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        order = w.repos.orders.get("o1")
        w.repos.orders.save(replace(order, itinerary_id="it-1"))
        w.repos.jobs.save(replace(w.repos.jobs.get("j1"), step=3))
        w.fill(QuotaClass.PURCHASE, 85)                # 1 + 85 = 86: c'è posto per 1 sola chiamata
        w.processor.run_once()
        self.assertEqual(w.status(1), OrderStatus.AWAITING_PAYMENT)

    def test_unused_calls_are_not_refunded(self):
        w = World(hofj=FakeHofJ(fail_at={"set_customer": [UpstreamError("timeout")]}))
        w.boot()
        w.purchase(1)
        w.processor.run_once()
        self.assertEqual(w.repos.quota.snapshot(w.clock())["used"], 1 + 5)
        self.assertEqual(w.repos.jobs.get("j1").step, 1)


class QuotaErrorTest(unittest.TestCase):
    def test_429_zeroes_budget_and_retries_next_window(self):
        w = World(hofj=FakeHofJ(fail_at={"create_itinerary": [QuotaError("429")]}))
        w.boot()
        w.purchase(1)
        w.booking(2)
        w.repos.jobs.save(replace(w.repos.jobs.get("b2"), run_after=NOW + timedelta(seconds=10)))
        w.processor.run_once()                         # acquisto: 429
        snap = w.repos.quota.snapshot(w.clock())
        self.assertEqual(snap["remaining"], 0)
        self.assertTrue(snap["needs_refresh"])
        w.clock.advance(10)
        w.processor.run_once()                         # booking: nessun budget nemmeno per la riserva
        self.assertEqual(w.status(2), OrderStatus.PAID_PENDING_BOOKING)
        self.assertEqual(w.hofj_methods(), ["create_itinerary"])
        w.clock.advance(50)                            # finestra successiva
        w.processor.run_once()
        self.assertEqual(w.hofj_methods()[1], "get_quota")
        self.assertEqual(w.status(2), OrderStatus.CONFIRMED)

    def test_quota_refresh_only_at_boot_and_after_429(self):
        w = World()
        w.processor.refresh_quota()
        for n in range(1, 6):
            w.purchase(n)
        for _ in range(50):
            w.processor.run_once()
        self.assertEqual(sum(1 for c in w.hofj.calls if c[0] == "get_quota"), 1)

    def test_refresh_is_attempted_once_per_window_when_it_fails(self):
        w = World(hofj=FakeHofJ(fail_at={"get_quota": [UpstreamError("down")] * 10}))
        w.purchase(1)
        for _ in range(20):
            w.processor.run_once()
        self.assertEqual(sum(1 for c in w.hofj.calls if c[0] == "get_quota"), 1)
        self.assertEqual(w.status(1), OrderStatus.AWAITING_PAYMENT)   # si lavora con i default
        w.clock.advance(60)
        w.processor.run_once()
        self.assertEqual(sum(1 for c in w.hofj.calls if c[0] == "get_quota"), 2)

    def test_boot_refresh_aligns_the_window_to_hofj(self):
        start = NOW - timedelta(seconds=40)
        w = World(quota=QuotaSnapshot(120, 30, start, start + timedelta(seconds=60)))
        self.assertTrue(w.processor.refresh_quota())
        snap = w.repos.quota.snapshot(w.clock())
        self.assertEqual((snap["used"], snap["window_end"], snap["needs_refresh"]),
                         (30, NOW + timedelta(seconds=20), False))


if __name__ == "__main__":
    unittest.main()
