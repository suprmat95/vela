import unittest
from datetime import date
from decimal import Decimal

from vela.domain.intent import (QUESTION_PAX, QUESTION_SPORT_OR_PERIOD, detect_language,
                                parse_budget, parse_intent, parse_pax, parse_period)
from vela.domain.models import Area, Period, TravelerProfile

TODAY = date(2026, 9, 25)   # venerdì

# testo → (sport, codice paese, (start, end), pax, budget, lingua)
TABLE = [
    ("un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro",
     ("padel", "ES", (date(2026, 10, 1), date(2026, 10, 31)), 2, Decimal("800"), "it")),
    ("a padel weekend in Spain in October, we are two, max 800 euros",
     ("padel", "ES", (date(2026, 10, 1), date(2026, 10, 31)), 2, Decimal("800"), "en")),
    ("vorrei fare tennis in Toscana a novembre per 4 persone",
     ("tennis", "IT", (date(2026, 11, 1), date(2026, 11, 30)), 4, None, "it")),
    ("padel a Lanzarote il 10 ottobre, siamo in 3, budget 1.000 euro",
     ("padel", "ES", (date(2026, 10, 10), date(2026, 10, 10)), 3, Decimal("1000"), "it")),
    ("tennis camp in Mallorca next weekend for 2 people under 1,000 euros",
     ("tennis", "ES", (date(2026, 9, 26), date(2026, 9, 27)), 2, Decimal("1000"), "en")),
    ("padel in estate a Ibiza, 2 persone",
     ("padel", "ES", (date(2027, 6, 1), date(2027, 8, 31)), 2, None, "it")),
    ("un viaggio di padel a marzo, siamo in quattro",
     ("padel", None, (date(2027, 3, 1), date(2027, 3, 31)), 4, None, "it")),
    ("tennis in Italia il 2026-12-05 per due",
     ("tennis", "IT", (date(2026, 12, 5), date(2026, 12, 5)), 2, None, "it")),
    ("padel weekend, x2, 600€",
     ("padel", None, (date(2026, 9, 26), date(2026, 9, 27)), 2, Decimal("600"), "it")),
    ("we want a tennis holiday in winter, three of us, no more than 2000 euros",
     ("tennis", None, (date(2026, 12, 1), date(2027, 2, 28)), 3, Decimal("2000"), "en")),
]


class TableTest(unittest.TestCase):
    def test_table(self):
        for text, (sport, country, period, pax, budget, lang) in TABLE:
            with self.subTest(text=text):
                r = parse_intent(text, today=TODAY)
                c = r.criteria
                self.assertEqual(c.sport, sport)
                self.assertEqual(c.area.country_code if c.area else None, country)
                self.assertEqual((c.period.start, c.period.end) if c.period else None, period)
                self.assertEqual(c.pax, pax)
                self.assertEqual(c.budget, budget)
                self.assertEqual(c.language, lang)
                self.assertIsNone(r.question)


