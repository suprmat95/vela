"""Verifica del pagamento per interrogazione, senza webhook (RF-20, RF-51)."""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, make_product
from vela.adapters.hofj_router import SingleClientRouter
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.booking import BookingJob
from vela.domain.jobs import JobProcessor
from vela.domain.models import (Job, JobKind, JobStatus, NoMatch, Order, OrderStatus, QuotaClass,
                                TravelerProfile)
from vela.domain.orders import OrderService
from vela.domain.payment_check import PaymentCheckJob
from vela.domain.purchase import PurchaseJob
from vela.ports.hofj import QuotaSnapshot
from vela.ports.payments import LinkStatus, PaymentsError


class ScriptedPayments(StubPayments):
    """Stati della sessione in sequenza; l'ultimo si ripete."""

    def __init__(self, *statuses):
        super().__init__()
        self.statuses = list(statuses)
        self.checked = []

    def link_status(self, reference):
        self.checked.append(reference)
        status = self.statuses[0] if len(self.statuses) == 1 else self.statuses.pop(0)
        if isinstance(status, Exception):
            raise status
        return status


PAID = LinkStatus("paid", 100000, "EUR", "pi_real")


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at


class World:
    def __init__(self, payments):
        self.clock = Clock()
        self.repos = MemoryRepositories()
        self.repos.orders.add(Order("o1", "p1", "i1", "1", OrderStatus.AWAITING_PAYMENT, 2,
                                    Decimal("500"), Decimal("1000"), "EUR", TravelerProfile(), NOW, NOW,
                                    itinerary_id="it-1", payment_url="https://pay/o1",
                                    payment_ref="cs_1"))
        self.repos.jobs.enqueue(Job("c1", JobKind.PAYMENT_CHECK, "o1", JobStatus.PENDING, NOW, NOW))
        ids = iter("job%d" % i for i in range(1, 100))
        self.orders = OrderService(self.repos, FakeHofJ(), now=self.clock, new_id=lambda: next(ids))
        self.payments = payments
        self.check = PaymentCheckJob(self.repos, payments, self.orders, now=self.clock, poll_seconds=60)
        self.hofj = FakeHofJ()
        router = SingleClientRouter(self.hofj)
        self.processor = JobProcessor(self.repos, router, {
            JobKind.PAYMENT_CHECK: self.check,
            JobKind.BOOKING: BookingJob(self.repos, router, now=self.clock)},
            now=self.clock)
        self.repos.quota.acquire(QuotaClass.BOOKING, 1, NOW)       # finestra già aperta

    def run(self):
        job = replace(self.repos.jobs.get("c1"), status=JobStatus.RUNNING, locked_at=self.clock())
        self.repos.jobs.save(job)
        return self.check.run(job, NOW + timedelta(seconds=60))

    def order(self):
        return self.repos.orders.get("o1")

    def bookings(self):
        return [j for j in self.repos.jobs._jobs.values() if j.kind == JobKind.BOOKING]


