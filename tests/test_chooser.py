import re
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from support import TODAY, make_product
from vela.domain.chooser import (ELSEWHERE, FILTERS, INSIDE, SAME_COUNTRY, SAME_REGION, Choice,
                                 NoChoice, area_score, choose, departure, place_of)
from vela.domain.models import Area, Criteria, Period

OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")
LANZAROTE = Area("city", "Lanzarote", "ES")
CANARIE = Area("region", "Canarie", "ES")
GREECE = Area("country", "Grecia", "GR")


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, budget=Decimal("800"))
    base.update(kw)
    return Criteria(**base)


def d(text):
    return date.fromisoformat(text)


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


class PriceCeilingTest(unittest.TestCase):
    """Decisione M7: dopo "troppo caro" solo totali strettamente minori del rifiutato (§10.1)."""

    def test_equal_or_higher_totals_are_excluded(self):
        products = [make_product(1, price=350), make_product(2, price=349), make_product(3, price=300)]
        r = choose(products, crit(), set(), TODAY, max_total=Decimal("700"))   # 2 persone
        self.assertEqual(r.product.id, "3")
        r = choose(products[:2], crit(), set(), TODAY, max_total=Decimal("700"))
        self.assertEqual(r.product.id, "2")                                   # 698 < 700

    def test_area_still_ranks_first_among_cheaper_products(self):
        products = [make_product(1, price=300, country="ES", destination="Valencia"),
                    make_product(2, price=100, country="IT", destination="Riccione"),
                    make_product(3, price=400, country="ES", destination="Madrid")]
        r = choose(products, crit(), set(), TODAY, max_total=Decimal("800"))
        self.assertEqual(r.product.id, "1")

    def test_cheaper_product_in_another_country_is_proposed_and_declared(self):
        products = [make_product(1, price=300, country="ES", destination="Valencia"),
                    make_product(2, price=200, country="IT", destination="Riccione")]
        r = choose(products, crit(), {"1"}, TODAY, max_total=Decimal("600"))
        self.assertEqual(r.product.id, "2")
        self.assertIn("Spagna", r.reason)

    def test_nothing_cheaper_is_price(self):
        products = [make_product(1, price=300), make_product(2, price=400)]
        self.assertEqual(choose(products, crit(), {"1"}, TODAY, max_total=Decimal("600")),
                         NoChoice("price"))

    def test_cheaper_products_all_rejected_is_rejected(self):
        products = [make_product(1, price=300), make_product(2, price=200)]
        self.assertEqual(choose(products, crit(), {"1", "2"}, TODAY, max_total=Decimal("700")),
                         NoChoice("rejected"))

    def test_no_ceiling_keeps_expensive_products(self):
        r = choose([make_product(1, price=900)], crit(), set(), TODAY)
        self.assertEqual(r.product.id, "1")


