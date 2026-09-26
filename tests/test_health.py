import os
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from support import NOW, inline_worker, make_product
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus, TravelerProfile
from vela.domain.usecases import Vela

UNREACHABLE = "postgresql+psycopg://u:p@127.0.0.1:1/x"


def client(database_url):
    return TestClient(create_app(Settings(database_url=database_url)))


class HealthTest(unittest.TestCase):
    def test_no_database_configured_is_503(self):
        r = client(None).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json(), {"status": "degraded", "db": "error", "catalog": None, "quota": None,
                                    "queue": None})

    def test_reachable_database_is_200(self):
        # SQLite senza tabelle: il catalogo non si legge, ma la salute dipende solo dal DB.
        r = client("sqlite://").get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok", "db": "ok", "catalog": None, "quota": None,
                                    "queue": None})

    def test_unreachable_database_is_503(self):
        r = client(UNREACHABLE).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["db"], "error")

    def test_health_is_public(self):
        r = TestClient(create_app(Settings(database_url="sqlite://")), headers={}).get("/health")
        self.assertNotIn(r.status_code, (401, 403))

    def test_response_is_json(self):
        r = client("sqlite://").get("/health")
        self.assertTrue(r.headers["content-type"].startswith("application/json"))


class AppFactoryTest(unittest.TestCase):
    def test_module_level_app_for_uvicorn(self):
        from vela.app import app
        self.assertIsInstance(app, FastAPI)

    def test_create_app_without_env_does_not_raise(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
        self.assertIsNone(app.state.engine)
        self.assertEqual(app.state.settings.vela_upstream_mode, "replay")

    def test_openapi_and_docs_are_served(self):
        c = client("sqlite://")
        self.assertIn("/health", c.get("/openapi.json").json()["paths"])
        self.assertEqual(c.get("/docs").status_code, 200)

    def test_settings_and_engine_on_state(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertEqual(app.state.settings.database_url, "sqlite://")
        self.assertIsNotNone(app.state.engine)


def order_stub(order_id):
    return Order(order_id, "p-" + order_id, "i1", "1", OrderStatus.QUEUED, 2, Decimal("300"), None,
                 "EUR", TravelerProfile(), NOW, NOW, enqueued_at=NOW)


def catalog_client(products, database_url="sqlite://", now=NOW + timedelta(hours=1)):
    repos = MemoryRepositories()
    repos.products.upsert_many(products)
    vela = Vela(repos, ReplayHofJ(), FakePayments("http://test"), DEFAULT_TRAVELER, now=lambda: now)
    app = create_app(Settings(database_url=database_url), vela=vela, worker=inline_worker(vela))
    return TestClient(app)


class CatalogHealthTest(unittest.TestCase):
    def test_reports_catalog_size_and_age(self):
        older = replace(make_product(2), fetched_at=NOW - timedelta(days=1))
        r = catalog_client([make_product(1), older]).get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["catalog"], {"products": 2, "fetched_at": "2026-09-25T12:00:00+00:00",
                                               "age_seconds": 3600})

    def test_reports_the_quota_bucket(self):
        """M18: lo stato del token bucket condiviso, prima di ogni lettura di /v1/quota."""
        r = catalog_client([make_product(1)]).get("/health")
        self.assertEqual(r.json()["quota"], {
            "limit_per_minute": 120, "effective_limit": 108, "burst": 8, "rate_per_minute": 100.0,
            "purchase_floor": 2, "tokens": 8.0, "purchases_per_minute": 16.0, "needs_refresh": True,
            "hofj_window_start": "2026-09-25T13:00:00+00:00",
            "hofj_window_end": "2026-09-25T13:01:00+00:00"})

    def test_reports_queue_age_and_orphan_itineraries(self):
        """M18: età del più vecchio acquisto in coda e itinerari lasciati orfani da un timeout."""
        repos = MemoryRepositories()
        vela = Vela(repos, ReplayHofJ(), FakePayments("http://test"), DEFAULT_TRAVELER,
                    now=lambda: NOW + timedelta(minutes=5))
        repos.jobs.enqueue(Job("j1", JobKind.PURCHASE, "o1", JobStatus.PENDING, NOW, NOW))
        repos.jobs.enqueue(Job("j2", JobKind.PURCHASE, "o2", JobStatus.DONE, NOW - timedelta(hours=1), NOW))
        repos.orders.save(replace(order_stub("o1"), orphan_itineraries=2))
        app = create_app(Settings(database_url="sqlite://"), vela=vela, worker=inline_worker(vela))
        r = TestClient(app).get("/health")
        self.assertEqual(r.json()["queue"], {"oldest_purchase_age_seconds": 300, "orphan_itineraries": 2})

    def test_empty_queue(self):
        r = catalog_client([]).get("/health")
        self.assertEqual(r.json()["queue"], {"oldest_purchase_age_seconds": None, "orphan_itineraries": 0})

    def test_empty_catalog(self):
        r = catalog_client([]).get("/health")
        self.assertEqual(r.json()["catalog"], {"products": 0, "fetched_at": None, "age_seconds": None})

    def test_age_is_never_negative(self):
        r = catalog_client([make_product(1)], now=NOW - timedelta(minutes=5)).get("/health")
        self.assertEqual(r.json()["catalog"]["age_seconds"], 0)

    def test_no_catalog_when_database_is_down(self):
        r = catalog_client([make_product(1)], database_url=UNREACHABLE).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertIsNone(r.json()["catalog"])

    def test_health_needs_no_token(self):
        app = create_app(Settings(database_url="sqlite://", vela_api_token="tok"))
        self.assertEqual(TestClient(app).get("/health").status_code, 200)
