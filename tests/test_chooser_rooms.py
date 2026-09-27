"""M21-D (UC-D, RF-66, RF-68): il filtro duro delle camere, dopo le persone, e la motivazione
che dichiara il limite per camera quando conta."""
import unittest
from dataclasses import replace
from decimal import Decimal

from support import NOW, TODAY, make_product
from vela.domain.chooser import FILTERS, Choice, NoChoice, cheapest_total, choose
from vela.domain.models import Criteria

TWO_PER_ROOM = make_product(1, price=300, max_pax_per_room=2)
NO_LIMIT = make_product(2, price=400)
FOUR_PER_ROOM = make_product(3, price=350, max_pax_per_room=4)


def crit(**kw):
    base = dict(sport="padel", pax=5, rooms=3)
    base.update(kw)
    return Criteria(**base)


def pick(products, criteria):
    return choose(products, criteria, set(), TODAY, NOW)


class RoomsFilterTest(unittest.TestCase):
    def test_rooms_filter_comes_after_pax(self):
        self.assertEqual(FILTERS, ("archived", "bookable", "trip", "sport", "dates", "pax", "rooms", "level", "place", "hotel",
                                   "price", "rejected"))

    def test_enough_rooms_keeps_the_product(self):
        r = pick([TWO_PER_ROOM], crit(pax=5, rooms=3))   # ceil(5 / 2) = 3
        self.assertIsInstance(r, Choice)
        self.assertEqual(r.product.id, "1")

    def test_too_few_rooms_excludes_the_product(self):
        r = pick([TWO_PER_ROOM, NO_LIMIT], crit(pax=5, rooms=2))
        self.assertEqual(r.product.id, "2")   # il più economico è escluso, non declassato

    def test_no_limit_accepts_any_number_of_rooms(self):
        self.assertEqual(pick([NO_LIMIT], crit(pax=5, rooms=1)).product.id, "2")

    def test_zero_limit_means_no_limit(self):
        p = replace(NO_LIMIT, max_pax_per_room=0)
        self.assertEqual(pick([p], crit(pax=5, rooms=1)).product.id, "2")

    def test_no_candidate_left_names_rooms_with_the_minimum(self):
        """`NoChoice("rooms")` dice le camere minime che avrebbero salvato almeno un prodotto e
        il relativo massimo per camera: 5 persone in camere da 4 = 2 camere."""
        r = pick([TWO_PER_ROOM, FOUR_PER_ROOM], crit(pax=5, rooms=1))
        self.assertEqual(r, NoChoice("rooms", rooms_needed=2, max_pax_per_room=4))
        self.assertEqual(r.failed_criterion, "rooms")

    def test_old_intent_without_rooms_is_not_filtered(self):
        self.assertIsInstance(pick([TWO_PER_ROOM], crit(pax=5, rooms=None)), Choice)

    def test_no_pax_is_not_filtered(self):
        self.assertIsInstance(pick([TWO_PER_ROOM], crit(pax=None, rooms=1)), Choice)

    def test_pax_fails_before_rooms(self):
        solo = make_product(4, min_pax=2, max_pax_per_room=2)
        self.assertEqual(pick([solo], crit(pax=1, rooms=1)), NoChoice("pax"))

    def test_cheapest_total_respects_the_rooms(self):
        """RF-69, regola 4 (M21-E): il più economico compatibile sta dopo il filtro camere."""
        self.assertEqual(cheapest_total([TWO_PER_ROOM, NO_LIMIT], crit(pax=5, rooms=2), TODAY, NOW),
                         Decimal("2000"))
        self.assertEqual(cheapest_total([TWO_PER_ROOM, NO_LIMIT], crit(pax=5, rooms=3), TODAY, NOW),
                         Decimal("1500"))


class RoomsReasonTest(unittest.TestCase):
    def test_reason_says_the_limit_when_it_forces_more_rooms(self):
        r = pick([TWO_PER_ROOM], crit(pax=5, rooms=3))
        self.assertTrue(r.reason.endswith(
            "Le camere di questo viaggio ospitano al massimo 2 persone: per 5 servono almeno "
            "3 camere, come hai chiesto."), r.reason)

    def test_reason_when_more_rooms_than_needed(self):
        r = pick([TWO_PER_ROOM], crit(pax=5, rooms=4))
        self.assertTrue(r.reason.endswith("per 5 servono almeno 3 camere, tu ne hai chieste 4."), r.reason)

    def test_reason_in_english(self):
        r = pick([TWO_PER_ROOM], crit(pax=5, rooms=3, language="en"))
        self.assertTrue(r.reason.endswith(
            "The rooms of this trip hold at most 2 people: 5 people need at least 3 rooms, as you "
            "asked."), r.reason)
        r = pick([TWO_PER_ROOM], crit(pax=5, rooms=4, language="en"))
        self.assertTrue(r.reason.endswith("5 people need at least 3 rooms, you asked for 4."), r.reason)

    def test_reason_is_silent_when_one_room_is_enough_or_there_is_no_limit(self):
        for products, criteria in (([TWO_PER_ROOM], crit(pax=2, rooms=1)),
                                   ([NO_LIMIT], crit(pax=5, rooms=3)),
                                   ([TWO_PER_ROOM], crit(pax=5, rooms=None))):
            with self.subTest(product=products[0].id, rooms=criteria.rooms):
                self.assertNotIn("camer", pick(products, criteria).reason)


if __name__ == "__main__":
    unittest.main()
