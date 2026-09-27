"""M21-C (UC-C, RF-62, RF-52, RF-53): livello di gioco e lezioni dal testo e dai campi."""
import unittest
from datetime import date
from decimal import Decimal

from vela.domain import say
from vela.domain.intent import parse_intent, parse_level, parse_pax, parse_wants_coaching, validate_fields
from vela.domain.models import Area, Criteria, Period, StructuredFields, criteria_from_dict, criteria_to_dict

TODAY = date(2026, 9, 25)

# testo → (livello, lezioni); le varianti di UC-C in italiano e in inglese, più i casi di confine
TABLE = [
    ("Siamo principianti, vorremmo lezioni di padel in Spagna a ottobre, in due.", "beginner", True),
    ("Non abbiamo mai giocato, ci serve un maestro", "beginner", True),
    ("giochiamo a livello intermedio, vorremmo allenarci con un coach", "intermediate", True),
    ("siamo agonisti, niente corsi per principianti", "advanced", False),
    ("We're beginners and would like lessons", "beginner", True),
    ("intermediate players, looking for a clinic", "intermediate", True),
    ("advanced players, no coaching needed", "advanced", False),
    ("siamo alle prime armi con il padel", "beginner", None),
    ("we have never played tennis", "beginner", None),
    ("siamo giocatori esperti di tennis", "advanced", None),
    ("competitive padel players looking for a week in Spain", "advanced", None),
    ("un corso di padel a Malaga", None, True),
    ("a padel training camp in Portugal", None, True),
    ("padel senza lezioni, solo partite", None, False),
    ("tennis without lessons please", None, False),
    ("padel in Spagna a ottobre, siamo in due", None, None),
    ("tennis nel corso di ottobre", None, None),                 # "nel corso di" è un periodo
    ("padel con un maestro esperto", None, True),                # esperto è il maestro
    ("non siamo esperti, ci serve un coach", None, True),        # livello negato: non detto
    ("io sono principiante, lei è di livello intermedio", "beginner", None),   # il più basso
    ("we're not beginners, we play at an intermediate level", "intermediate", None),
]


