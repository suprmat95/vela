"""Rifiuto con motivo (RF-08): dal motivo in testo libero ai criteri aggiornati."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import NOW, TODAY
from vela.domain.models import Area, Criteria, Period, Proposal, StructuredFields
from vela.domain.refine import is_price_reason, refine

SPAIN = Area("country", "Spagna", "ES")
VALENCIA = Area("city", "Valencia", "ES")
OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
CRIT = Criteria("padel", SPAIN, OCTOBER, 2, Decimal("800"), "it")
PROPOSAL = Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("350"),
                    "EUR", "Motivo.", NOW)   # totale 700 → 80% = 560


def refined(reason, criteria=CRIT, area=VALENCIA):
    return refine(criteria, reason, PROPOSAL, area, TODAY).criteria


def refinement(reason="", fields=None, area=VALENCIA):
    return refine(CRIT, reason, PROPOSAL, area, TODAY, fields=fields)


class PriceReasonTest(unittest.TestCase):
    """Decisione M7: un motivo di prezzo mette un tetto al totale delle proposte successive."""

    def test_price_words_and_figures_are_price_reasons(self):
        for reason in ("troppo caro", "Troppo cara!", "vorrei qualcosa di più economico",
                       "too expensive", "something cheaper", "massimo 500 euro", "max 400€"):
            with self.subTest(reason):
                self.assertTrue(is_price_reason(reason))

    def test_other_reasons_are_not_price_reasons(self):
        for reason in ("più a sud", "a novembre", "siamo in 3", "no", "", None):
            with self.subTest(reason):
                self.assertFalse(is_price_reason(reason))


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
        self.assertEqual(refine(once, "troppo caro", PROPOSAL, VALENCIA, TODAY).criteria, once)

    def test_language_is_kept(self):
        en = replace(CRIT, language="en")
        self.assertEqual(refined("too expensive", en).language, "en")


class TemperatureTest(unittest.TestCase):
    """M17: "più fresco" = più a nord, "più caldo" = più a sud (nessun dato climatico)."""

    def test_cooler_goes_north(self):
        for reason in ("Troppo caldo, vorrei un posto più fresco", "più freddo", "vorrei più fresca",
                       "somewhere cooler", "colder please", "too hot"):
            with self.subTest(reason=reason):
                self.assertEqual(refined(reason).area, Area("city", "Tarragona", "ES"))

    def test_warmer_goes_south(self):
        for reason in ("vorrei un posto più caldo", "somewhere warmer", "hotter", "troppo freddo",
                       "too cold"):
            with self.subTest(reason=reason):
                self.assertEqual(refined(reason).area, Area("city", "Alicante", "ES"))


class FieldsTest(unittest.TestCase):
    """RF-52, RF-53 sul rifiuto: campo valido > testo; `area` > `direction`."""

    def test_direction_field(self):
        r = refinement("Troppo caldo", StructuredFields(direction="north"))
        self.assertEqual(r.criteria.area, Area("city", "Tarragona", "ES"))
        self.assertTrue(r.understood)
        self.assertEqual((r.discarded, r.conflicts), ((), ()))

    def test_direction_field_beats_text_direction(self):
        self.assertEqual(refinement("più a nord", StructuredFields(direction="south")).criteria.area,
                         Area("city", "Alicante", "ES"))

    def test_invalid_or_unmovable_direction_is_discarded(self):
        for direction, area in (("east", VALENCIA), ("south", Area("region", "Lanzarote", "ES")),
                                ("north", None)):
            with self.subTest(direction=direction):
                r = refinement("", StructuredFields(direction=direction), area=area)
                self.assertEqual(r.criteria, CRIT)
                self.assertEqual(r.discarded, (("direction", direction),))

    def test_area_beats_direction_with_conflict(self):
        r = refinement("più fresco", StructuredFields(area="Italia", direction="north"))
        self.assertEqual(r.criteria.area, Area("country", "Italia", "IT"))
        self.assertEqual(r.conflicts, (("area", "Tarragona", "Italia"),))

    def test_fields_update_criteria(self):
        r = refinement("Preferisco il tennis", StructuredFields(
            sport="tennis", period_start="2026-11-01", period_end="2026-11-30", pax=3, budget=600))
        c = r.criteria
        self.assertEqual((c.sport, c.pax, c.budget), ("tennis", 3, Decimal("600.00")))
        self.assertEqual((c.period.start, c.period.end), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(r.conflicts, ())

    def test_text_field_conflict(self):
        r = refinement("preferisco il tennis", StructuredFields(sport="padel"))
        self.assertEqual(r.criteria.sport, "padel")
        self.assertEqual(r.conflicts, (("sport", "tennis", "padel"),))

    def test_old_criteria_are_not_conflicts(self):
        self.assertEqual(refinement("", StructuredFields(budget=500)).conflicts, ())

    def test_invalid_fields_are_discarded(self):
        r = refinement("", StructuredFields(sport="golf", area="Atlantide", pax=0))
        self.assertEqual(r.criteria, CRIT)
        self.assertEqual([d[0] for d in r.discarded], ["sport", "area", "pax"])
        self.assertFalse(r.understood)

    def test_sport_any_from_text(self):
        self.assertEqual(refined("va bene anche il tennis, padel o tennis indifferente").sport, "any")


class UnderstoodTest(unittest.TestCase):
    """RF-54: un motivo che non si traduce in nessun criterio va dichiarato."""

    def test_untranslatable_reason(self):
        self.assertFalse(refinement("Voglio un hotel con la spa").understood)

    def test_translatable_reasons(self):
        for reason in ("troppo caro", "più a sud", "a novembre", "siamo in 4", "più fresco",
                       "meglio in Grecia"):
            with self.subTest(reason=reason):
                self.assertTrue(refinement(reason).understood)

    def test_recognised_but_unchanged_is_understood(self):
        self.assertTrue(refinement("a ottobre").understood)


class DurationTest(unittest.TestCase):
    """M21-A: "troppo lungo/corto" sposta la durata rispetto alla proposta (3 notti); una durata
    esplicita nel motivo o nei campi la sostituisce."""

    def nights(self, reason, criteria=CRIT, fields=None):
        c = refine(criteria, reason, PROPOSAL, VALENCIA, TODAY, fields=fields).criteria
        return c.duration_min_nights, c.duration_max_nights

    def with_duration(self, low, high):
        return replace(CRIT, duration_min_nights=low, duration_max_nights=high)

    def test_too_long_caps_below_the_proposal(self):
        for reason in ("troppo lungo", "è troppo lunga", "dura troppo", "too long",
                       "something shorter", "vorrei qualcosa di più breve", "più corto"):
            with self.subTest(reason):
                self.assertEqual(self.nights(reason), (None, 2))
        self.assertEqual(self.nights("too long", self.with_duration(1, 3)), (1, 2))
        self.assertEqual(self.nights("troppo lungo", self.with_duration(3, 5)), (2, 2))

    def test_too_short_asks_more_than_the_proposal(self):
        for reason in ("troppo corto", "è troppo breve", "too short", "something longer",
                       "vorrei qualcosa di più lungo"):
            with self.subTest(reason):
                self.assertEqual(self.nights(reason), (4, None))
        self.assertEqual(self.nights("troppo corto", self.with_duration(1, 3)), (4, 4))
        self.assertEqual(self.nights("too short", self.with_duration(1, 8)), (4, 8))

    def test_one_night_cannot_be_shorter(self):
        one = replace(PROPOSAL, end_date=date(2026, 10, 2))
        r = refine(CRIT, "troppo lungo", one, VALENCIA, TODAY)
        self.assertEqual((r.criteria.duration_min_nights, r.criteria.duration_max_nights),
                         (None, None))
        self.assertFalse(r.understood)

    def test_explicit_duration_in_the_reason(self):
        self.assertEqual(self.nights("vorrei una settimana"), (6, 8))
        self.assertEqual(self.nights("meglio 4 notti"), (4, 4))
        self.assertEqual(self.nights("two weeks please"), (13, 15))
        self.assertEqual(self.nights("troppo corto, almeno 5 notti"), (5, None))

    def test_fields_beat_the_text(self):
        r = refine(CRIT, "vorrei una settimana", PROPOSAL, VALENCIA, TODAY,
                   fields=StructuredFields(duration_min_nights=4, duration_max_nights=5))
        self.assertEqual((r.criteria.duration_min_nights, r.criteria.duration_max_nights), (4, 5))
        self.assertIn(("duration_min_nights", 6, 4), r.conflicts)
        self.assertTrue(r.understood)

    def test_invalid_fields_are_discarded(self):
        r = refine(CRIT, "", PROPOSAL, VALENCIA, TODAY,
                   fields=StructuredFields(duration_min_nights=9, duration_max_nights=2))
        self.assertEqual(r.discarded, (("duration", (9, 2)),))
        self.assertIsNone(r.criteria.duration_min_nights)

    def test_too_long_is_understood_and_keeps_other_criteria(self):
        r = refine(CRIT, "too long", PROPOSAL, VALENCIA, TODAY)
        self.assertTrue(r.understood)
        self.assertEqual(replace(r.criteria, duration_max_nights=None), CRIT)


class RoomsTest(unittest.TestCase):
    """M21-D (RF-65): le camere nel rifiuto, da testo e da campo, sempre entro le persone
    aggiornate; se cambiano le persone senza dire le camere, `rooms = min(rooms, pax)`
    (decisione M21-D, 1)."""

    ONE_ROOM = replace(CRIT, rooms=1)   # intento creato dopo M21-D: 2 persone, una camera

    def rooms(self, reason, criteria=ONE_ROOM, fields=None):
        return refine(criteria, reason, PROPOSAL, VALENCIA, TODAY, fields=fields)

    def test_rooms_from_the_text(self):
        r = self.rooms("siamo in 4, in due camere")
        self.assertEqual((r.criteria.pax, r.criteria.rooms), (4, 2))
        self.assertTrue(r.understood)

    def test_two_couples(self):
        self.assertEqual((self.rooms("due coppie").criteria.pax, self.rooms("due coppie").criteria.rooms), (4, 2))

    def test_rooms_from_the_field(self):
        r = self.rooms("siamo in cinque", fields=StructuredFields(rooms=3))
        self.assertEqual((r.criteria.pax, r.criteria.rooms), (5, 3))
        self.assertEqual(r.discarded, ())

    def test_more_people_without_rooms_keep_the_rooms(self):
        self.assertEqual(self.rooms("siamo in 5").criteria.rooms, 1)

    def test_fewer_people_clamp_the_rooms(self):
        r = self.rooms("siamo in due", replace(CRIT, pax=4, rooms=3))
        self.assertEqual((r.criteria.pax, r.criteria.rooms), (2, 2))

    def test_field_above_the_people_is_discarded(self):
        r = self.rooms("", fields=StructuredFields(rooms=3))
        self.assertEqual(r.criteria.rooms, 1)
        self.assertEqual(r.discarded, (("rooms", 3),))
        self.assertEqual(r.conflicts, ())

    def test_text_above_the_people_is_ignored(self):
        r = self.rooms("tre camere")
        self.assertEqual(r.criteria.rooms, 1)
        self.assertEqual(r.discarded, ())

    def test_field_beats_text_with_a_conflict(self):
        r = self.rooms("siamo in 5, due camere", fields=StructuredFields(rooms=3))
        self.assertEqual(r.criteria.rooms, 3)
        self.assertEqual(r.conflicts, (("rooms", 2, 3),))

    def test_invalid_field_is_discarded(self):
        r = self.rooms("", fields=StructuredFields(rooms=0))
        self.assertEqual(r.criteria.rooms, 1)
        self.assertEqual(r.discarded, (("rooms", 0),))

    def test_old_intent_without_rooms_stays_without(self):
        self.assertIsNone(self.rooms("siamo in 4", CRIT).criteria.rooms)
        self.assertEqual(self.rooms("siamo in 4, due camere", CRIT).criteria.rooms, 2)
