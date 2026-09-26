import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain.models import (Area, Criteria, Order, OrderStatus, Participant, Period,
                                ProductSummary, Proposal, ProposalMade, TravelerProfile, criteria_from_dict, criteria_to_dict,
                                money_str, profile_from_dict, profile_to_dict)

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


class MoneyTest(unittest.TestCase):
    def test_two_decimals(self):
        self.assertEqual(money_str(Decimal("800")), "800.00")
        self.assertEqual(money_str(Decimal("812.5")), "812.50")


class CriteriaRoundTripTest(unittest.TestCase):
    def test_round_trip(self):
        c = Criteria(sport="padel", area=Area("country", "Spagna", "ES"),
                     period=Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"),
                     pax=2, budget=Decimal("800"), language="it")
        self.assertEqual(criteria_from_dict(criteria_to_dict(c)), c)

    def test_empty_round_trip(self):
        c = Criteria()
        d = criteria_to_dict(c)
        self.assertEqual(d, {"sport": None, "area": None, "period": None, "pax": None,
                             "budget": None, "duration_min_nights": None,
                             "duration_max_nights": None, "language": "it"})
        self.assertEqual(criteria_from_dict(d), c)

    def test_duration_round_trip(self):
        c = Criteria(sport="padel", duration_min_nights=1, duration_max_nights=3)
        self.assertEqual(criteria_from_dict(criteria_to_dict(c)), c)

    def test_intent_saved_before_m21_has_no_duration(self):
        old = {"sport": "padel", "area": None, "period": None, "pax": 2, "budget": None,
               "language": "it"}
        c = criteria_from_dict(old)
        self.assertIsNone(c.duration_min_nights)
        self.assertIsNone(c.duration_max_nights)


class ProposalNightsTest(unittest.TestCase):
    """M21-A: le notti del viaggio proposto nella risposta `proposal`."""

    def test_nights_in_the_response(self):
        p = Proposal("p1", "i1", "181", date(2026, 10, 9), date(2026, 10, 14), 2, Decimal("400"),
                     "EUR", "Motivo.", NOW)
        self.assertEqual(p.nights, 5)
        d = ProposalMade(p, ProductSummary("181", "T", None, None), "Ti propongo.").to_dict()
        self.assertEqual(d["nights"], 5)


class ProfileTest(unittest.TestCase):
    def test_merge_keeps_known_values_and_takes_new_ones(self):
        base = TravelerProfile(first_name="Anna", email="a@x.it")
        merged = base.merged_with(TravelerProfile(last_name="Rossi", email=None,
                                                  participants=(Participant("Bo", "Bi"),)))
        self.assertEqual(merged.first_name, "Anna")
        self.assertEqual(merged.last_name, "Rossi")
        self.assertEqual(merged.email, "a@x.it")
        self.assertEqual(merged.participants, (Participant("Bo", "Bi"),))

    def test_missing_fields_for_two_pax(self):
        p = TravelerProfile(first_name="Anna", last_name="Rossi", participants=(Participant("Bo"),))
        self.assertEqual(p.missing_fields(2), ["email", "phone", "participants[0].last_name"])

    def test_missing_fields_complete(self):
        p = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", participants=(Participant("Bo", "Bi"),))
        self.assertEqual(p.missing_fields(2), [])
        self.assertEqual(p.missing_fields(1), [])

    def test_round_trip(self):
        p = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", pax=2,
                            participants=(Participant("Bo", "Bi"),))
        self.assertEqual(profile_from_dict(profile_to_dict(p)), p)


class ProposalTest(unittest.TestCase):
    def test_total_from(self):
        p = Proposal("p1", "i1", "181", date(2026, 10, 1), date(2026, 10, 4), 2,
                     Decimal("578"), "EUR", "motivo", NOW)
        self.assertEqual(p.total_from, Decimal("1156"))


class OrderStatusTest(unittest.TestCase):
    def test_values_are_rf25(self):
        self.assertEqual([s.value for s in OrderStatus],
                         ["queued", "awaiting_confirmation", "awaiting_payment", "paid_pending_booking", "confirmed",
                          "replaced", "cancelled", "failed", "booking_failed", "expired"])

    def test_order_is_frozen(self):
        o = Order("o1", "p1", "i1", "181", OrderStatus.AWAITING_PAYMENT, 2, Decimal("578"),
                  Decimal("1156"), "EUR", TravelerProfile(), NOW, NOW)
        with self.assertRaises(Exception):
            o.status = OrderStatus.CONFIRMED
