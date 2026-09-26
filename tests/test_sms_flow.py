"""Flusso completo in replay con gli SMS finti: due messaggi, nell'ordine, mai doppioni."""
import unittest
from datetime import timedelta

from support import NOW
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.sms_fake import FakeSms
from vela.adapters.stripe_fake import FakePayments
from vela.app import build_worker
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import OrderStatus, Participant, TravelerProfile
from vela.domain.usecases import Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
TRAVELER = TravelerProfile("Anna", "Rossi", "anna@x.it", "333 123 4567",
                           participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at


class Flow:
    """FakeSms sta al posto di Twilio: la Vela nasce con `sms_enabled=True` come in produzione."""

    def __init__(self, traveler=TRAVELER, sms_enabled=True):
        self.clock = Clock()
        self.repos = MemoryRepositories()
        hofj = ReplayHofJ(now=self.clock)
        self.repos.products.upsert_many(hofj.load_catalog())
        self.payments = FakePayments("http://test", now=self.clock)
        self.vela = Vela(self.repos, hofj, self.payments, DEFAULT_TRAVELER, now=self.clock,
                         sms_enabled=sms_enabled)
        self.sms = FakeSms()
        self.worker = build_worker(self.vela, Settings(worker_concurrency=0), notifier=self.sms)
        self.worker.processor.refresh_quota()
        self.traveler = traveler

    def accept(self):
        iid = self.vela.create_intent(INTENT, self.traveler).intent_id
        return self.vela.accept_proposal(self.vela.get_proposal(iid).proposal.id)

    def run_until(self, order_id, status, max_seconds=900):
        for _ in range(max_seconds):
            self.worker.drain()
            if self.repos.orders.get(order_id).status == status:
                return self.repos.orders.get(order_id)
            self.clock.at += timedelta(seconds=1)
        raise AssertionError("ordine non %s in %d secondi simulati" % (status.value, max_seconds))


class SmsFlowTest(unittest.TestCase):
    def test_link_then_confirmation_exactly_once(self):
        f = Flow()
        order_id = f.accept().order_id
        order = f.run_until(order_id, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(len(f.sms.sent), 1)
        to, body = f.sms.sent[0]
        self.assertEqual(to, "+393331234567")
        self.assertIn(order.payment_url, body)
        for _ in range(3):                                   # il viaggiatore chiede lo stato
            f.vela.get_order_status(order_id)
            f.worker.drain()
        f.payments.pay(order)
        order = f.run_until(order_id, OrderStatus.CONFIRMED)
        f.worker.drain()
        self.assertEqual(len(f.sms.sent), 2)
        self.assertTrue(f.sms.sent[1][1].startswith("Vela: prenotazione confermata!"))
        self.assertIn(order.booking_code, f.sms.sent[1][1])

    def test_invalid_phone_books_without_sms(self):
        f = Flow(TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000",
                                 participants=(Participant("Bo", "Bi"),)))
        order_id = f.accept().order_id
        order = f.run_until(order_id, OrderStatus.AWAITING_PAYMENT)
        f.payments.pay(order)
        f.run_until(order_id, OrderStatus.CONFIRMED)
        self.assertEqual(f.sms.sent, [])


class AgentPhraseTest(unittest.TestCase):
    def test_accept_announces_the_sms_with_the_last_digits(self):
        queued = Flow().accept()
        self.assertIn("SMS al numero che finisce con 4567", queued.say)

    def test_status_while_awaiting_payment_mentions_the_sms(self):
        f = Flow()
        order_id = f.accept().order_id
        f.run_until(order_id, OrderStatus.AWAITING_PAYMENT)
        self.assertIn("anche per SMS", f.vela.get_order_status(order_id).say)

    def test_invalid_phone_keeps_todays_phrase(self):
        f = Flow(TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000",
                                 participants=(Participant("Bo", "Bi"),)))
        self.assertNotIn("SMS", f.accept().say)

    def test_sms_disabled_keeps_todays_phrases_even_with_a_valid_phone(self):
        f = Flow(sms_enabled=False)
        queued = f.accept()
        self.assertNotIn("SMS", queued.say)
        self.assertIn("Chiedimi a che punto è quando vuoi", queued.say)
        self.assertNotIn("SMS", f.vela.get_order_status(queued.order_id).say)
        f.run_until(queued.order_id, OrderStatus.AWAITING_PAYMENT)
        awaiting = f.vela.get_order_status(queued.order_id).say
        self.assertNotIn("SMS", awaiting)
        self.assertTrue(awaiting.endswith("usa il link che ti ho mandato."), awaiting)


if __name__ == "__main__":
    unittest.main()
