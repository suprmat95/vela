import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from support import NOW, FakeHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.models import JobKind, Order, OrderStatus, TravelerProfile
from vela.domain.orders import NotFound, OrderService


def order(oid="o1", status=OrderStatus.AWAITING_PAYMENT):
    return Order(oid, "p-" + oid, "i1", "1", status, 2, Decimal("500"), Decimal("1000"), "EUR",
                 TravelerProfile(), NOW, NOW, itinerary_id="it-1", payment_url="http://x/" + oid,
                 payment_ref="pi_replay_" + oid)


def service(*orders, hofj=None):
    repos = MemoryRepositories()
    for o in orders:
        repos.orders.add(o)
    ids = iter("job%d" % i for i in range(1, 100))
    return OrderService(repos, hofj or FakeHofJ(code="R-123456"), now=lambda: NOW + timedelta(minutes=1),
                        new_id=lambda: next(ids))


class MarkPaidTest(unittest.TestCase):
    def test_awaiting_becomes_paid_pending_booking(self):
        s = service(order())
        o = s.mark_paid("o1", "pi_real")
        self.assertEqual(o.status, OrderStatus.PAID_PENDING_BOOKING)
        self.assertEqual(o.payment_ref, "pi_real")
        self.assertEqual(o.paid_at, NOW + timedelta(minutes=1))
        self.assertEqual(s.repos.orders.get("o1"), o)

    def test_second_call_is_noop(self):
        s = service(order())
        first = s.mark_paid("o1", "pi_1")
        self.assertEqual(s.mark_paid("o1", "pi_2"), first)

    def test_other_states_untouched(self):
        s = service(order(status=OrderStatus.CONFIRMED))
        self.assertEqual(s.mark_paid("o1", "pi").status, OrderStatus.CONFIRMED)

    def test_unknown(self):
        with self.assertRaises(NotFound):
            service().mark_paid("nope", "pi")


    def test_mark_paid_enqueues_booking_once(self):
        from vela.domain.models import JobKind, JobStatus
        s = service(order())
        s.mark_paid("o1", "pi_1")
        s.mark_paid("o1", "pi_1")
        job = s.repos.jobs.active_for_order("o1", JobKind.BOOKING)
        self.assertEqual((job.id, job.status, job.run_after, job.enqueued_at),
                         ("job1", JobStatus.PENDING, NOW + timedelta(minutes=1), NOW + timedelta(minutes=1)))
        self.assertIsNone(s.repos.jobs.get("job2"))

    def test_mark_paid_on_cancelled_order_is_ignored(self):
        from vela.domain.models import JobKind
        s = service(order(status=OrderStatus.CANCELLED))
        self.assertEqual(s.mark_paid("o1", "pi").status, OrderStatus.CANCELLED)
        self.assertIsNone(s.repos.jobs.active_for_order("o1", JobKind.BOOKING))

    def test_enqueue_booking_for_paid_order_without_job(self):
        """RF-27: al boot un ordine pagato senza job attivo riceve il suo job di prenotazione."""
        from vela.domain.models import JobKind
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING), order("o2"))
        self.assertEqual(s.resume_bookings(), ["o1"])
        self.assertEqual(s.resume_bookings(), [])
        self.assertIsNotNone(s.repos.jobs.active_for_order("o1", JobKind.BOOKING))

class ConcurrentPaymentTest(unittest.TestCase):
    """Checkout e verifica del pagamento che leggono l'ordine insieme (M13b, `task/booking-race`):
    la seconda lettura è vecchia, ma il passaggio di stato atomico la ferma."""

    def test_stale_mark_paid_enqueues_no_second_booking(self):
        s = service(order())
        stale = s.repos.orders.get("o1")
        first = s.mark_paid("o1", "pi_1")
        with patch.object(s.repos.orders, "get", return_value=stale), \
                patch.object(s.repos.jobs, "active_for_order", return_value=None):
            s.mark_paid("o1", "pi_2")
        self.assertIsNone(s.repos.jobs.get("job2"))
        self.assertEqual(s.repos.orders.get("o1"), first)

    def test_stale_expire_does_not_undo_a_payment(self):
        s = service(order())
        stale = s.repos.orders.get("o1")
        paid = s.mark_paid("o1", "pi_1")
        with patch.object(s.repos.orders, "get", return_value=stale):
            s.expire("o1")
        self.assertEqual(s.repos.orders.get("o1"), paid)

    def test_resume_bookings_skips_a_job_enqueued_meanwhile(self):
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING))
        self.assertEqual(s.resume_bookings(), ["o1"])
        with patch.object(s.repos.jobs, "active_for_order", return_value=None):
            self.assertEqual(s.resume_bookings(), [])
        self.assertEqual(s.repos.jobs.active_for_order("o1", JobKind.BOOKING).id, "job1")


class ExpireTest(unittest.TestCase):
    def test_awaiting_becomes_expired(self):
        s = service(order())
        o = s.expire("o1")
        self.assertEqual(o.status, OrderStatus.EXPIRED)
        self.assertEqual(o.updated_at, NOW + timedelta(minutes=1))
        self.assertEqual(s.get("o1").status, OrderStatus.EXPIRED)

    def test_second_call_is_noop(self):
        s = service(order())
        first = s.expire("o1")
        self.assertEqual(s.expire("o1"), first)

    def test_paid_or_confirmed_orders_never_expire(self):
        for status in (OrderStatus.PAID_PENDING_BOOKING, OrderStatus.CONFIRMED,
                       OrderStatus.BOOKING_FAILED):
            with self.subTest(status):
                s = service(order(status=status))
                self.assertEqual(s.expire("o1").status, status)

    def test_unknown(self):
        with self.assertRaises(NotFound):
            service().expire("nope")


class PendingBookingsTest(unittest.TestCase):
    def test_pending_ids(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), order("b"),
                    order("c", OrderStatus.PAID_PENDING_BOOKING))
        self.assertEqual(s.pending_booking_ids(), ["a", "c"])
