import unittest
from datetime import date
from decimal import Decimal

from vela.domain.intent import (QUESTION_PAX, QUESTION_PAX_EN, QUESTION_SPORT,
                                QUESTION_SPORT_EN, detect_language,
                                is_per_person, parse_budget, parse_intent, parse_pax,
                                parse_period, parse_sport)
from vela.domain.models import Area, Period, StructuredFields, TravelerProfile

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
    ("padel dal 10 al 14 ottobre a Malaga, siamo in 2",
     ("padel", "ES", (date(2026, 10, 10), date(2026, 10, 14)), 2, None, "it")),
    ("tennis from 10 to 14 October in Greece, two of us",
     ("tennis", "GR", (date(2026, 10, 10), date(2026, 10, 14)), 2, None, "en")),
    ("padel 20-23 novembre in Sardegna per 4 persone, budget 2k",
     ("padel", "IT", (date(2026, 11, 20), date(2026, 11, 23)), 4, Decimal("2000"), "it")),
    ("padel tra il 5 e l'8 dicembre, in coppia",
     ("padel", None, (date(2026, 12, 5), date(2026, 12, 8)), 2, None, "it")),
    ("tennis dal 28 dicembre al 3 gennaio a Tenerife, siamo in tre",
     ("tennis", "ES", (date(2026, 12, 28), date(2027, 1, 3)), 3, None, "it")),
    ("padel October 10-12 in Mallorca for two",
     ("padel", "ES", (date(2026, 10, 10), date(2026, 10, 12)), 2, None, "en")),
    ("padel a fine ottobre per 2 persone",
     ("padel", None, (date(2026, 10, 21), date(2026, 10, 31)), 2, None, "it")),
    ("tennis in early November, just me",
     ("tennis", None, (date(2026, 11, 1), date(2026, 11, 10)), 1, None, "en")),
    ("padel a metà marzo a Valencia, io e mia moglie",
     ("padel", "ES", (date(2027, 3, 11), date(2027, 3, 20)), 2, None, "it")),
    ("padel il mese prossimo, siamo una famiglia di 4",
     ("padel", None, (date(2026, 10, 1), date(2026, 10, 31)), 4, None, "it")),
    ("tennis next month in Italy, a couple, under 1500 euros",
     ("tennis", "IT", (date(2026, 10, 1), date(2026, 10, 31)), 2, Decimal("1500"), "en")),
    ("padel in Andalusia a novembre, 500 euro a testa, siamo in 2",
     ("padel", "ES", (date(2026, 11, 1), date(2026, 11, 30)), 2, Decimal("1000"), "it")),
    ("padel weekend in Catalonia for 3 people, 400 euros each",
     ("padel", "ES", (date(2026, 9, 26), date(2026, 9, 27)), 3, Decimal("1200"), "en")),
    ("padel a Lloret de Mar a ottobre in 2",
     ("padel", "ES", (date(2026, 10, 1), date(2026, 10, 31)), 2, None, "it")),
    ("vorrei giocare a padel il 12 ott, sotto i 900 euro, da solo",
     ("padel", None, (date(2026, 10, 12), date(2026, 10, 12)), 1, Decimal("900"), "it")),
    ("tennis Oct 3rd in Madrid for four players",
     ("tennis", "ES", (date(2026, 10, 3), date(2026, 10, 3)), 4, None, "en")),
    ("padel in primavera in Grecia, due coppie, massimo 3000 euro",
     ("padel", "GR", (date(2027, 3, 1), date(2027, 5, 31)), 4, Decimal("3000"), "it")),
    ("tennis on 2026-11-07 - 2026-11-09 in Emilia-Romagna, we are 2, max 1.200 euros",
     ("tennis", "IT", (date(2026, 11, 7), date(2026, 11, 9)), 2, Decimal("1200"), "en")),
    ("padel dal 10/10 al 13/10, siamo in 4",
     ("padel", None, (date(2026, 10, 10), date(2026, 10, 13)), 4, None, "it")),
    ("tennis tra il 1 e il 5 giugno in Toscana per due",
     ("tennis", "IT", (date(2027, 6, 1), date(2027, 6, 5)), 2, None, "it")),
    ("tennis in Zanzibar between 14 and 20 November for 2 people",
     ("tennis", "TZ", (date(2026, 11, 14), date(2026, 11, 20)), 2, None, "en")),
    ("padel from the 3rd to the 7th of December in Cyprus, 2 adults",
     ("padel", "CY", (date(2026, 12, 3), date(2026, 12, 7)), 2, None, "en")),
]