class PaymentCheckJobTest(unittest.TestCase):
    def test_check_paid_session_settles_and_enqueues_booking_once(self):
        w = World(ScriptedPayments(PAID))
        result = w.run()
        self.assertEqual(result.job.status, JobStatus.DONE)
        order = w.order()
        self.assertEqual((order.status, order.payment_ref), (OrderStatus.PAID_PENDING_BOOKING, "pi_real"))
        self.assertEqual(len(w.bookings()), 1)
        self.assertEqual(w.payments.checked, ["cs_1"])

    def test_check_open_session_reschedules(self):
        w = World(ScriptedPayments(LinkStatus("open", None, None, None)))
        result = w.run()
        self.assertEqual((result.job.status, result.job.run_after, result.job.attempts),
                         (JobStatus.PENDING, NOW + timedelta(seconds=60), 0))
        self.assertEqual(w.order().status, OrderStatus.AWAITING_PAYMENT)

    def test_check_expired_session_expires_order(self):
        w = World(ScriptedPayments(LinkStatus("expired", None, None, None)))
        self.assertEqual(w.run().job.status, JobStatus.DONE)
        self.assertEqual(w.order().status, OrderStatus.EXPIRED)

    def test_check_amount_mismatch_does_not_settle(self):
        w = World(ScriptedPayments(LinkStatus("paid", 99999, "EUR", "pi_x")))
        with self.assertLogs("vela.domain.orders", "WARNING"):
            result = w.run()
        self.assertEqual(result.job.status, JobStatus.DONE)
        self.assertEqual(w.order().status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(w.bookings(), [])

    def test_check_currency_mismatch_does_not_settle(self):
        w = World(ScriptedPayments(LinkStatus("paid", 100000, "USD", "pi_x")))
        with self.assertLogs("vela.domain.orders", "WARNING"):
            w.run()
        self.assertEqual(w.order().status, OrderStatus.AWAITING_PAYMENT)

    def test_check_payments_error_reschedules(self):
        w = World(ScriptedPayments(PaymentsError("rete"), PAID))
        result = w.run()
        self.assertEqual((result.job.status, result.job.run_after), (JobStatus.PENDING, NOW + timedelta(seconds=60)))
        self.assertIn("rete", result.job.last_error)

    def test_check_on_order_no_longer_awaiting_is_noop(self):
        w = World(ScriptedPayments(PAID))
        w.repos.orders.save(replace(w.order(), status=OrderStatus.CANCELLED))
        self.assertEqual(w.run().job.status, JobStatus.DONE)
        self.assertEqual(w.payments.checked, [])

    def test_check_twice_after_paid_is_noop(self):
        w = World(ScriptedPayments(PAID))
        w.run()
        w.repos.jobs.enqueue(Job("c2", JobKind.PAYMENT_CHECK, "o1", JobStatus.PENDING, NOW, NOW))
        w.processor.run_once()        # booking
        w.processor.run_once()        # seconda verifica: ordine confermato, nessun effetto
        self.assertEqual(len(w.bookings()), 1)
        self.assertEqual(w.order().status, OrderStatus.CONFIRMED)

    def test_check_runs_with_no_hofj_budget_left(self):
        w = World(ScriptedPayments(LinkStatus("open", None, None, None)))
        w.repos.quota.sync_from_snapshot(QuotaSnapshot(120, 108, NOW, NOW + timedelta(seconds=60)), NOW)
        self.assertTrue(w.processor.run_once())
        self.assertEqual(w.payments.checked, ["cs_1"])
        self.assertEqual(w.hofj.calls, [])
        self.assertEqual(w.repos.quota.snapshot(NOW)["tokens"], -100)   # bloccato fino a fine finestra

class PurchaseEnqueuesCheckTest(unittest.TestCase):
    def test_link_step_enqueues_a_payment_check(self):
        repos = MemoryRepositories()
        repos.products.upsert_many([make_product(1)])
        from vela.domain.models import Proposal
        repos.proposals.add(Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2,
                                     Decimal("500"), "EUR", "M.", NOW))
        repos.orders.add(Order("o1", "p1", "i1", "1", OrderStatus.QUEUED, 2, Decimal("500"), Decimal("1000"),
                               "EUR", TravelerProfile(), NOW, NOW, itinerary_id="it-1"))
        job = Job("j1", JobKind.PURCHASE, "o1", JobStatus.RUNNING, NOW, NOW, step=4, locked_at=NOW)
        repos.jobs.enqueue(job)
        ids = iter(["chk1", "sms1"])   # id distinto per il job di verifica e per l'SMS accodati insieme
        purchase = PurchaseJob(repos, SingleClientRouter(FakeHofJ()), StubPayments(), lambda i: NoMatch("i1", "x", "x"),
                               DEFAULT_TRAVELER, now=lambda: NOW, max_attempts=3,
                               new_id=lambda: next(ids), poll_seconds=60)
        purchase.run(job, NOW + timedelta(seconds=60))
        check = repos.jobs.active_for_order("o1", JobKind.PAYMENT_CHECK)
        self.assertEqual((check.id, check.run_after), ("chk1", NOW + timedelta(seconds=60)))


class FakePaymentsStatusTest(unittest.TestCase):
    def order(self):
        return Order("o1", "p1", "i1", "1", OrderStatus.AWAITING_PAYMENT, 2, Decimal("500"),
                     Decimal("1000"), "EUR", TravelerProfile(), NOW, NOW)

    def test_link_is_open_until_the_replay_checkout_pays_it(self):
        fake = FakePayments(now=lambda: NOW)
        link = fake.create_payment_link(self.order(), "Padel")
        self.assertEqual(fake.link_status(link.reference).state, "open")
        fake.pay(self.order())
        self.assertEqual(fake.link_status(link.reference),
                         LinkStatus("paid", 100000, "EUR", "pi_replay_o1"))

    def test_unknown_reference_is_open(self):
        self.assertEqual(FakePayments().link_status("cs_nope").state, "open")


if __name__ == "__main__":
    unittest.main()
