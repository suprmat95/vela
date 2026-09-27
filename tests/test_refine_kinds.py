"""M21-F (RF-71..75): tipo del rifiuto, `keep_product`, luoghi esclusi e domande in `refine`."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import NOW, TODAY
from vela.domain.models import REJECT_KINDS, Area, Criteria, Period, Proposal, StructuredFields
from vela.domain.refine import refine

SPAIN = Area("country", "Spagna", "ES")
ESTEPONA = Area("city", "Estepona", "ES")
MARBELLA = Area("city", "Marbella", "ES")
OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
CRIT = Criteria("padel", SPAIN, OCTOBER, 2, Decimal("800"), "it", rooms=1, level="intermediate")
PROPOSAL = Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("350"),
                    "EUR", "Motivo.", NOW)


def refinement(reason="", fields=None, criteria=CRIT, area=ESTEPONA):
    return refine(criteria, reason, PROPOSAL, area, TODAY, fields=fields)


class ClassificationTableTest(unittest.TestCase):
    """UC-F "Altri tipi": una frase it e una en per tipo, con il criterio che cambia."""
    CASES = [
        ("troppo caro", "price", "budget"),
        ("too expensive", "price", "budget"),
        ("vorrei andare a Valencia", "place", "area"),
        ("Valencia would be better", "place", "area"),
        ("l'hotel non mi piace", "hotel", None),
        ("I don't like the hotel", "hotel", None),
        ("meglio a novembre", "dates", "period"),
        ("November would be better", "dates", "period"),
        ("troppo lungo", "duration", "duration_max_nights"),
        ("too long", "duration", "duration_max_nights"),
        ("preferisco il tennis", "sport", "sport"),
        ("we'd rather play tennis", "sport", "sport"),
        ("siamo in 2, ma con due camere", "pax", "rooms"),
        ("we need two rooms", "pax", "rooms"),
        ("troppo difficile", "level", "level"),
        ("too hard for us", "level", "level"),
        ("più a sud", "direction", "area"),
        ("somewhere warmer", "direction", "area"),
    ]

    def test_table(self):
        for reason, kind, changed in self.CASES:
            with self.subTest(reason=reason):
                r = refinement(reason)
                self.assertEqual(r.kind, kind)
                self.assertIsNone(r.ask)
                if changed is None:
                    self.assertEqual(r.criteria, CRIT)
                else:
                    self.assertNotEqual(getattr(r.criteria, changed), getattr(CRIT, changed))

    def test_every_kind_but_other_comes_from_text(self):
        kinds = {kind for _, kind, _ in self.CASES}
        self.assertEqual(kinds, set(REJECT_KINDS) - {"other"})

    def test_unclassifiable_reasons_have_no_kind_and_change_nothing(self):
        for reason in ("Non mi convince", "mah, non so", "non fa per me", "not convinced", "not for me",
                       "meh", "no", "non mi piace", "", None):
            with self.subTest(reason=reason):
                r = refinement(reason)
                self.assertIsNone(r.kind)
                self.assertEqual(r.ask, "reason")
                self.assertEqual(r.criteria, CRIT)


class MultipleKindsTest(unittest.TestCase):
    """Decisione A della roadmap: criteri aggiornati tutti, tipo = il primo dell'elenco di RF-71."""

    def test_too_expensive_and_too_far(self):
        r = refinement("troppo caro e troppo lontano")
        self.assertEqual(r.kind, "price")
        self.assertEqual(r.kinds, ("price", "place"))
        self.assertEqual(r.criteria.budget, Decimal("560.00"))
        self.assertEqual(r.criteria.excluded_areas, (ESTEPONA,))   # il luogo del prodotto

    def test_order_follows_rf71_not_the_sentence(self):
        r = refinement("più a sud, e troppo caro")
        self.assertEqual(r.kinds, ("price", "direction"))
        self.assertEqual(r.kind, "price")


