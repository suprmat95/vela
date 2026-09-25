"""Pagine statiche di ritorno dal Checkout (decisione M6): HTML, nessun dato, nessun DB."""
import unittest

from fastapi.testclient import TestClient

from vela.app import create_app
from vela.config import Settings


class CheckoutPagesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(Settings()))   # senza DATABASE_URL: nessun dominio

    def test_success_page(self):
        r = self.client.get("/checkout/success")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("text/html"))
        self.assertIn("Pagamento riuscito", r.text)
        self.assertIn('lang="it"', r.text)
        self.assertIn("noindex", r.text)

    def test_cancel_page(self):
        r = self.client.get("/checkout/cancel")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("text/html"))
        self.assertIn("Pagamento non completato", r.text)

    def test_query_parameters_are_never_reflected(self):
        r = self.client.get("/checkout/success?order_id=<script>x</script>&session_id=cs_1")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("<script>", r.text)
        self.assertNotIn("cs_1", r.text)

    def test_pages_have_no_scripts(self):
        for path in ("/checkout/success", "/checkout/cancel"):
            self.assertNotIn("<script", self.client.get(path).text)
