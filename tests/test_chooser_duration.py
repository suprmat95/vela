"""M21-A (UC-A, RF-58, RF-59): la durata ordina, non esclude, e la motivazione la dichiara."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import TODAY, make_product
from vela.domain.chooser import FILTERS, choose
from vela.domain.models import Area, Criteria, Period

OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")
WEEKEND = dict(duration_min_nights=1, duration_max_nights=3)
WEEK = dict(duration_min_nights=6, duration_max_nights=8)


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, budget=None)
    base.update(kw)
    return Criteria(**base)


def trip(pid, nights, price, start="2026-10-01", **kw):
    """Prodotto a finestra fissa lunga `nights` notti."""
    first = date.fromisoformat(start)
    end = first.toordinal() + nights
    p = make_product(pid, price=price, windows=((start, date.fromordinal(end).isoformat()),), **kw)
    return replace(p, duration_days=nights + 1)


SEVEN = trip(1, 7, 300)        # più economico, una settimana
THREE = trip(2, 3, 400)        # più caro, un weekend


class DurationOrderingTest(unittest.TestCase):
    def test_filters_are_unchanged(self):
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "rooms",
                                   "price", "rejected"))   # "rooms" da M21-D

    def test_weekend_prefers_the_weekend_even_if_more_expensive(self):
        r = choose([SEVEN, THREE], crit(**WEEKEND), set(), TODAY)
        self.assertEqual(r.product.id, "2")
        self.assertEqual((r.nights, r.duration_ok), (3, True))

    def test_week_prefers_seven_nights(self):
        r = choose([THREE, SEVEN], crit(**WEEK), set(), TODAY)
        self.assertEqual(r.product.id, "1")
        self.assertEqual((r.nights, r.duration_ok), (7, True))

    def test_without_duration_everything_fits_and_price_decides(self):
        r = choose([SEVEN, THREE], crit(), set(), TODAY)
        self.assertEqual(r.product.id, "1")
        self.assertEqual((r.nights, r.duration_ok), (7, True))

    def test_duration_never_excludes(self):
        r = choose([SEVEN], crit(**WEEKEND), set(), TODAY)
        self.assertEqual(r.product.id, "1")
        self.assertEqual((r.nights, r.duration_ok), (7, False))

    def test_area_beats_duration(self):
        greece = trip(3, 3, 200, country="GR", destination="Atene")
        r = choose([greece, SEVEN], crit(**WEEKEND), set(), TODAY)
        self.assertEqual(r.product.id, "1")

    def test_budget_beats_duration(self):
        r = choose([SEVEN, THREE], crit(budget=Decimal("700"), **WEEKEND), set(), TODAY)
        self.assertEqual(r.product.id, "1")    # 600 entro budget, il weekend costa 800

    def test_open_window_nights_are_duration_minus_one(self):
        p = replace(make_product(4, windows=(("2026-10-01", "2026-10-31"),)), duration_days=6)
        r = choose([p], crit(**WEEKEND), set(), TODAY)
        self.assertEqual((r.start_date, r.end_date, r.nights), (date(2026, 10, 1), date(2026, 10, 6), 5))

    def test_fixed_window_without_duration_uses_the_window(self):
        p = replace(make_product(5, windows=(("2026-10-02", "2026-10-04"),)), duration_days=None)
        r = choose([p], crit(**WEEKEND), set(), TODAY)
        self.assertEqual((r.nights, r.duration_ok), (2, True))

    def test_only_one_bound(self):
        self.assertTrue(choose([SEVEN], crit(duration_min_nights=5), set(), TODAY).duration_ok)
        self.assertFalse(choose([SEVEN], crit(duration_max_nights=5), set(), TODAY).duration_ok)


class DurationReasonTest(unittest.TestCase):
    def reason(self, products, **kw):
        return choose(products, crit(**kw), set(), TODAY).reason

    def test_mismatch_is_declared_with_the_real_length(self):
        self.assertIn("Non ho weekend compatibili: questo dura 7 notti, dal 1 all'8 ottobre.",
                      self.reason([SEVEN], **WEEKEND))

    def test_mismatch_in_english(self):
        self.assertIn("I have no weekend trips: this one is 7 nights, from 1 to 8 October.",
                      self.reason([SEVEN], language="en", **WEEKEND))

    def test_sentence_comes_after_the_area_and_before_the_dates(self):
        r = self.reason([SEVEN], **WEEKEND)
        self.assertLess(r.index("come hai chiesto."), r.index("Non ho weekend"))
        self.assertLess(r.index("Non ho weekend"), r.index("Parte il 1 ottobre"))

    def test_no_sentence_when_the_duration_fits(self):
        self.assertNotIn("notti", self.reason([SEVEN, THREE], **WEEKEND))
        self.assertNotIn("notti", self.reason([SEVEN]))

    def test_labels(self):
        cases = [
            (dict(duration_min_nights=6, duration_max_nights=8), "Non ho viaggi di una settimana compatibili"),
            (dict(duration_min_nights=13, duration_max_nights=15), "Non ho viaggi di due settimane compatibili"),
            (dict(duration_min_nights=2, duration_max_nights=4), "Non ho ponti o weekend lunghi compatibili"),
            (dict(duration_min_nights=4, duration_max_nights=4), "Non ho viaggi di 4 notti compatibili"),
            (dict(duration_min_nights=1, duration_max_nights=1), "Non ho viaggi di 1 notte compatibili"),
            (dict(duration_min_nights=3, duration_max_nights=5), "Non ho viaggi da 3 a 5 notti compatibili"),
            (dict(duration_min_nights=10), "Non ho viaggi di almeno 10 notti compatibili"),
            (dict(duration_max_nights=2), "Non ho viaggi di al massimo 2 notti compatibili"),
        ]
        product = trip(9, 9, 300)
        for kw, expected in cases:
            with self.subTest(kw=kw):
                self.assertIn(expected, self.reason([product], **kw))

    def test_labels_in_english(self):
        product = trip(9, 9, 300)
        self.assertIn("I have no week-long trips: this one is 9 nights",
                      self.reason([product], language="en", **WEEK))
        self.assertIn("I have no trips of 3 to 5 nights:",
                      self.reason([product], language="en", duration_min_nights=3,
                                  duration_max_nights=5))

    def test_one_night_trip_is_singular(self):
        one = trip(8, 1, 300)
        self.assertIn("questo dura 1 notte, dal 1 al 2 ottobre.", self.reason([one], **WEEK))

    def test_across_months(self):
        late = trip(7, 5, 300, start="2026-10-29")
        self.assertIn("dal 29 ottobre al 3 novembre.", self.reason([late], **WEEKEND))
        self.assertIn("from 29 October to 3 November.",
                      self.reason([late], language="en", **WEEKEND))

    def test_cheapest_claim_stays_true_when_duration_wins_over_price(self):
        r = self.reason([SEVEN, THREE], area=None, **WEEKEND)
        self.assertNotIn("è la più economica compatibile.", r)
        self.assertIn("è la più economica compatibile tra quelle della durata che hai chiesto.", r)
        r = self.reason([SEVEN, THREE], budget=Decimal("100"), **WEEKEND)
        self.assertIn("ma è la più economica in Spagna tra quelle della durata che hai chiesto.", r)
        r = self.reason([SEVEN, THREE], area=None, language="en", **WEEKEND)
        self.assertIn("it's the cheapest compatible option of the length you asked for.", r)

    def test_cheapest_claim_unchanged_when_it_is_the_cheapest(self):
        self.assertIn("è la più economica compatibile.",
                      self.reason([THREE, SEVEN], area=None, **WEEK))


if __name__ == "__main__":
    unittest.main()
