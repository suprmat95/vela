import json
import os
import unittest

from vela.domain.geo import COUNTRIES, area_of_destination, find_area
from vela.domain.models import Area

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")


class FindAreaTest(unittest.TestCase):
    def test_country_it_and_en(self):
        self.assertEqual(find_area("un weekend di padel in Spagna"), Area("country", "Spagna", "ES"))
        self.assertEqual(find_area("a padel weekend in Spain"), Area("country", "Spagna", "ES"))

    def test_city_alias(self):
        self.assertEqual(find_area("padel a Barcelona"), Area("city", "Barcellona", "ES"))
        self.assertEqual(find_area("tennis in Tuscany"), Area("region", "Toscana", "IT"))

    def test_longest_alias_wins(self):
        self.assertEqual(find_area("Palma de Mallorca in ottobre").name, "Palma de Mallorca")

    def test_place_beats_country(self):
        self.assertEqual(find_area("Lanzarote, Spagna").name, "Lanzarote")

    def test_word_boundaries(self):
        self.assertIsNone(find_area("baliamo tutta la notte"))
        self.assertIsNone(find_area("nessun posto"))

    def test_case_insensitive(self):
        self.assertEqual(find_area("SPAGNA").country_code, "ES")


class AreaOfDestinationTest(unittest.TestCase):
    def test_known_title(self):
        self.assertEqual(area_of_destination("Maiorca", "ES"), Area("region", "Maiorca", "ES"))

    def test_unknown_title_falls_back_to_country(self):
        self.assertEqual(area_of_destination("Weebora", "IT"), Area("country", "Italia", "IT"))

    def test_nothing(self):
        self.assertIsNone(area_of_destination(None, None))


@unittest.skipUnless(os.path.exists(FIXTURE), "fixture assente")
class FixtureCoverageTest(unittest.TestCase):
    SKIP = {"Weebora"}   # destinazione fittizia del brand, senza luogo

    def test_every_fixture_destination_resolves(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            data = json.load(fh)
        for detail in data["details"].values():
            dest = detail["catalog"].get("destination") or {}
            title, country = dest.get("title"), dest.get("country")
            if not title or title in self.SKIP:
                continue
            area = find_area(title)
            self.assertIsNotNone(area, "destinazione non in geo.py: %r" % title)
            self.assertEqual(area.country_code, country, title)
            self.assertIn(country, COUNTRIES)
