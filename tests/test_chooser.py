import unittest
from datetime import date
from decimal import Decimal

from support import TODAY, make_product
from vela.domain.chooser import Choice, NoChoice, area_score, choose, window_for
from vela.domain.models import Area, Criteria, Period

OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, budget=Decimal("800"))
    base.update(kw)
    return Criteria(**base)


class ExclusionTest(unittest.TestCase):
    def test_archived_bookable_rejected_are_never_chosen(self):
        products = [make_product(1, archived=True), make_product(2, bookable=False),
                    make_product(3), make_product(4, price=900)]
        r = choose(products, crit(), rejected_ids={"3"}, today=TODAY)
        self.assertIsInstance(r, Choice)
        self.assertEqual(r.product.id, "4")

    def test_sport_mismatch(self):
        r = choose([make_product(1, sport="tennis")], crit(sport="padel"), set(), TODAY)
        self.assertEqual(r, NoChoice("sport"))

    def test_no_sport_in_intent_accepts_any_sport(self):
        r = choose([make_product(1, sport="tennis")], crit(sport=None), set(), TODAY)
        self.assertIsInstance(r, Choice)

    def test_dates_outside_min_max(self):
        p = make_product(1, min_date="2026-11-01", max_date="2026-12-31",
                         windows=(("2026-11-05", "2026-11-08"),))
        self.assertEqual(choose([p], crit(), set(), TODAY), NoChoice("dates"))

    def test_dates_no_window_in_period(self):
        p = make_product(1, windows=(("2026-11-05", "2026-11-08"),))
        self.assertEqual(choose([p], crit(), set(), TODAY), NoChoice("dates"))

    def test_past_window_is_skipped(self):
        p = make_product(1, windows=(("2026-09-20", "2026-09-22"), ("2026-10-15", "2026-10-18")))
        r = choose([p], crit(), set(), TODAY)
        self.assertEqual((r.start_date, r.end_date), (date(2026, 10, 15), date(2026, 10, 18)))

    def test_no_period_takes_first_future_window(self):
        p = make_product(1, windows=(("2026-09-20", "2026-09-22"), ("2026-12-01", "2026-12-04")))
        r = choose([p], crit(period=None), set(), TODAY)
        self.assertEqual(r.start_date, date(2026, 12, 1))

    def test_pax_bounds(self):
        self.assertEqual(choose([make_product(1, min_pax=3)], crit(pax=2), set(), TODAY), NoChoice("pax"))
        self.assertEqual(choose([make_product(1, max_pax=1)], crit(pax=2), set(), TODAY), NoChoice("pax"))

    def test_zero_or_null_pax_bounds_do_not_exclude(self):
        self.assertIsInstance(choose([make_product(1, min_pax=None, max_pax=0)], crit(pax=6), set(), TODAY), Choice)
        self.assertIsInstance(choose([make_product(1, min_pax=0, max_pax=None)], crit(pax=1), set(), TODAY), Choice)

    def test_failed_criterion_is_the_first_emptying_filter(self):
        products = [make_product(1, archived=True), make_product(2, sport="tennis")]
        self.assertEqual(choose(products, crit(), set(), TODAY), NoChoice("sport"))
        self.assertEqual(choose([make_product(1)], crit(), {"1"}, TODAY), NoChoice("rejected"))
        self.assertEqual(choose([], crit(), set(), TODAY), NoChoice("archived"))


class OrderingTest(unittest.TestCase):
    def test_area_then_budget_then_price(self):
        products = [make_product(1, price=300, country="IT", destination="Riccione"),
                    make_product(2, price=450, country="ES", destination="Madrid"),
                    make_product(3, price=350, country="ES", destination="Valencia"),
                    make_product(4, price=390, country="ES", destination="Lanzarote")]
        r = choose(products, crit(area=Area("city", "Lanzarote", "ES")), set(), TODAY)
        self.assertEqual(r.product.id, "4")           # città coincidente batte il prezzo
        r = choose(products, crit(), set(), TODAY)
        self.assertEqual(r.product.id, "3")           # paese: 350×2 = 700 ≤ 800, il più economico
        r = choose(products, crit(budget=Decimal("720")), set(), TODAY)
        self.assertEqual(r.product.id, "3")           # 700 entro budget, 900 no
        r = choose(products, crit(budget=Decimal("100")), set(), TODAY)
        self.assertEqual(r.product.id, "3")           # nessuno entro budget: prezzo crescente in area

    def test_without_area_and_budget_is_price_then_id(self):
        products = [make_product(2, price=300), make_product(1, price=300), make_product(3, price=200)]
        r = choose(products, crit(area=None, budget=None), set(), TODAY)
        self.assertEqual(r.product.id, "3")
        r = choose(products, crit(area=None, budget=None), {"3"}, TODAY)
        self.assertEqual(r.product.id, "1")

    def test_area_score(self):
        p = make_product(1, country="ES", destination="Palma de Mallorca")
        self.assertEqual(area_score(p, None), 0)
        self.assertEqual(area_score(p, Area("city", "Palma de Mallorca", "ES")), 2)
        self.assertEqual(area_score(p, Area("region", "Maiorca", "ES")), 1)
        self.assertEqual(area_score(p, Area("country", "Italia", "IT")), 0)
        self.assertEqual(area_score(make_product(2, country=None, destination=None), SPAIN), 0)


class ReasonAndWindowTest(unittest.TestCase):
    def test_reason_mentions_area_dates_and_budget(self):
        r = choose([make_product(1, price=300)], crit(), set(), TODAY)
        self.assertIn("Spagna", r.reason)
        self.assertIn("1 ottobre", r.reason)
        self.assertIn("800", r.reason)
        self.assertTrue(r.reason.endswith("."))

    def test_reason_over_budget_says_cheapest(self):
        r = choose([make_product(1, price=900)], crit(area=None), set(), TODAY)
        self.assertIn("più economic", r.reason)

    def test_window_for(self):
        p = make_product(1, windows=(("2026-10-01", "2026-10-04"), ("2026-10-08", "2026-10-11")))
        self.assertEqual(window_for(p, OCTOBER, TODAY).start, date(2026, 10, 1))
        self.assertEqual(window_for(p, OCTOBER, date(2026, 10, 2)).start, date(2026, 10, 8))
        self.assertIsNone(window_for(p, OCTOBER, date(2026, 10, 9)))
