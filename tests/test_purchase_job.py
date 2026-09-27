"""Job d'acquisto a passi ripartibili (RF-46, RF-17, RF-33, RF-34, RF-38).

Ordini `queued` e job creati a mano: il job non passa dall'accettazione. Porte finte in memoria,
orologio fermo, finestra successiva passata esplicitamente.
"""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, FlakyPayments, StubPayments, make_product
from vela.adapters.hofj_router import SingleClientRouter
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain import say
from vela.domain.models import (Area, Criteria, Intent, Job, JobKind, JobStatus, NoMatch, Order,
                                OrderStatus, Participant, Period, Proposal, ProposalMade,
                                TravelerProfile)
from vela.domain.purchase import PurchaseJob, calls_needed
from vela.ports.hofj import ConfigError, ProductError, QuotaError, UpstreamError, UpstreamTimeout

NEXT_WINDOW = NOW + timedelta(seconds=45)
CRITERIA = Criteria("padel", Area("country", "Spagna", "ES"),
                    Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39 333", 2, (Participant("Bo", "Bi"),))


def fixed_now():
    return NOW


class Setup:
    """Un intento, una proposta sul prodotto 1, un ordine `queued` e il suo job d'acquisto."""

    def __init__(self, hofj=None, payments=None, products=None, language="it"):
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many(products or [
            make_product(1, price=350, destination="Valencia"),
            make_product(2, price=390, destination="Lanzarote")])
        criteria = replace(CRITERIA, language=language)
        self.repos.intents.add(Intent("i1", "padel", criteria, PROFILE, NOW))
        self.repos.proposals.add(Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2,
                                          Decimal("350"), "EUR", "Motivo.", NOW))
        self.repos.orders.add(Order("o1", "p1", "i1", "1", OrderStatus.QUEUED, 2, Decimal("350"),
                                    None, "EUR", PROFILE, NOW, NOW, enqueued_at=NOW, rooms=2))
        self.hofj = hofj or FakeHofJ()
        self.payments = payments or StubPayments()
        self.proposed = []
        ids = iter("new%d" % i for i in range(1, 100))
        self.job = PurchaseJob(self.repos, SingleClientRouter(self.hofj), self.payments, self.propose,
                               now=fixed_now, max_attempts=3)
        self.new_id = lambda: next(ids)
        self.repos.jobs.enqueue(Job("j1", JobKind.PURCHASE, "o1", JobStatus.PENDING, NOW, NOW))

    def propose(self, intent):
        """Stand-in di `Vela._propose`: la prossima proposta non rifiutata, o NoMatch."""
        self.proposed.append(intent.id)
        excluded = self.repos.rejections.product_ids_for_intent(intent.id)
        for product in self.repos.products.list_all():
            if product.id not in excluded and product.bookable:
                p = Proposal(self.new_id(), intent.id, product.id, date(2026, 10, 1),
                             date(2026, 10, 4), 2, product.price, "EUR", "Motivo.", NOW)
                self.repos.proposals.add(p)
                return ProposalMade(p, None, "proposta")
        return NoMatch(intent.id, "bookable", "niente")

    def running(self, step=0, attempts=0):
        j = replace(self.repos.jobs.get("j1"), status=JobStatus.RUNNING, locked_at=NOW, step=step,
                    attempts=attempts)
        self.repos.jobs.save(j)
        return j

    def run(self, step=0, attempts=0):
        return self.job.run(self.running(step, attempts), NEXT_WINDOW)

    def order(self):
        return self.repos.orders.get("o1")

    def saved_job(self):
        return self.repos.jobs.get("j1")

    def methods(self):
        return [c[0] for c in self.hofj.calls]


class CallsNeededTest(unittest.TestCase):
    def test_calls_needed_decreases_with_steps(self):
        base = Job("j", JobKind.PURCHASE, "o", JobStatus.RUNNING, NOW, NOW)
        self.assertEqual([calls_needed(replace(base, step=s)) for s in range(6)], [2, 1, 1, 1, 0, 0])


