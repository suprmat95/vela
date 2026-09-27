"""M21-E (UC-E, RF-69, RF-70): budget a testa o totale."""
import unittest
from datetime import date
from decimal import Decimal

from vela.domain.intent import parse_budget, parse_budget_scope, parse_intent, validate_fields
from vela.domain.models import StructuredFields

TODAY = date(2026, 9, 25)   # venerdì


class BudgetScopeFieldTest(unittest.TestCase):
    """RF-52, RF-53: `budget_scope` valido, invalido scartato, assente né l'uno né l'altro."""

    def test_valid_values(self):
        for value in ("per_person", "total", " Total "):
            with self.subTest(value=value):
                valid, discarded = validate_fields({"budget_scope": value}, TODAY)
                self.assertEqual(valid, {"budget_scope": value.strip().lower()})
                self.assertEqual(discarded, ())

    def test_invalid_values_are_discarded(self):
        for value in ("each", "", 3, True):
            with self.subTest(value=value):
                valid, discarded = validate_fields({"budget_scope": value}, TODAY)
                self.assertEqual(valid, {})
                self.assertEqual(discarded, (("budget_scope", value),))

    def test_absent_is_neither(self):
        self.assertEqual(validate_fields({"budget_scope": None}, TODAY), ({}, ()))

    def test_structured_fields_carry_it(self):
        self.assertEqual(StructuredFields(budget_scope="total").as_dict()["budget_scope"], "total")


# UC-E, regole 2-3: testo con tre persone → (tetto sul totale, lettura)
TABLE = [
    ("tennis in Spagna a maggio, siamo in tre, 600 euro a testa", (Decimal("1800"), "per_person")),
    ("tennis in Spagna a maggio, siamo in tre, 1.800 euro in tutto", (Decimal("1800"), "total")),
    ("tennis in Spagna a maggio, siamo in tre, non più di 600 a persona", (Decimal("1800"), "per_person")),
    ("tennis in Spagna a maggio, siamo in tre, budget totale 1.500", (Decimal("1500"), "total")),
    ("tennis in Spagna a maggio, siamo in tre, 1.500 euro complessivi", (Decimal("1500"), "total")),
    ("tennis in Spagna a maggio, siamo in tre, in totale 1500 euro", (Decimal("1500"), "total")),
    ("tennis in Spain in May, three of us, 600 euros each", (Decimal("1800"), "per_person")),
    ("tennis in Spain in May, three of us, 1,800 in total", (Decimal("1800"), "total")),
    ("tennis in Spain in May, three of us, up to 600 per person", (Decimal("1800"), "per_person")),
    ("tennis in Spain in May, three of us, total budget 1,500", (Decimal("1500"), "total")),
    ("tennis in Spain in May, three of us, 1500 euros altogether", (Decimal("1500"), "total")),
    ("tennis in Spain in May, three of us, 600 each", (Decimal("1800"), "per_person")),
]


class BudgetWordsTest(unittest.TestCase):
    """RF-69, regole 2-3: le parole del testo decidono la lettura."""

    def test_table(self):
        for text, expected in TABLE:
            with self.subTest(text=text):
                c = parse_intent(text, today=TODAY).criteria
                self.assertEqual(c.pax, 3)
                self.assertEqual((c.budget, c.budget_scope), expected)

    def test_scope_words(self):
        for text, scope in (("500 euro a testa", "per_person"), ("600 per head", "per_person"),
                            ("1800 in tutto", "total"), ("in total 1800", "total"),
                            ("massimo 800 euro", None)):
            with self.subTest(text=text):
                self.assertEqual(parse_budget_scope(text), scope)

    def test_people_in_total_is_not_a_budget_reading(self):
        """"Siamo 4 in tutto" parla delle persone, non del budget."""
        for text in ("siamo 4 in tutto, massimo 800 euro", "we are four in total, max 800 euros",
                     "3 persone in tutto, budget 900"):
            with self.subTest(text=text):
                self.assertIsNone(parse_budget_scope(text))

    def test_small_figure_before_the_words_is_not_money(self):
        self.assertIsNone(parse_budget("siamo 4 in tutto"))
        self.assertIsNone(parse_budget("we are 2 each"))

    def test_one_person_is_total(self):
        """Regola 5: con una persona le due letture coincidono."""
        c = parse_intent("padel a ottobre da solo, massimo 600 euro", today=TODAY).criteria
        self.assertEqual((c.pax, c.budget, c.budget_scope), (1, Decimal("600"), "total"))

    def test_bare_figure_with_a_group_and_no_catalog_is_total(self):
        c = parse_intent("padel a ottobre, siamo in tre, massimo 600 euro", today=TODAY).criteria
        self.assertEqual((c.budget, c.budget_scope), (Decimal("600"), "total"))

    def test_no_budget_no_scope(self):
        c = parse_intent("padel a ottobre, siamo in tre, a testa", today=TODAY).criteria
        self.assertEqual((c.budget, c.budget_scope), (None, None))


class BudgetScopeFieldPrecedenceTest(unittest.TestCase):
    """RF-69, regola 1: il campo vince sulle parole, il conflitto va nei log (RF-53)."""

    def parse(self, text, **fields):
        return parse_intent(text, today=TODAY, fields=StructuredFields(**fields))

    def test_field_beats_the_words(self):
        r = self.parse("padel, siamo in tre, 600 euro a testa", budget_scope="total")
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope), (Decimal("600"), "total"))
        self.assertIn(("budget_scope", "per_person", "total"), r.conflicts)

    def test_field_figure_and_field_scope(self):
        r = self.parse("padel a maggio", pax=3, budget=600, budget_scope="per_person")
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope),
                         (Decimal("1800.00"), "per_person"))
        self.assertEqual(r.conflicts, ())

    def test_field_figure_read_with_the_words(self):
        """L'agente passa la cifra detta; "a testa" nel testo la moltiplica."""
        r = self.parse("padel, siamo in tre, 600 euro a testa", pax=3, budget=600)
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope),
                         (Decimal("1800.00"), "per_person"))
        self.assertEqual(r.conflicts, ())

    def test_scope_without_budget_has_no_effect(self):
        r = self.parse("padel a maggio, siamo in tre", budget_scope="per_person")
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope), (None, None))
        self.assertEqual(r.discarded, ())

    def test_invalid_scope_is_discarded_and_the_words_decide(self):
        r = self.parse("padel, siamo in tre, 600 euro a testa", budget_scope="each")
        self.assertEqual(r.discarded, (("budget_scope", "each"),))
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope),
                         (Decimal("1800"), "per_person"))
