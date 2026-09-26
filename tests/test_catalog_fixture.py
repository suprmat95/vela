"""Verifica fixtures/catalog.json, la fixture padel di produzione (`python -m vela.sync --record`).

Si salta se il file non esiste (RNF-09: la suite non richiede servizi esterni).
"""
import json
import os
import unittest

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")
MEDIA_KEYS = ("gallery", "image", "images", "cover", "media", "travelProgram")
MAX_BYTES = 1500000


def has_key(value, key):
    if isinstance(value, dict):
        return key in value or any(has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(has_key(v, key) for v in value)
    return False


@unittest.skipUnless(os.path.exists(FIXTURE),
                     "fixtures/catalog.json assente: eseguire python -m vela.sync --record")
class CatalogFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.catalog = json.loads(cls.text)
        cls.products = cls.catalog["products"]
        cls.details = cls.catalog["details"]

    def test_header(self):
        self.assertEqual(self.catalog["locale"], "it")
        self.assertRegex(self.catalog["recorded_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual((self.catalog["brand"], self.catalog["sport"]), ("weebora.com", "padel"))
        self.assertTrue(self.catalog["base_url"].startswith("https://"))

    def test_every_active_product_has_a_detail_and_vice_versa(self):
        active = [p["id"] for p in self.products if not p["archived"]]
        self.assertEqual(sorted(active), sorted(self.details))
        self.assertEqual(len(active), len(set(active)))       # nessun duplicato
        self.assertGreaterEqual(len(active), 70)              # 77 attivi in it il 2026-09-25 (docs/fixtures.md)

    def test_list_items_have_pricing_and_dates(self):
        for product in self.products:
            for key in ("price", "currency", "minDate", "maxDate", "availabilities", "archived"):
                self.assertIn(key, product, product["id"])
            self.assertEqual(product["locale"], "it", product["id"])
            if not product["archived"]:
                self.assertGreater(product["price"], 0, product["id"])
                self.assertEqual(product["currency"], "EUR", product["id"])

    def test_details_have_rf28_fields_and_no_media(self):
        for pid, detail in self.details.items():
            catalog, raw = detail["catalog"], detail["raw"]
            for key in ("category", "venue", "destination", "hotels", "price", "minDate",
                        "maxDate", "availabilities", "defaultDurationInDays", "updatedAt"):
                self.assertIn(key, catalog, pid)
            self.assertIsInstance(catalog["category"], dict, pid)
            self.assertEqual(catalog["id"], pid)
            self.assertIn("hotels", raw.get("rawAttributes") or {}, pid)
            for key in MEDIA_KEYS:
                self.assertFalse(has_key(raw, key), "%s contiene %s" % (pid, key))

    def test_no_credentials(self):
        self.assertNotIn("Authorization", self.text)
        self.assertNotIn("Bearer ", self.text)
        for env in ("HOFJ_API_KEY", "API_BEAR_KEY"):
            key = os.environ.get(env)
            if key:   # mai stampare la chiave: messaggio senza il valore
                self.assertFalse(key in self.text, "%s presente nella fixture" % env)

    def test_size_within_budget(self):
        self.assertLess(os.path.getsize(FIXTURE), MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
