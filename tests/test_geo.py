import json
import os
import unittest

from vela.domain.geo import (COUNTRIES, NORTH_OF, SOUTH_OF, area_by_name, area_of_destination,
                             display_name, find_area, move)
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


class RegionTest(unittest.TestCase):
    def test_regions_it_and_en(self):
        self.assertEqual(find_area("padel in Andalusia"), Area("region", "Andalusia", "ES"))
        self.assertEqual(find_area("tennis in Catalonia"), Area("region", "Catalogna", "ES"))
        self.assertEqual(find_area("Emilia Romagna"), Area("region", "Emilia-Romagna", "IT"))
        self.assertEqual(find_area("in Lombardy"), Area("region", "Lombardia", "IT"))

    def test_valencian_community_is_not_valencia(self):
        self.assertEqual(find_area("Comunità Valenciana").name, "Comunità Valenciana")
        self.assertEqual(find_area("Valencia").name, "Valencia")


class NamesTest(unittest.TestCase):
    def test_area_by_name(self):
        self.assertEqual(area_by_name("Spagna"), Area("country", "Spagna", "ES"))
        self.assertEqual(area_by_name("Malaga"), Area("city", "Malaga", "ES"))
        self.assertEqual(area_by_name("Canarie"), Area("region", "Canarie", "ES"))
        self.assertIsNone(area_by_name("Atlantide"))

    def test_display_name(self):
        self.assertEqual(display_name(Area("country", "Spagna", "ES"), "en"), "Spain")
        self.assertEqual(display_name(Area("country", "Spagna", "ES"), "it"), "Spagna")
        self.assertEqual(display_name(Area("city", "Barcellona", "ES"), "en"), "Barcelona")
        self.assertEqual(display_name(Area("region", "Lanzarote", "ES"), "en"), "Lanzarote")


class DirectionTest(unittest.TestCase):
    def test_tables_only_name_known_areas(self):
        for table in (SOUTH_OF, NORTH_OF):
            for key, targets in table.items():
                self.assertIsNotNone(area_by_name(key), key)
                for target in targets:
                    self.assertIsNotNone(area_by_name(target), "%s → %s" % (key, target))
                    self.assertNotEqual(target, key)

    def test_place_entry_wins(self):
        self.assertEqual(move(Area("city", "Valencia", "ES"), "south"), Area("city", "Alicante", "ES"))
        self.assertEqual(move(Area("city", "Valencia", "ES"), "north"), Area("city", "Tarragona", "ES"))

    def test_falls_back_to_country(self):
        self.assertEqual(move(Area("city", "Malaga", "ES"), "south"), Area("country", "Marocco", "MA"))
        self.assertEqual(move(Area("city", "Milano", "IT"), "north"), Area("country", "Francia", "FR"))

    def test_empty_entry_stops(self):
        self.assertIsNone(move(Area("region", "Lanzarote", "ES"), "south"))
        self.assertIsNone(move(Area("city", "Reims", "FR"), "north"))

    def test_unknown(self):
        self.assertIsNone(move(Area("city", "Buenos Aires", "AR"), "north"))
        self.assertIsNone(move(None, "south"))


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

    def test_every_fixture_destination_slug_resolves(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            data = json.load(fh)
        for detail in data["details"].values():
            dest = detail["catalog"].get("destination") or {}
            slug, country = dest.get("slug"), dest.get("country")
            if not slug or dest.get("title") in self.SKIP:
                continue
            area = find_area(slug.replace("-", " "))
            self.assertIsNotNone(area, "slug non in geo.py: %r" % slug)
            self.assertEqual(area.country_code, country, slug)
