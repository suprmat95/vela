"""La coda sotto carico, in replay (twist, RF-45..51): attesa dichiarata, mai errori di quota.

HofJ replay con la quota vera (120/min, finestra fissa ancorata alla prima chiamata), repository
in memoria, orologio manuale che avanza di un secondo per giro; il worker gira con `drain`.
Vela esce dal token bucket di M18: B = 8, 100 gettoni/min, attesa dichiarata su 16 acquisti/min.
"""
import unittest
from datetime import timedelta

from support import NOW, FakeHofJ
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import build_worker
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import JobKind, JobStatus, OrderQueued, OrderStatus, Participant, TravelerProfile
from vela.domain.usecases import Vela
from vela.ports.hofj import ProductError

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, seconds=1):
        self.at += timedelta(seconds=seconds)


class Launch:
    def __init__(self, hofj=None, repos=None, clock=None):
        self.clock = clock or Clock()
        self.hofj = hofj or ReplayHofJ(limit=120, now=self.clock)
        self.repos = repos or MemoryRepositories()
        if self.repos.products.count() == 0:
            self.repos.products.upsert_many(ReplayHofJ().load_catalog())
        self.vela = Vela(self.repos, self.hofj, FakePayments("http://test", now=self.clock),
                         DEFAULT_TRAVELER, now=self.clock)
        self.worker = build_worker(self.vela, Settings(worker_concurrency=0))
        self.worker.processor.refresh_quota()          # il boot

    def accept(self, n=1):
        """`n` viaggiatori che accettano uno dopo l'altro, a 50 ms di distanza."""
        out = []
        for _ in range(n):
            iid = self.vela.create_intent(INTENT, FULL).intent_id
            out.append(self.vela.accept_proposal(self.vela.get_proposal(iid).proposal.id))
            self.clock.at += timedelta(milliseconds=50)
        return out

    def run(self, until, max_seconds=3600, watch=None):
        for _ in range(max_seconds):
            self.worker.drain()
            if watch:
                watch()
            if until():
                return
            self.clock.advance()
        raise AssertionError("condizione non raggiunta in %d secondi simulati" % max_seconds)

    def statuses(self, orders):
        return [self.repos.orders.get(o.order_id).status for o in orders]


class LaunchBurstTest(unittest.TestCase):
    def test_two_hundred_accepts_all_queued_with_growing_wait(self):
        w = Launch()
        accepted = w.accept(200)
        self.assertTrue(all(isinstance(a, OrderQueued) for a in accepted))
        waits = [a.wait_seconds for a in accepted]
        self.assertEqual(waits, sorted(waits))
        self.assertEqual((accepted[0].position, accepted[-1].position), (1, 200))
        self.assertEqual(accepted[-1].wait_seconds, 750)      # 200 × 60 ÷ 16 (M18)
        self.assertIn("13 minuti", accepted[-1].say)
        self.assertEqual(w.hofj._used, 1)                     # solo la lettura della quota al boot

    def test_throughput_never_exceeds_effective_limit_per_window(self):
        w = Launch()
        orders = w.accept(200)
        peak = []

        def watch():
            peak.append(w.hofj._used)

        w.run(lambda: all(s == OrderStatus.AWAITING_PAYMENT for s in w.statuses(orders)), watch=watch)
        self.assertLessEqual(max(peak), 108)
        errors = [j.last_error for j in w.repos.jobs._jobs.values() if j.last_error]
        self.assertEqual([e for e in errors if "QuotaError" in e], [])
        minutes = (w.clock() - NOW).total_seconds() / 60
        self.assertLess(minutes, 11)                           # ~200 ÷ 20 acquisti/min senza booking

    def test_declared_wait_is_prudent_and_close_to_the_real_one(self):
        """RF-48 con la soglia di M18: l'attesa conta l'80% del ritmo, quindi senza prenotazioni
        l'acquisto arriva prima di quanto detto, ma non molto prima."""
        w = Launch()
        orders = w.accept(100)
        last = orders[-1]
        w.run(lambda: w.repos.orders.get(last.order_id).status == OrderStatus.AWAITING_PAYMENT)
        real = (w.clock() - NOW).total_seconds()
        self.assertLessEqual(real, last.wait_seconds)
        self.assertGreaterEqual(real, 0.75 * last.wait_seconds)

    def test_paid_order_booked_within_next_window(self):
        """RF-51: con 150 acquisti in coda la prenotazione usa la riserva e non aspetta la coda."""
        w = Launch()
        first = w.accept(1)[0]
        w.run(lambda: w.repos.orders.get(first.order_id).status == OrderStatus.AWAITING_PAYMENT)
        w.accept(150)
        order = w.repos.orders.get(first.order_id)
        w.vela.orders.settle_payment(order.id, w.vela.payments.pay(order))
        paid_at = w.clock()
        w.run(lambda: w.repos.orders.get(first.order_id).status == OrderStatus.CONFIRMED)
        self.assertLessEqual((w.clock() - paid_at).total_seconds(), 60)
        queued = [o for o in w.repos.orders._items.values() if o.status == OrderStatus.QUEUED]
        self.assertGreater(len(queued), 100)                   # la coda degli acquisti è ancora lì


class EndToEndTest(unittest.TestCase):
    def test_replacement_flow_end_to_end(self):
        hofj = FakeHofJ(fail_at={"create_itinerary": [ProductError("404 upstream")]})
        w = Launch(hofj=hofj)
        first = w.accept(1)[0]
        w.worker.drain()
        status = w.vela.get_order_status(first.order_id)
        self.assertEqual(status.status, OrderStatus.REPLACED)
        replacement = status.proposal.proposal.id
        again = w.vela.accept_proposal(replacement)
        self.assertEqual(again.position, 1)
        w.clock.advance(5)                                     # il bucket si riempie di nuovo
        w.worker.drain()
        final = w.vela.get_order_status(again.order_id)
        self.assertEqual(final.status, OrderStatus.AWAITING_PAYMENT)
        self.assertNotEqual(final.order_id, first.order_id)

    def test_restart_mid_job_resumes_without_new_itinerary(self):
        """RF-27: il processo muore a metà acquisto; un'altra istanza riprende dopo il lease."""
        hofj = FakeHofJ(fail_at={"set_pax": [RuntimeError("processo ucciso")]})
        w = Launch(hofj=hofj)
        order = w.accept(1)[0]
        with self.assertRaises(RuntimeError):
            w.worker.processor.run_once()
        job = w.repos.jobs.active_for_order(order.order_id, JobKind.PURCHASE)
        self.assertEqual((job.status, job.step), (JobStatus.RUNNING, 2))
        restarted = Launch(hofj=hofj, repos=w.repos, clock=Clock(w.clock() + timedelta(minutes=3)))
        restarted.worker.drain()
        self.assertEqual(restarted.repos.orders.get(order.order_id).status, OrderStatus.AWAITING_PAYMENT)
        created = [c for c in hofj.calls if c[0] == "create_itinerary"]
        self.assertEqual(len(created), 1)


if __name__ == "__main__":
    unittest.main()