class FilterTest(unittest.TestCase):
    def test_filter_order(self):
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "price",
                                   "rejected"))

    def test_archived_bookable_rejected_are_never_chosen(self):
        products = [make_product(1, archived=True), make_product(2, bookable=False),
                    make_product(3), make_product(4, price=900)]
        r = choose(products, crit(), rejected_ids={"3"}, today=TODAY)
        self.assertIsInstance(r, Choice)
        self.assertEqual(r.product.id, "4")

    def test_gift_card_is_not_a_trip(self):
        gift = make_product(1, price=50, destination="Weebora", country="IT")
        slug = replace(make_product(2, price=60), slug="weebora-gift-card")
        self.assertEqual(choose([gift, slug], crit(), set(), TODAY), NoChoice("trip"))
        r = choose([gift, make_product(3, price=500)], crit(), set(), TODAY)
        self.assertEqual(r.product.id, "3")

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

    def test_pax_bounds(self):
        self.assertEqual(choose([make_product(1, min_pax=3)], crit(pax=2), set(), TODAY), NoChoice("pax"))
        self.assertEqual(choose([make_product(1, max_pax=1)], crit(pax=2), set(), TODAY), NoChoice("pax"))

    def test_zero_or_null_pax_bounds_do_not_exclude(self):
        self.assertIsInstance(choose([make_product(1, min_pax=None, max_pax=0)], crit(pax=6), set(), TODAY), Choice)
        self.assertIsInstance(choose([make_product(1, min_pax=0, max_pax=None)], crit(pax=1), set(), TODAY), Choice)

    def test_rejected_is_reported_only_when_compatible_products_were_all_rejected(self):
        # l'unico padel è stato rifiutato: il criterio che manca è "rejected", non "sport"
        products = [make_product(1), make_product(2, sport="tennis"), make_product(3, sport="tennis")]
        self.assertEqual(choose(products, crit(), {"1"}, TODAY), NoChoice("rejected"))

    def test_failed_criterion_is_the_first_emptying_filter(self):
        products = [make_product(1, archived=True), make_product(2, sport="tennis")]
        self.assertEqual(choose(products, crit(), set(), TODAY), NoChoice("sport"))
        self.assertEqual(choose([make_product(1)], crit(), {"1"}, TODAY), NoChoice("rejected"))
        self.assertEqual(choose([], crit(), set(), TODAY), NoChoice("archived"))


class DepartureTest(unittest.TestCase):
    def test_fixed_window_is_the_trip(self):
        p = make_product(1, windows=(("2026-10-01", "2026-10-04"),))   # durata 4
        self.assertEqual(departure(p, OCTOBER, TODAY), (d("2026-10-01"), d("2026-10-04")))

    def test_fixed_window_must_start_in_period_and_not_in_the_past(self):
        p = make_product(1, windows=(("2026-09-20", "2026-09-22"), ("2026-10-15", "2026-10-18"),
                                     ("2026-11-05", "2026-11-08")))
        self.assertEqual(departure(p, OCTOBER, TODAY), (d("2026-10-15"), d("2026-10-18")))
        self.assertEqual(departure(p, None, TODAY), (d("2026-10-15"), d("2026-10-18")))
        self.assertIsNone(departure(p, OCTOBER, d("2026-10-16")))

    def test_return_may_fall_outside_the_period(self):
        weekend = Period(d("2026-10-03"), d("2026-10-04"), "weekend")
        p = make_product(1, windows=(("2026-10-03", "2026-10-06"),))
        self.assertEqual(departure(p, weekend, TODAY), (d("2026-10-03"), d("2026-10-06")))

    def test_open_window_starts_at_the_latest_of_window_today_period(self):
        p = make_product(1, windows=(("2026-09-20", "2027-01-02"),))      # aperta, durata 4
        self.assertEqual(departure(p, None, TODAY), (d("2026-09-25"), d("2026-09-28")))
        self.assertEqual(departure(p, OCTOBER, TODAY), (d("2026-10-01"), d("2026-10-04")))
        late = Period(d("2026-12-30"), d("2027-01-05"), "capodanno")
        self.assertIsNone(departure(p, late, TODAY))                     # 30/12 + 4 giorni > 2/1

    def test_open_window_respects_min_date(self):
        p = make_product(1, min_date="2026-10-10", windows=(("2026-09-26", "2026-12-31"),))
        self.assertEqual(departure(p, OCTOBER, TODAY), (d("2026-10-10"), d("2026-10-13")))

    def test_open_window_must_fit_before_max_date(self):
        p = make_product(1, max_date="2026-10-02", windows=(("2026-09-26", "2026-12-31"),))
        self.assertIsNone(departure(p, OCTOBER, TODAY))

    def test_open_window_ending_before_period(self):
        p = make_product(1, windows=(("2026-09-26", "2026-10-20"),))
        self.assertIsNone(departure(p, Period(d("2026-11-01"), d("2026-11-30"), "novembre"), TODAY))

    def test_window_without_duration_is_fixed(self):
        p = replace(make_product(1, windows=(("2026-10-01", "2026-12-31"),)), duration_days=None)
        self.assertEqual(departure(p, OCTOBER, TODAY), (d("2026-10-01"), d("2026-12-31")))


