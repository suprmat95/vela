"""Scelta della fixture del catalogo per ambiente (decisione M7): `base_url` della fixture = HOFJ_BASE_URL."""
import json
import os
import tempfile
import unittest

from vela.domain.catalog import fixture_meta, load_fixture, select_fixtures

STAGING = "https://staging.api.hofj.com"
PRODUCTION = "https://api.hofj.com"


def write_fixture(folder, name, base_url, locale="it", brand=None, sport=None, entries=()):
    path = os.path.join(folder, name)
    data = {"recorded_at": "2026-09-25T12:00:00+00:00", "locale": locale, "brand": brand,
            "base_url": base_url, "products": list(entries),
            "details": {e["id"]: {"catalog": e, "raw": e} for e in entries}}
    if sport is not None:
        data["sport"] = sport
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def entry(pid, title):
    return {"id": pid, "title": title, "slug": "s-%s" % pid, "price": 100, "currency": "EUR",
            "availabilities": []}


class FixtureMetaTest(unittest.TestCase):
    def test_reads_base_url_locale_and_brand(self):
        folder = tempfile.mkdtemp()
        path = write_fixture(folder, "catalog-staging.json", STAGING, "en", "staging.weebora.com")
        self.assertEqual(fixture_meta(path), {"base_url": STAGING, "locale": "en",
                                              "brand": "staging.weebora.com", "sport": None})

    def test_reads_sport(self):
        path = write_fixture(tempfile.mkdtemp(), "catalog-tennis.json", PRODUCTION,
                             brand="terrarossa.com", sport="tennis")
        self.assertEqual(fixture_meta(path)["sport"], "tennis")


class LoadFixtureBrandTest(unittest.TestCase):
    def test_brand_and_sport_come_from_the_fixture(self):
        path = write_fixture(tempfile.mkdtemp(), "catalog-tennis.json", PRODUCTION,
                             brand="terrarossa.com", sport="tennis",
                             entries=[entry("5", "Rafa Nadal Academy")])
        (product,) = load_fixture(path)
        self.assertEqual((product.brand, product.sport), ("terrarossa.com", "tennis"))

    def test_without_sport_the_text_decides(self):
        path = write_fixture(tempfile.mkdtemp(), "catalog.json", PRODUCTION,
                             entries=[entry("6", "Tennis a Roma")])
        (product,) = load_fixture(path)
        self.assertEqual((product.brand, product.sport), (None, "tennis"))


class SelectFixturesTest(unittest.TestCase):
    """Tutte le fixture dell'host, una per brand (M10, RF-32)."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.production = write_fixture(self.folder, "catalog.json", PRODUCTION, brand="weebora.com")
        self.tennis = write_fixture(self.folder, "catalog-tennis.json", PRODUCTION,
                                    brand="terrarossa.com")
        self.staging = write_fixture(self.folder, "catalog-staging.json", STAGING, "en")

    def test_picks_every_fixture_recorded_on_that_host(self):
        self.assertCountEqual(select_fixtures(self.folder, PRODUCTION), [self.production, self.tennis])
        self.assertEqual(select_fixtures(self.folder, STAGING), [self.staging])

    def test_trailing_slash_does_not_matter(self):
        self.assertEqual(select_fixtures(self.folder, STAGING + "/"), [self.staging])
        write_fixture(self.folder, "catalog-sandbox.json", "https://sandbox.api.hofj.com/")
        self.assertEqual(select_fixtures(self.folder, "https://sandbox.api.hofj.com"),
                         [os.path.join(self.folder, "catalog-sandbox.json")])

    def test_no_match_lists_the_hosts_found(self):
        with self.assertRaises(RuntimeError) as ctx:
            select_fixtures(self.folder, "https://altro.hofj.com")
        message = str(ctx.exception)
        for text in ("https://altro.hofj.com", STAGING, PRODUCTION):
            self.assertIn(text, message)

    def test_only_catalog_json_files_are_considered(self):
        write_fixture(self.folder, "other.json", "https://altro.hofj.com")
        write_fixture(self.folder, "catalog-old.json.bak", "https://altro.hofj.com")
        with self.assertRaises(RuntimeError):
            select_fixtures(self.folder, "https://altro.hofj.com")

    def test_two_fixtures_of_the_same_brand_on_one_host_are_an_error(self):
        write_fixture(self.folder, "catalog-copy.json", PRODUCTION, brand="terrarossa.com")
        with self.assertRaises(RuntimeError) as ctx:
            select_fixtures(self.folder, PRODUCTION)
        self.assertIn("terrarossa.com", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
