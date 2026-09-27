"""Chooser e rifiuti di M21-F: luoghi esclusi (RF-73), hotel rifiutato (RF-72), stesso prodotto con
altre date (RF-74)."""
import unittest
from dataclasses import replace
from datetime import date

from support import make_product
from vela.domain.chooser import (FILTERS, Choice, NoChoice, cheapest_total, choose, departure,
                                 hotel_key)
from vela.domain.models import Area, Criteria, Period

TODAY = date(2026, 9, 26)
OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")
ESTEPONA = Area("city", "Estepona", "ES")
CRITERIA = Criteria("padel", SPAIN, OCTOBER, 2)


def pick(products, criteria=CRITERIA, rejected=(), **kw):
    return choose(products, criteria, set(rejected), today=TODAY, **kw)


class FiltersTest(unittest.TestCase):
    def test_place_and_hotel_come_after_level_and_before_price(self):
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "rooms",
                                   "level", "place", "hotel", "price", "rejected"))


class ExcludedAreasTest(unittest.TestCase):
    """RF-73: filtro duro; un'area esclusa esclude anche i luoghi che contiene."""

    def test_excluded_city_leaves_the_rest_of_the_country(self):
        products = [make_product(1, price=300, destination="Estepona"),
                    make_product(2, price=400, destination="Valencia")]
        self.assertEqual(pick(products).product.id, "1")
        c = replace(CRITERIA, excluded_areas=(ESTEPONA,))
        self.assertEqual(pick(products, c).product.id, "2")

    def test_excluded_region_excludes_its_cities(self):
        products = [make_product(1, price=300, destination="Malaga"),
                    make_product(2, price=310, destination="Marbella"),
                    make_product(3, price=400, destination="Valencia")]
        c = replace(CRITERIA, excluded_areas=(Area("region", "Costa del Sol", "ES"),))
        self.assertEqual(pick(products, c).product.id, "3")

    def test_excluded_country_excludes_products_without_a_known_place(self):
        products = [make_product(1, destination=None, title="Padel camp"),
                    make_product(2, destination="Firenze", country="IT")]
        c = replace(CRITERIA, area=None, excluded_areas=(SPAIN,))
        self.assertEqual(pick(products, c).product.id, "2")

    def test_nothing_left_is_place(self):
        products = [make_product(1, destination="Estepona")]
        c = replace(CRITERIA, excluded_areas=(ESTEPONA,))
        self.assertEqual(pick(products, c), NoChoice("place"))

    def test_cheapest_total_respects_the_excluded_areas(self):
        products = [make_product(1, price=100, destination="Estepona"),
                    make_product(2, price=300, destination="Valencia")]
        c = replace(CRITERIA, excluded_areas=(ESTEPONA,))
        self.assertEqual(cheapest_total(products, c, TODAY), 600)


class HotelTest(unittest.TestCase):
    """RF-72: dopo un rifiuto `hotel` escono tutti i prodotti con lo stesso hotel (nome
    normalizzato); senza hotel, quelli con lo stesso titolo e la stessa destinazione."""

    def test_same_hotel_is_excluded_whatever_the_case_and_spaces(self):
        products = [make_product(1, price=300, hotel="Hotel  Sole"),
                    make_product(2, price=320, hotel="hotel sole", destination="Valencia"),
                    make_product(3, price=500, hotel="Hotel Luna")]
        result = pick(products, rejected={"1"}, hotel_rejected={"1"})
        self.assertEqual(result.product.id, "3")

    def test_without_hotel_rejection_the_same_hotel_stays(self):
        products = [make_product(1, price=300), make_product(2, price=320, destination="Valencia"),
                    make_product(3, price=500, hotel="Hotel Luna")]
        self.assertEqual(pick(products, rejected={"1"}).product.id, "2")

    def test_nothing_left_is_hotel(self):
        products = [make_product(1, price=300), make_product(2, price=320, destination="Valencia")]
        self.assertEqual(pick(products, rejected={"1"}, hotel_rejected={"1"}), NoChoice("hotel"))

    def test_product_without_hotel_excludes_the_same_trip_at_any_price(self):
        same = dict(hotel=None, title="Padel Camp", destination="Firenze", country="IT")
        products = [make_product(78, price=250, **same), make_product(900078, price=100, **same),
                    make_product(5, price=900, hotel=None, title="Altro camp", destination="Firenze",
                                 country="IT")]
        c = replace(CRITERIA, area=None)
        self.assertEqual(pick(products, c, rejected={"78"}).product.id, "900078")
        self.assertEqual(pick(products, c, rejected={"78"}, hotel_rejected={"78"}).product.id, "5")

    def test_hotel_key(self):
        self.assertEqual(hotel_key(make_product(1, hotel=" Hotel  SOLE ")), ("hotel", "hotel sole"))
        self.assertEqual(hotel_key(make_product(1, hotel=None, title="Camp  X", destination="Roma")),
                         ("trip", "camp x", "Roma"))


class KeptWindowsTest(unittest.TestCase):
    """RF-74: il prodotto resta candidato senza le finestre già rifiutate."""
    WINDOWS = (("2026-10-01", "2026-10-04"), ("2026-10-08", "2026-10-11"), ("2026-10-15", "2026-10-18"))

    def test_fixed_windows_move_to_the_next_departure(self):
        product = make_product(1, windows=self.WINDOWS)
        first = (date(2026, 10, 1), date(2026, 10, 4))
        second = (date(2026, 10, 8), date(2026, 10, 11))
        third = (date(2026, 10, 15), date(2026, 10, 18))
        self.assertEqual(departure(product, OCTOBER, TODAY), first)
        self.assertEqual(departure(product, OCTOBER, TODAY, (first,)), second)
        self.assertEqual(departure(product, OCTOBER, TODAY, (first, second)), third)
        self.assertIsNone(departure(product, OCTOBER, TODAY, (first, second, third)))

    def test_open_window_restarts_where_the_excluded_trip_ends(self):
        product = make_product(1, windows=(("2026-10-01", "2026-10-31"),))   # durata 4 giorni
        first = departure(product, OCTOBER, TODAY)
        self.assertEqual(first, (date(2026, 10, 1), date(2026, 10, 4)))
        self.assertEqual(departure(product, OCTOBER, TODAY, (first,)), (date(2026, 10, 4), date(2026, 10, 7)))

    def test_choose_uses_the_kept_windows(self):
        products = [make_product(1, windows=self.WINDOWS)]
        kept = {"1": ((date(2026, 10, 1), date(2026, 10, 4)),)}
        result = pick(products, kept_windows=kept)
        self.assertIsInstance(result, Choice)
        self.assertEqual((result.start_date, result.end_date), (date(2026, 10, 8), date(2026, 10, 11)))

    def test_no_departure_left_is_dates(self):
        products = [make_product(1)]
        kept = {"1": ((date(2026, 10, 1), date(2026, 10, 4)),)}
        self.assertEqual(pick(products, kept_windows=kept), NoChoice("dates"))


if __name__ == "__main__":
    unittest.main()