class ParserTableTest(unittest.TestCase):
    def test_table(self):
        for text, level, coaching in TABLE:
            with self.subTest(text):
                self.assertEqual((parse_level(text), parse_wants_coaching(text)), (level, coaching))

    def test_uc_c_sentence_keeps_the_other_criteria(self):
        r = parse_intent("Siamo principianti, vorremmo lezioni di padel in Spagna a ottobre, in due.",
                         today=TODAY)
        c = r.criteria
        self.assertIsNone(r.question)
        self.assertEqual((c.sport, c.area.name, c.pax, c.level, c.wants_coaching),
                         ("padel", "Spagna", 2, "beginner", True))
        self.assertEqual((c.period.start, c.period.end), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_in_due_is_two_people_but_not_a_length(self):
        """UC-C chiude con "in due": due persone; "in due settimane" resta una durata e "in una
        villa" non è un numero di persone."""
        self.assertEqual(parse_pax("padel a ottobre, in due"), 2)
        self.assertEqual(parse_pax("tennis in three"), 3)
        self.assertIsNone(parse_pax("padel in due settimane"))
        self.assertIsNone(parse_pax("padel in una villa"))

    def test_english_sentence_is_english(self):
        c = parse_intent("We're beginners and would like padel lessons in Spain, two of us",
                         today=TODAY).criteria
        self.assertEqual((c.language, c.level, c.wants_coaching, c.pax), ("en", "beginner", True, 2))


class FieldsTest(unittest.TestCase):
    """RF-52, RF-53: `level` e `wants_coaching` come campi; invalidi scartati e detti."""

    def test_valid_fields(self):
        valid, discarded = validate_fields({"level": " Advanced ", "wants_coaching": False}, TODAY)
        self.assertEqual(valid, {"level": "advanced", "wants_coaching": False})
        self.assertEqual(discarded, ())

    def test_invalid_fields_are_discarded(self):
        valid, discarded = validate_fields({"level": "pro", "wants_coaching": "yes"}, TODAY)
        self.assertEqual(valid, {})
        self.assertEqual(discarded, (("level", "pro"), ("wants_coaching", "yes")))
        for value in (3, None):
            with self.subTest(value=value):
                valid, _ = validate_fields({"level": value}, TODAY)
                self.assertNotIn("level", valid)

    def test_field_wins_over_text_and_the_conflict_is_logged(self):
        r = parse_intent("siamo principianti, padel a Malaga in due", today=TODAY,
                         fields=StructuredFields(level="intermediate", wants_coaching=True))
        self.assertEqual((r.criteria.level, r.criteria.wants_coaching), ("intermediate", True))
        self.assertIn(("level", "beginner", "intermediate"), r.conflicts)

    def test_uc_c_agent_call(self):
        """UC-C: la chiamata dell'agente con tutti i campi."""
        r = parse_intent("Siamo principianti, vorremmo lezioni di padel in Spagna a ottobre, in due.",
                         today=TODAY, fields=StructuredFields(
                             sport="padel", area="Spagna", period_start="2026-10-01",
                             period_end="2026-10-31", pax=2, level="beginner", wants_coaching=True))
        self.assertEqual((r.criteria.level, r.criteria.wants_coaching, r.discarded, r.conflicts),
                         ("beginner", True, (), ()))

    def test_invalid_field_leaves_the_text_value(self):
        r = parse_intent("siamo principianti, padel a Malaga in due", today=TODAY,
                         fields=StructuredFields(level="expert"))
        self.assertEqual(r.criteria.level, "beginner")
        self.assertEqual(r.discarded, (("level", "expert"),))


class CriteriaTest(unittest.TestCase):
    def test_round_trip(self):
        c = Criteria(sport="padel", pax=2, rooms=1, level="beginner", wants_coaching=False)
        d = criteria_to_dict(c)
        self.assertEqual((d["level"], d["wants_coaching"]), ("beginner", False))
        self.assertEqual(criteria_from_dict(d), c)

    def test_intent_saved_before_m21c_has_no_level(self):
        c = criteria_from_dict({"sport": "padel", "pax": 2, "language": "it"})
        self.assertEqual((c.level, c.wants_coaching), (None, None))


PERIOD = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")


class SayTest(unittest.TestCase):
    """RF-54: il livello e le lezioni nella riga dei criteri capiti."""

    def test_level_and_coaching_in_the_understood_line(self):
        c = Criteria("padel", SPAIN, PERIOD, 2, rooms=1, level="beginner", wants_coaching=True)
        self.assertEqual(say.say_understood(c),
                         "Ho capito: un viaggio di padel in Spagna tra il 1 ottobre 2026 e il 31 "
                         "ottobre 2026 per 2 persone, livello principiante, con lezioni.")
        c = Criteria("padel", SPAIN, PERIOD, 2, Decimal("800"), rooms=1, level="advanced",
                     wants_coaching=False, budget_scope="total")
        self.assertEqual(say.say_understood(c),
                         "Ho capito: un viaggio di padel in Spagna tra il 1 ottobre 2026 e il 31 "
                         "ottobre 2026 per 2 persone, livello avanzato, senza lezioni, con un "
                         "budget di 800 euro in tutto.")
        c = Criteria("padel", pax=2, rooms=1, wants_coaching=True)
        self.assertEqual(say.say_understood(c), "Ho capito: un viaggio di padel per 2 persone, con lezioni.")

    def test_english(self):
        c = Criteria("padel", SPAIN, None, 2, language="en", rooms=1, level="intermediate",
                     wants_coaching=True)
        self.assertEqual(say.say_understood(c),
                         "Got it: a padel trip in Spain for 2 people, intermediate level, with lessons.")

    def test_nothing_said_nothing_added(self):
        c = Criteria("padel", pax=2, rooms=1)
        self.assertEqual(say.say_understood(c), "Ho capito: un viaggio di padel per 2 persone.")

    def test_discarded_sentences(self):
        self.assertEqual(say.say_discarded((("level", "pro"), ("wants_coaching", "yes"))),
                         "Non ho potuto usare pro come livello di gioco: principiante, intermedio "
                         "o avanzato. Non ho potuto usare yes per sapere se vuoi lezioni: sì o no.")
        self.assertEqual(say.say_discarded((("level", "pro"),), "en"),
                         "I couldn't use pro as the playing level: beginner, intermediate or advanced.")
        self.assertEqual(say.say_discarded((("wants_coaching", "yes"),), "en"),
                         "I couldn't use yes to know whether you want lessons: yes or no.")


if __name__ == "__main__":
    unittest.main()
