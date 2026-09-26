import json
import os
import random
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest import mock
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from support import NOW, inline_worker, make_product
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
                     vela=vela, worker=inline_worker(vela), catalog_loader=hofj.load_catalog)
    return app, vela


def staging_fixtures_dir(locale="en"):
    """Cartella con la sola fixture di staging (un prodotto, id 118): in live si sceglie per host."""
    folder = tempfile.mkdtemp()
    entry = {"id": "118", "title": "Padel Barcelona", "slug": "padel-barcelona", "price": 245,
             "currency": "EUR", "minPax": 1, "availabilities": []}
    with open(os.path.join(folder, "catalog-staging.json"), "w", encoding="utf-8") as fh:
        json.dump({"locale": locale, "brand": "staging.weebora.com",
                   "base_url": "https://staging.api.hofj.com", "products": [entry],
                   "details": {"118": {"catalog": entry, "raw": entry}}}, fh)
    return folder


def ready_order(app, vela):
    """Ordine accettato e passato dal job d'acquisto: lo stato ha il link di pagamento."""
    iid = vela.create_intent(INTENT, FULL).intent_id
    proposal = vela.get_proposal(iid)
    oid = vela.accept_proposal(proposal.proposal.id).order_id
    app.state.worker.drain()
    return vela.get_order_status(oid)


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
        """RF-27: un ordine pagato senza job di prenotazione (processo morto prima di accodarlo)."""
        app, vela = make_app(preload=True)
        oid = ready_order(app, vela).order_id
        order = vela.repos.orders.get(oid)
        vela.repos.orders.save(replace(order, status=OrderStatus.PAID_PENDING_BOOKING, payment_ref="pi"))
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["resumed"], [oid])
            app.state.worker.drain()
            self.assertEqual(vela.get_order_status(oid).status, OrderStatus.CONFIRMED)

    def test_bootstrap_reads_the_quota_once(self):
        app, vela = make_app(preload=True)
        with TestClient(app):
            self.assertTrue(app.state.bootstrap["quota_synced"])
            snap = vela.repos.quota.snapshot(vela.now())
            self.assertEqual((snap["limit_per_minute"], snap["needs_refresh"]), (120, False))


class FakeScheduler:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("scheduler")

    def stop(self):
        self.events.append("stop")


class LiveBootstrapTest(unittest.TestCase):
    """Live (M10): al boot niente fixture; quota, poi lo scheduler del sync, fermato alla chiusura."""

    def test_starts_the_sync_scheduler_after_reading_the_quota(self):
        events = []
        repos = MemoryRepositories()
        vela = Vela(repos, ReplayHofJ(rng=random.Random(7)), FakePayments("http://test"),
                    DEFAULT_TRAVELER, now=Clock())
        worker = inline_worker(vela)
        refresh = worker.processor.refresh_quota
        worker.processor.refresh_quota = lambda: (events.append("quota"), refresh())[1]
        app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://test"),
                         vela=vela, worker=worker, catalog_loader=None,
                         scheduler=FakeScheduler(events))
        with TestClient(app):
            self.assertEqual(events, ["quota", "scheduler"])
            self.assertEqual(app.state.bootstrap["catalog_sync"], "scheduled")
            self.assertEqual(repos.products.count(), 0)
        self.assertEqual(events[-1], "stop")


STAGING = [make_product("118", destination="Barcellona", country="ES", price=245),
           make_product("119", destination="Madrid", country="ES", price=300),
           make_product("120", archived=True)]


def app_with_catalog(repos, loader):
    vela = Vela(repos, ReplayHofJ(rng=random.Random(7)), FakePayments("http://test"), DEFAULT_TRAVELER,
                now=Clock())
    app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://test"),
                     vela=vela, worker=inline_worker(vela), catalog_loader=loader)
    return app, vela


def active_ids(vela):
    return sorted(p.id for p in vela.repos.products.list_all() if not p.archived)