class HappyPathTest(unittest.TestCase):
    def test_steps_in_sequence_stop_at_the_actual_price(self):
        """Decisione 2026-09-26: dopo il totale l'ordine aspetta la conferma, niente link."""
        s = Setup(hofj=FakeHofJ(total=Decimal("720")))
        result = s.run()
        self.assertEqual(s.methods(), ["create_itinerary", "get_itinerary"])   # M19
        order = s.order()
        self.assertEqual(order.status, OrderStatus.AWAITING_CONFIRMATION)
        self.assertEqual((order.itinerary_id, order.total, order.currency), ("it-1", Decimal("720"), "EUR"))
        self.assertEqual((order.payment_url, s.payments.links), (None, []))
        self.assertEqual((result.job.status, result.job.step), (JobStatus.DONE, 4))
        self.assertEqual(s.saved_job(), result.job)
        self.assertFalse(result.hit_429)
        self.assertFalse(any(j.kind in (JobKind.SMS_LINK, JobKind.PAYMENT_CHECK)
                             for j in s.repos.jobs._jobs.values()))

    def test_confirmed_order_resumes_at_the_link(self):
        s = Setup(hofj=FakeHofJ(total=Decimal("720")))
        s.run()
        s.repos.orders.save(replace(s.order(), status=OrderStatus.QUEUED))   # la conferma
        s.hofj.calls.clear()
        result = s.run(step=4)
        self.assertEqual(s.methods(), [])
        order = s.order()
        self.assertEqual(order.status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual((order.payment_url, order.payment_ref, order.total),
                         ("http://pay.test/o1", "pi_o1", Decimal("720")))
        self.assertEqual(s.payments.descriptions, ["Padel a Valencia 1"])
        self.assertEqual((result.job.status, result.job.step), (JobStatus.DONE, 5))

    def test_customer_and_pax_wait_for_the_booking(self):
        """M19: cliente e passeggeri passano nel job di prenotazione, dopo il pagamento."""
        s = Setup()
        s.run()
        s.run(step=4)
        self.assertEqual(s.hofj.customers, {})
        self.assertEqual([p.first_name for p in s.hofj.pax["it-1"]], [None, None])
        self.assertNotIn("set_pax", s.methods())

    def test_itinerary_request_uses_the_proposal_and_the_rooms_of_the_order(self):
        """RF-14, RF-67 (M21-D): le camere dell'ordine, non più 1 fisso."""
        s = Setup()
        s.run()
        self.assertEqual(s.hofj.calls[0], ("create_itinerary", "1", date(2026, 10, 1), 2, 2, "EUR"))

    def test_success_reenables_unbookable_product(self):
        stale = replace(make_product(1, price=350), bookable=False,
                        bookable_checked_at=NOW - timedelta(hours=30))
        s = Setup(products=[stale])
        s.run()
        p = s.repos.products.get("1")
        self.assertEqual((p.bookable, p.bookable_checked_at), (True, NOW))


class ResumeTest(unittest.TestCase):
    def test_each_step_is_saved_before_the_next(self):
        s = Setup(hofj=FakeHofJ(fail_at={"get_itinerary": [UpstreamError("timeout")]}))
        s.run()
        self.assertEqual(s.order().itinerary_id, "it-1")
        self.assertEqual(s.saved_job().step, 3)   # M19: dall'itinerario si salta al totale
        self.assertEqual(s.order().status, OrderStatus.QUEUED)

    def test_job_from_before_m19_at_customer_or_pax_goes_to_the_total(self):
        """Un job salvato dal codice di prima al passo 1 o 2 non chiama più cliente e pax."""
        for step in (1, 2):
            s = Setup()
            s.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
            s.repos.orders.save(replace(s.order(), itinerary_id="it-1"))
            s.hofj.calls.clear()
            result = s.run(step=step)
            self.assertEqual(s.methods(), ["get_itinerary"], step)
            self.assertEqual(s.order().status, OrderStatus.AWAITING_CONFIRMATION)
            self.assertEqual(result.job.step, 4)

    def test_resume_at_total_reads_only_the_total(self):
        s = Setup()
        s.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        s.repos.orders.save(replace(s.order(), itinerary_id="it-1"))
        s.hofj.calls.clear()
        s.run(step=3)
        self.assertEqual(s.methods(), ["get_itinerary"])

    def test_resume_at_link_calls_no_hofj(self):
        s = Setup()
        s.repos.orders.save(replace(s.order(), itinerary_id="it-1", total=Decimal("700")))
        s.run(step=4)
        self.assertEqual(s.methods(), [])
        self.assertEqual(s.order().status, OrderStatus.AWAITING_PAYMENT)


class RetryTest(unittest.TestCase):
    def test_network_error_retries_next_window(self):
        s = Setup(hofj=FakeHofJ(fail_at={"get_itinerary": [UpstreamError("timeout")]}))
        result = s.run()
        job = result.job
        self.assertEqual((job.status, job.attempts, job.run_after, job.step),
                         (JobStatus.PENDING, 1, NEXT_WINDOW, 3))
        self.assertIn("timeout", job.last_error)
        self.assertIsNone(job.locked_at)
        self.assertEqual(s.saved_job(), job)
        self.assertEqual(s.order().status, OrderStatus.QUEUED)

    def test_itinerary_timeout_counts_an_orphan_and_retries(self):
        """M18: HofJ può aver creato l'itinerario; il nuovo tentativo ne crea un altro."""
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [UpstreamTimeout("timeout")]}))
        with self.assertLogs("vela.purchase", "WARNING") as logs:
            s.run()
        self.assertEqual(s.order().orphan_itineraries, 1)
        self.assertIn("orphan_itinerary order_id=o1", logs.output[0])
        job = s.saved_job()
        self.assertEqual((job.status, job.step, job.attempts, job.run_after),
                         (JobStatus.PENDING, 0, 1, NEXT_WINDOW))
        s.run(attempts=1)
        self.assertEqual(s.order().status, OrderStatus.AWAITING_CONFIRMATION)
        self.assertEqual(s.order().orphan_itineraries, 1)

    def test_timeout_after_the_itinerary_is_not_an_orphan(self):
        s = Setup(hofj=FakeHofJ(fail_at={"get_itinerary": [UpstreamTimeout("timeout")]}))
        s.run()
        self.assertEqual(s.order().orphan_itineraries, 0)

    def test_network_error_on_the_itinerary_is_not_an_orphan(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [UpstreamError("rete")]}))
        s.run()
        self.assertEqual(s.order().orphan_itineraries, 0)

    def test_third_network_failure_fails_the_order_with_a_readable_reason(self):
        s = Setup(hofj=FakeHofJ(fail_at={"get_itinerary": [UpstreamError("502")]}))
        s.repos.orders.save(replace(s.order(), itinerary_id="it-1"))
        s.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        result = s.run(step=3, attempts=2)
        self.assertEqual(result.job.status, JobStatus.DEAD)
        order = s.order()
        self.assertEqual(order.status, OrderStatus.FAILED)
        self.assertEqual(order.failure_reason, say.failure_reason("upstream"))

    def test_failure_reason_follows_the_intent_language(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [UpstreamError("x")]}), language="en")
        s.run(attempts=2)
        self.assertEqual(s.order().failure_reason, say.failure_reason("upstream", "en"))

    def test_quota_error_reschedules_without_counting_an_attempt(self):
        s = Setup(hofj=FakeHofJ(fail_at={"get_itinerary": [QuotaError("429")]}))
        result = s.run(attempts=1)
        self.assertTrue(result.hit_429)
        self.assertEqual((result.job.status, result.job.attempts, result.job.run_after, result.job.step),
                         (JobStatus.PENDING, 1, NEXT_WINDOW, 3))

    def test_payments_error_retries_then_fails(self):
        s = Setup(payments=FlakyPayments(failures=5))
        s.repos.orders.save(replace(s.order(), itinerary_id="it-1", total=Decimal("700")))
        first = s.run(step=4)
        self.assertEqual((first.job.status, first.job.attempts), (JobStatus.PENDING, 1))
        s.run(step=4, attempts=2)
        self.assertEqual(s.order().status, OrderStatus.FAILED)
        self.assertEqual(s.order().failure_reason, say.failure_reason("payments"))


