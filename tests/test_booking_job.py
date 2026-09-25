"""Job di prenotazione (RF-23, RF-24, RF-51): una chiamata, retry con backoff su rete e 5xx."""
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from support import NOW, FakeHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain import say
from vela.domain.booking import BookingJob
from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus, TravelerProfile
from vela.ports.hofj import ConfigError, ProductError, QuotaError, UpstreamError

NEXT_WINDOW = NOW + timedelta(seconds=30)


class Setup:
    def __init__(self, hofj=None, status=OrderStatus.PAID_PENDING_BOOKING):
        self.repos = MemoryRepositories()
        self.repos.orders.add(Order("o1", "p1", "i1", "1", status, 2, Decimal("500"), Decimal("1000"),
                                    "EUR", TravelerProfile(), NOW, NOW, itinerary_id="it-1",
                                    payment_ref="pi_123"))
        self.hofj = hofj or FakeHofJ(code="R-123456")
        self.job = BookingJob(self.repos, self.hofj, now=lambda: NOW, max_attempts=5,
                              backoff=(5, 10, 20, 40))
        self.repos.jobs.enqueue(Job("b1", JobKind.BOOKING, "o1", JobStatus.PENDING, NOW, NOW))

    def run(self, attempts=0):
        j = replace(self.repos.jobs.get("b1"), status=JobStatus.RUNNING, locked_at=NOW, attempts=attempts)
        self.repos.jobs.save(j)
        return self.job.run(j, NEXT_WINDOW)

    def order(self):
        return self.repos.orders.get("o1")


class BookingJobTest(unittest.TestCase):
    def test_booking_confirms_with_code(self):
        s = Setup()
        result = s.run()
        self.assertEqual((s.order().status, s.order().booking_code), (OrderStatus.CONFIRMED, "R-123456"))
        self.assertEqual(result.job.status, JobStatus.DONE)
        self.assertEqual(s.repos.jobs.get("b1"), result.job)

    def test_booking_forwards_the_payment_intent(self):
        s = Setup()
        s.run()
        proof = s.hofj.calls[0][2]
        self.assertEqual((proof.payment_intent_id, proof.payment_status, proof.payment_type),
                         ("pi_123", "succeeded", "full"))

    def test_retry_with_backoff_on_5xx(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [UpstreamError("502")] * 4}))
        waits = []
        for attempt in range(4):
            result = s.run(attempts=attempt)
            self.assertEqual((result.job.status, result.job.attempts), (JobStatus.PENDING, attempt + 1))
            waits.append((result.job.run_after - NOW).total_seconds())
        self.assertEqual(waits, [5, 10, 20, 40])
        self.assertEqual(s.order().status, OrderStatus.PAID_PENDING_BOOKING)
        s.run(attempts=4)
        self.assertEqual(s.order().status, OrderStatus.CONFIRMED)

    def test_stops_after_max_attempts_booking_failed_with_reason(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [UpstreamError("timeout")]}))
        result = s.run(attempts=4)
        self.assertEqual(result.job.status, JobStatus.DEAD)
        self.assertEqual(s.order().status, OrderStatus.BOOKING_FAILED)
        self.assertEqual(s.order().failure_reason, say.failure_reason("booking_upstream"))
        self.assertIn("timeout", result.job.last_error)

    def test_4xx_fails_immediately(self):
        for exc in (ProductError("400"), ConfigError("403")):
            s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [exc]}))
            result = s.run()
            self.assertEqual(result.job.status, JobStatus.DEAD)
            self.assertEqual(s.order().status, OrderStatus.BOOKING_FAILED)
            self.assertEqual(s.order().failure_reason, say.failure_reason("booking_rejected"))

    def test_429_reschedules_next_window_without_counting(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [QuotaError("429")]}))
        result = s.run(attempts=2)
        self.assertTrue(result.hit_429)
        self.assertEqual((result.job.status, result.job.attempts, result.job.run_after),
                         (JobStatus.PENDING, 2, NEXT_WINDOW))

    def test_order_not_paid_pending_is_left_alone(self):
        for status in (OrderStatus.CONFIRMED, OrderStatus.AWAITING_PAYMENT, OrderStatus.CANCELLED):
            s = Setup(status=status)
            result = s.run()
            self.assertEqual(result.job.status, JobStatus.DONE)
            self.assertEqual(s.hofj.calls, [])
            self.assertEqual(s.order().status, status)


if __name__ == "__main__":
    unittest.main()
