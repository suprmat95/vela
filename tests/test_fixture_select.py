"""Scelta della fixture del catalogo per ambiente (decisione M7): `base_url` della fixture = HOFJ_BASE_URL."""
import json
import os
import tempfile
import unittest

from vela.domain.catalog import fixture_meta, select_fixture

STAGING = "https://staging.api.hofj.com"
PRODUCTION = "https://api.hofj.com"


def write_fixture(folder, name, base_url, locale="it", brand=None):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"recorded_at": "2026-09-25T12:00:00+00:00", "locale": locale, "brand": brand,
                   "base_url": base_url, "products": [], "details": {}}, fh)
    return path


class FixtureMetaTest(unittest.TestCase):
    def test_reads_base_url_locale_and_brand(self):
        folder = tempfile.mkdtemp()
        path = write_fixture(folder, "catalog-staging.json", STAGING, "en", "staging.weebora.com")
        self.assertEqual(fixture_meta(path), {"base_url": STAGING, "locale": "en",
                                              "brand": "staging.weebora.com"})


class SelectFixtureTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.production = write_fixture(self.folder, "catalog.json", PRODUCTION)
        self.staging = write_fixture(self.folder, "catalog-staging.json", STAGING, "en")

    def test_picks_the_fixture_recorded_on_that_host(self):
        self.assertEqual(select_fixture(self.folder, STAGING), self.staging)
        self.assertEqual(select_fixture(self.folder, PRODUCTION), self.production)

    def test_trailing_slash_does_not_matter(self):
        self.assertEqual(select_fixture(self.folder, STAGING + "/"), self.staging)
        write_fixture(self.folder, "catalog-sandbox.json", "https://sandbox.api.hofj.com/")
        self.assertEqual(select_fixture(self.folder, "https://sandbox.api.hofj.com"),
                         os.path.join(self.folder, "catalog-sandbox.json"))

    def test_no_match_lists_the_hosts_found(self):
        with self.assertRaises(RuntimeError) as ctx:
            select_fixture(self.folder, "https://altro.hofj.com")
        message = str(ctx.exception)
        for text in ("https://altro.hofj.com", STAGING, PRODUCTION):
            self.assertIn(text, message)

    def test_only_catalog_json_files_are_considered(self):
        write_fixture(self.folder, "other.json", "https://altro.hofj.com")
        write_fixture(self.folder, "catalog-old.json.bak", "https://altro.hofj.com")
        with self.assertRaises(RuntimeError):
            select_fixture(self.folder, "https://altro.hofj.com")


if __name__ == "__main__":
    unittest.main()