class AreaScoreTest(unittest.TestCase):
    def test_levels(self):
        lanz = make_product(1, destination="Lanzarote")
        tene = make_product(2, destination="Tenerife")
        madrid = make_product(3, destination="Madrid")
        riccione = make_product(4, country="IT", destination="Riccione")
        self.assertEqual(area_score(lanz, None), ELSEWHERE)
        self.assertEqual(area_score(lanz, LANZAROTE), INSIDE)
        self.assertEqual(area_score(lanz, CANARIE), INSIDE)
        self.assertEqual(area_score(lanz, SPAIN), INSIDE)
        self.assertEqual(area_score(tene, LANZAROTE), SAME_REGION)
        self.assertEqual(area_score(madrid, LANZAROTE), SAME_COUNTRY)
        self.assertEqual(area_score(riccione, LANZAROTE), ELSEWHERE)

    def test_nested_regions(self):
        palma = make_product(1, destination="Palma de Mallorca")
        ibiza = make_product(2, destination="Ibiza")
        maiorca = make_product(3, destination="Maiorca")
        self.assertEqual(area_score(palma, Area("region", "Maiorca", "ES")), INSIDE)
        self.assertEqual(area_score(palma, Area("region", "Baleari", "ES")), INSIDE)
        self.assertEqual(area_score(ibiza, Area("city", "Palma de Mallorca", "ES")), SAME_REGION)
        self.assertEqual(area_score(maiorca, Area("city", "Palma de Mallorca", "ES")), SAME_REGION)

    def test_product_without_destination_uses_title_then_country(self):
        watch = make_product(1, destination=None, country=None,
                             title="Watch & Stay Experience per Premier Padel® Milano 2026")
        self.assertEqual(place_of(watch), Area("city", "Milano", "IT"))
        self.assertEqual(area_score(watch, Area("country", "Italia", "IT")), INSIDE)
        nothing = make_product(2, destination=None, country=None, title="Evento speciale")
        self.assertIsNone(place_of(nothing))
        self.assertEqual(area_score(nothing, SPAIN), ELSEWHERE)
        only_country = make_product(3, destination=None, country="ES", title="Evento speciale")
        self.assertEqual(area_score(only_country, SPAIN), INSIDE)
        self.assertEqual(area_score(only_country, LANZAROTE), SAME_COUNTRY)


    def test_unknown_destination_falls_back_to_country(self):
        # una destinazione nuova arrivata col sync (M10) e non ancora in geo.py
        p = make_product(1, destination="Atlantide", country="ES")
        self.assertEqual(place_of(p), SPAIN)
        self.assertEqual(area_score(p, SPAIN), INSIDE)
        self.assertEqual(area_score(p, LANZAROTE), SAME_COUNTRY)
        r = choose([p], crit(area=LANZAROTE), set(), TODAY)
        self.assertTrue(r.reason.startswith("Non ho partenze compatibili a Lanzarote: questa è in Spagna."),
                        r.reason)


