"""Job di prenotazione (RF-23, RF-24, RF-51): cliente, passeggeri e booking (M19), retry con backoff
su rete e 5xx."""
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from support import NOW, FakeHofJ
from vela.adapters.hofj_router import SingleClientRouter
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain import say
from vela.domain.booking import BookingJob, booking_calls_needed
from vela.domain.models import (Job, JobKind, JobStatus, Order, OrderStatus, Participant, TravelerDefaults,
                                TravelerProfile)
from vela.ports.hofj import ConfigError, Pax, ProductError, QuotaError, UpstreamError

NEXT_WINDOW = NOW + timedelta(seconds=30)
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39 333", 2, (Participant("Bo", "Bi"),))
DEFAULTS = TravelerDefaults("Via Uno 1", "00100", "Roma", "RM", "IT")


class Setup:
    def __init__(self, hofj=None, status=OrderStatus.PAID_PENDING_BOOKING, pax=2, profile=PROFILE):
        self.repos = MemoryRepositories()
        self.repos.orders.add(Order("o1", "p1", "i1", "1", status, pax, Decimal("500"), Decimal("1000"),
                                    "EUR", profile, NOW, NOW, itinerary_id="it-1",
                                    payment_ref="pi_123"))
        self.hofj = hofj or FakeHofJ(code="R-123456")
        self.job = BookingJob(self.repos, SingleClientRouter(self.hofj), now=lambda: NOW, max_attempts=5,
                              backoff=(5, 10, 20, 40), defaults=DEFAULTS)
        self.repos.jobs.enqueue(Job("b1", JobKind.BOOKING, "o1", JobStatus.PENDING, NOW, NOW))

    def run(self, attempts=None):
        saved = self.repos.jobs.get("b1")
        j = replace(saved, status=JobStatus.RUNNING, locked_at=NOW,
                    attempts=saved.attempts if attempts is None else attempts)
        self.repos.jobs.save(j)
        return self.job.run(j, NEXT_WINDOW)

    def order(self):
        return self.repos.orders.get("o1")

    def methods(self):
        return [c[0] for c in self.hofj.calls]


class CallsNeededTest(unittest.TestCase):
    def test_calls_needed_decreases_with_steps(self):
        """M19: cliente, passeggeri, (lettura dei passeggeri solo nel ripiego), booking."""
        base = Job("b", JobKind.BOOKING, "o", JobStatus.RUNNING, NOW, NOW)
        self.assertEqual([booking_calls_needed(replace(base, step=s)) for s in range(5)], [3, 2, 3, 1, 0])


