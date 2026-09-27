"""M21-B (UC-B): ordinamento di RF-60 e prodotti equivalenti di RF-61 in `chooser.choose`."""
import random
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

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
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "rooms", "price",
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


def prod(pid, start="2026-10-01", nights=3, featured=False, special_offer=False, **kw):
    """Prodotto a finestra fissa: parte `start`, dura `nights` notti; Lanzarote (ES) di default."""
    first = date.fromisoformat(start)
    end = date.fromordinal(first.toordinal() + nights).isoformat()
    p = make_product(pid, windows=((start, end),), **kw)
    return replace(p, duration_days=nights + 1, featured=featured, special_offer=special_offer)


WEEKEND = dict(duration_min_nights=1, duration_max_nights=3)


class OrderingLevelsTest(unittest.TestCase):
    """RF-60: coppie di prodotti che differiscono per un solo livello dell'ordine; il perdente
    è migliore su tutti i livelli successivi, così il test prova la precedenza."""

    LEVELS = [
        ("1 area", crit(),
         prod(1, start="2026-10-10"),
         prod(2, start="2026-10-01", price=100, featured=True, country="IT", destination="Riccione")),
        ("2 entro budget", crit(budget=Decimal("1000")),
         prod(1, start="2026-10-10", price=450),                      # 900 entro
         prod(2, start="2026-10-01", price=600, featured=True)),      # 1200 oltre
        ("3 durata", crit(**WEEKEND),
         prod(1, start="2026-10-10"),
         prod(2, start="2026-10-01", nights=7, price=100, featured=True)),
        # 4 livello e lezioni: neutro fino a M21-C (RF-62..64)
        ("5 partenza", crit(),
         prod(1, start="2026-10-05"),
         prod(2, start="2026-10-20", price=100, featured=True)),
        ("6 featured", crit(),
         prod(1, featured=True),
         prod(2, price=100)),
        ("6 offerta speciale", crit(),
         prod(1, special_offer=True),
         prod(2, price=100)),
        ("7 prezzo", crit(),
         prod(2, price=300),
         prod(1, price=500)),
        ("8 id numerico", crit(),
         prod(78, hotel="Hotel A"),
         prod(100, hotel="Hotel B")),
        ("8 id non numerico dopo", crit(),
         prod(9, hotel="Hotel A"),
         prod("t:1", hotel="Hotel B")),
    ]

    def test_each_level_beats_the_next_ones(self):
        for name, criteria, winner, loser in self.LEVELS:
            with self.subTest(name):
                self.assertEqual(chosen([loser, winner], criteria), winner.id)
                self.assertEqual(chosen([winner, loser], criteria), winner.id)
                self.assertEqual(chosen([loser, winner], criteria, rejected={winner.id}), loser.id)

    def test_without_budget_the_closest_departure_beats_a_cheaper_later_one(self):
        """UC-B: parte il 2 novembre batte parte il 25 anche se costa di più."""
        november = Period(date(2026, 11, 1), date(2026, 11, 30), "novembre")
        early = prod(1, start="2026-11-02", price=400)
        late = prod(2, start="2026-11-25", price=250)
        r = choose([late, early], crit(period=november), set(), TODAY)
        self.assertEqual((r.product.id, r.start_date), ("1", date(2026, 11, 2)))

    def test_without_period_the_departure_closest_to_today_wins(self):
        fixed = prod(1, start="2026-10-10", price=100)
        open_window = replace(make_product(2, price=500, windows=(("2026-09-20", "2026-12-31"),)),
                              duration_days=4)
        r = choose([fixed, open_window], crit(period=None), set(), TODAY)
        self.assertEqual((r.product.id, r.start_date), ("2", TODAY))

    def test_featured_beats_a_lower_price_only_when_levels_one_to_five_tie(self):
        self.assertEqual(chosen([prod(1, featured=True), prod(2, price=100)]), "1")
        self.assertEqual(chosen([prod(1, featured=True, start="2026-10-02"), prod(2, price=100)]), "2")

    def test_same_inputs_always_give_the_same_choice(self):
        products = [prod(1, start="2026-10-05"), prod(2, price=100, featured=True, start="2026-10-05"),
                    prod(3, price=100, start="2026-10-05", hotel="Hotel B"), prod(4, start="2026-10-20"),
                    prod(5, price=90, country="IT", destination="Firenze"), prod(6, price=100)]
        first = choose(products, crit(), set(), TODAY)
        for seed in range(20):
            shuffled = list(products)
            random.Random(seed).shuffle(shuffled)
            r = choose(shuffled, crit(), set(), TODAY)
            self.assertEqual((r.product.id, r.start_date, r.reason),
                             (first.product.id, first.start_date, first.reason), seed)
        self.assertEqual(first.product.id, "6")   # 1 ottobre, prezzo 100: batte il 2 (5 ottobre, featured)


