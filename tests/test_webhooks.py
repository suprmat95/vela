"""Webhook Stripe (RF-20, RF-21, RNF-03, RNF-07): firma, idempotenza, transizioni, errori."""
import hashlib
import hmac
import json
import time
import unittest
from datetime import timedelta

from fastapi.testclient import TestClient

from support import NOW, FakeHofJ, StubPayments, make_product
from vela.adapters.background import InlineRunner
from vela.adapters.repo_memory import MemoryRepositories
from vela.app import create_app
from vela.config import Settings
from vela.domain.models import OrderStatus, Participant, TravelerProfile
from vela.domain.usecases import Vela
from vela.ports.payments import to_cents
from vela.surfaces.webhooks import COMPLETED, EXPIRED, WEBHOOK_PATH

SECRET = "whsec_test_segreto"
INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


class RecordingRunner:
    def __init__(self):
        self.submitted = []

    def submit(self, order_id):
        self.submitted.append(order_id)

    def resume(self):
        return []

    def shutdown(self, wait=True):
        pass


def signed(event, secret=SECRET, at=None):
    payload = event if isinstance(event, str) else json.dumps(event)
    t = int(time.time() if at is None else at)
    sig = hmac.new(secret.encode(), ("%d.%s" % (t, payload)).encode(), hashlib.sha256).hexdigest()
    return payload, {"Stripe-Signature": "t=%d,v1=%s" % (t, sig), "Content-Type": "application/json"}


def session_event(order, type=COMPLETED, event_id="evt_1", **over):
    obj = {"id": "cs_test_1", "object": "checkout.session",
           "metadata": {"order_id": order.id, "itinerary_id": order.itinerary_id},
           "amount_total": to_cents(order.total), "currency": "eur", "payment_status": "paid",
           "payment_intent": "pi_test_1"}
    obj.update(over)
    return {"id": event_id, "object": "event", "type": type, "data": {"object": obj}}


class WebhookCase(unittest.TestCase):
    def make(self, secret=SECRET, with_domain=True, runner_factory=None):
        """`runner_factory(vela)` costruisce il runner; di default un RecordingRunner."""
        repos = MemoryRepositories()
        repos.products.upsert_many([make_product(3, price=350, country="ES", destination="Valencia")])
        self.hofj = FakeHofJ(code="R-654321")
        self.vela = Vela(repos, self.hofj, StubPayments(), now=Clock())
        self.runner = runner_factory(self.vela) if runner_factory else RecordingRunner()
        app = create_app(Settings(stripe_webhook_secret=secret),
                         vela=self.vela if with_domain else None, runner=self.runner)
        self.client = TestClient(app, raise_server_exceptions=False)

    def setUp(self):
        self.make()

    def new_order(self):
        iid = self.vela.create_intent(INTENT, FULL).intent_id
        proposal = self.vela.get_proposal(iid)
        return self.vela.repos.orders.get(self.vela.accept_proposal(proposal.proposal.id).order_id)

    def post(self, event, **kw):
        payload, headers = signed(event, **kw)
        return self.client.post(WEBHOOK_PATH, content=payload, headers=headers)

    def status(self, order):
        return self.vela.repos.orders.get(order.id).status


class CompletedTest(WebhookCase):
    def test_completed_marks_paid_and_submits_booking(self):
        order = self.new_order()
        r = self.post(session_event(order))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"received": True, "outcome": "paid"})
        saved = self.vela.repos.orders.get(order.id)
        self.assertEqual(saved.status, OrderStatus.PAID_PENDING_BOOKING)
        self.assertEqual(saved.payment_ref, "pi_test_1")
        self.assertEqual(self.runner.submitted, [order.id])

    def test_completed_with_inline_runner_confirms_with_code(self):
        self.make(runner_factory=lambda vela: InlineRunner(vela.orders))
        order = self.new_order()
        self.post(session_event(order))
        saved = self.vela.repos.orders.get(order.id)
        self.assertEqual((saved.status, saved.booking_code), (OrderStatus.CONFIRMED, "R-654321"))
        self.assertEqual(self.hofj.bookings, 1)

    def test_duplicate_event_has_no_effect(self):
        order = self.new_order()
        self.post(session_event(order))
        r = self.post(session_event(order))
        self.assertEqual(r.json()["outcome"], "duplicate")
        self.assertEqual(self.runner.submitted, [order.id])

    def test_second_event_for_paid_order_is_noop(self):
        order = self.new_order()
        self.post(session_event(order))
        r = self.post(session_event(order, event_id="evt_2"))
        self.assertEqual(r.json()["outcome"], "noop")
        self.assertEqual(self.runner.submitted, [order.id])

    def test_mismatches_are_not_applied(self):
        cases = {"amount": {"amount_total": 1}, "currency": {"currency": "usd"},
                 "unpaid": {"payment_status": "unpaid"}}
        for name, over in cases.items():
            with self.subTest(name):
                self.make()
                order = self.new_order()
                with self.assertLogs("vela.webhooks", "WARNING") as logs:
                    r = self.post(session_event(order, **over))
                self.assertEqual((r.status_code, r.json()["outcome"]), (200, "rejected"))
                self.assertEqual(self.status(order), OrderStatus.AWAITING_PAYMENT)
                self.assertEqual(self.runner.submitted, [])
                self.assertIn(order.id, logs.output[0])
                self.assertNotIn("anna@x.it", "\n".join(logs.output))
                self.assertEqual(self.post(session_event(order, **over)).json()["outcome"], "duplicate")

    def test_unknown_or_missing_order_is_rejected(self):
        order = self.new_order()
        for i, metadata in enumerate(({"order_id": "sconosciuto"}, {}, None)):
            with self.subTest(metadata=metadata), self.assertLogs("vela.webhooks", "WARNING"):
                r = self.post(session_event(order, event_id="evt_u%d" % i, metadata=metadata))
                self.assertEqual((r.status_code, r.json()["outcome"]), (200, "rejected"))
        self.assertEqual(self.status(order), OrderStatus.AWAITING_PAYMENT)


