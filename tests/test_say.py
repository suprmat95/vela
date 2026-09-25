import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain import say
from vela.domain.models import Area, Criteria, OrderStatus, Period, ProductSummary, Proposal

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
PRODUCT = ProductSummary("181", "Magnifico Padel a Lanzarote", "Lanzarote", "THB Lanzarote Beach")
PROPOSAL = Proposal("p1", "i1", "181", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("578"),
                    "EUR", "È in Spagna, parte il 1 ottobre 2026 e resta nel tuo budget di 800 euro.", NOW)


class FormatTest(unittest.TestCase):
    def test_date_and_money(self):
        self.assertEqual(say.fmt_date(date(2026, 10, 1)), "1 ottobre 2026")
        self.assertEqual(say.fmt_money(Decimal("800")), "800 euro")
        self.assertEqual(say.fmt_money(Decimal("812.5")), "812,50 euro")


class SayTest(unittest.TestCase):
    def test_intent_created(self):
        c = Criteria("padel", Area("country", "Spagna", "ES"),
                     Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
        s = say.say_intent_created(c)
        for piece in ("padel", "Spagna", "1 ottobre 2026", "31 ottobre 2026", "2 persone", "800 euro"):
            self.assertIn(piece, s)
        self.assertIn("1 persona", say.say_intent_created(Criteria(pax=1)))

    def test_proposal(self):
        s = say.say_proposal(PRODUCT, PROPOSAL)
        for piece in ("Magnifico Padel a Lanzarote", "Lanzarote", "THB Lanzarote Beach",
                      "1 ottobre 2026", "4 ottobre 2026", "2 persone", "578 euro", PROPOSAL.reason):
            self.assertIn(piece, s)
        self.assertNotIn("http", s)
        self.assertNotIn("*", s)

    def test_proposal_without_hotel_and_single_day(self):
        p = ProductSummary("1", "Titolo", None, None)
        s = say.say_proposal(p, Proposal("p", "i", "1", date(2026, 10, 1), date(2026, 10, 1), 1,
                                         Decimal("50"), "EUR", "Motivo.", NOW))
        self.assertIn("il 1 ottobre 2026", s)
        self.assertNotIn("hotel", s.lower())

    def test_no_match_covers_every_criterion(self):
        from vela.domain.chooser import FILTERS
        texts = {c: say.say_no_match(c) for c in FILTERS}
        self.assertEqual(len(set(texts.values())), 5)   # archived e bookable condividono la frase
        self.assertIn("scartato", texts["rejected"])
        self.assertIn("periodo", texts["dates"])

    def test_missing(self):
        s = say.say_missing(["email", "phone", "participants[0].last_name"])
        self.assertIn("l'email", s)
        self.assertIn("il telefono", s)
        self.assertIn("cognome del secondo partecipante", s)

    def test_accept(self):
        same = say.say_accept(Decimal("1156"), Decimal("1156"), False)
        self.assertIn("1156 euro", same)
        self.assertNotIn("non i", same)
        differs = say.say_accept(Decimal("1200"), Decimal("1156"), True)
        self.assertLess(differs.index("1200 euro"), differs.index("link"))
        self.assertIn("1156 euro", differs)

    def test_status(self):
        self.assertIn("R-123456", say.say_status(OrderStatus.CONFIRMED, "R-123456", None))
        self.assertIn("attesa", say.say_status(OrderStatus.AWAITING_PAYMENT, None, None))
        self.assertIn("completando", say.say_status(OrderStatus.PAID_PENDING_BOOKING, None, None))
        self.assertIn("non è riuscita", say.say_status(OrderStatus.BOOKING_FAILED, None, "timeout"))
        self.assertIn("scaduto", say.say_status(OrderStatus.EXPIRED, None, None))

    def test_paid(self):
        self.assertIn("Pagamento", say.say_paid())


class SayM11Test(unittest.TestCase):
    OCT = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")

    def test_on_date(self):
        self.assertEqual(say.on_date(date(2026, 10, 1)), "il 1 ottobre 2026")
        self.assertEqual(say.on_date(date(2026, 10, 8)), "l'8 ottobre 2026")
        self.assertEqual(say.on_date(date(2026, 10, 11)), "l'11 ottobre 2026")
        self.assertEqual(say.on_date(date(2026, 10, 18)), "il 18 ottobre 2026")

    def test_intent_created_uses_the_right_preposition(self):
        s = say.say_intent_created(Criteria("padel", Area("region", "Sardegna", "IT")))
        self.assertIn("in Sardegna", s)
        s = say.say_intent_created(Criteria("padel", Area("region", "Canarie", "ES")))
        self.assertIn("alle Canarie", s)

    def test_no_match_cites_the_value(self):
        c = Criteria("tennis", None, self.OCT, 8)
        self.assertIn("di tennis", say.say_no_match("sport", c))
        self.assertIn("tra il 1 ottobre 2026 e il 31 ottobre 2026", say.say_no_match("dates", c))
        self.assertIn("per 8 persone", say.say_no_match("pax", c))
        self.assertIn("scartato", say.say_no_match("rejected", c))
        self.assertEqual(say.say_no_match("trip", c), say.say_no_match("archived"))

    def test_no_match_without_value_falls_back(self):
        self.assertIn("periodo", say.say_no_match("dates", Criteria()))
        self.assertIn("sport", say.say_no_match("sport"))
