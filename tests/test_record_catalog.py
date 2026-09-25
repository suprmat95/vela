import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import api_explore  # noqa: E402
import record_catalog  # noqa: E402


def item(pid, archived=False, **over):
    """Item della lista /v1/products come lo restituisce l'API (campi principali)."""
    base = {
        "id": str(pid), "slug": "padel-%d" % pid, "title": "Padel %d" % pid,
        "shortDescription": "breve", "description": "**lunga**", "archived": archived,
        "channelId": "1", "venueId": "194", "categoryId": "1", "destinationId": "17",
        "createdAt": "2026-03-09T09:26:05.776Z", "updatedAt": "2026-09-25T09:20:18.757Z",
        "publishedAt": "2026-03-10T11:54:04.217Z", "tripCode": "MKT_%d" % pid,
        "providerID": "t%07d" % pid, "price": 340, "currency": "EUR", "minPax": 2,
        "maxPax": None, "minDate": "2026-09-25", "maxDate": "2027-01-07",
        "defaultDurationInDays": 3, "hotelSelection": False, "locale": "it",
        "availabilities": [] if archived else [
            {"status": "Bookable", "startDate": "2026-09-28", "endDate": "2026-10-01",
             "serviceLevels": []}],
    }
    base.update(over)
    return base


def detail_of(list_item):
    """Dettaglio extended=true dello stesso prodotto, con i campi pesanti da scartare."""
    detail = dict(list_item)
    detail.update({
        "category": {"id": "1", "name": "Padel", "slug": "padel"},
        "venue": {"id": "194", "title": "Club", "slug": "club", "coverUrl": "https://x/v.jpg"},
        "destination": {"id": "17", "title": "Sinalunga", "slug": "sinalunga", "country": "IT",
                        "geohierarchy": "IT_123", "coverUrl": "https://x/d.jpg"},
        "image": {"url": "https://x/i.jpg", "width": 1, "height": 1},
        "gallery": [{"url": "https://x/g1.jpg", "source": "venue"}],
        "travelProgram": {"id": "733", "description": "...", "details": []},
        "rawAttributes": {
            "hotels": {"data": [{"id": 5, "attributes": {"name": "Hotel Uno",
                                                         "gallery": {"data": []}}}]},
            "gallery": {"data": [{"id": 1}]}, "cover": {"data": {"id": 2}},
            "playtomicLevel": "3",
        },
    })
    return detail


class StripMediaTest(unittest.TestCase):
    def test_removes_media_keys_at_any_depth_without_touching_input(self):
        detail = detail_of(item(12))
        out = record_catalog.strip_media(detail)
        for key in ("gallery", "image", "travelProgram"):
            self.assertNotIn(key, out)
        self.assertNotIn("gallery", out["rawAttributes"])
        self.assertNotIn("cover", out["rawAttributes"])
        hotel = out["rawAttributes"]["hotels"]["data"][0]["attributes"]
        self.assertEqual(hotel, {"name": "Hotel Uno"})
        self.assertEqual(out["venue"]["coverUrl"], "https://x/v.jpg")  # una stringa URL resta
        self.assertEqual(out["rawAttributes"]["playtomicLevel"], "3")
        self.assertIn("gallery", detail)  # l'originale non viene modificato

    def test_scalars_and_lists_pass_through(self):
        self.assertEqual(record_catalog.strip_media([1, {"gallery": 1, "a": 2}]), [1, {"a": 2}])
        self.assertIsNone(record_catalog.strip_media(None))


class ProjectDetailTest(unittest.TestCase):
    def test_keeps_rf28_fields_with_api_names(self):
        catalog = record_catalog.project_detail(detail_of(item(12)))
        self.assertEqual(sorted(catalog), sorted([
            "id", "title", "slug", "shortDescription", "price", "currency", "minPax", "maxPax",
            "minDate", "maxDate", "availabilities", "defaultDurationInDays", "updatedAt",
            "category", "venue", "destination", "hotels"]))
        self.assertEqual(catalog["category"]["slug"], "padel")
        self.assertEqual(catalog["destination"]["geohierarchy"], "IT_123")
        self.assertEqual(catalog["hotels"]["data"][0]["attributes"], {"name": "Hotel Uno"})
        self.assertEqual(catalog["price"], 340)

    def test_missing_fields_become_none(self):
        catalog = record_catalog.project_detail({"id": "1"})
        self.assertIsNone(catalog["venue"])
        self.assertIsNone(catalog["hotels"])
        self.assertIsNone(catalog["price"])


if __name__ == "__main__":
    unittest.main()
