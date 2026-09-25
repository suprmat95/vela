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

    def test_status_awaiting_says_the_amount_never_the_url(self):
        s = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, total=Decimal("799.9"))
        self.assertIn("799,90 euro", s)
        self.assertNotIn("http", s)
        en = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "en", Decimal("799.9"))
        self.assertIn("799.90 euros", en)
        self.assertNotIn("http", en)

    def test_payments_unavailable(self):
        s = say.say_payments_unavailable()
        self.assertIn("pagamento", s)
        self.assertNotIn("http", s)

    def test_paid(self):
        self.assertIn("Pagamento", say.say_paid())


class NotFoundSayTest(unittest.TestCase):
    def test_each_kind_has_its_own_sentence(self):
        sentences = {kind: say.say_not_found(kind) for kind in ("intent", "proposal", "order")}
        self.assertEqual(len(set(sentences.values())), 3)
        self.assertIn("proposta", sentences["proposal"])
        self.assertIn("ordine", sentences["order"])
        self.assertIn("richiesta", sentences["intent"])

    def test_unknown_kind_is_generic(self):
        self.assertTrue(say.say_not_found("boh"))
        self.assertNotIn(say.say_not_found("boh"), [say.say_not_found("order")])

    def test_error_sentences_are_speakable(self):
        for s in (say.say_not_found("intent"), say.say_not_found("proposal"),
                  say.say_not_found("order"), say.say_not_found("x"),
                  say.say_unavailable(), say.say_error()):
            self.assertNotIn("http", s)
            self.assertNotIn("**", s)
            self.assertNotIn("`", s)
            self.assertTrue(s.endswith("."))


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


class EnglishTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(say.fmt_date(date(2026, 10, 1), "en"), "1 October 2026")
        self.assertEqual(say.fmt_money(Decimal("800"), "en"), "800 euros")
        self.assertEqual(say.fmt_money(Decimal("812.5"), "en"), "812.50 euros")

    def test_intent_created(self):
        c = Criteria("padel", Area("country", "Spagna", "ES"),
                     Period(date(2026, 10, 1), date(2026, 10, 31), "october"), 2, Decimal("800"), "en")
        s = say.say_intent_created(c)
        for piece in ("padel", "Spain", "1 October 2026", "31 October 2026", "2 people", "800 euros"):
            self.assertIn(piece, s)
        self.assertNotIn("Spagna", s)
        self.assertIn("1 person", say.say_intent_created(Criteria(pax=1, language="en")))

    def test_proposal(self):
        s = say.say_proposal(PRODUCT, PROPOSAL, "en")
        for piece in ("Magnifico Padel a Lanzarote", "THB Lanzarote Beach", "1 October 2026",
                      "4 October 2026", "2 people", "578 euros"):
            self.assertIn(piece, s)
        self.assertNotIn("http", s)

    def test_no_match(self):
        from vela.domain.chooser import FILTERS
        en = Criteria(language="en")
        texts = {c: say.say_no_match(c, en) for c in FILTERS}
        self.assertEqual(len(set(texts.values())), 5)   # archived, bookable e trip condividono la frase
        self.assertIn("period", texts["dates"])
        self.assertNotEqual(texts["dates"], say.say_no_match("dates"))

    def test_no_match_cites_the_value(self):
        c = Criteria("tennis", None, Period(date(2026, 10, 1), date(2026, 10, 31), "october"), 8,
                     language="en")
        self.assertIn("any tennis trip", say.say_no_match("sport", c))
        self.assertIn("between 1 October 2026 and 31 October 2026", say.say_no_match("dates", c))
        self.assertIn("for 8 people", say.say_no_match("pax", c))

    def test_on_date_and_places(self):
        self.assertEqual(say.on_date(date(2026, 10, 8), "en"), "on 8 October 2026")
        s = say.say_intent_created(Criteria("padel", Area("region", "Canarie", "ES"), language="en"))
        self.assertIn("in the Canary Islands", s)

    def test_missing(self):
        s = say.say_missing(["email", "phone", "participants[0].last_name"], "en")
        self.assertIn("the email", s)
        self.assertIn("the phone number", s)
        self.assertIn("last name of the second participant", s)
        self.assertIn(" and ", s)

    def test_accept_and_status(self):
        self.assertIn("750 euros", say.say_accept(Decimal("750"), Decimal("700"), True, "en"))
        for status in OrderStatus:
            with self.subTest(status=status):
                it = say.say_status(status, "R-1", None)
                en = say.say_status(status, "R-1", None, "en")
                self.assertNotEqual(it, en)
        self.assertIn("R-1", say.say_status(OrderStatus.CONFIRMED, "R-1", None, "en"))

    def test_italian_is_default(self):
        self.assertEqual(say.say_no_match("pax"), say.say_no_match("pax", Criteria(language="it")))