class FieldTest(unittest.TestCase):
    def test_field_wins_on_text(self):
        r = refinement("troppo caro", StructuredFields(reject_kind="hotel"))
        self.assertEqual(r.kind, "hotel")
        self.assertEqual(r.criteria.budget, Decimal("560.00"))   # il testo aggiorna comunque i criteri

    def test_field_is_trimmed_and_lowercased(self):
        self.assertEqual(refinement("boh", StructuredFields(reject_kind=" Other ")).kind, "other")

    def test_invalid_field_is_discarded_and_the_text_decides(self):
        r = refinement("troppo caro", StructuredFields(reject_kind="weather"))
        self.assertEqual(r.kind, "price")
        self.assertIn(("reject_kind", "weather"), r.discarded)
        r = refinement("boh", StructuredFields(reject_kind=3))
        self.assertIsNone(r.kind)
        self.assertIn(("reject_kind", 3), r.discarded)

    def test_structured_fields_give_a_kind_without_words(self):
        cases = [(StructuredFields(budget=500), "price"), (StructuredFields(area="Valencia"), "place"),
                 (StructuredFields(period_start="2026-11-01", period_end="2026-11-30"), "dates"),
                 (StructuredFields(duration_max_nights=3), "duration"), (StructuredFields(sport="tennis"), "sport"),
                 (StructuredFields(pax=2, rooms=2), "pax"), (StructuredFields(level="beginner"), "level"),
                 (StructuredFields(direction="south"), "direction")]
        for fields, kind in cases:
            with self.subTest(kind=kind):
                self.assertEqual(refinement("ok", fields).kind, kind)

    def test_explicit_other_is_understood_only_through_criteria(self):
        r = refinement("hotel con la spa?", StructuredFields(reject_kind="other"))
        self.assertEqual(r.kind, "other")
        self.assertIsNone(r.ask)
        self.assertFalse(r.understood)


class KeepProductTest(unittest.TestCase):
    """RF-74: "mi piace ma", "quando altro", "same trip"… → `keep_product`, tipo `dates`."""

    def test_phrases_keep_the_product(self):
        for reason in ("Questo mi piace ma non posso in quelle date", "tienimi questo viaggio, quando altro è disponibile?",
                       "stesso viaggio ma a novembre", "altre date?", "I like this one, but I can't make those dates",
                       "when else is it available?", "same trip in November", "other dates please"):
            with self.subTest(reason=reason):
                r = refinement(reason)
                self.assertEqual((r.kind, r.keep_product), ("dates", True))

    def test_negated_like_does_not_keep(self):
        for reason in ("non mi piace", "I don't like it", "I do not like this"):
            with self.subTest(reason=reason):
                self.assertFalse(refinement(reason).keep_product)

    def test_field_keeps_and_implies_dates(self):
        r = refinement("", StructuredFields(keep_product=True))
        self.assertEqual((r.kind, r.keep_product), ("dates", True))

    def test_keep_only_with_dates(self):
        r = refinement("mi piace ma costa troppo")
        self.assertEqual((r.kind, r.keep_product), ("price", False))
        r = refinement("", StructuredFields(reject_kind="hotel", keep_product=True))
        self.assertEqual((r.kind, r.keep_product), ("hotel", False))

    def test_explicit_false_wins_on_the_text(self):
        r = refinement("stesso viaggio a novembre", StructuredFields(keep_product=False))
        self.assertEqual((r.kind, r.keep_product), ("dates", False))

    def test_invalid_field_is_discarded(self):
        r = refinement("same trip", StructuredFields(keep_product="maybe"))
        self.assertIn(("keep_product", "maybe"), r.discarded)
        self.assertTrue(r.keep_product)   # il testo decide