class CatalogRealignTest(unittest.TestCase):
    """Decisione M7: al boot il DB si riallinea alla fixture dell'ambiente, senza DELETE."""

    def setUp(self):
        self.production = ReplayHofJ().load_catalog
        self.production_active = sorted(p.id for p in self.production() if not p.archived)

    def test_switch_to_another_catalog_archives_the_old_one(self):
        repos = MemoryRepositories()
        repos.products.upsert_many(self.production())
        app, vela = app_with_catalog(repos, lambda: STAGING)
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["catalog_loaded"], 3)
            self.assertEqual(app.state.bootstrap["catalog_archived"], len(self.production_active))
            self.assertEqual(active_ids(vela), ["118", "119"])
            self.assertEqual(vela.repos.products.count(), 110 + 3)   # nessun prodotto cancellato

    def test_proposals_on_archived_products_stay_readable_and_new_intents_use_the_new_catalog(self):
        repos = MemoryRepositories()
        app, vela = app_with_catalog(repos, self.production)
        with TestClient(app):
            old = vela.get_proposal(vela.create_intent(INTENT, FULL).intent_id).proposal
        self.assertIn(old.product_id, self.production_active)
        app, vela = app_with_catalog(repos, lambda: STAGING)
        with TestClient(app):
            self.assertEqual(vela.repos.proposals.get(old.id).product_id, old.product_id)
            self.assertTrue(vela.repos.products.get(old.product_id).archived)
            new = vela.get_proposal(vela.create_intent(INTENT, FULL).intent_id).proposal
            self.assertIn(new.product_id, ("118", "119"))

    def test_same_catalog_is_not_reloaded_and_keeps_bookable_flags(self):
        repos = MemoryRepositories()
        repos.products.upsert_many(STAGING)
        repos.products.set_bookable("118", False, NOW)
        app, vela = app_with_catalog(repos, lambda: STAGING)
        with TestClient(app):
            self.assertEqual((app.state.bootstrap["catalog_loaded"],
                              app.state.bootstrap["catalog_archived"]), (0, 0))
            self.assertFalse(vela.repos.products.get("118").bookable)

    def test_back_to_the_production_catalog_archives_the_staging_one(self):
        repos = MemoryRepositories()
        repos.products.upsert_many(self.production())
        repos.products.archive_missing([p.id for p in STAGING])
        repos.products.upsert_many(STAGING)
        app, vela = app_with_catalog(repos, self.production)
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["catalog_archived"], 2)
            self.assertEqual(active_ids(vela), self.production_active)


