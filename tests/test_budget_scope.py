"""M21-E (UC-E, RF-69, RF-70): budget a testa o totale."""
import unittest
from datetime import date

from vela.domain.intent import validate_fields
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