class PlaceTest(unittest.TestCase):
    """RF-73: luogo negato → esclusione, area invariata; tipo `place` senza luogo → quello del
    prodotto."""

    def test_negated_place_is_excluded_and_area_kept(self):
        for reason in ("Estepona no, ma la Spagna va bene", "non a Estepona", "ovunque tranne Estepona",
                       "not Estepona, Spain is fine", "anywhere but Estepona"):
            with self.subTest(reason=reason):
                r = refinement(reason, area=MARBELLA)
                self.assertEqual(r.kind, "place")
                self.assertEqual(r.criteria.area, SPAIN)
                self.assertEqual(r.criteria.excluded_areas, (ESTEPONA,))

    def test_marbella_no(self):
        r = refinement("Marbella no", area=MARBELLA)
        self.assertEqual((r.criteria.area, r.criteria.excluded_areas), (SPAIN, (MARBELLA,)))

    def test_place_without_negation_is_the_new_area_as_before(self):
        r = refinement("a Marbella")
        self.assertEqual((r.criteria.area, r.criteria.excluded_areas), (MARBELLA, ()))

    def test_place_kind_without_a_place_excludes_the_product_place(self):
        r = refinement("Non mi piace il posto")
        self.assertEqual((r.kind, r.criteria.area, r.criteria.excluded_areas), ("place", SPAIN, (ESTEPONA,)))
        r = refinement("boh", StructuredFields(reject_kind="place"))
        self.assertEqual(r.criteria.excluded_areas, (ESTEPONA,))

    def test_place_kind_with_an_area_changes_place_as_before(self):
        r = refinement("boh", StructuredFields(reject_kind="place", area="Valencia"))
        self.assertEqual((r.criteria.area.name, r.criteria.excluded_areas), ("Valencia", ()))

    def test_exclusions_add_up_without_repeats(self):
        before = replace(CRIT, excluded_areas=(ESTEPONA,))
        r = refinement("Marbella no, e nemmeno Estepona", criteria=before, area=MARBELLA)
        self.assertEqual(r.criteria.excluded_areas, (ESTEPONA, MARBELLA))

    def test_excluding_the_intent_area_moves_up_to_the_first_allowed_ancestor(self):
        before = replace(CRIT, area=ESTEPONA)
        r = refinement("Estepona no", criteria=before)
        self.assertEqual(r.criteria.area, Area("region", "Costa del Sol", "ES"))
        r = refinement("Spagna no", criteria=replace(CRIT, area=SPAIN))
        self.assertIsNone(r.criteria.area)

    def test_direction_words_are_not_a_place(self):
        r = refinement("troppo caldo, vorrei un posto più fresco", area=Area("city", "Valencia", "ES"))
        self.assertEqual(r.kind, "direction")
        self.assertEqual(r.criteria.excluded_areas, ())


class RoomsQuestionTest(unittest.TestCase):
    """Da M21-D: più di 2 persone senza camere dette → domanda "In quante camere?"."""

    def test_more_than_two_people_without_rooms_asks(self):
        r = refinement("siamo in 5")
        self.assertEqual((r.kind, r.ask), ("pax", "rooms"))
        self.assertEqual(r.criteria, CRIT)

    def test_rooms_said_in_text_or_field_do_not_ask(self):
        self.assertIsNone(refinement("siamo in 5, tre camere").ask)
        self.assertIsNone(refinement("siamo in 5", StructuredFields(rooms=3)).ask)

    def test_intent_saved_before_m21d_does_not_ask(self):
        r = refinement("siamo in 5", criteria=replace(CRIT, rooms=None))
        self.assertIsNone(r.ask)
        self.assertEqual((r.criteria.pax, r.criteria.rooms), (5, None))

    def test_two_people_or_unchanged_pax_do_not_ask(self):
        self.assertIsNone(refinement("siamo in 2").ask)
        five = replace(CRIT, pax=5, rooms=3)
        self.assertIsNone(refinement("troppo caro", criteria=five).ask)


if __name__ == "__main__":
    unittest.main()
