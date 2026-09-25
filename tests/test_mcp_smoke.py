"""Smoke test MCP (scripts/mcp_smoke.py) contro l'app replay in-process, catalogo della fixture."""
import contextlib
import io
import os
import random
import sys
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from mcp import Client

from support import inline_worker, NOW
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.usecases import Vela

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_smoke  # noqa: E402


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_app(preload=True):
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    if preload:
        repos.products.upsert_many(hofj.load_catalog())
    vela = Vela(repos, hofj, FakePayments("http://test"), DEFAULT_TRAVELER, now=Clock())
    app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://test"),
                     vela=vela, worker=inline_worker(vela), catalog_loader=None)
    return app


class SmokeFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_flow_passes_against_the_replay_app(self):
        app = make_app()
        opened = []
        with TestClient(app) as tc:
            def open_url(url):
                opened.append(url)
                self.assertEqual(tc.get(urlparse(url).path).status_code, 200)
                app.state.worker.drain()        # la prenotazione passa dal worker

            async with Client(app.state.mcp) as client:
                summary = await mcp_smoke.run_flow(client, open_url, expected_base="http://test", delay=0)
        self.assertRegex(summary["booking_code"], r"^R-\d{6}$")
        self.assertNotEqual(summary["first"], summary["second"])
        self.assertEqual(len(opened), 1)

    async def test_payment_link_on_another_host_fails(self):
        app = make_app()
        with TestClient(app):
            async with Client(app.state.mcp) as client:
                with self.assertRaises(mcp_smoke.SmokeFailure) as ctx:
                    await mcp_smoke.run_flow(client, lambda url: None,
                                             expected_base="https://elsewhere.example", delay=0)
        self.assertIn("VELA_PUBLIC_URL", str(ctx.exception))

    async def test_empty_catalog_fails_at_get_proposal(self):
        app = make_app(preload=False)
        async with Client(app.state.mcp) as client:
            with self.assertRaises(mcp_smoke.SmokeFailure) as ctx:
                await mcp_smoke.run_flow(client, lambda url: None, delay=0)
        self.assertIn("get_proposal", str(ctx.exception))

    async def test_unpaid_order_is_reported(self):
        app = make_app()
        async with Client(app.state.mcp) as client:
            with self.assertRaises(mcp_smoke.SmokeFailure) as ctx:
                await mcp_smoke.run_flow(client, lambda url: None, attempts=2, delay=0)
        self.assertIn("awaiting_payment", str(ctx.exception))


class SmokeCliTest(unittest.TestCase):
    def test_usage(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(mcp_smoke.main([]), 2)
        self.assertIn("uso:", err.getvalue())

    def test_base_of(self):
        self.assertEqual(mcp_smoke.base_of("https://vela-n506.onrender.com/mcp"),
                         "https://vela-n506.onrender.com")

    def test_count_products(self):
        self.assertEqual(mcp_smoke.count_products({"a": [{"product_id": 1}, {"product_id": 2}]}), 2)
