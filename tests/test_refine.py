"""Rifiuto con motivo (RF-08): dal motivo in testo libero ai criteri aggiornati."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import NOW, TODAY
from vela.domain.models import Area, Criteria, Period, Proposal
from vela.domain.refine import refine

SPAIN = Area("country", "Spagna", "ES")
VALENCIA = Area("city", "Valencia", "ES")
OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
CRIT = Criteria("padel", SPAIN, OCTOBER, 2, Decimal("800"), "it")
PROPOSAL = Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("350"),
                    "EUR", "Motivo.", NOW)   # totale 700 → 80% = 560


def refined(reason, criteria=CRIT, area=VALENCIA):
    return refine(criteria, reason, PROPOSAL, area, TODAY)


class PriceTest(unittest.TestCase):
    def test_price_words_lower_budget_to_80_percent(self):
        for reason in ("troppo caro", "Troppo cara!", "costa troppo", "vorrei qualcosa di più economico",
                       "too expensive", "a bit too pricey", "something cheaper"):
            with self.subTest(reason=reason):
                self.assertEqual(refined(reason).budget, Decimal("560.00"))

    def test_explicit_figure_wins(self):
        self.assertEqual(refined("troppo caro, max 500 euro").budget, Decimal("500"))
        self.assertEqual(refined("massimo 650 euro").budget, Decimal("650"))

    def test_without_budget(self):
        self.assertEqual(refined("troppo caro", replace(CRIT, budget=None)).budget, Decimal("560.00"))

    def test_never_raises_budget(self):
        self.assertEqual(refined("troppo caro", replace(CRIT, budget=Decimal("400"))).budget,
                         Decimal("400"))


class DirectionTest(unittest.TestCase):
    def test_south_and_north(self):
        self.assertEqual(refined("più a sud").area, Area("city", "Alicante", "ES"))
        self.assertEqual(refined("further north please").area, Area("city", "Tarragona", "ES"))

    def test_no_entry_keeps_area(self):
        self.assertEqual(refined("più a sud", area=Area("region", "Lanzarote", "ES")).area, SPAIN)
        self.assertEqual(refined("più a sud", area=None).area, SPAIN)

    def test_direction_beats_named_place(self):
        self.assertEqual(refined("più a sud, magari in Grecia").area, Area("city", "Alicante", "ES"))


class OtherFieldsTest(unittest.TestCase):
    def test_named_place(self):
        self.assertEqual(refined("meglio in Grecia").area, Area("country", "Grecia", "GR"))

    def test_period(self):
        self.assertEqual(refined("a novembre").period,
                         Period(date(2026, 11, 1), date(2026, 11, 30), "novembre"))
        self.assertEqual(refined("dal 10 al 14 novembre").period.start, date(2026, 11, 10))

    def test_sport_and_pax(self):
        self.assertEqual(refined("preferisco il tennis").sport, "tennis")
        self.assertEqual(refined("siamo in 4").pax, 4)

    def test_rules_combine(self):
        c = refined("troppo caro e a novembre")
        self.assertEqual((c.budget, c.period.start), (Decimal("560.00"), date(2026, 11, 1)))
        self.assertEqual((c.sport, c.area, c.pax, c.language), ("padel", SPAIN, 2, "it"))


class UnrecognizedTest(unittest.TestCase):
    def test_unrecognized_reasons_keep_criteria(self):
        for reason in ("più vicino", "closer to home", "non mi piace", "no", "", None):
            with self.subTest(reason=reason):
                self.assertIs(refined(reason), CRIT)

    def test_idempotent(self):
        once = refined("troppo caro")
        self.assertEqual(refine(once, "troppo caro", PROPOSAL, VALENCIA, TODAY), once)

    def test_language_is_kept(self):
        en = replace(CRIT, language="en")
        self.assertEqual(refined("too expensive", en).language, "en")