class PeriodTest(unittest.TestCase):
    def test_current_month_is_this_year(self):
        p = parse_period("a settembre", TODAY)
        self.assertEqual((p.start, p.end, p.label), (date(2026, 9, 1), date(2026, 9, 30), "settembre"))

    def test_past_month_is_next_year(self):
        p = parse_period("ad agosto", TODAY)
        self.assertEqual(p.start, date(2027, 8, 1))

    def test_weekend_on_saturday_is_today(self):
        p = parse_period("questo weekend", date(2026, 9, 26))
        self.assertEqual((p.start, p.end), (date(2026, 9, 26), date(2026, 9, 27)))

    def test_weekend_on_sunday_is_next(self):
        p = parse_period("fine settimana", date(2026, 9, 27))
        self.assertEqual((p.start, p.end), (date(2026, 10, 3), date(2026, 10, 4)))

    def test_month_beats_weekend(self):
        p = parse_period("un weekend a ottobre", TODAY)
        self.assertEqual(p.label, "ottobre")

    def test_day_month_slash(self):
        self.assertEqual(parse_period("il 12/10", TODAY).start, date(2026, 10, 12))
        self.assertEqual(parse_period("il 12/03", TODAY).start, date(2027, 3, 12))

    def test_winter_in_january(self):
        p = parse_period("in inverno", date(2027, 1, 10))
        self.assertEqual((p.start, p.end), (date(2026, 12, 1), date(2027, 2, 28)))

    def test_none(self):
        self.assertIsNone(parse_period("padel in Spagna", TODAY))

    def span(self, text, today=TODAY):
        p = parse_period(text, today)
        return (p.start, p.end) if p else None

    def test_ranges(self):
        cases = [
            ("dal 10 al 14 ottobre", (date(2026, 10, 10), date(2026, 10, 14))),
            ("20-23 novembre", (date(2026, 11, 20), date(2026, 11, 23))),
            ("from 10 to 14 October", (date(2026, 10, 10), date(2026, 10, 14))),
            ("from the 3rd to the 7th of December", (date(2026, 12, 3), date(2026, 12, 7))),
            ("tra il 5 e l'8 dicembre", (date(2026, 12, 5), date(2026, 12, 8))),
            ("between 14 and 20 November", (date(2026, 11, 14), date(2026, 11, 20))),
            ("October 10-12", (date(2026, 10, 10), date(2026, 10, 12))),
            ("oct 10 to nov 2", (date(2026, 10, 10), date(2026, 11, 2))),
            ("dal 10/10 al 13/10", (date(2026, 10, 10), date(2026, 10, 13))),
            ("2026-11-07 - 2026-11-09", (date(2026, 11, 7), date(2026, 11, 9))),
            ("dal 28 ottobre al 3 novembre", (date(2026, 10, 28), date(2026, 11, 3))),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.span(text), expected)

    def test_range_across_new_year(self):
        self.assertEqual(self.span("dal 28 dicembre al 3 gennaio"),
                         (date(2026, 12, 28), date(2027, 1, 3)))

    def test_past_range_is_next_year(self):
        self.assertEqual(self.span("dal 1 al 5 giugno"), (date(2027, 6, 1), date(2027, 6, 5)))

    def test_impossible_range_falls_through(self):
        p = parse_period("dal 30 al 31 febbraio", TODAY)
        self.assertEqual(p.label, "febbraio")

    def test_abbreviations_and_ordinals(self):
        self.assertEqual(self.span("il 12 ott"), (date(2026, 10, 12), date(2026, 10, 12)))
        self.assertEqual(self.span("the 10th of October"), (date(2026, 10, 10), date(2026, 10, 10)))
        self.assertEqual(self.span("Oct 3rd"), (date(2026, 10, 3), date(2026, 10, 3)))

    def test_abbreviation_only_next_to_a_day(self):
        self.assertEqual(parse_period("Lloret de Mar a ottobre", TODAY).label, "ottobre")
        self.assertIsNone(parse_period("padel a Lloret de Mar", TODAY))

    def test_month_first_is_not_people(self):
        p = parse_period("October 2 people", TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_month_parts(self):
        self.assertEqual(self.span("a inizio ottobre"), (date(2026, 10, 1), date(2026, 10, 10)))
        self.assertEqual(self.span("a metà marzo"), (date(2027, 3, 11), date(2027, 3, 20)))
        self.assertEqual(self.span("a fine ottobre"), (date(2026, 10, 21), date(2026, 10, 31)))
        self.assertEqual(self.span("early November"), (date(2026, 11, 1), date(2026, 11, 10)))
        self.assertEqual(self.span("mid-October"), (date(2026, 10, 11), date(2026, 10, 20)))
        self.assertEqual(self.span("late February"), (date(2027, 2, 21), date(2027, 2, 28)))

    def test_fine_settimana_is_still_weekend(self):
        self.assertEqual(parse_period("fine settimana", TODAY).label, "fine settimana")

    def test_next_month(self):
        self.assertEqual(self.span("il mese prossimo"), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(self.span("next month", date(2026, 12, 10)),
                         (date(2027, 1, 1), date(2027, 1, 31)))

    def test_impossible_single_date_falls_through(self):
        self.assertEqual(parse_period("il 31/02 a marzo", TODAY).label, "marzo")


class PaxTest(unittest.TestCase):
    def test_forms(self):
        for text, pax in [("siamo in due", 2), ("we are 3", 3), ("per due", 2), ("for four", 4),
                          ("2 persone", 2), ("three people", 3), ("x4", 4), ("in 2", 2),
                          ("siamo in tre amici", 3), ("we're 5", 5)]:
            with self.subTest(text=text):
                self.assertEqual(parse_pax(text), pax)

    def test_not_a_pax(self):
        self.assertIsNone(parse_pax("for 800 euro"))
        self.assertIsNone(parse_pax("per ottobre"))
        self.assertIsNone(parse_pax("padel in Spagna"))


class BudgetTest(unittest.TestCase):
    def test_forms(self):
        for text, budget in [("massimo 800 euro", 800), ("max 800", 800), ("budget di 950 euro", 950),
                             ("under 1000", 1000), ("up to 700 euros", 700), ("€ 650", 650),
                             ("650€", 650), ("fino a 1.200 euro", 1200), ("812,50 euro", Decimal("812.50")),
                             ("not more than 1,500 euros", 1500), ("meno di 900 euro", 900)]:
            with self.subTest(text=text):
                self.assertEqual(parse_budget(text), Decimal(budget))

    def test_budget_thousands_separator(self):
        self.assertEqual(parse_budget("1.000 euro"), Decimal("1000"))
        self.assertEqual(parse_budget("1,000 euros"), Decimal("1000"))

    def test_none(self):
        self.assertIsNone(parse_budget("siamo in 2 a ottobre"))


class LanguageTest(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(detect_language("un weekend di padel, siamo in due"), "it")
        self.assertEqual(detect_language("a weekend of padel for the two of us"), "en")
        self.assertEqual(detect_language("padel"), "it")


class QuestionTest(unittest.TestCase):
    def test_missing_sport_and_period_asks_sport_or_period(self):
        r = parse_intent("un viaggio in Spagna per due", today=TODAY)
        self.assertEqual(r.question, QUESTION_SPORT_OR_PERIOD)

    def test_missing_pax_asks_one_question(self):
        r = parse_intent("padel a ottobre", today=TODAY)
        self.assertEqual(r.question, QUESTION_PAX)
        self.assertEqual(r.criteria.sport, "padel")

    def test_pax_from_profile(self):
        r = parse_intent("padel a ottobre", profile=TravelerProfile(pax=2), today=TODAY)
        self.assertIsNone(r.question)
        self.assertEqual(r.criteria.pax, 2)

    def test_text_pax_beats_profile(self):
        r = parse_intent("padel a ottobre, siamo in 3", profile=TravelerProfile(pax=2), today=TODAY)
        self.assertEqual(r.criteria.pax, 3)

    def test_only_period_is_enough(self):
        r = parse_intent("qualcosa a ottobre per due", today=TODAY)
        self.assertIsNone(r.question)
        self.assertIsNone(r.criteria.sport)

    def test_area_and_period_objects(self):
        c = parse_intent("padel in Spagna a ottobre per due", today=TODAY).criteria
        self.assertEqual(c.area, Area("country", "Spagna", "ES"))
        self.assertEqual(c.period, Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"))
