"""M21-B (UC-B): ordinamento di RF-60 e prodotti equivalenti di RF-61 in `chooser.choose`."""
import unittest
from dataclasses import replace
from datetime import date

from support import TODAY, make_product
from vela.domain.chooser import FILTERS, Choice, NoChoice, choose
from vela.domain.models import Area, Criteria, Period

OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, budget=None)
    base.update(kw)
    return Criteria(**base)


def twin(pid, price, **kw):
    """Un prodotto della stessa famiglia del 78: stesso hotel, titolo e destinazione."""
    fields = dict(price=price, hotel="Hotel Firenze", title="Padel a Firenze", destination="Firenze",
                  country="IT")
    fields.update(kw)
    return make_product(pid, **fields)


def chosen(products, criteria=None, rejected=(), **kw):
    r = choose(products, criteria or crit(), set(rejected), TODAY, **kw)
    assert isinstance(r, Choice), r
    return r.product.id


class EquivalentProductsTest(unittest.TestCase):
    """RF-61: stesso hotel, stesso titolo normalizzato, stessa destinazione, prezzo entro il 5%:
    un solo candidato, quello con l'id numerico più basso. La trappola 900078 non vince sul 78."""

    def test_grouping_is_not_a_filter(self):
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "price",
                                   "rejected"))

    def test_trap_with_a_lower_price_loses_to_the_lowest_id(self):
        self.assertEqual(chosen([twin(900078, 499), twin(78, 500)]), "78")
        self.assertEqual(chosen([twin(78, 500), twin(900078, 499)]), "78")

    def test_price_tolerance_is_five_percent_of_the_anchor_price(self):
        # anchor = id più basso (78, 500 euro): 475 sta nel 5%, 474 no
        self.assertEqual(chosen([twin(78, 500), twin(900078, 475)]), "78")
        self.assertEqual(chosen([twin(78, 500), twin(900078, 474)]), "900078")   # più economico
        self.assertEqual(chosen([twin(78, 500), twin(900078, 525)]), "78")
        self.assertEqual(chosen([twin(78, 500), twin(900078, 526)]), "78")       # non equivalente, più caro

    def test_no_transitive_chains(self):
        """104 sta nel 5% di 100, 108 nel 5% di 104 ma non di 100: 108 resta un candidato e vince
        sulla durata (un weekend, gli altri due una settimana). A catena sarebbe uscito col 104."""
        week = (("2026-10-01", "2026-10-08"),)
        products = [replace(twin(1, 100, windows=week), duration_days=8),
                    replace(twin(2, 104, windows=week), duration_days=8), twin(3, 108)]
        weekend = crit(duration_min_nights=1, duration_max_nights=3)
        self.assertEqual(chosen(products, weekend), "3")
        self.assertEqual(chosen(products, weekend, rejected={"3"}), "1")
        self.assertEqual(chosen(products, weekend, rejected={"1", "3"}), "2")   # dopo i filtri
        self.assertEqual(choose(products, weekend, {"1", "2", "3"}, TODAY), NoChoice("rejected"))

    def test_different_hotel_title_or_destination_is_not_equivalent(self):
        for other in (twin(900078, 499, hotel="Hotel Duomo"),
                      twin(900078, 499, title="Padel a Firenze, edizione autunno"),
                      twin(900078, 499, destination="Fiesole")):
            with self.subTest(other=other):
                self.assertEqual(chosen([twin(78, 500), other]), "900078")   # più economico

    def test_title_is_compared_lowercase_without_double_spaces(self):
        self.assertEqual(chosen([twin(78, 500, title="  PADEL a   Firenze "), twin(900078, 499)]), "78")

    def test_products_without_a_hotel_are_equivalent_to_each_other(self):
        """Il 78 di staging non ha hotel: la sua trappola nemmeno, e devono raggrupparsi."""
        self.assertEqual(chosen([twin(78, 500, hotel=None), twin(900078, 499, hotel=None)]), "78")
        self.assertEqual(chosen([twin(78, 500, hotel=None), twin(900078, 499)]), "900078")

    def test_grouping_happens_after_the_hard_filters(self):
        """Se il 78 esce dai filtri (rifiutato, archiviato, non prenotabile) l'equivalente resta."""
        self.assertEqual(chosen([twin(78, 500), twin(900078, 499)], rejected={"78"}), "900078")
        self.assertEqual(chosen([twin(78, 500, archived=True), twin(900078, 499)]), "900078")
        self.assertEqual(chosen([twin(78, 500, bookable=False), twin(900078, 499)]), "900078")

    def test_equivalents_of_a_rejected_product_are_still_proposed(self):
        """Solo il prodotto rifiutato è escluso; l'esclusione per hotel è RF-72 (M21-F)."""
        seen = []
        rejected = set()
        products = [twin(78, 500), twin(900078, 499),
                    make_product(3, price=700, country="IT", destination="Firenze")]
        while isinstance(r := choose(products, crit(), rejected, TODAY), Choice):
            seen.append(r.product.id)
            rejected.add(r.product.id)
        self.assertEqual(seen, ["78", "900078", "3"])

    def test_non_numeric_ids_sort_after_numeric_ones_as_strings(self):
        """Decisione M10: gli id potrebbero avere prefissi (`t:`, `p:`); mai un'eccezione."""
        self.assertEqual(chosen([twin(100, 500), twin(78, 500)]), "78")   # numerico, non "100" < "78"
        self.assertEqual(chosen([twin("t:7", 500), twin(78, 500)]), "78")
        self.assertEqual(chosen([twin("t:b", 500), twin("t:a", 500)]), "t:a")
        self.assertEqual(chosen([twin("p:9", 500), twin("t:10", 500)]), "p:9")


if __name__ == "__main__":
    unittest.main()