class OrderingTest(unittest.TestCase):
    PRODUCTS = [make_product(1, price=300, country="IT", destination="Riccione"),
                make_product(2, price=450, country="ES", destination="Madrid"),
                make_product(3, price=350, country="ES", destination="Valencia"),
                make_product(4, price=390, country="ES", destination="Lanzarote"),
                make_product(5, price=320, country="ES", destination="Tenerife")]

    def test_area_beats_budget_and_price(self):
        r = choose(self.PRODUCTS, crit(area=LANZAROTE, budget=Decimal("700")), set(), TODAY)
        self.assertEqual((r.product.id, r.area_score, r.within_budget), ("4", INSIDE, False))

    def test_same_region_beats_same_country(self):
        r = choose(self.PRODUCTS, crit(area=LANZAROTE), {"4"}, TODAY)
        self.assertEqual((r.product.id, r.area_score), ("5", SAME_REGION))
        r = choose(self.PRODUCTS, crit(area=LANZAROTE), {"4", "5"}, TODAY)
        self.assertEqual((r.product.id, r.area_score), ("3", SAME_COUNTRY))
        r = choose(self.PRODUCTS, crit(area=LANZAROTE), {"2", "3", "4", "5"}, TODAY)
        self.assertEqual((r.product.id, r.area_score), ("1", ELSEWHERE))

    def test_budget_is_on_total_then_price(self):
        r = choose(self.PRODUCTS, crit(), set(), TODAY)
        self.assertEqual(r.product.id, "5")                       # 320×2 = 640 ≤ 800
        r = choose(self.PRODUCTS, crit(budget=Decimal("100")), set(), TODAY)
        self.assertEqual((r.product.id, r.within_budget), ("5", False))   # nessuno entro: il più economico
        r = choose(self.PRODUCTS, crit(pax=None, budget=Decimal("340")), set(), TODAY)
        self.assertEqual((r.product.id, r.within_budget), ("5", True))    # pax assente = 1

    def test_in_budget_beats_cheaper_over_budget_within_same_area_score(self):
        products = [make_product(1, price=300, destination="Madrid"),
                    make_product(2, price=500, destination="Valencia", min_pax=None)]
        r = choose(products, crit(pax=1, budget=Decimal("400")), set(), TODAY)
        self.assertEqual(r.product.id, "1")
        r = choose(products, crit(pax=1, budget=Decimal("400")), {"1"}, TODAY)
        self.assertEqual((r.product.id, r.within_budget), ("2", False))

    def test_without_area_and_budget_is_price_then_id(self):
        products = [make_product(2, price=300), make_product(1, price=300), make_product(3, price=200)]
        r = choose(products, crit(area=None, budget=None), set(), TODAY)
        self.assertEqual(r.product.id, "3")
        r = choose(products, crit(area=None, budget=None), {"3"}, TODAY)
        self.assertEqual(r.product.id, "1")