class ProductErrorTest(unittest.TestCase):
    def test_product_error_marks_unbookable_and_replaces(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [ProductError("404 upstream")]}))
        result = s.run()
        product = s.repos.products.get("1")
        self.assertEqual((product.bookable, product.bookable_checked_at), (False, NOW))
        order = s.order()
        self.assertEqual(order.status, OrderStatus.REPLACED)
        replacement = s.repos.proposals.get(order.replacement_proposal_id)
        self.assertEqual(replacement.product_id, "2")
        self.assertIn("p1", s.repos.rejections.proposal_ids_for_intent("i1"))
        self.assertEqual(result.job.status, JobStatus.DONE)
        self.assertEqual(s.methods(), ["create_itinerary"])

    def test_product_error_without_alternative_fails_with_no_match_reason(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [ProductError("404")]}),
                  products=[make_product(1, price=350)])
        s.run()
        order = s.order()
        self.assertEqual(order.status, OrderStatus.FAILED)
        self.assertEqual(order.failure_reason, say.failure_reason("no_alternative"))
        self.assertIsNone(order.replacement_proposal_id)

    def test_product_error_after_the_itinerary_is_treated_as_network(self):
        s = Setup(hofj=FakeHofJ(fail_at={"get_itinerary": [ProductError("strano")]}))
        result = s.run()
        self.assertEqual((result.job.status, result.job.attempts), (JobStatus.PENDING, 1))
        self.assertTrue(s.repos.products.get("1").bookable)

    def test_config_error_fails_without_marking_product(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [ConfigError("403")]}))
        result = s.run()
        self.assertEqual(result.job.status, JobStatus.DEAD)
        self.assertEqual(s.order().status, OrderStatus.FAILED)
        self.assertEqual(s.order().failure_reason, say.failure_reason("config"))
        self.assertTrue(s.repos.products.get("1").bookable)
        self.assertEqual(s.proposed, [])