class TableSizeTest(unittest.TestCase):
    def test_at_least_thirty_cases_in_both_languages(self):
        self.assertGreaterEqual(len(TABLE), 30)
        langs = [row[1][5] for row in TABLE]
        self.assertGreaterEqual(langs.count("en"), 10)
        self.assertGreaterEqual(langs.count("it"), 15)


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


# M17: esclusioni, poi "any", poi sinonimi, poi padel/tennis
SPORT_TABLE = [
    ("un weekend di padel a Valencia", "padel"),
    ("tennis camp in Mallorca", "tennis"),
    ("un viaggio sulla terra rossa a maggio", "tennis"),
    ("giocare sulla Terra Rossa", "tennis"),
    ("una settimana con Terrarossa in Puglia", "tennis"),
    ("a clay court week in Spain", "tennis"),
    ("playing on clay in May", "tennis"),
    ("un weekend di paddle a Valencia", "padel"),
    ("pádel en Madrid", "padel"),
    ("un viaggio Weebora in Spagna", "padel"),
    ("padel e tennis in Spagna", "any"),
    ("tennis and padel in Portugal", "any"),
    ("Padel o tennis? Indifferente, basta che sia al caldo", "any"),
    ("indifferente", "any"),
    ("tutti e due", "any"),
    ("vanno bene entrambi gli sport", "any"),
    ("lo sport non importa", "any"),
    ("either is fine", "any"),
    ("both sports are fine", "any"),
    ("the sport doesn't matter", "any"),
    ("beach tennis a Rimini", None),
    ("a paddle tennis week", None),
    ("beach tennis e padel", "padel"),
    ("una vacanza a Maiorca a giugno", None),
    ("siamo in due, per il ponte", None),
]


class SportTest(unittest.TestCase):
    def test_sport_table(self):
        for text, sport in SPORT_TABLE:
            with self.subTest(text=text):
                self.assertEqual(parse_sport(text), sport)

    def test_both_of_us_is_not_both_sports(self):
        self.assertIsNone(parse_sport("a trip for both of us"))
        self.assertEqual(parse_sport("a padel trip for both of us"), "padel")


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

    def test_new_forms(self):
        for text, pax in [("in coppia", 2), ("siamo una coppia", 2), ("as a couple", 2),
                          ("a couple", 2), ("io e mia moglie", 2), ("io e il mio compagno", 2),
                          ("me and my wife", 2), ("my husband and I", 2), ("da solo", 1),
                          ("da sola", 1), ("just me", 1), ("on my own", 1), ("alone", 1),
                          ("famiglia di 4", 4), ("a family of five", 5), ("group of 6", 6),
                          ("due coppie", 4), ("three couples", 6)]:
            with self.subTest(text=text):
                self.assertEqual(parse_pax(text), pax)

    def test_number_beats_phrase(self):
        self.assertEqual(parse_pax("io e mia moglie, in tutto siamo in 4"), 4)

    def test_couple_of_days_is_not_pax(self):
        self.assertIsNone(parse_pax("a couple of days of padel"))


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

    def test_new_forms(self):
        for text, budget in [("budget 2k", 2000), ("max 1,5k", 1500), ("1.5k euro", 1500),
                             ("sotto i 900 euro", 900), ("sotto 900", 900), ("non oltre 700", 700),
                             ("below 650", 650), ("at most 1000", 1000), ("tetto di 1200", 1200)]:
            with self.subTest(text=text):
                self.assertEqual(parse_budget(text), Decimal(budget))

    def test_number_before_people_is_not_budget(self):
        self.assertIsNone(parse_budget("massimo 4 persone"))
        self.assertIsNone(parse_budget("max 3 nights"))
        self.assertIsNone(parse_budget("massimo 40 persone"))
        self.assertEqual(parse_intent("padel a ottobre, massimo 4 persone", today=TODAY).criteria.pax, 4)

    def test_per_person(self):
        self.assertTrue(is_per_person("500 euro a testa"))
        self.assertTrue(is_per_person("400 euros each"))
        self.assertTrue(is_per_person("600 per person"))
        self.assertFalse(is_per_person("per persone 4"))
        self.assertFalse(is_per_person("massimo 800 euro"))

    def test_per_person_budget(self):
        c = parse_intent("padel a ottobre, 500 euro a testa, siamo in 3", today=TODAY).criteria
        self.assertEqual(c.budget, Decimal("1500"))
        c = parse_intent("padel a ottobre, 500 euro a testa", today=TODAY).criteria
        self.assertEqual(c.budget, Decimal("500"))
        self.assertIsNone(c.pax)


