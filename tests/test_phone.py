"""Numeri per gli SMS (decisione 2026-09-26): E.164 con +39 di default."""
import unittest

from vela.domain.phone import mask, normalize_it, tail


class NormalizeTest(unittest.TestCase):
    def test_italian_mobile_gets_plus39(self):
        self.assertEqual(normalize_it("333 123 4567"), "+393331234567")

    def test_separators_are_removed(self):
        self.assertEqual(normalize_it("(333) 123-45.67"), "+393331234567")
        self.assertEqual(normalize_it("333/1234567"), "+393331234567")

    def test_plus39_is_not_doubled(self):
        self.assertEqual(normalize_it("+39 333 1234567"), "+393331234567")

    def test_0039_becomes_plus39(self):
        self.assertEqual(normalize_it("0039 333 1234567"), "+393331234567")

    def test_foreign_number_is_kept(self):
        self.assertEqual(normalize_it("+44 20 7946 0958"), "+442079460958")

    def test_landline_keeps_leading_zero(self):
        self.assertEqual(normalize_it("02 1234 5678"), "+390212345678")

    def test_invalid_numbers_give_none(self):
        for raw in (None, "", "   ", "abc", "+39 333", "12", "+39 3331234567890123", "333 abc 4567"):
            self.assertIsNone(normalize_it(raw), raw)


class TailAndMaskTest(unittest.TestCase):
    def test_tail_is_last_four_digits_of_normalized_number(self):
        self.assertEqual(tail("333 123 4567"), "4567")
        self.assertIsNone(tail("abc"))
        self.assertIsNone(tail(None))

    def test_mask_keeps_prefix_and_last_four(self):
        self.assertEqual(mask("+393331234567"), "+39******4567")
        self.assertNotIn("3331234", mask("+393331234567"))
