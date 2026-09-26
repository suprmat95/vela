import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain.catalog import detect_sport, load_fixture, product_from_entry

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

ENTRY = {
    "id": "181", "title": "Magnifico Padel a Lanzarote ", "slug": "magnifico-padel-a-lanzarote",
    "shortDescription": "Weekend di lusso", "price": 578, "currency": "EUR",
    "minPax": None, "maxPax": None, "minDate": "2026-09-25", "maxDate": "2026-12-29",
    "availabilities": [{"status": "Bookable", "startDate": "2026-10-08", "endDate": "2026-10-11"},
                       {"status": "Bookable", "startDate": "2026-10-01", "endDate": "2026-10-04"}],
    "defaultDurationInDays": 4, "updatedAt": "2026-09-25T10:44:12.537Z",
    "category": {"id": "8", "name": "Vacanze", "slug": "vacanze"},
    "venue": {"id": "492", "title": "TocaHub Lanzarote"},
    "destination": {"id": "284", "title": "Lanzarote", "country": "ES"},
    "hotels": {"data": [{"id": 204, "attributes": {"name": "THB Lanzarote Beach "}}]},
}


class DetectSportTest(unittest.TestCase):
    def test_padel_in_title(self):
        self.assertEqual(detect_sport("Magnifico Padel a Lanzarote", "slug"), "padel")

    def test_tennis_in_description_only(self):
        self.assertEqual(detect_sport("TODA Sinalunga", "toda-sinalunga", "", "Tre giorni di tennis"),
                         "tennis")

    def test_first_text_wins(self):
        self.assertEqual(detect_sport("Padel camp", "", "", "vicino ai campi da tennis"), "padel")

    def test_unknown_is_padel(self):
        self.assertEqual(detect_sport("Champagne weekend", "rcr-premium", None, None), "padel")


class ProductFromEntryTest(unittest.TestCase):
    def test_maps_fields(self):
        p = product_from_entry(ENTRY, archived=False, raw={"k": 1}, fetched_at=NOW)
        self.assertEqual(p.id, "181")
        self.assertEqual(p.title, "Magnifico Padel a Lanzarote")
        self.assertEqual(p.sport, "padel")
        self.assertEqual(p.category, "Vacanze")
        self.assertEqual((p.destination, p.country, p.venue), ("Lanzarote", "ES", "TocaHub Lanzarote"))
        self.assertEqual(p.hotel, "THB Lanzarote Beach")
        self.assertEqual(p.price, Decimal("578"))
        self.assertEqual((p.min_date, p.max_date), (date(2026, 9, 25), date(2026, 12, 29)))
        self.assertEqual([a.start for a in p.availabilities], [date(2026, 10, 1), date(2026, 10, 8)])
        self.assertEqual(p.duration_days, 4)
        self.assertEqual(p.raw, {"k": 1})
        self.assertTrue(p.bookable)
        self.assertFalse(p.archived)

    def test_missing_destination_venue_hotel(self):
        entry = dict(ENTRY, destination=None, venue=None, hotels={"data": []}, minPax=2, maxPax=0)
        p = product_from_entry(entry, archived=True, raw={}, fetched_at=NOW)
        self.assertIsNone(p.destination)
        self.assertIsNone(p.country)
        self.assertIsNone(p.venue)
        self.assertIsNone(p.hotel)
        self.assertEqual((p.min_pax, p.max_pax), (2, 0))
        self.assertTrue(p.archived)

    def test_list_item_without_detail_fields(self):
        entry = {k: v for k, v in ENTRY.items() if k not in ("category", "venue", "destination", "hotels")}
        p = product_from_entry(entry, archived=True, raw=entry, fetched_at=NOW)
        self.assertIsNone(p.category)
        self.assertEqual(p.sport, "padel")


@unittest.skipUnless(os.path.exists(FIXTURE), "fixture assente")
class LoadFixtureTest(unittest.TestCase):
    def test_loads_all_products_with_archived_flag(self):
        products = load_fixture(FIXTURE, fetched_at=NOW)
        self.assertEqual(len(products), 110)
        active = [p for p in products if not p.archived]
        self.assertEqual(len(active), 77)
        self.assertTrue(all(p.raw for p in active))
        self.assertTrue(all(p.sport in ("padel", "tennis") for p in products))
        self.assertTrue(all(p.fetched_at == NOW for p in products))
        by_id = {p.id: p for p in products}
        self.assertEqual(by_id["181"].hotel, "THB Lanzarote Beach")


class IsTripTest(unittest.TestCase):
    def test_brand_destination_and_gift_card_slug_are_not_trips(self):
        from dataclasses import replace
        from support import make_product
        from vela.domain.catalog import is_trip
        self.assertTrue(is_trip(make_product(1)))
        self.assertFalse(is_trip(make_product(2, destination="Weebora", country="IT")))
        self.assertFalse(is_trip(replace(make_product(3), slug="weebora-gift-card")))
        self.assertTrue(is_trip(make_product(4, destination=None, country=None)))

    def test_gift_card_of_any_brand_is_not_a_trip(self):
        from support import make_product
        from vela.domain.catalog import is_trip
        self.assertFalse(is_trip(make_product(1, slug="giftcard", destination="Roma")))
        self.assertFalse(is_trip(make_product(2, slug="terrarossa-gift", destination="Roma",
                                              title="Terrarossa Gift Card")))
        self.assertFalse(is_trip(make_product(3, destination="Terrarossa", country="IT",
                                              brand="terrarossa.com")))
        self.assertTrue(is_trip(make_product(4, title="Giftcard a parte, tennis a Roma",
                                             slug="tennis-roma")))