class CheckoutTest(unittest.TestCase):
    def test_checkout_marks_paid_and_books(self):
        app, vela = make_app(preload=True)
        with TestClient(app) as c:
            accepted = ready_order(app, vela)
            self.assertTrue(accepted.payment_url.startswith("http://test/replay/checkout/"))
            r = c.get(urlparse(accepted.payment_url).path)
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["order_id"], accepted.order_id)
            self.assertEqual(body["status"], "paid_pending_booking")
            self.assertIn("Pagamento", body["say"])
            app.state.worker.drain()                               # il job di prenotazione
            status = vela.get_order_status(accepted.order_id)
            self.assertEqual(status.status, OrderStatus.CONFIRMED)
            self.assertRegex(status.booking_code, r"^R-\d{6}$")

    def test_second_visit_has_no_effect(self):
        app, vela = make_app(preload=True)
        with TestClient(app) as c:
            accepted = ready_order(app, vela)
            path = urlparse(accepted.payment_url).path
            c.get(path)
            app.state.worker.drain()
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

    LIVE = dict(database_url="sqlite://", vela_upstream_mode="live",
                hofj_api_key="hofj-segreta", hofj_base_url="https://staging.api.hofj.com",
                hofj_brands="padel=staging.weebora.com,tennis=staging.tennis.weebora.com",
                stripe_secret_key="rk_test_segreta", vela_public_url="https://vela.test")

    def live_app(self, locale="en", **over):
        with mock.patch("vela.app.FIXTURES_DIR", staging_fixtures_dir(locale)):
            return create_app(Settings(**dict(self.LIVE, **over)))

    def test_live_builds_one_http_client_per_brand_and_m6_payments(self):
        from vela.adapters.hofj_http import HofJHttp
        from vela.adapters.hofj_router import BrandRouter
        from vela.adapters.stripe_links import StripePayments
        app = self.live_app()
        router = app.state.vela.hofj
        self.assertIsInstance(router, BrandRouter)
        self.assertEqual(sorted(router.clients), ["staging.tennis.weebora.com", "staging.weebora.com"])
        for brand, client in router.clients.items():
            self.assertIsInstance(client, HofJHttp)
            self.assertEqual((str(client.client.base_url), client.brand, client.locale),
                             ("https://staging.api.hofj.com", brand, "en"))
        self.assertEqual(router.sport_brands, {"padel": "staging.weebora.com",
                                               "tennis": "staging.tennis.weebora.com"})
        self.assertIsInstance(app.state.vela.payments, StripePayments)

    def test_live_worker_uses_the_brand_router(self):
        app = self.live_app()
        self.assertIs(app.state.worker.processor.hofj, app.state.vela.hofj)

    def test_live_syncs_the_catalog_instead_of_loading_a_fixture(self):
        from vela.sync import SyncScheduler
        app = self.live_app()
        self.assertIsNone(app.state.catalog_loader)
        scheduler = app.state.scheduler
        self.assertIsInstance(scheduler, SyncScheduler)
        self.assertEqual(scheduler.sync.brands, {"padel": "staging.weebora.com",
                                                 "tennis": "staging.tennis.weebora.com"})
        self.assertIs(scheduler.sync.repos, app.state.vela.repos)

    def test_live_cart_locale_is_the_locale_of_the_host_fixtures(self):
        for locale in ("en", "it"):
            with self.subTest(locale):
                router = self.live_app(locale).state.vela.hofj
                self.assertEqual({c.locale for c in router.clients.values()}, {locale})

    def test_live_without_a_fixture_for_the_host_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.live_app(hofj_base_url="https://sandbox.api.hofj.com")
        self.assertIn("https://sandbox.api.hofj.com", str(ctx.exception))
        self.assertNotIn("hofj-segreta", str(ctx.exception))

    def test_replay_keeps_the_production_fixtures_and_no_scheduler(self):
        with mock.patch("vela.app.FIXTURES_DIR", staging_fixtures_dir()):
            app = create_app(Settings(database_url="sqlite://"))
        self.assertEqual(len(app.state.catalog_loader()), len(ReplayHofJ().load_catalog()))
        self.assertIsNone(app.state.scheduler)

    def test_live_requires_hofj_settings(self):
        for missing, variable in (("hofj_api_key", "HOFJ_API_KEY"), ("hofj_base_url", "HOFJ_BASE_URL"),
                                  ("hofj_brands", "HOFJ_BRANDS")):
            with self.subTest(missing), self.assertRaises(RuntimeError) as ctx:
                self.live_app(**{missing: None})
            self.assertIn(variable, str(ctx.exception))
            for secret in ("hofj-segreta", "rk_test_segreta"):
                self.assertNotIn(secret, str(ctx.exception))

    def test_live_with_the_old_brand_variable_asks_to_migrate(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.live_app(hofj_brands=None, hofj_brand="staging.weebora.com")
        self.assertIn("HOFJ_BRANDS=padel=staging.weebora.com", str(ctx.exception))

    def test_live_with_an_invalid_brand_map_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.live_app(hofj_brands="golf=golf.com")
        self.assertIn("golf", str(ctx.exception))

    def test_live_requires_real_payments(self):
        with self.assertRaises(RuntimeError) as ctx:
            create_app(Settings(**dict(self.LIVE, stripe_secret_key=None)))
        self.assertIn("STRIPE_SECRET_KEY", str(ctx.exception))

    def test_replay_without_database_has_no_domain(self):
        app = create_app(Settings())
        self.assertIsNone(app.state.vela)
        with TestClient(app) as c:
            self.assertEqual(c.get("/replay/checkout/x").status_code, 503)

    def test_no_stripe_key_keeps_fake_payments(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsInstance(app.state.vela.payments, FakePayments)

    def test_stripe_key_and_public_url_select_stripe_payments(self):
        from vela.adapters.stripe_links import StripePayments
        app = create_app(Settings(database_url="sqlite://", stripe_secret_key="rk_test_x",
                                  vela_public_url="https://vela.test"))
        self.assertIsInstance(app.state.vela.payments, StripePayments)
        self.assertEqual(app.state.vela.payments.base, "https://vela.test")

    def test_stripe_key_without_public_url_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            create_app(Settings(database_url="sqlite://", stripe_secret_key="rk_test_x"))
        self.assertIn("VELA_PUBLIC_URL", str(ctx.exception))
        self.assertNotIn("rk_test_x", str(ctx.exception))

    def test_checkout_pages_mounted_and_no_stripe_webhook(self):
        for mode in ("replay", "live"):
            with self.subTest(mode), TestClient(create_app(Settings(vela_upstream_mode=mode))) as c:
                self.assertEqual(c.post("/webhooks/stripe").status_code, 404)   # pagamento via HofJ
                self.assertEqual(c.get("/checkout/success").status_code, 200)
                self.assertEqual(c.get("/checkout/cancel").status_code, 200)

    def test_no_key_no_extractor(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsNone(app.state.vela.extractor)

    def test_key_builds_haiku_extractor_without_calling_it(self):
        from vela.adapters.haiku import HaikuExtractor
        app = create_app(Settings(database_url="sqlite://", anthropic_api_key="sk-ant-test"))
        self.assertIsInstance(app.state.vela.extractor, HaikuExtractor)

    def test_replay_with_database_builds_domain(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsNotNone(app.state.vela)
        self.assertIsNotNone(app.state.worker)
        self.assertTrue(callable(app.state.catalog_loader))
