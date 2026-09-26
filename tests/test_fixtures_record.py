"""Registrazione delle fixture con il codice del sync (M10, RF-32): sorgente finta, mai la rete."""
import json
import os
import tempfile
import unittest
from datetime import timedelta

from hofj_samples import detail_of, item
from test_sync import T0, Clock, FakeSource
from vela.domain.catalog import fixture_meta, load_fixture, project_detail, strip_media
from vela.fixtures import RecordError, fixture_name, record_fixtures, write_catalog
from vela.ports.hofj import QuotaSnapshot, UpstreamError

PRODUCTION = "https://api.hofj.com"
STAGING = "https://staging.api.hofj.com"


class QuotaSource(FakeSource):
    """Sorgente finta che risponde anche a `/v1/quota`."""

    def __init__(self, pages, used=0):
        super().__init__(pages)
        self.used = used

    def get_quota(self):
        self.calls.append(("quota",))
        return QuotaSnapshot(120, self.used, T0, T0 + timedelta(seconds=60))


class FixtureNameTest(unittest.TestCase):
    def test_names_follow_the_existing_fixtures(self):
        self.assertEqual(fixture_name(PRODUCTION, "padel"), "catalog.json")
        self.assertEqual(fixture_name(PRODUCTION, "tennis"), "catalog-tennis.json")
        self.assertEqual(fixture_name(STAGING, "padel"), "catalog-staging.json")
        self.assertEqual(fixture_name(STAGING + "/", "tennis"), "catalog-staging-tennis.json")
        self.assertEqual(fixture_name("https://sandbox.api.hofj.com", "tennis"),
                         "catalog-sandbox-tennis.json")


class RecordFixturesTest(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.clock = Clock()
        self.active, self.gone = item(11, title="Rafa Nadal Academy"), item(12, archived=True)
        self.source = QuotaSource({"terrarossa.com": [[self.active], [self.gone]]})

    def record(self, brands=None, base_url=PRODUCTION):
        return record_fixtures(self.source, brands or {"tennis": "terrarossa.com"}, base_url, "it",
                               self.out, now=self.clock, sleep=self.clock.sleep)

    def test_writes_one_fixture_per_brand_with_its_header(self):
        (path,) = self.record()
        self.assertEqual(os.path.basename(path), "catalog-tennis.json")
        self.assertEqual(fixture_meta(path), {"base_url": PRODUCTION, "locale": "it",
                                              "brand": "terrarossa.com", "sport": "tennis"})
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["recorded_at"], T0.isoformat())

    def test_keeps_every_list_item_and_the_details_of_active_products(self):
        (path,) = self.record()
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["products"], [self.active, self.gone])
        detail = detail_of(self.active)
        self.assertEqual(data["details"], {"11": {"catalog": project_detail(detail),
                                                  "raw": strip_media(detail)}})

    def test_the_fixture_loads_as_the_brand_catalog(self):
        (path,) = self.record()
        products = {p.id: p for p in load_fixture(path)}
        self.assertEqual((products["11"].brand, products["11"].sport, products["11"].archived),
                         ("terrarossa.com", "tennis", False))
        self.assertTrue(products["12"].archived)

    def test_reads_the_quota_first_and_counts_every_call(self):
        self.record()
        self.assertEqual(self.source.calls[0], ("quota",))
        self.assertEqual(len(self.source.calls), 1 + 2 + 1)    # quota, due pagine, un dettaglio

    def test_respects_the_calls_already_used_in_the_window(self):
        self.source.used = 86                                  # 87 = tetto del sync nella finestra
        self.record()
        self.assertTrue(self.clock.slept)

    def test_a_failing_brand_writes_nothing(self):
        self.source.fail[("detail", "11")] = UpstreamError("503")
        with self.assertRaises(RecordError) as ctx:
            self.record()
        self.assertIn("503", str(ctx.exception))
        self.assertEqual(os.listdir(self.out), [])

    def test_write_catalog_is_utf8_with_a_trailing_newline(self):
        path = os.path.join(self.out, "sub", "catalog.json")
        write_catalog({"title": "Città"}, path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.endswith("\n"))
        self.assertIn("Città", text)


if __name__ == "__main__":
    unittest.main()
