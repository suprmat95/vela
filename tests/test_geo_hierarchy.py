import json
import os
import unittest

from vela.domain.geo import (COUNTRIES, PARENTS, PLACES, ancestors, common_region, country_area,
                             find_area, where)
from vela.domain.models import Area

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")
NAMES = {place[0] for place in PLACES}


class HierarchyTest(unittest.TestCase):
    def test_parents_are_known_places_of_the_same_country(self):
        by_name = {place[0]: place for place in PLACES}
        for child, parent in PARENTS.items():
            self.assertIn(child, NAMES)
            self.assertIn(parent, NAMES)
            self.assertEqual(by_name[child][2], by_name[parent][2], child)
            self.assertNotEqual(by_name[parent][1], "city", parent)

    def test_no_cycles(self):
        for name in PARENTS:
            seen, current = set(), name
            while current in PARENTS:
                self.assertNotIn(current, seen, "ciclo da %s" % name)
                seen.add(current)
                current = PARENTS[current]

    def test_ancestors(self):
        self.assertEqual([a.name for a in ancestors(find_area("Palma de Mallorca"))],
                         ["Palma de Mallorca", "Maiorca", "Baleari", "Spagna"])
        self.assertEqual([a.name for a in ancestors(find_area("Madrid"))], ["Madrid", "Spagna"])
        spain = Area("country", "Spagna", "ES")
        self.assertEqual(ancestors(spain), [spain])

    def test_common_region(self):
        self.assertEqual(common_region(find_area("Lanzarote"), find_area("Tenerife")).name, "Canarie")
        self.assertEqual(common_region(find_area("Palma"), find_area("Ibiza")).name, "Baleari")
        self.assertEqual(common_region(find_area("Firenze"), find_area("Pietrasanta")).name, "Toscana")
        self.assertIsNone(common_region(find_area("Madrid"), find_area("Valencia")))
        self.assertIsNone(common_region(find_area("Lanzarote"), Area("country", "Spagna", "ES")))

    def test_country_area(self):
        self.assertEqual(country_area("ES"), Area("country", "Spagna", "ES"))
        self.assertIsNone(country_area(None))
        self.assertIsNone(country_area("ZZ"))

    def test_where(self):
        self.assertEqual(where(find_area("Spagna")), "in Spagna")
        self.assertEqual(where(find_area("Lanzarote")), "a Lanzarote")
        self.assertEqual(where(find_area("Canarie")), "alle Canarie")
        self.assertEqual(where(find_area("Baleari")), "alle Baleari")
        self.assertEqual(where(find_area("Sardegna")), "in Sardegna")
        self.assertEqual(where(find_area("Toscana")), "in Toscana")


@unittest.skipUnless(os.path.exists(FIXTURE), "fixture assente")
class FixtureHierarchyTest(unittest.TestCase):
    def test_every_fixture_destination_climbs_to_its_country(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            data = json.load(fh)
        for detail in data["details"].values():
            dest = detail["catalog"].get("destination") or {}
            title, country = dest.get("title"), dest.get("country")
            if not title or title == "Weebora":
                continue
            chain = ancestors(find_area(title))
            self.assertEqual(chain[-1], Area("country", COUNTRIES[country], country), title)


class M9RegionsTest(unittest.TestCase):
    """Le regioni aggiunte da M9 contengono le città del catalogo e hanno la preposizione giusta."""

    def test_catalog_cities_sit_in_their_region(self):
        cases = [("Malaga", "Andalusia"), ("Estepona", "Costa del Sol"), ("Siviglia", "Andalusia"),
                 ("Barcellona", "Catalogna"), ("Tarragona", "Catalogna"),
                 ("Valencia", "Comunità Valenciana"), ("Dénia", "Comunità Valenciana"),
                 ("Milano", "Lombardia"), ("Venezia", "Veneto"), ("Riccione", "Emilia-Romagna"),
                 ("Cap d'Agde", "Occitania")]
        for city, region in cases:
            with self.subTest(city=city):
                names = [a.name for a in ancestors(find_area(city))]
                self.assertIn(region, names)
                self.assertEqual(names[-1], COUNTRIES[find_area(city).country_code])

    def test_region_prepositions(self):
        self.assertEqual(where(Area("region", "Andalusia", "ES")), "in Andalusia")
        self.assertEqual(where(Area("region", "Costa del Sol", "ES")), "sulla Costa del Sol")
        self.assertEqual(where(Area("region", "Comunità Valenciana", "ES")),
                         "nella Comunità Valenciana")
        self.assertEqual(where(Area("region", "Emilia-Romagna", "IT")), "in Emilia-Romagna")
        self.assertEqual(where(Area("region", "Costa del Sol", "ES"), "en"), "on the Costa del Sol")
        self.assertEqual(where(Area("region", "Comunità Valenciana", "ES"), "en"),
                         "in the Valencian Community")

