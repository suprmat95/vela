"""Sorgente del catalogo sulle fixture (M10): la stessa porta del sync, senza rete."""
import json
import os
import tempfile
import unittest

from hofj_samples import detail_of, item
from vela.adapters.catalog_fixture import FixtureCatalogSource
from vela.domain.catalog import project_detail, strip_media
from vela.ports.hofj import ProductError


def write(folder, name, brand, items, details):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"base_url": "https://api.hofj.com", "locale": "it", "brand": brand,
                   "sport": "tennis", "products": items,
                   "details": {d["id"]: {"catalog": project_detail(d), "raw": strip_media(d)}
                               for d in details}}, fh)
    return path


class FixtureCatalogSourceTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.active, self.gone = item(12), item(13, archived=True)
        self.source = FixtureCatalogSource([
            write(folder, "catalog-tennis.json", "terrarossa.com", [self.active, self.gone],
                  [detail_of(self.active)]),
            write(folder, "catalog.json", "weebora.com", [item(20)], [detail_of(item(20))])])

    def test_one_page_per_brand_with_every_list_item(self):
        self.assertEqual(self.source.list_page("terrarossa.com", None), ([self.active, self.gone], None))
        self.assertEqual([i["id"] for i in self.source.list_page("weebora.com", None)[0]], ["20"])

    def test_detail_is_the_recorded_raw_detail(self):
        detail = self.source.detail("terrarossa.com", "12")
        self.assertEqual(detail, strip_media(detail_of(self.active)))
        self.assertEqual(project_detail(detail), project_detail(detail_of(self.active)))

    def test_unknown_brand_or_product(self):
        with self.assertRaises(ProductError):
            self.source.list_page("altro.com", None)
        with self.assertRaises(ProductError):
            self.source.detail("terrarossa.com", "20")


if __name__ == "__main__":
    unittest.main()