class LanguageTest(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(detect_language("un weekend di padel, siamo in due"), "it")
        self.assertEqual(detect_language("a weekend of padel for the two of us"), "en")
        self.assertEqual(detect_language("padel"), "it")

    def test_new_markers(self):
        self.assertEqual(detect_language("tennis in early November, just me"), "en")
        self.assertEqual(detect_language("padel tra il 5 e l'8 dicembre, in coppia"), "it")
        self.assertEqual(detect_language("padel a Lloret de Mar a ottobre in 2"), "it")


class QuestionTest(unittest.TestCase):
    def test_missing_sport_asks_sport(self):
        r = parse_intent("un viaggio in Spagna per due", today=TODAY)
        self.assertEqual(r.question, QUESTION_SPORT)

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

    def test_period_without_sport_asks_sport(self):
        # RF-04 (M17): lo sport è sempre indispensabile, il periodo non basta più
        r = parse_intent("qualcosa a ottobre per due", today=TODAY)
        self.assertEqual(r.question, QUESTION_SPORT)

    def test_sport_without_period_is_enough(self):
        r = parse_intent("padel per due", today=TODAY)
        self.assertIsNone(r.question)
        self.assertIsNone(r.criteria.period)

    def test_sport_asked_before_pax(self):
        self.assertEqual(parse_intent("una vacanza a Maiorca a giugno", today=TODAY).question,
                         QUESTION_SPORT)

    def test_any_is_a_valid_sport(self):
        r = parse_intent("padel o tennis indifferente, a novembre per due", today=TODAY)
        self.assertIsNone(r.question)
        self.assertEqual(r.criteria.sport, "any")

    def test_questions_in_english(self):
        self.assertEqual(parse_intent("a trip to Spain for the two of us", today=TODAY).question,
                         QUESTION_SPORT_EN)
        self.assertEqual(parse_intent("we want padel in October", today=TODAY).question,
                         QUESTION_PAX_EN)

    def test_area_and_period_objects(self):
        c = parse_intent("padel in Spagna a ottobre per due", today=TODAY).criteria
        self.assertEqual(c.area, Area("country", "Spagna", "ES"))
        self.assertEqual(c.period, Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"))


class FakeExtractor:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def extract(self, text, today):
        self.calls.append((text, today))
        if self.error:
            raise self.error
        return self.result


VAGUE = "una vacanza con la racchetta in Spagna per due"   # né sport né periodo
GOOD = {"sport": "padel", "area": "Greece", "period_start": "2026-11-01",
        "period_end": "2026-11-30", "pax": 3, "budget": 1500}


class FallbackTest(unittest.TestCase):
    def test_not_called_when_sport_found(self):
        fx = FakeExtractor(GOOD)
        parse_intent("padel in Spagna per due", today=TODAY, extractor=fx)
        self.assertEqual(fx.calls, [])

    def test_called_when_sport_missing_even_with_period(self):
        # RF-03 (M17): il fallback parte quando manca lo sport, anche se il periodo c'è
        fx = FakeExtractor(GOOD)
        r = parse_intent("qualcosa a ottobre per due", today=TODAY, extractor=fx)
        self.assertEqual(len(fx.calls), 1)
        self.assertEqual(r.criteria.sport, "padel")
        self.assertEqual(r.criteria.period.label, "ottobre")

    def test_fills_only_missing_criteria(self):
        # RF-53: parser > Haiku; il fallback riempie solo i criteri vuoti
        fx = FakeExtractor(GOOD)
        r = parse_intent(VAGUE, today=TODAY, extractor=fx)
        self.assertEqual(fx.calls, [(VAGUE, TODAY)])
        c = r.criteria
        self.assertEqual(c.sport, "padel")
        self.assertEqual(c.area, Area("country", "Spagna", "ES"))
        self.assertEqual(c.period, Period(date(2026, 11, 1), date(2026, 11, 30), "llm"))
        self.assertEqual(c.pax, 2)
        self.assertEqual(c.budget, Decimal("1500"))
        self.assertEqual(c.language, "it")
        self.assertIsNone(r.question)

    def test_any_from_fallback(self):
        r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor({"sport": "any"}))
        self.assertEqual(r.criteria.sport, "any")
        self.assertIsNone(r.question)

    def test_null_fields_keep_parser_values(self):
        fx = FakeExtractor({"sport": "tennis", "area": None, "period_start": None,
                            "period_end": None, "pax": None, "budget": None})
        c = parse_intent(VAGUE, today=TODAY, extractor=fx).criteria
        self.assertEqual((c.sport, c.area.country_code, c.pax), ("tennis", "ES", 2))

    def test_invalid_fields_are_ignored(self):
        baseline = parse_intent(VAGUE, today=TODAY).criteria
        for bad in [
            {"sport": "golf", "area": "Atlantide", "period_start": "2026-12-10",
             "period_end": "2026-12-01", "pax": 0, "budget": -5},
            {"sport": 7, "area": 3, "period_start": "2025-01-01", "period_end": "2025-01-05",
             "pax": True, "budget": "abc"},
            {"period_start": "ieri", "period_end": "domani", "pax": 50, "budget": True},
            {"period_start": "2026-11-01"},
        ]:
            with self.subTest(bad=bad):
                r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor(bad))
                self.assertEqual(r.criteria, baseline)
                self.assertEqual(r.question, QUESTION_SPORT)

    def test_extractor_error_is_ignored(self):
        r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor(error=RuntimeError("boom")))
        self.assertEqual(r.question, QUESTION_SPORT)

    def test_extractor_returning_none_or_junk(self):
        for result in (None, "testo", ["x"]):
            with self.subTest(result=result):
                r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor(result))
                self.assertEqual(r.question, QUESTION_SPORT)

    def test_no_extractor_no_error(self):
        self.assertEqual(parse_intent(VAGUE, today=TODAY).question, QUESTION_SPORT)


