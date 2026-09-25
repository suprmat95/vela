"""Adapter Stripe (RF-18, RF-21, RF-22): parametri della Checkout Session con un client finto, mai la rete."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import stripe

from support import NOW
from vela.adapters.stripe_links import StripePayments, build_stripe_client
from vela.domain.models import Order, OrderStatus, TravelerProfile
from vela.ports.payments import LinkStatus, PaymentsError


class FakeSessions:
    def __init__(self, error=None, retrieved=None):
        self.calls = []
        self.error = error
        self.retrieved = retrieved
        self.retrieve_calls = []

    def retrieve(self, session_id, params=None, options=None):
        self.retrieve_calls.append(session_id)
        if self.error:
            raise self.error
        return self.retrieved

    def create(self, params=None, options=None):
        self.calls.append((params, options))
        if self.error:
            raise self.error
        return SimpleNamespace(id="cs_test_1", url="https://checkout.stripe.com/c/pay/cs_test_1")


def fake_client(sessions):
    return SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=sessions)))


def order(total="799.90", currency="EUR"):
    return Order("o1", "p1", "i1", "1", OrderStatus.AWAITING_PAYMENT, 2, Decimal("400"),
                 Decimal(total), currency, TravelerProfile(email="anna@x.it"), NOW, NOW,
                 itinerary_id="it-9")


class StripePaymentsTest(unittest.TestCase):
    def setUp(self):
        self.sessions = FakeSessions()
        self.payments = StripePayments(fake_client(self.sessions), "https://vela.test/")

    def test_session_params(self):
        link = self.payments.create_payment_link(order(), "Padel a Lanzarote")
        params, options = self.sessions.calls[0]
        self.assertEqual(params["mode"], "payment")
        self.assertEqual(params["payment_method_types"], ["card"])
        self.assertEqual(params["line_items"], [{"quantity": 1, "price_data": {
            "currency": "eur", "unit_amount": 79990,
            "product_data": {"name": "Padel a Lanzarote"}}}])
        self.assertEqual(params["metadata"], {"order_id": "o1", "itinerary_id": "it-9"})
        self.assertEqual(params["payment_intent_data"], {"metadata": {
            "order_id": "o1", "itinerary_id": "it-9", "checkoutRefId": "it-9"}})
        self.assertEqual(params["client_reference_id"], "o1")
        self.assertEqual(params["success_url"], "https://vela.test/checkout/success")
        self.assertEqual(params["cancel_url"], "https://vela.test/checkout/cancel")
        self.assertEqual(options, {"idempotency_key": "vela-order-o1"})
        self.assertEqual((link.url, link.reference),
                         ("https://checkout.stripe.com/c/pay/cs_test_1", "cs_test_1"))

    def test_expiry_is_just_under_24_hours_from_the_order(self):
        # NOW = 2026-09-25 12:00 UTC; scadenza 23 h 59 min dopo.
        expected = datetime(2026, 9, 26, 11, 59, tzinfo=timezone.utc)
        link = self.payments.create_payment_link(order(), "Padel")
        params, _ = self.sessions.calls[0]
        self.assertEqual(params["expires_at"], int(expected.timestamp()))
        self.assertEqual(link.expires_at, expected)

    def test_params_are_deterministic_for_idempotency(self):
        self.payments.create_payment_link(order(), "Padel")
        self.payments.create_payment_link(order(), "Padel")
        self.assertEqual(self.sessions.calls[0], self.sessions.calls[1])

    def test_no_personal_data_is_sent(self):
        self.payments.create_payment_link(order(), "Padel")
        self.assertNotIn("anna@x.it", repr(self.sessions.calls[0]))

    def test_stripe_error_becomes_payments_error(self):
        payments = StripePayments(fake_client(FakeSessions(stripe.APIConnectionError("giù"))),
                                  "https://vela.test")
        with self.assertRaises(PaymentsError):
            payments.create_payment_link(order(), "Padel")

    def test_only_eur(self):
        with self.assertRaises(PaymentsError):
            self.payments.create_payment_link(order(currency="USD"), "Padel")
        self.assertEqual(self.sessions.calls, [])

    def test_missing_itinerary_is_an_empty_metadata_value(self):
        self.payments.create_payment_link(replace(order(), itinerary_id=None), "Padel")
        self.assertEqual(self.sessions.calls[0][0]["metadata"]["itinerary_id"], "")

    def test_payment_intent_carries_hofj_checkout_ref(self):
        """HofJ lega il PaymentIntent al carrello con metadata.checkoutRefId = itineraryId."""
        self.payments.create_payment_link(order(), "Padel")
        pi_metadata = self.sessions.calls[0][0]["payment_intent_data"]["metadata"]
        self.assertEqual(pi_metadata["checkoutRefId"], "it-9")
        self.assertNotIn("checkoutRefId", self.sessions.calls[0][0]["metadata"])


class BuildClientTest(unittest.TestCase):
    def test_builds_a_client_without_network(self):
        self.assertIsInstance(build_stripe_client("sk_test_x"), stripe.StripeClient)


def session(status, payment_status, amount=79990, currency="eur", payment_intent="pi_9"):
    return SimpleNamespace(status=status, payment_status=payment_status, amount_total=amount,
                           currency=currency, payment_intent=payment_intent)


class LinkStatusTest(unittest.TestCase):
    """RF-20: Vela legge lo stato della Checkout Session invece di ricevere un webhook."""

    def status_of(self, retrieved=None, error=None):
        sessions = FakeSessions(error=error, retrieved=retrieved)
        payments = StripePayments(fake_client(sessions), "https://vela.test")
        return payments.link_status("cs_test_1"), sessions

    def test_complete_and_paid_is_paid_with_the_payment_intent(self):
        status, sessions = self.status_of(session("complete", "paid"))
        self.assertEqual(status, LinkStatus("paid", 79990, "EUR", "pi_9"))
        self.assertEqual(sessions.retrieve_calls, ["cs_test_1"])

    def test_expanded_payment_intent_object_gives_its_id(self):
        status, _ = self.status_of(session("complete", "paid", payment_intent=SimpleNamespace(id="pi_x")))
        self.assertEqual(status.payment_ref, "pi_x")

    def test_expired_and_open(self):
        self.assertEqual(self.status_of(session("expired", "unpaid", payment_intent=None))[0].state, "expired")
        self.assertEqual(self.status_of(session("open", "unpaid", payment_intent=None))[0].state, "open")
        self.assertEqual(self.status_of(session("complete", "unpaid"))[0].state, "open")

    def test_stripe_error_becomes_payments_error(self):
        with self.assertRaises(PaymentsError):
            self.status_of(error=stripe.APIConnectionError("rete"))