class CancelledTest(unittest.TestCase):
    def test_cancelled_order_stops_job_without_calls(self):
        s = Setup()
        s.repos.orders.save(replace(s.order(), status=OrderStatus.CANCELLED))
        result = s.run()
        self.assertEqual(s.methods(), [])
        self.assertEqual(result.job.status, JobStatus.DONE)

    def test_cancelled_between_steps_stops_before_the_next(self):
        s = Setup()
        save = s.repos.orders.save

        def cancel_after_the_itinerary(order):   # la rinuncia arriva tra il passo 0 e il 3
            save(order)
            if order.itinerary_id and order.status == OrderStatus.QUEUED:
                save(replace(order, status=OrderStatus.CANCELLED))

        s.repos.orders.save = cancel_after_the_itinerary
        result = s.run()
        self.assertEqual(s.methods(), ["create_itinerary"])
        self.assertEqual(result.job.status, JobStatus.DONE)
        self.assertEqual(s.order().status, OrderStatus.CANCELLED)
        self.assertEqual(s.payments.links, [])


class SmsLinkTest(unittest.TestCase):
    def test_link_step_enqueues_one_sms_link(self):
        s = Setup()
        s.repos.orders.save(replace(s.order(), itinerary_id="it-1", total=Decimal("700")))
        j = replace(s.repos.jobs.get("j1"), status=JobStatus.RUNNING, locked_at=NOW, step=4)
        s.job.run(j, NEXT_WINDOW)
        self.assertEqual(s.repos.orders.get("o1").status, OrderStatus.AWAITING_PAYMENT)
        sms = [j for j in s.repos.jobs._jobs.values() if j.kind == JobKind.SMS_LINK]
        self.assertEqual([(j.order_id, j.status) for j in sms], [("o1", JobStatus.PENDING)])

    def test_failed_purchase_enqueues_no_sms(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [ConfigError("401")]}))
        j = replace(s.repos.jobs.get("j1"), status=JobStatus.RUNNING, locked_at=NOW)
        s.job.run(j, NEXT_WINDOW)
        self.assertFalse(any(j.kind == JobKind.SMS_LINK for j in s.repos.jobs._jobs.values()))


if __name__ == "__main__":
    unittest.main()