class FieldsTest(unittest.TestCase):
    """RF-52, RF-53: campo strutturato valido > parser > Haiku; campo invalido scartato."""

    def test_fields_alone_build_the_criteria(self):
        f = StructuredFields(sport="padel", area="Spagna", period_start="2026-10-01",
                             period_end="2026-10-31", pax=2, budget=800)
        r = parse_intent("qualcosa", today=TODAY, fields=f)
        c = r.criteria
        self.assertIsNone(r.question)
        self.assertEqual(c.sport, "padel")
        self.assertEqual(c.area, Area("country", "Spagna", "ES"))
        self.assertEqual((c.period.start, c.period.end), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual((c.pax, c.budget), (2, Decimal("800.00")))
        self.assertEqual((r.discarded, r.conflicts), ((), ()))

    def test_field_beats_parser_and_conflict_is_reported(self):
        r = parse_intent("Tennis a Roma a maggio per due", today=TODAY,
                         fields=StructuredFields(sport="padel"))
        self.assertEqual(r.criteria.sport, "padel")
        self.assertEqual(r.conflicts, (("sport", "tennis", "padel"),))

    def test_same_value_is_not_a_conflict(self):
        r = parse_intent("padel per due", today=TODAY, fields=StructuredFields(sport="padel", pax=2))
        self.assertEqual(r.conflicts, ())

    def test_field_pax_beats_text_and_profile(self):
        r = parse_intent("padel, siamo in 3", profile=TravelerProfile(pax=4), today=TODAY,
                         fields=StructuredFields(pax=2))
        self.assertEqual(r.criteria.pax, 2)
        self.assertEqual(r.conflicts, (("pax", 3, 2),))

    def test_field_pax_used_for_per_person_budget(self):
        r = parse_intent("padel, 500 euro a testa", today=TODAY, fields=StructuredFields(pax=2))
        self.assertEqual(r.criteria.budget, Decimal("1000"))

    def test_invalid_fields_are_discarded_not_blocking(self):
        f = StructuredFields(sport="golf", area="Atlantide", period_start="2026-12-10",
                             period_end="2026-12-01", pax=0, budget=-5)
        r = parse_intent("padel in Spagna per due", today=TODAY, fields=f)
        self.assertIsNone(r.question)
        c = r.criteria
        self.assertEqual((c.sport, c.area.name, c.pax), ("padel", "Spagna", 2))
        self.assertEqual([d[0] for d in r.discarded], ["sport", "area", "period", "pax", "budget"])
        self.assertIn(("area", "Atlantide"), r.discarded)

    def test_past_or_partial_period_is_discarded(self):
        for f in (StructuredFields(period_start="2025-01-01", period_end="2025-01-05"),
                  StructuredFields(period_start="2026-11-01"),
                  StructuredFields(period_end="2026-11-30"),
                  StructuredFields(period_start="ieri", period_end="domani")):
            with self.subTest(f=f):
                r = parse_intent("padel per due", today=TODAY, fields=f)
                self.assertIsNone(r.criteria.period)
                self.assertEqual([d[0] for d in r.discarded], ["period"])

    def test_pax_out_of_range_and_bool(self):
        for pax in (0, 21, True):
            with self.subTest(pax=pax):
                r = parse_intent("padel per due", today=TODAY, fields=StructuredFields(pax=pax))
                self.assertEqual(r.criteria.pax, 2)
                self.assertEqual(r.discarded, (("pax", pax),))

    def test_field_sport_any(self):
        r = parse_intent("al caldo a novembre per due", today=TODAY,
                         fields=StructuredFields(sport="ANY"))
        self.assertEqual(r.criteria.sport, "any")
        self.assertIsNone(r.question)

    def test_field_sport_skips_fallback(self):
        fx = FakeExtractor(GOOD)
        parse_intent(VAGUE, today=TODAY, extractor=fx, fields=StructuredFields(sport="tennis"))
        self.assertEqual(fx.calls, [])

    def test_field_beats_fallback(self):
        fx = FakeExtractor(GOOD)
        r = parse_intent("una vacanza per due", today=TODAY, extractor=fx,
                         fields=StructuredFields(budget=900, area="Italia"))
        c = r.criteria
        self.assertEqual(c.sport, "padel")
        self.assertEqual((c.budget, c.area.name), (Decimal("900.00"), "Italia"))

    def test_no_sport_from_fields_parser_or_fallback_asks(self):
        r = parse_intent("per il ponte dell'8 dicembre, siamo in due", today=TODAY,
                         fields=StructuredFields(period_start="2026-12-05", period_end="2026-12-08"))
        self.assertEqual(r.question, QUESTION_SPORT)