class QueueSayTest(unittest.TestCase):
    """Frasi di M5 (RF-45, RF-16, RF-17, RF-25, RF-49): italiano e inglese, niente URL né markdown."""

    def test_queued_minutes_singular_and_plural(self):
        self.assertEqual(say.say_queued(1), "Ti ho messo in coda: tra circa un minuto il link di "
                         "pagamento sarà pronto. Chiedimi a che punto è quando vuoi.")
        self.assertIn("tra circa 12 minuti", say.say_queued(12))
        self.assertEqual(say.say_queued(1, "en"), "You're in the queue: the payment link will be "
                         "ready in about a minute. Ask me how it's going whenever you like.")
        self.assertIn("in about 12 minutes", say.say_queued(12, "en"))

    def test_status_queued_repeats_the_wait_or_says_preparing(self):
        self.assertIn("tra circa 3 minuti", say.say_status(OrderStatus.QUEUED, None, None, minutes=3))
        preparing = say.say_status(OrderStatus.QUEUED, None, None)
        self.assertIn("Sto preparando il pagamento", preparing)
        self.assertIn("I'm preparing the payment", say.say_status(OrderStatus.QUEUED, None, None, "en"))

    def test_awaiting_payment_states_difference_before_link(self):
        s = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, total=Decimal("720"),
                           price_from_total=Decimal("700"))
        self.assertTrue(s.startswith("Il totale reale è 720 euro, non i 700 stimati."))
        self.assertLess(s.index("720 euro"), s.index("link"))
        en = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "en", total=Decimal("720"),
                            price_from_total=Decimal("700"))
        self.assertTrue(en.startswith("The real total is 720 euros, not the estimated 700."))
        self.assertIn("waiting for payment", en)

    def test_awaiting_payment_without_difference_keeps_the_m6_sentence(self):
        s = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, total=Decimal("700"),
                           price_from_total=Decimal("700"))
        self.assertEqual(s, "L'ordine è in attesa del pagamento di 700 euro: usa il link che ti ho mandato.")

    def test_replaced_does_not_mention_error(self):
        s = say.say_replaced(PRODUCT, PROPOSAL)
        self.assertTrue(s.startswith("Quel viaggio non è più prenotabile, ti propongo un'alternativa. "))
        self.assertIn(say.say_proposal(PRODUCT, PROPOSAL), s)
        en = say.say_replaced(PRODUCT, PROPOSAL, "en")
        self.assertTrue(en.startswith("That trip can no longer be booked, here is an alternative. "))
        for text in (s.lower(), en.lower()):
            for word in ("errore", "error", "502", "404", "hofj"):
                self.assertNotIn(word, text)

    def test_cancelled_then_next_proposal(self):
        self.assertEqual(say.say_status(OrderStatus.CANCELLED, None, None), "Ho annullato l'ordine.")
        s = say.say_cancelled_then("Ti propongo altro.")
        self.assertEqual(s, "Ho annullato l'ordine. Ti propongo altro.")
        self.assertEqual(say.say_cancelled_then("I suggest something else.", "en"),
                         "I've cancelled the order. I suggest something else.")

    def test_failed_includes_reason(self):
        reason = say.failure_reason("upstream")
        self.assertEqual(reason, "il fornitore non ha risposto dopo tre tentativi")
        s = say.say_status(OrderStatus.FAILED, None, reason)
        self.assertEqual(s, "Non sono riuscito a preparare il pagamento: il fornitore non ha risposto "
                         "dopo tre tentativi. Se vuoi, riproviamo con una nuova proposta.")
        en = say.say_status(OrderStatus.FAILED, None, say.failure_reason("upstream", "en"), "en")
        self.assertIn("the supplier did not answer after three attempts", en)

    def test_every_failure_reason_has_both_languages(self):
        for code in ("upstream", "config", "no_alternative", "payments", "booking_upstream",
                     "booking_rejected"):
            self.assertTrue(say.failure_reason(code))
            self.assertTrue(say.failure_reason(code, "en"))
            self.assertNotEqual(say.failure_reason(code), say.failure_reason(code, "en"))

    def test_new_phrases_have_no_url_or_markdown(self):
        texts = [say.say_queued(5), say.say_queued(5, "en"), say.say_replaced(PRODUCT, PROPOSAL),
                 say.say_replaced(PRODUCT, PROPOSAL, "en"), say.say_cancelled_then("x"),
                 say.failure_reason("config"), say.failure_reason("config", "en")]
        for status in (OrderStatus.QUEUED, OrderStatus.REPLACED, OrderStatus.CANCELLED, OrderStatus.FAILED):
            for lang in ("it", "en"):
                texts.append(say.say_status(status, None, "motivo", lang))
        for t in texts:
            self.assertNotIn("http", t)
            self.assertNotIn("**", t)
            self.assertNotIn("`", t)
