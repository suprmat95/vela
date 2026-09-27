"""M21-C (UC-C, RF-08, RF-62): il rifiuto che sposta il livello o chiede le lezioni."""
import unittest
from datetime import date
from decimal import Decimal

from support import NOW, TODAY
from vela.domain.models import Area, Criteria, Period, Proposal, StructuredFields
from vela.domain.refine import refine

SPAIN = Area("country", "Spagna", "ES")
OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
PROPOSAL = Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("350"),
                    "EUR", "Motivo.", NOW)
B, M, A, ALL = "beginner", "intermediate", "advanced", "all"


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, rooms=1)
    base.update(kw)
    return Criteria(**base)


def run(reason, criteria=None, levels=(), fields=None):
    return refine(criteria or crit(), reason, PROPOSAL, SPAIN, TODAY, fields=fields,
                  product_levels=frozenset(levels))


class RelativeLevelTest(unittest.TestCase):
    """"Troppo difficile" abbassa di un livello, "troppo facile" alza: rispetto al livello
    dell'intento, o senza livello rispetto ai livelli del prodotto rifiutato."""

    def test_from_the_level_of_the_intent(self):
        table = [("troppo difficile", M, B), ("too hard for us", A, M), ("era troppo impegnativo", A, M),
                 ("troppo facile", B, M), ("too easy", M, A), ("vorremmo qualcosa di più impegnativo", M, A),
                 ("qualcosa di più facile", M, B), ("troppo avanzato per noi", M, B)]
        for reason, before, after in table:
            with self.subTest(reason):
                r = run(reason, crit(level=before), levels=(ALL,))
                self.assertEqual((r.criteria.level, r.understood), (after, True))

    def test_from_the_levels_of_the_rejected_product(self):
        self.assertEqual(run("troppo difficile", levels=(M, A)).criteria.level, B)
        self.assertEqual(run("too easy", levels=(B, M, ALL)).criteria.level, A)

    def test_nothing_to_move(self):
        """Già al livello più basso (o più alto), o nessun livello da cui partire: il motivo resta
        non capito (RF-54) e i criteri non cambiano."""
        for reason, criteria, levels in (("troppo difficile", crit(level=B), (M,)),
                                         ("too easy", crit(level=A), ()),
                                         ("troppo difficile", crit(), ()),
                                         ("troppo difficile", crit(), (ALL,))):
            with self.subTest(reason=reason, level=criteria.level, levels=levels):
                r = run(reason, criteria, levels)
                self.assertEqual((r.criteria, r.understood), (criteria, False))

    def test_a_quieter_place_is_not_an_easier_level(self):
        r = run("un posto più tranquillo", crit(level=M), levels=(M,))
        self.assertEqual(r.criteria.level, M)

    def test_an_explicit_level_wins_over_the_relative_words(self):
        r = run("troppo difficile, siamo principianti", crit(level=A), levels=(A,))
        self.assertEqual(r.criteria.level, B)


class ExplicitTest(unittest.TestCase):
    def test_level_and_lessons_in_the_reason(self):
        r = run("siamo principianti e vorremmo lezioni")
        self.assertEqual((r.criteria.level, r.criteria.wants_coaching, r.understood), (B, True, True))
        r = run("no coaching, we are advanced players", crit(language="en"))
        self.assertEqual((r.criteria.level, r.criteria.wants_coaching), (A, False))

    def test_fields_win_over_the_reason(self):
        r = run("siamo principianti", fields=StructuredFields(level="intermediate", wants_coaching=True))
        self.assertEqual((r.criteria.level, r.criteria.wants_coaching), (M, True))
        self.assertIn(("level", B, M), r.conflicts)

    def test_invalid_fields_are_discarded(self):
        r = run("", crit(level=M), fields=StructuredFields(level="pro", wants_coaching="si"))
        self.assertEqual(r.criteria.level, M)
        self.assertEqual(r.discarded, (("level", "pro"), ("wants_coaching", "si")))

    def test_a_field_alone_is_understood(self):
        r = run("", fields=StructuredFields(level="advanced"))
        self.assertEqual((r.criteria.level, r.understood), (A, True))

    def test_other_reasons_keep_level_and_lessons(self):
        before = crit(level=B, wants_coaching=True)
        r = run("a novembre", before)
        self.assertEqual((r.criteria.level, r.criteria.wants_coaching), (B, True))


if __name__ == "__main__":
    unittest.main()
