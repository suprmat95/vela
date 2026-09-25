import unittest
from datetime import timedelta
from decimal import Decimal

from support import NOW, FakeHofJ
from vela.adapters.background import BookingRunner, InlineRunner
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.models import Order, OrderStatus, TravelerProfile
from vela.domain.orders import NotFound, OrderService
from vela.ports.hofj import UpstreamError


def order(oid="o1", status=OrderStatus.AWAITING_PAYMENT):
    return Order(oid, "p-" + oid, "i1", "1", status, 2, Decimal("500"), Decimal("1000"), "EUR",
                 TravelerProfile(), NOW, NOW, itinerary_id="it-1", payment_url="http://x/" + oid,
                 payment_ref="pi_replay_" + oid)


def service(*orders, hofj=None):
    repos = MemoryRepositories()
    for o in orders:
        repos.orders.add(o)
    return OrderService(repos, hofj or FakeHofJ(code="R-123456"), now=lambda: NOW + timedelta(minutes=1))


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


class CompleteBookingTest(unittest.TestCase):
    def test_confirms_with_code(self):
        hofj = FakeHofJ(code="R-654321")
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING), hofj=hofj)
        o = s.complete_booking("o1")
        self.assertEqual((o.status, o.booking_code), (OrderStatus.CONFIRMED, "R-654321"))
        self.assertEqual(hofj.calls[-1][1], "it-1")
        self.assertEqual(hofj.calls[-1][2].payment_intent_id, "pi_replay_o1")
        self.assertEqual(hofj.calls[-1][2].payment_type, "full")

    def test_not_paid_is_untouched_and_no_call(self):
        hofj = FakeHofJ()
        s = service(order(), hofj=hofj)
        self.assertEqual(s.complete_booking("o1").status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(hofj.calls, [])

    def test_confirmed_is_not_booked_twice(self):
        hofj = FakeHofJ()
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING), hofj=hofj)
        s.complete_booking("o1")
        s.complete_booking("o1")
        self.assertEqual(hofj.bookings, 1)

    def test_failure_is_recorded(self):
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING),
                    hofj=FakeHofJ(fail_booking=UpstreamError("timeout")))
        o = s.complete_booking("o1")
        self.assertEqual((o.status, o.failure_reason), (OrderStatus.BOOKING_FAILED, "timeout"))

    def test_pending_ids(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), order("b"),
                    order("c", OrderStatus.PAID_PENDING_BOOKING))
        self.assertEqual(s.pending_booking_ids(), ["a", "c"])


class RunnerTest(unittest.TestCase):
    def test_inline_runner_resume(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), order("b"))
        self.assertEqual(InlineRunner(s).resume(), ["a"])
        self.assertEqual(s.get("a").status, OrderStatus.CONFIRMED)
        self.assertEqual(s.get("b").status, OrderStatus.AWAITING_PAYMENT)

    def test_thread_runner_submit_and_resume(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING),
                    order("b", OrderStatus.PAID_PENDING_BOOKING), order("c"))
        runner = BookingRunner(s)
        self.assertEqual(runner.resume(), ["a", "b"])
        runner.submit("c")
        runner.shutdown(wait=True)
        self.assertEqual([s.get(i).status for i in "abc"],
                         [OrderStatus.CONFIRMED, OrderStatus.CONFIRMED, OrderStatus.AWAITING_PAYMENT])

    def test_thread_runner_swallows_unexpected_errors(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), hofj=FakeHofJ(fail_booking=RuntimeError("boom")))
        runner = BookingRunner(s)
        with self.assertLogs("vela.booking", "ERROR") as logs:
            runner.submit("a")
            runner.shutdown(wait=True)
        self.assertIn("a", logs.output[0])
        self.assertEqual(s.get("a").status, OrderStatus.PAID_PENDING_BOOKING)   # riprovato al prossimo avvio
