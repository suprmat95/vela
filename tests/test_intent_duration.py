"""M21-A (UC-A, RF-58): durata in notti dal testo e dai campi dell'agente."""
import unittest
from datetime import date

from vela.domain.intent import parse_duration, parse_intent, parse_pax, parse_period
from vela.domain.models import StructuredFields

TODAY = date(2026, 9, 25)   # venerdì

# testo → (min notti, max notti); la tabella di UC-A, in italiano e in inglese
TABLE = [
    ("un weekend di padel in Spagna a ottobre, siamo in due", (1, 3)),
    ("padel nel fine settimana", (1, 3)),
    ("a padel weekend in Spain in October for two", (1, 3)),
    ("un ponte di padel a dicembre", (2, 4)),
    ("un lungo weekend di tennis", (2, 4)),
    ("un weekend lungo a Valencia", (2, 4)),
    ("a long weekend of padel", (2, 4)),
    ("una settimana di tennis in Portogallo, siamo in due", (6, 8)),
    ("a week of tennis in Portugal", (6, 8)),
    ("one week of padel", (6, 8)),
    ("due settimane di padel in Sardegna", (13, 15)),
    ("two weeks of tennis in Greece", (13, 15)),
    ("cinque giorni di tennis in Sardegna a maggio", (4, 4)),
    ("5 giorni di padel", (4, 4)),
    ("5 days of padel in Spain", (4, 4)),
    ("four nights of padel in May", (4, 4)),
    ("4 notti di padel a Malaga", (4, 4)),
    ("tre notti a Ibiza", (3, 3)),
    ("3 o 4 notti di padel", (3, 4)),
    ("3-4 notti di padel", (3, 4)),
    ("da 3 a 5 notti di tennis", (3, 5)),
    ("3 to 4 nights of padel", (3, 4)),
    ("3 or 4 nights of tennis", (3, 4)),
    ("almeno 3 notti di padel", (3, None)),
    ("at least 5 nights of tennis", (5, None)),
]

NO_DURATION = [
    "padel in Spagna a ottobre",
    "tennis dal 10 al 14 ottobre a Malaga",
    "padel la prima settimana di ottobre",
    "tennis in early October",
    "padel 20-23 novembre in Sardegna",
    "1 giorno di padel",          # 0 notti: non è una durata
    "40 notti di tennis",         # oltre 30
    "padel il mese prossimo",
]


class DurationTableTest(unittest.TestCase):
    def test_table(self):
        for text, expected in TABLE:
            with self.subTest(text=text):
                self.assertEqual(parse_duration(text), expected)

    def test_no_duration(self):
        for text in NO_DURATION:
            with self.subTest(text=text):
                self.assertIsNone(parse_duration(text))

    def test_both_languages_covered(self):
        en = [t for t, _ in TABLE if " of " in t or t.startswith("a ")]
        self.assertGreaterEqual(len(en), 8)
        self.assertGreaterEqual(len(TABLE) - len(en), 12)


class WeekendPeriodTest(unittest.TestCase):
    """Decisione "Un weekend": con l'articolo indeterminato è solo durata."""

    def test_a_weekend_is_not_a_period(self):
        for text in ("un weekend di padel in Spagna", "a padel weekend in Spain",
                     "un lungo weekend di tennis", "a weekend of padel", "un fine settimana"):
            with self.subTest(text=text):
                self.assertIsNone(parse_period(text, TODAY))

    def test_this_and_next_weekend_are_still_a_period(self):
        for text in ("questo weekend", "il prossimo weekend", "this weekend", "next weekend",
                     "fine settimana", "padel weekend, x2, 600€"):
            with self.subTest(text=text):
                p = parse_period(text, TODAY)
                self.assertEqual((p.start, p.end), (date(2026, 9, 26), date(2026, 9, 27)))

    def test_a_weekend_in_october(self):
        r = parse_intent("un weekend di padel a ottobre, siamo in due", today=TODAY)
        self.assertEqual(r.criteria.period.label, "ottobre")
        self.assertEqual((r.criteria.duration_min_nights, r.criteria.duration_max_nights), (1, 3))

    def test_this_weekend_is_period_and_duration(self):
        r = parse_intent("padel questo weekend, siamo in due", today=TODAY)
        self.assertEqual(r.criteria.period.start, date(2026, 9, 26))
        self.assertEqual((r.criteria.duration_min_nights, r.criteria.duration_max_nights), (1, 3))


class NightsAreNotPeopleTest(unittest.TestCase):
    def test_nights_and_days_are_not_pax(self):
        for text in ("padel for 3 nights", "tennis per 4 notti", "padel in 5 giorni",
                     "tennis for five days"):
            with self.subTest(text=text):
                self.assertIsNone(parse_pax(text))

    def test_people_still_read(self):
        self.assertEqual(parse_pax("4 notti di padel per 2"), 2)


class DurationFieldsTest(unittest.TestCase):
    def parse(self, text, **fields):
        return parse_intent(text, today=TODAY, fields=StructuredFields(**fields))

    def nights(self, r):
        return (r.criteria.duration_min_nights, r.criteria.duration_max_nights)

    def test_fields_alone(self):
        r = self.parse("padel in Spagna per 2", duration_min_nights=1, duration_max_nights=3)
        self.assertEqual(self.nights(r), (1, 3))
        self.assertEqual(r.discarded, ())

    def test_one_field_is_enough(self):
        self.assertEqual(self.nights(self.parse("padel per 2", duration_min_nights=4)), (4, None))
        self.assertEqual(self.nights(self.parse("padel per 2", duration_max_nights=4)), (None, 4))

    def test_field_beats_text_and_conflict_is_reported(self):
        r = self.parse("un weekend di padel per 2", duration_min_nights=6, duration_max_nights=8)
        self.assertEqual(self.nights(r), (6, 8))
        self.assertIn(("duration_min_nights", 1, 6), r.conflicts)
        self.assertIn(("duration_max_nights", 3, 8), r.conflicts)

    def test_one_field_replaces_the_whole_text_duration(self):
        r = self.parse("un weekend di padel per 2", duration_min_nights=5)
        self.assertEqual(self.nights(r), (5, None))

    def test_invalid_fields_are_discarded_and_declared(self):
        for min_n, max_n in ((0, 3), (4, 2), (1, 31), (True, 3), ("3", 4), (2.5, None)):
            with self.subTest(min=min_n, max=max_n):
                r = self.parse("un weekend di padel per 2", duration_min_nights=min_n,
                               duration_max_nights=max_n)
                self.assertEqual(r.discarded, (("duration", (min_n, max_n)),))
                self.assertEqual(self.nights(r), (1, 3))   # resta la durata del testo


if __name__ == "__main__":
    unittest.main()
