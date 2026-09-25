import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vela.app import create_app
from vela.config import Settings

UNREACHABLE = "postgresql+psycopg://u:p@127.0.0.1:1/x"


def client(database_url):
    return TestClient(create_app(Settings(database_url=database_url)))


class HealthTest(unittest.TestCase):
    def test_no_database_configured_is_503(self):
        r = client(None).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json(), {"status": "degraded", "db": "error"})

    def test_reachable_database_is_200(self):
        r = client("sqlite://").get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok", "db": "ok"})

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

    def test_settings_and_engine_on_state(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertEqual(app.state.settings.database_url, "sqlite://")
        self.assertIsNotNone(app.state.engine)