class CustomerAndPaxTest(unittest.TestCase):
    """M19: cliente e passeggeri dopo il pagamento, nello stesso job, prima di `POST /v1/bookings`."""

    def test_three_calls_customer_pax_booking(self):
        s = Setup()
        result = s.run()
        self.assertEqual(s.methods(), ["set_customer", "set_pax", "create_booking"])
        self.assertEqual((s.order().status, s.order().booking_code), (OrderStatus.CONFIRMED, "R-123456"))
        self.assertEqual((result.job.status, result.job.step), (JobStatus.DONE, 4))

    def test_customer_from_the_traveler_and_the_defaults(self):
        s = Setup()
        s.run()
        customer = s.hofj.calls[0][2]
        self.assertEqual((customer.first_name, customer.last_name, customer.email, customer.phone),
                         ("Anna", "Rossi", "a@x.it", "+39 333"))
        self.assertEqual((customer.street1, customer.postal_code, customer.city, customer.region,
                          customer.country_code), ("Via Uno 1", "00100", "Roma", "RM", "IT"))

    def test_pax_use_the_known_ref_ids_without_reading_them(self):
        """Differenza #36: `pax-1..N` esistono dalla creazione dell'itinerario."""
        s = Setup()
        s.run()
        self.assertEqual(s.hofj.calls[1][2], [Pax("pax-1", "Anna", "Rossi"), Pax("pax-2", "Bo", "Bi")])

    def test_pax_without_a_name_stay_empty(self):
        s = Setup(pax=3)
        s.run()
        self.assertEqual(s.hofj.calls[1][2][2], Pax("pax-3", None, None))

    def test_each_step_is_saved_before_the_next(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [UpstreamError("502")]}))
        s.run()
        self.assertEqual(s.repos.jobs.get("b1").step, 3)
        s.hofj.calls.clear()
        s.run()
        self.assertEqual(s.methods(), ["create_booking"])
        self.assertEqual(s.order().status, OrderStatus.CONFIRMED)

    def test_resume_at_pax_does_not_repeat_the_customer(self):
        s = Setup(hofj=FakeHofJ(fail_at={"set_pax": [UpstreamError("timeout")]}))
        result = s.run()
        self.assertEqual((result.job.status, result.job.step, result.job.attempts), (JobStatus.PENDING, 1, 1))
        s.hofj.calls.clear()
        s.run()
        self.assertEqual(s.methods(), ["set_pax", "create_booking"])

    def test_unknown_ref_ids_fall_back_to_reading_the_pax(self):
        """Un 4xx sul `PUT pax` con `refId` diversi: passo con `get_pax`, rimesso in coda subito
        per prendere i suoi gettoni, senza contare un tentativo."""
        s = Setup()
        s.hofj.pax["it-1"] = [Pax("a"), Pax("b")]
        first = s.run()
        self.assertEqual(s.methods(), ["set_customer", "set_pax"])
        self.assertEqual((first.job.status, first.job.step, first.job.attempts, first.job.run_after),
                         (JobStatus.PENDING, 2, 0, NOW))
        self.assertEqual(s.order().status, OrderStatus.PAID_PENDING_BOOKING)
        s.hofj.calls.clear()
        s.run()
        self.assertEqual(s.methods(), ["get_pax", "set_pax", "create_booking"])
        self.assertEqual(s.hofj.calls[1][2], [Pax("a", "Anna", "Rossi"), Pax("b", "Bo", "Bi")])
        self.assertEqual(s.order().status, OrderStatus.CONFIRMED)

    def test_rejected_pax_after_the_fallback_fails_the_booking(self):
        s = Setup(hofj=FakeHofJ(fail_at={"set_pax": [ProductError("400"), ProductError("400")]}))
        s.hofj.pax["it-1"] = [Pax("pax-1"), Pax("pax-2")]
        s.run()
        result = s.run()
        self.assertEqual(result.job.status, JobStatus.DEAD)
        self.assertEqual(s.order().status, OrderStatus.BOOKING_FAILED)
        self.assertEqual(s.order().failure_reason, say.failure_reason("booking_rejected"))
        self.assertNotIn("create_booking", s.methods())

    def test_rejected_customer_fails_the_booking(self):
        s = Setup(hofj=FakeHofJ(fail_at={"set_customer": [ProductError("409")]}))
        result = s.run()
        self.assertEqual(result.job.status, JobStatus.DEAD)
        self.assertEqual(s.order().status, OrderStatus.BOOKING_FAILED)
        self.assertEqual(s.methods(), ["set_customer"])

    def test_network_error_on_the_customer_retries_with_backoff(self):
        s = Setup(hofj=FakeHofJ(fail_at={"set_customer": [UpstreamError("502")]}))
        result = s.run()
        self.assertEqual((result.job.status, result.job.step, result.job.attempts, result.job.run_after),
                         (JobStatus.PENDING, 0, 1, NOW + timedelta(seconds=5)))

    def test_429_on_the_pax_waits_for_the_next_window_without_counting(self):
        s = Setup(hofj=FakeHofJ(fail_at={"set_pax": [QuotaError("429")]}))
        result = s.run()
        self.assertTrue(result.hit_429)
        self.assertEqual((result.job.status, result.job.step, result.job.attempts, result.job.run_after),
                         (JobStatus.PENDING, 1, 0, NEXT_WINDOW))


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
        proof = s.hofj.calls[-1][2]
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


class SmsConfirmedTest(unittest.TestCase):
    def sms_jobs(self, s):
        return [j for j in s.repos.jobs._jobs.values() if j.kind == JobKind.SMS_CONFIRMED]

    def test_confirmation_enqueues_one_sms(self):
        s = Setup()
        s.run()
        self.assertEqual([j.order_id for j in self.sms_jobs(s)], ["o1"])

    def test_second_run_on_confirmed_order_adds_nothing(self):
        s = Setup()
        s.run()
        s.run()
        self.assertEqual(len(self.sms_jobs(s)), 1)

    def test_failed_booking_enqueues_no_sms(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [ProductError("400")]}))
        s.run()
        self.assertEqual(self.sms_jobs(s), [])


if __name__ == "__main__":
    unittest.main()
