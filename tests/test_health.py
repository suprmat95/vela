import os
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from support import NOW, make_product
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.usecases import Vela

UNREACHABLE = "postgresql+psycopg://u:p@127.0.0.1:1/x"


def client(database_url):
    return TestClient(create_app(Settings(database_url=database_url)))


class HealthTest(unittest.TestCase):
    def test_no_database_configured_is_503(self):
        r = client(None).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json(), {"status": "degraded", "db": "error", "catalog": None, "quota": None})

    def test_reachable_database_is_200(self):
        # SQLite senza tabelle: il catalogo non si legge, ma la salute dipende solo dal DB.
        r = client("sqlite://").get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok", "db": "ok", "catalog": None, "quota": None})

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


def catalog_client(products, database_url="sqlite://", now=NOW + timedelta(hours=1)):
    repos = MemoryRepositories()
    repos.products.upsert_many(products)
    vela = Vela(repos, ReplayHofJ(), FakePayments("http://test"), DEFAULT_TRAVELER, now=lambda: now)
    app = create_app(Settings(database_url=database_url), vela=vela, runner=InlineRunner(vela.orders))
    return TestClient(app)


class CatalogHealthTest(unittest.TestCase):
    def test_reports_catalog_size_and_age(self):
        older = replace(make_product(2), fetched_at=NOW - timedelta(days=1))
        r = catalog_client([make_product(1), older]).get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["catalog"], {"products": 2, "fetched_at": "2026-09-25T12:00:00+00:00",
                                               "age_seconds": 3600})
        self.assertIsNone(r.json()["quota"])

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
