import random
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from support import NOW
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import OrderStatus, Participant, TravelerProfile
from vela.domain.usecases import Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_app(preload=False):
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    if preload:
        repos.products.upsert_many(hofj.load_catalog())
    vela = Vela(repos, hofj, FakePayments("http://test"), DEFAULT_TRAVELER, now=Clock())
    app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://test"),
                     vela=vela, runner=InlineRunner(vela.orders), catalog_loader=hofj.load_catalog)
    return app, vela


def paid_order(vela):
    iid = vela.create_intent(INTENT, FULL).intent_id
    proposal = vela.get_proposal(iid)
    return vela.accept_proposal(proposal.proposal.id)


class BootstrapTest(unittest.TestCase):
    def test_loads_fixture_when_catalog_is_empty(self):
        app, vela = make_app()
        with TestClient(app):
            self.assertEqual(vela.repos.products.count(), 110)
            self.assertEqual(app.state.bootstrap["catalog_loaded"], 110)

    def test_does_not_reload_when_catalog_exists(self):
        app, vela = make_app(preload=True)
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["catalog_loaded"], 0)
            self.assertEqual(vela.repos.products.count(), 110)

    def test_resumes_pending_bookings(self):
        app, vela = make_app(preload=True)
        oid = paid_order(vela).order_id
        vela.orders.mark_paid(oid, "pi")
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["resumed"], [oid])
            self.assertEqual(vela.get_order_status(oid).status, OrderStatus.CONFIRMED)


class CheckoutTest(unittest.TestCase):
    def test_checkout_marks_paid_and_books(self):
        app, vela = make_app(preload=True)
        with TestClient(app) as c:
            accepted = paid_order(vela)
            self.assertTrue(accepted.payment_url.startswith("http://test/replay/checkout/"))
            r = c.get(urlparse(accepted.payment_url).path)
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["order_id"], accepted.order_id)
            self.assertEqual(body["status"], "paid_pending_booking")
            self.assertIn("Pagamento", body["say"])
            status = vela.get_order_status(accepted.order_id)
            self.assertEqual(status.status, OrderStatus.CONFIRMED)
            self.assertRegex(status.booking_code, r"^R-\d{6}$")

    def test_second_visit_has_no_effect(self):
        app, vela = make_app(preload=True)
        with TestClient(app) as c:
            accepted = paid_order(vela)
            path = urlparse(accepted.payment_url).path
            c.get(path)
            code = vela.get_order_status(accepted.order_id).booking_code
            r = c.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "confirmed")
            self.assertIn(code, r.json()["say"])
            self.assertEqual(vela.get_order_status(accepted.order_id).booking_code, code)
            self.assertEqual(len(vela.hofj._codes), 1)

    def test_unknown_order_is_404(self):
        app, _ = make_app(preload=True)
        with TestClient(app) as c:
            self.assertEqual(c.get("/replay/checkout/nope").status_code, 404)

    def test_health_still_works(self):
        app, _ = make_app(preload=True)
        with TestClient(app) as c:
            self.assertEqual(c.get("/health").status_code, 503)   # nessun DATABASE_URL nei test


class ModeTest(unittest.TestCase):
    def test_replay_router_absent_in_live(self):
        app = create_app(Settings(vela_upstream_mode="live"))
        self.assertNotIn("/replay/checkout/{order_id}", [getattr(r, "path", None) for r in app.routes])

    def test_live_with_database_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            create_app(Settings(database_url="sqlite://", vela_upstream_mode="live"))
        self.assertIn("M5", str(ctx.exception))

    def test_replay_without_database_has_no_domain(self):
        app = create_app(Settings())
        self.assertIsNone(app.state.vela)
        with TestClient(app) as c:
            self.assertEqual(c.get("/replay/checkout/x").status_code, 503)

    def test_no_stripe_key_keeps_fake_payments(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsInstance(app.state.vela.payments, FakePayments)

    def test_stripe_key_selects_stripe_payments(self):
        from vela.adapters.stripe_links import StripePayments
        app = create_app(Settings(database_url="sqlite://", stripe_secret_key="sk_test_x",
                                  stripe_webhook_secret="whsec_x",
                                  vela_public_url="https://vela.test"))
        self.assertIsInstance(app.state.vela.payments, StripePayments)
        self.assertEqual(app.state.vela.payments.base, "https://vela.test")

    def test_stripe_key_without_webhook_secret_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            create_app(Settings(database_url="sqlite://", stripe_secret_key="sk_test_x",
                                vela_public_url="https://vela.test"))
        self.assertIn("STRIPE_WEBHOOK_SECRET", str(ctx.exception))
        self.assertNotIn("sk_test_x", str(ctx.exception))

    def test_stripe_key_without_public_url_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            create_app(Settings(database_url="sqlite://", stripe_secret_key="sk_test_x",
                                stripe_webhook_secret="whsec_x"))
        self.assertIn("VELA_PUBLIC_URL", str(ctx.exception))

    def test_webhook_and_checkout_routes_always_mounted(self):
        for mode in ("replay", "live"):
            with self.subTest(mode), TestClient(create_app(Settings(vela_upstream_mode=mode))) as c:
                self.assertEqual(c.post("/webhooks/stripe").status_code, 503)   # senza secret
                self.assertEqual(c.get("/checkout/success").status_code, 200)
                self.assertEqual(c.get("/checkout/cancel").status_code, 200)

    def test_replay_with_database_builds_domain(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsNotNone(app.state.vela)
        self.assertIsNotNone(app.state.runner)
        self.assertTrue(callable(app.state.catalog_loader))
