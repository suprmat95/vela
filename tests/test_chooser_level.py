"""M21-C (UC-C, RF-60 livello 4, RF-64): livello e lezioni nel chooser."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import TODAY, make_product
from vela.domain import say
from vela.domain.chooser import FILTERS, Choice, NoChoice, cheapest_total, choose
from vela.domain.models import Area, Criteria, Period

OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")
B, M, A, ALL = "beginner", "intermediate", "advanced", "all"


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, budget=None, rooms=1)
    base.update(kw)
    return Criteria(**base)


def prod(pid, levels=(), exclusive=False, coaching=False, start="2026-10-01", **kw):
    """Prodotto a Lanzarote (ES), finestra fissa di 3 notti da `start`, con le etichette di M21-C."""
    end = date.fromordinal(date.fromisoformat(start).toordinal() + 3).isoformat()
    p = make_product(pid, windows=((start, end),), **kw)
    return replace(p, levels=frozenset(levels), levels_exclusive=exclusive, coaching=coaching)


def chosen(products, criteria):
    r = choose(products, criteria, set(), TODAY)
    assert isinstance(r, Choice), r
    return r


class HardFilterTest(unittest.TestCase):
    """RF-64: escluso solo un prodotto riservato esplicitamente ad altri livelli."""

    def test_level_filter_comes_after_rooms(self):
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "rooms",
                                   "level", "price", "rejected"))

    def test_only_an_exclusive_product_of_another_level_is_excluded(self):
        only_advanced = prod(1, {A}, exclusive=True, price=100)
        not_exclusive = prod(2, {M, A}, price=900)   # 962: per un principiante solo meno preferito
        self.assertEqual(chosen([only_advanced, not_exclusive], crit(level=B)).product.id, "2")
        self.assertEqual(chosen([only_advanced, not_exclusive], crit(level=A)).product.id, "1")

    def test_without_a_level_nothing_is_excluded(self):
        only_advanced = prod(1, {A}, exclusive=True)
        self.assertEqual(chosen([only_advanced], crit()).product.id, "1")
        self.assertEqual(chosen([only_advanced], crit(wants_coaching=True)).product.id, "1")

    def test_exclusive_to_several_levels(self):
        middle_up = prod(1, {M, A}, exclusive=True)
        self.assertEqual(chosen([middle_up], crit(level=M)).product.id, "1")
        self.assertEqual(choose([middle_up], crit(level=B), set(), TODAY),
                         NoChoice("level", levels=("intermediate", "advanced")))

    def test_no_choice_level_names_the_reserved_levels(self):
        r = choose([prod(1, {A}, exclusive=True), prod(2, {A}, exclusive=True)], crit(level=B), set(), TODAY)
        self.assertEqual(r, NoChoice("level", levels=("advanced",)))
        self.assertEqual(say.say_no_match("level", crit(level=B), levels=r.levels),
                         "I viaggi compatibili sono riservati a giocatori avanzati. Vuoi cambiare qualcosa?")
        self.assertEqual(say.say_no_match("level", crit(level=A, language="en"), levels=("beginner",)),
                         "The compatible trips are reserved for beginners. Do you want to change something?")
        self.assertEqual(say.say_no_match("level", crit(level=B)),
                         "I viaggi compatibili sono riservati a un altro livello di gioco. Vuoi cambiare qualcosa?")

    def test_cheapest_total_uses_the_level_filter(self):
        """RF-69 regola 4 con i filtri duri di `choose`: il più economico riservato ad altri
        livelli non conta (differenza annotata in `docs/decisions.md`)."""
        products = [prod(1, {A}, exclusive=True, price=100), prod(2, price=300)]
        self.assertEqual(cheapest_total(products, crit(level=B), TODAY), Decimal("600"))
        self.assertEqual(cheapest_total(products, crit(level=A), TODAY), Decimal("200"))
        self.assertEqual(cheapest_total(products, crit(), TODAY), Decimal("200"))


class RankingTest(unittest.TestCase):
    """RF-60, livello 4: compatibile = livello sconosciuto, `all` o il livello chiesto; con
    `wants_coaching=true` conta anche `coaching`. Il livello pesa prima delle lezioni."""

    def test_compatible_level_beats_an_earlier_cheaper_featured_product(self):
        wrong = replace(prod(1, {M, A}, start="2026-10-01", price=100), featured=True)
        right = prod(2, {B, M}, start="2026-10-20", price=900)
        self.assertEqual(chosen([wrong, right], crit(level=B)).product.id, "2")

    def test_unknown_level_and_all_levels_are_compatible(self):
        for levels in ((), (ALL,), (B, ALL)):
            with self.subTest(levels=levels):
                ok = prod(1, levels, start="2026-10-20", price=900)
                wrong = prod(2, {A}, start="2026-10-01", price=100)
                self.assertEqual(chosen([wrong, ok], crit(level=B)).product.id, "1")

    def test_coaching_counts_only_when_asked(self):
        lessons = prod(1, coaching=True, start="2026-10-20", price=900)
        plain = prod(2, start="2026-10-01", price=100)
        self.assertEqual(chosen([plain, lessons], crit(wants_coaching=True)).product.id, "1")
        self.assertEqual(chosen([plain, lessons], crit()).product.id, "2")
        # `wants_coaching=false` non penalizza le lezioni (decisione "Scelta v3")
        self.assertEqual(chosen([plain, lessons], crit(wants_coaching=False)).product.id, "2")
        self.assertEqual(chosen([replace(plain, coaching=True), replace(lessons, coaching=False)],
                                crit(wants_coaching=False)).product.id, "2")

    def test_level_weighs_before_coaching(self):
        level_only = prod(1, {B}, start="2026-10-20", price=900)
        coaching_only = prod(2, {A}, coaching=True, start="2026-10-01", price=100)
        both = prod(3, {B}, coaching=True, start="2026-10-25", price=950)
        c = crit(level=B, wants_coaching=True)
        self.assertEqual(chosen([coaching_only, level_only], c).product.id, "1")
        self.assertEqual(chosen([coaching_only, level_only, both], c).product.id, "3")

    def test_level_comes_after_duration_and_before_departure(self):
        weekend = dict(duration_min_nights=1, duration_max_nights=3)
        long_right = make_product(1, windows=(("2026-10-01", "2026-10-08"),))
        long_right = replace(long_right, levels=frozenset({B}), duration_days=8)
        short_wrong = prod(2, {A}, start="2026-10-20")
        self.assertEqual(chosen([long_right, short_wrong], crit(level=B, **weekend)).product.id, "2")

    def test_same_inputs_same_choice(self):
        products = [prod(i, levels, coaching=bool(i % 2), start="2026-10-%02d" % (i + 1), price=100 * i)
                    for i, levels in enumerate([(), (A,), (B, M), (ALL,), (M,)], start=1)]
        c = crit(level=M, wants_coaching=True)
        first = chosen(products, c)
        for _ in range(5):
            self.assertEqual(chosen(list(reversed(products)), c), first)


class ReasonTest(unittest.TestCase):
    """RF-64: il `say` dice se il prodotto proposto rispetta livello e lezioni; UC-C, tre forme."""

    def test_compatible(self):
        r = chosen([prod(1, {B, M}, coaching=True)], crit(level=B, wants_coaching=True))
        self.assertIn("Il programma è pensato anche per principianti e include lezioni o allenamenti.",
                      r.reason)
        r = chosen([prod(1, {B}, coaching=True)], crit(level=B))
        self.assertIn("Il programma è pensato per principianti.", r.reason)
        r = chosen([prod(1, {ALL})], crit(level=A, language="en"))
        self.assertIn("The programme is designed for players of every level.", r.reason)
        r = chosen([prod(1, coaching=True)], crit(level=B, wants_coaching=True))
        self.assertIn("Il programma non indica un livello di gioco e include lezioni o allenamenti.",
                      r.reason)

    def test_incompatible_but_proposed(self):
        """UC-C: "Non ho trovato viaggi per principianti con lezioni: questo è pensato per
        giocatori intermedi e avanzati…" """
        r = chosen([prod(1, {M, A}, coaching=True)], crit(level=B, wants_coaching=True))
        self.assertIn("Non ho trovato viaggi per principianti con lezioni: questo è pensato per "
                      "giocatori intermedi e avanzati e include lezioni o allenamenti.", r.reason)
        r = chosen([prod(1, {B})], crit(level=B, wants_coaching=True))
        self.assertIn("Non ho trovato viaggi per principianti con lezioni: questo è pensato per "
                      "principianti e non prevede lezioni.", r.reason)
        r = chosen([prod(1, {M, A})], crit(level=B, language="en"))
        self.assertIn("I have no trips for beginners: this one is designed for intermediate and "
                      "advanced players.", r.reason)
        r = chosen([prod(1)], crit(wants_coaching=True, language="en"))
        self.assertIn("I have no trips with lessons: this one doesn't include lessons.", r.reason)

    def test_order_of_the_sentences(self):
        """Area, (durata), livello e lezioni, date e budget: il livello è un criterio morbido
        dichiarato come la durata (RF-06)."""
        r = chosen([prod(1, {M, A})], crit(level=B))
        self.assertTrue(r.reason.startswith("È a Lanzarote, in Spagna come hai chiesto. Non ho trovato "
                                            "viaggi per principianti: questo è pensato per giocatori "
                                            "intermedi e avanzati. Parte il 1 ottobre 2026"), r.reason)

    def test_nothing_asked_nothing_said(self):
        r = chosen([prod(1, {M, A}, coaching=True)], crit())
        self.assertNotIn("programma", r.reason)
        self.assertNotIn("principianti", r.reason)
        r = chosen([prod(1, {M, A})], crit(wants_coaching=False))
        self.assertNotIn("lezioni", r.reason)

    def test_no_cheapest_claim_when_a_cheaper_product_lost_on_level(self):
        wrong = prod(1, {A}, price=100)
        right = prod(2, {B}, price=300)
        r = chosen([wrong, right], crit(level=B))
        self.assertEqual(r.product.id, "2")
        self.assertNotIn("economica", r.reason)
        r = chosen([prod(2, {B}, price=300)], crit(level=B, area=None))
        self.assertIn("la più economica", r.reason)


class NothingAskedTest(unittest.TestCase):
    def test_without_level_or_lessons_the_order_is_the_one_of_m21b(self):
        """Senza livello né lezioni il livello 4 è neutro: stesse scelte di prima di M21-C."""
        products = [prod(1, {A}, start="2026-10-05", price=100),
                    prod(2, {B}, coaching=True, start="2026-10-01", price=900)]
        self.assertEqual(chosen(products, crit()).product.id, "2")   # partenza più vicina
        self.assertEqual(chosen(products, crit(wants_coaching=False)).product.id, "2")


if __name__ == "__main__":
    unittest.main()
