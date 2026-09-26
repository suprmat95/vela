"""Modo `VELA_UPSTREAM_MODE=loadtest` (M13a): HofJ via HTTP verso il finto, pagamenti finti,
checkout di replay; qualunque host diverso da localhost o `fake-hofj` è rifiutato all'avvio."""
import unittest

from vela.adapters.hofj_http import HofJHttp
from vela.adapters.hofj_router import BrandRouter
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import Settings
from vela.sync import SyncScheduler

LOADTEST = dict(database_url="sqlite://", vela_upstream_mode="loadtest",
                hofj_api_key="loadtest-key", hofj_base_url="http://fake-hofj:8001",
                hofj_brands="padel=weebora.com,tennis=terrarossa.com",
                vela_public_url="http://vela:8000")


def loadtest_app(**over):
    return create_app(Settings(**dict(LOADTEST, **over)))


class LoadtestModeTest(unittest.TestCase):
    def test_http_clients_per_brand_against_the_fake(self):
        router = loadtest_app().state.vela.hofj
        self.assertIsInstance(router, BrandRouter)
        self.assertEqual(sorted(router.clients), ["terrarossa.com", "weebora.com"])
        for client in router.clients.values():
            self.assertIsInstance(client, HofJHttp)
            self.assertEqual(str(client.client.base_url), "http://fake-hofj:8001")

    def test_locale_is_the_one_of_the_brand_fixture(self):
        router = loadtest_app().state.vela.hofj
        self.assertEqual({b: c.locale for b, c in router.clients.items()},
                         {"weebora.com": "it", "terrarossa.com": "it"})
        staging = loadtest_app(hofj_brands="padel=staging.weebora.com").state.vela.hofj
        self.assertEqual(staging.clients["staging.weebora.com"].locale, "en")

    def test_catalog_comes_from_the_sync(self):
        app = loadtest_app()
        self.assertIsNone(app.state.catalog_loader)
        self.assertIsInstance(app.state.scheduler, SyncScheduler)

    def test_payments_are_fake_even_with_a_stripe_key(self):
        app = loadtest_app(stripe_secret_key="rk_test_segreta")
        self.assertIsInstance(app.state.vela.payments, FakePayments)
        self.assertTrue(app.state.vela.payments.base.startswith("http://vela:8000"))

    def test_replay_checkout_is_mounted(self):
        self.assertEqual(loadtest_app().url_path_for("replay_checkout", order_id="o1"),
                         "/replay/checkout/o1")

    def test_allowed_hosts(self):
        for url in ("http://localhost:8001", "http://127.0.0.1:8001", "http://fake-hofj:8001/"):
            with self.subTest(url):
                loadtest_app(hofj_base_url=url)

    def test_real_hofj_is_refused(self):
        for url in ("https://staging.api.hofj.com", "https://api.hofj.com",
                    "http://fake-hofj.evil.com", "http://localhost.hofj.com"):
            with self.subTest(url), self.assertRaises(RuntimeError) as ctx:
                loadtest_app(hofj_base_url=url)
            self.assertIn("loadtest", str(ctx.exception))
            self.assertNotIn("loadtest-key", str(ctx.exception))

    def test_requires_the_hofj_settings(self):
        for missing in ("hofj_api_key", "hofj_base_url", "hofj_brands"):
            with self.subTest(missing), self.assertRaises(RuntimeError):
                loadtest_app(**{missing: None})

    def test_unknown_mode_lists_loadtest(self):
        with self.assertRaises(RuntimeError) as ctx:
            loadtest_app(vela_upstream_mode="stress")
        self.assertIn("loadtest", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