class ReasonTest(unittest.TestCase):
    """RF-06: la motivazione spiega il livello che ha deciso e non dice più "la più economica"
    quando un prodotto più economico ha perso sulla partenza o su `featured`."""

    def reason(self, products, criteria=None):
        return choose(products, criteria or crit(), set(), TODAY).reason

    def test_first_departure_in_the_period_over_a_cheaper_later_one(self):
        r = self.reason([prod(1, start="2026-10-05"), prod(2, start="2026-10-20", price=100)])
        self.assertEqual(r, "È a Lanzarote, in Spagna come hai chiesto. Parte il 5 ottobre 2026, la prima "
                            "partenza nel periodo che hai chiesto, con un totale a partire da 1000 euro.")

    def test_first_departure_in_english(self):
        r = self.reason([prod(1, start="2026-10-05"), prod(2, start="2026-10-20", price=100)],
                        crit(language="en"))
        self.assertEqual(r, "It's in Lanzarote, in Spain as you asked. It leaves on 5 October 2026, the "
                            "first departure in the period you asked for, with a total starting at "
                            "1000 euros.")

    def test_earliest_departure_without_a_period(self):
        products = [prod(1, start="2026-10-05"), prod(2, start="2026-10-20", price=100)]
        self.assertIn("Parte il 5 ottobre 2026, la prima partenza disponibile, con un totale",
                      self.reason(products, crit(period=None)))
        self.assertIn("It leaves on 5 October 2026, the earliest departure available, with a total",
                      self.reason(products, crit(period=None, language="en")))

    def test_first_departure_with_a_budget(self):
        products = [prod(1, start="2026-10-05"), prod(2, start="2026-10-20", price=100)]
        self.assertTrue(self.reason(products, crit(budget=Decimal("1500"))).endswith(
            "la prima partenza nel periodo che hai chiesto, con un totale a partire da 1000 euro, "
            "dentro il tuo budget di 1500 euro."))
        over = self.reason(products, crit(budget=Decimal("100")))
        self.assertTrue(over.endswith("con un totale a partire da 1000 euro, oltre il tuo budget di 100 euro."), over)
        self.assertNotIn("più economica", over)

    def test_no_cheapest_claim_without_area_when_departure_decided(self):
        r = self.reason([prod(1, start="2026-10-05"), prod(2, start="2026-10-20", price=100)],
                        crit(area=None))
        self.assertEqual(r, "È a Lanzarote. Parte il 5 ottobre 2026, la prima partenza nel periodo che "
                            "hai chiesto, con un totale a partire da 1000 euro.")

    def test_featured_over_a_cheaper_product_with_the_same_departure(self):
        products = [prod(1, featured=True), prod(2, price=100)]
        self.assertEqual(self.reason(products),
                         "È a Lanzarote, in Spagna come hai chiesto. Parte il 1 ottobre 2026, nel periodo "
                         "che hai chiesto, con un totale a partire da 1000 euro, ed è tra i viaggi in "
                         "evidenza del catalogo.")
        self.assertTrue(self.reason(products, crit(language="en")).endswith(
            "with a total starting at 1000 euros, and it's one of the catalogue's featured trips."))
        self.assertTrue(self.reason(products, crit(budget=Decimal("100"))).endswith(
            "oltre il tuo budget di 100 euro, ma è tra i viaggi in evidenza del catalogo."))
        self.assertTrue(self.reason(products, crit(area=None)).endswith(
            "con un totale a partire da 1000 euro, ed è tra i viaggi in evidenza del catalogo."))

    def test_cheapest_claim_stays_when_it_is_true(self):
        products = [prod(1, price=300), prod(2, price=320), prod(3, start="2026-10-05", price=350)]
        self.assertEqual(self.reason(products, crit(area=None)),
                         "È a Lanzarote. Parte il 1 ottobre 2026, nel periodo che hai chiesto, ed è la più "
                         "economica compatibile.")

    def test_departure_and_featured_together(self):
        """Un più economico perso sulla partenza e uno su `featured`: la frase dice tutti e due."""
        products = [prod(1, featured=True), prod(2, price=100), prod(3, start="2026-10-20", price=100)]
        self.assertTrue(self.reason(products, crit(area=None)).endswith(
            "Parte il 1 ottobre 2026, la prima partenza nel periodo che hai chiesto, con un totale a "
            "partire da 1000 euro, ed è tra i viaggi in evidenza del catalogo."))

    def test_duration_sentence_keeps_its_place(self):
        long = prod(1, nights=7, start="2026-10-05")
        r = self.reason([long, prod(2, nights=7, start="2026-10-20", price=100)], crit(**WEEKEND))
        self.assertLess(r.index("Non ho weekend compatibili"), r.index("Parte il 5 ottobre 2026, la prima partenza"))


if __name__ == "__main__":
    unittest.main()