class ExpiredTest(WebhookCase):
    def test_expired_marks_order_expired(self):
        order = self.new_order()
        r = self.post(session_event(order, type=EXPIRED, payment_status="unpaid"))
        self.assertEqual(r.json()["outcome"], "expired")
        self.assertEqual(self.status(order), OrderStatus.EXPIRED)

    def test_expired_after_payment_is_noop(self):
        order = self.new_order()
        self.post(session_event(order))
        r = self.post(session_event(order, type=EXPIRED, event_id="evt_2"))
        self.assertEqual(r.json()["outcome"], "noop")
        self.assertEqual(self.status(order), OrderStatus.PAID_PENDING_BOOKING)


class SignatureTest(WebhookCase):
    def test_wrong_secret_is_400(self):
        order = self.new_order()
        r = self.post(session_event(order), secret="whsec_altro")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.status(order), OrderStatus.AWAITING_PAYMENT)

    def test_missing_signature_is_400(self):
        order = self.new_order()
        r = self.client.post(WEBHOOK_PATH, content=json.dumps(session_event(order)),
                             headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 400)

    def test_stale_timestamp_is_400(self):
        order = self.new_order()
        r = self.post(session_event(order), at=time.time() - 3600)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.status(order), OrderStatus.AWAITING_PAYMENT)

    def test_tampered_payload_is_400(self):
        order = self.new_order()
        payload, headers = signed(session_event(order))
        tampered = payload.replace('"paid"', '"paid" ')
        r = self.client.post(WEBHOOK_PATH, content=tampered, headers=headers)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.status(order), OrderStatus.AWAITING_PAYMENT)

    def test_signed_invalid_json_is_400(self):
        r = self.post("non json")
        self.assertEqual(r.status_code, 400)

    def test_event_without_id_is_400(self):
        r = self.post({"type": COMPLETED, "data": {"object": {}}})
        self.assertEqual(r.status_code, 400)

    def test_signature_is_never_echoed(self):
        order = self.new_order()
        r = self.post(session_event(order), secret="whsec_altro")
        self.assertNotIn("v1=", r.text)
        self.assertNotIn("whsec", r.text)


class OtherTest(WebhookCase):
    def test_unhandled_type_is_ignored_and_not_recorded(self):
        r = self.post({"id": "evt_x", "object": "event", "type": "payment_intent.succeeded",
                       "data": {"object": {}}})
        self.assertEqual(r.json(), {"received": True, "outcome": "ignored"})
        self.assertTrue(self.vela.repos.webhook_events.claim("evt_x", "t", NOW))

    def test_processing_error_releases_claim_and_returns_500(self):
        order = self.new_order()
        original = self.vela.orders.mark_paid

        def boom(*args, **kwargs):
            raise RuntimeError("db giù")
        self.vela.orders.mark_paid = boom
        with self.assertLogs("vela.webhooks", "ERROR"):
            r = self.post(session_event(order))
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("db giù", r.text)
        self.vela.orders.mark_paid = original
        r = self.post(session_event(order))
        self.assertEqual(r.json()["outcome"], "paid")
        self.assertEqual(self.runner.submitted, [order.id])

    def test_without_secret_is_503(self):
        self.make(secret=None)
        order = self.new_order()
        self.assertEqual(self.post(session_event(order)).status_code, 503)

    def test_without_domain_is_503(self):
        self.make(with_domain=False)
        r = self.post({"id": "evt_1", "type": COMPLETED, "data": {"object": {}}})
        self.assertEqual(r.status_code, 503)

    def test_no_bearer_token_needed(self):
        order = self.new_order()
        self.assertEqual(self.post(session_event(order)).status_code, 200)