class ReasonTest(unittest.TestCase):
    P = [make_product(1, price=300, destination="Lanzarote"),
         make_product(2, price=320, destination="Tenerife"),
         make_product(3, price=350, destination="Madrid")]

    def reason(self, criteria, rejected=()):
        r = choose(self.P, criteria, set(rejected), TODAY)
        self.assertLessEqual(len(sentences(r.reason)), 2, r.reason)
        self.assertTrue(r.reason.endswith("."), r.reason)
        return r.reason

    def test_inside_area_says_as_requested(self):
        self.assertTrue(self.reason(crit(area=LANZAROTE)).startswith("È a Lanzarote, come hai chiesto."))
        self.assertTrue(self.reason(crit()).startswith("È a Lanzarote, in Spagna come hai chiesto."))
        self.assertTrue(self.reason(crit(area=CANARIE)).startswith("È a Lanzarote, alle Canarie come hai chiesto."))

    def test_compromise_on_area_is_declared(self):
        self.assertTrue(self.reason(crit(area=LANZAROTE), {"1"}).startswith(
            "Non ho partenze compatibili a Lanzarote: questa è a Tenerife, alle Canarie."))
        self.assertTrue(self.reason(crit(area=LANZAROTE), {"1", "2"}).startswith(
            "Non ho partenze compatibili a Lanzarote: questa è a Madrid, sempre in Spagna."))
        self.assertTrue(self.reason(crit(area=GREECE)).startswith(
            "Non ho partenze compatibili in Grecia: questa è a Lanzarote, in Spagna."))

    def test_dates_and_budget(self):
        within = self.reason(crit())
        self.assertIn("Parte il 1 ottobre 2026, nel periodo che hai chiesto,", within)
        self.assertIn("costa 600 euro in totale, dentro il tuo budget di 800 euro.", within)
        over = self.reason(crit(budget=Decimal("100")))
        self.assertIn("costa 600 euro in totale, oltre il tuo budget di 100 euro, ma è la più economica in Spagna.", over)
        over_elsewhere = self.reason(crit(area=LANZAROTE, budget=Decimal("100")), {"1"})
        self.assertTrue(over_elsewhere.endswith("oltre il tuo budget di 100 euro."), over_elsewhere)

    def test_no_area_no_budget_no_period(self):
        r = self.reason(crit(area=None, budget=None, period=None))
        self.assertEqual(r, "È a Lanzarote. Parte il 1 ottobre 2026 ed è la più economica compatibile.")

    def test_eighth_and_eleventh_take_the_elided_article(self):
        p = make_product(1, windows=(("2026-10-08", "2026-10-11"),))
        r = choose([p], crit(), set(), TODAY)
        self.assertIn("Parte l'8 ottobre 2026", r.reason)

    def test_m9_region_contains_its_cities(self):
        p = make_product(1, price=300, destination="Malaga")
        self.assertEqual(area_score(p, Area("region", "Andalusia", "ES")), INSIDE)
        r = choose([p], crit(area=Area("region", "Andalusia", "ES")), set(), TODAY)
        self.assertTrue(r.reason.startswith("È a Malaga, in Andalusia come hai chiesto."), r.reason)

    def test_reason_in_english(self):
        en = dict(language="en")
        self.assertTrue(self.reason(crit(**en)).startswith(
            "It's in Lanzarote, in Spain as you asked."))
        self.assertTrue(self.reason(crit(area=CANARIE, **en)).startswith(
            "It's in Lanzarote, in the Canary Islands as you asked."))
        self.assertTrue(self.reason(crit(area=LANZAROTE, **en), {"1", "2"}).startswith(
            "I have no compatible departures in Lanzarote: this one is in Madrid, still in Spain."))
        within = self.reason(crit(**en))
        self.assertIn("It leaves on 1 October 2026, in the period you asked for,", within)
        self.assertIn("costs 600 euros in total, within your budget of 800 euros.", within)
        self.assertEqual(self.reason(crit(area=None, budget=None, period=None, **en)),
                         "It's in Lanzarote. It leaves on 1 October 2026 and it's the cheapest "
                         "compatible option.")

    def test_italian_reason_is_unchanged_by_language_default(self):
        self.assertEqual(self.reason(crit(area=None, budget=None, period=None, language="it")),
                         "È a Lanzarote. Parte il 1 ottobre 2026 ed è la più economica compatibile.")


class UnbookableRecheckTest(unittest.TestCase):
    """RF-33, RF-34: un prodotto non prenotabile torna candidato 24 h dopo `bookable_checked_at`."""
    NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

    def unbookable(self, hours_ago):
        return replace(make_product(1), bookable=False,
                       bookable_checked_at=self.NOW - timedelta(hours=hours_ago))

    def test_unbookable_product_excluded_within_24h(self):
        result = choose([self.unbookable(23)], crit(), set(), TODAY, now=self.NOW)
        self.assertEqual(result, NoChoice("bookable"))

    def test_unbookable_product_candidate_again_after_24h(self):
        result = choose([self.unbookable(24)], crit(), set(), TODAY, now=self.NOW)
        self.assertIsInstance(result, Choice)
        self.assertEqual(result.product.id, "1")

    def test_unbookable_without_check_time_stays_excluded(self):
        p = replace(make_product(1), bookable=False, bookable_checked_at=None)
        self.assertEqual(choose([p], crit(), set(), TODAY, now=self.NOW), NoChoice("bookable"))

    def test_choose_without_now_keeps_old_behaviour(self):
        self.assertEqual(choose([self.unbookable(48)], crit(), set(), TODAY), NoChoice("bookable"))

