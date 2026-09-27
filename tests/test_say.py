import unittest
from dataclasses import replace
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

    def test_proposal_says_the_rooms_for_a_group(self):
        """M21-D (RF-06): "per 5 persone in 3 camere"; con 1 o 2 persone in 1 camera niente."""
        five = replace(PROPOSAL, pax=5)
        self.assertIn("per 5 persone in 3 camere", say.say_proposal(PRODUCT, five, rooms=3))
        self.assertIn("for 5 people in 3 rooms", say.say_proposal(PRODUCT, five, "en", rooms=3))
        self.assertIn("per 2 persone in 2 camere", say.say_proposal(PRODUCT, PROPOSAL, rooms=2))
        self.assertNotIn("camer", say.say_proposal(PRODUCT, PROPOSAL, rooms=1))
        self.assertNotIn("camer", say.say_proposal(PRODUCT, PROPOSAL))

    def test_rooms_below_minimum(self):
        """M21-D (RF-65): la domanda di `accept_proposal` con il minimo del prodotto."""
        self.assertEqual(say.say_rooms_below_minimum(2, 5, 3),
                         "Le camere di questo viaggio ospitano al massimo 2 persone: per 5 servono "
                         "almeno 3 camere. In quante camere?")
        self.assertEqual(say.say_rooms_below_minimum(2, 5, 3, "en"),
                         "The rooms of this trip hold at most 2 people: 5 people need at least 3 "
                         "rooms. How many rooms?")

    def test_proposal_without_hotel_and_single_day(self):
        p = ProductSummary("1", "Titolo", None, None)
        s = say.say_proposal(p, Proposal("p", "i", "1", date(2026, 10, 1), date(2026, 10, 1), 1,
                                         Decimal("50"), "EUR", "Motivo.", NOW))
        self.assertIn("il 1 ottobre 2026", s)
        self.assertNotIn("hotel", s.lower())

    def test_no_match_covers_every_criterion(self):
        from vela.domain.chooser import FILTERS
        texts = {c: say.say_no_match(c) for c in FILTERS}
        self.assertEqual(len(set(texts.values())), 8)   # archived, bookable e trip condividono la frase
        self.assertIn("scartato", texts["rejected"])
        self.assertIn("camere", texts["rooms"])   # M21-D
        self.assertIn("livello", texts["level"])   # M21-C
        self.assertIn("più economico", texts["price"])
        self.assertIn("periodo", texts["dates"])

    def test_missing(self):
        s = say.say_missing(["email", "phone", "participants[0].last_name"])
        self.assertIn("l'email", s)
        self.assertIn("il telefono", s)
        self.assertIn("cognome del secondo partecipante", s)

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

    def test_no_match_rooms_says_the_minimum(self):
        """M21-D (RF-66): le camere minime e il relativo massimo per camera dal chooser."""
        c = Criteria("padel", pax=5, rooms=1)
        self.assertEqual(say.say_no_match("rooms", c, rooms_needed=2, max_pax_per_room=4),
                         "I viaggi compatibili hanno camere da massimo 4 persone: per 5 persone "
                         "servono almeno 2 camere. Vuoi cambiare il numero di camere?")
        self.assertEqual(say.say_no_match("rooms", replace(c, language="en"), rooms_needed=2,
                                          max_pax_per_room=4),
                         "The compatible trips have rooms for at most 4 people: 5 people need at "
                         "least 2 rooms. Do you want to change the number of rooms?")

    def test_no_match_rooms_without_numbers(self):
        self.assertEqual(say.say_no_match("rooms"),
                         "Non trovo viaggi per il numero di camere indicato: prova a cambiare il "
                         "numero di camere.")

    def test_no_match_alone_says_trips_start_from_two(self):
        """M21-D (RF-68): da solo restano solo viaggi da 2 persone in su."""
        self.assertEqual(say.say_no_match("pax", Criteria("padel", pax=1)),
                         "I viaggi di padel compatibili partono da 2 persone: da solo non posso "
                         "prenotarli. Vuoi cambiare qualcosa?")
        self.assertEqual(say.say_no_match("pax", Criteria("any", pax=1)),
                         "I viaggi compatibili partono da 2 persone: da solo non posso prenotarli. "
                         "Vuoi cambiare qualcosa?")
        self.assertEqual(say.say_no_match("pax", Criteria("tennis", pax=1, language="en")),
                         "The compatible tennis trips start from 2 people: I can't book them for "
                         "you alone. Do you want to change something?")

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
        self.assertEqual(len(set(texts.values())), 8)   # archived, bookable e trip condividono la frase
        self.assertIn("period", texts["dates"])
        self.assertIn("rooms", texts["rooms"])   # M21-D
        self.assertIn("level", texts["level"])   # M21-C
        self.assertIn("cheaper", texts["price"])
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

    def test_status_in_both_languages(self):
        for status in OrderStatus:
            with self.subTest(status=status):
                it = say.say_status(status, "R-1", None)
                en = say.say_status(status, "R-1", None, "en")
                self.assertNotEqual(it, en)
        self.assertIn("R-1", say.say_status(OrderStatus.CONFIRMED, "R-1", None, "en"))

    def test_italian_is_default(self):
        self.assertEqual(say.say_no_match("pax"), say.say_no_match("pax", Criteria(language="it")))


class PriceConfirmationSayTest(unittest.TestCase):
    """Decisione 2026-09-26: "a partire da" è il minimo, il prezzo effettivo arriva prima del link."""

    def test_proposal_says_the_price_is_a_minimum_told_before_the_link(self):
        it = say.say_proposal(PRODUCT, PROPOSAL)
        self.assertIn("a partire da 578 euro a persona: è il prezzo minimo, il totale effettivo "
                      "dipende da date e disponibilità e te lo dico prima del link di pagamento.", it)
        self.assertTrue(it.endswith("Ti va?"))
        en = say.say_proposal(PRODUCT, PROPOSAL, "en")
        self.assertIn("starting at 578 euros per person: that's the minimum price, the actual total "
                      "depends on dates and availability and I'll tell you before the payment link.", en)

    def test_confirm_price_higher_lower_equal(self):
        higher = say.say_status(OrderStatus.AWAITING_CONFIRMATION, None, None, total=Decimal("840"),
                                price_from_total=Decimal("656"), pax=2)
        self.assertEqual(higher, "Il prezzo effettivo è 840 euro in totale per 2 persone, più dei 656 "
                                 "stimati. Confermi? Se mi dici di sì preparo il link di pagamento.")
        lower = say.say_confirm_price(Decimal("610"), Decimal("656"), 2)
        self.assertIn("610 euro in totale per 2 persone, meno dei 656 stimati.", lower)
        equal = say.say_confirm_price(Decimal("656"), Decimal("656"), 1)
        self.assertIn("656 euro in totale per 1 persona, come stimato. Confermi?", equal)

    def test_confirm_price_in_english(self):
        s = say.say_confirm_price(Decimal("840"), Decimal("656"), 2, "en")
        self.assertEqual(s, "The actual price is 840 euros in total for 2 people, more than the "
                            "estimated 656 euros. Do you confirm? If you say yes, I'll prepare the "
                            "payment link.")
        self.assertIn(", as estimated.", say.say_confirm_price(Decimal("5"), Decimal("5"), 2, "en"))

    def test_queued_for_the_price_mentions_no_sms_and_no_link_yet(self):
        it = say.say_queued_for_price(1)
        self.assertEqual(it, "Sto chiedendo il prezzo effettivo al fornitore: sarà pronto tra circa "
                             "un minuto. Chiedimelo e te lo dico prima di mandarti il link di pagamento.")
        self.assertIn("in about 3 minutes", say.say_queued_for_price(3, "en"))
        for text in (it, say.say_queued_for_price(3, "en")):
            self.assertNotIn("SMS", text)
            self.assertNotIn("http", text)

    def test_awaiting_confirmation_without_total_asks_to_confirm(self):
        self.assertIn("dimmi se confermi", say.say_status(OrderStatus.AWAITING_CONFIRMATION, None, None))
        self.assertIn("tell me if you confirm",
                      say.say_status(OrderStatus.AWAITING_CONFIRMATION, None, None, "en"))


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


SPAIN = Area("country", "Spagna", "ES")


class AgentToolSayTest(unittest.TestCase):
    """RF-54: criteri capiti sempre ripetuti, campi scartati, motivo non traducibile."""

    def test_any_sport_is_spoken(self):
        self.assertIn("padel o tennis", say.say_intent_created(Criteria("any", SPAIN, pax=2)))
        self.assertIn("padel or tennis",
                      say.say_intent_created(Criteria("any", SPAIN, pax=2, language="en")))

    def test_understood_repeats_every_criterion(self):
        c = Criteria("padel", Area("city", "Madrid", "ES"),
                     Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 3, Decimal("1000"))
        s = say.say_understood(c)
        self.assertTrue(s.startswith("Ho capito: un viaggio di padel"))
        for piece in ("Madrid", "1 ottobre 2026", "3 persone", "1000 euro"):
            self.assertIn(piece, s)
        self.assertTrue(say.say_understood(replace(c, language="en")).startswith("Got it: a padel trip"))

    def test_intent_created_with_discarded_fields(self):
        s = say.say_intent_created(Criteria("padel", pax=3, budget=Decimal("1000")),
                                   (("area", "Atlantide"),))
        self.assertTrue(s.startswith("Non conosco il luogo Atlantide"))
        self.assertIn("Ho capito: un viaggio di padel per 3 persone", s)

    def test_every_discarded_field_has_a_sentence_in_both_languages(self):
        items = (("sport", "golf"), ("area", "Atlantide"), ("period", ("2026-12-10", "2026-12-01")),
                 ("pax", 0), ("budget", -5), ("direction", "east"))
        for lang in ("it", "en"):
            with self.subTest(lang=lang):
                s = say.say_discarded(items, lang)
                for piece in ("golf", "Atlantide", "0", "-5"):
                    self.assertIn(piece, s)
                self.assertEqual(s.count("."), len(items))
        self.assertEqual(say.say_discarded((), "it"), "")

    def test_understood_says_the_duration_between_period_and_people(self):
        c = Criteria("padel", SPAIN, Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2,
                     duration_min_nights=1, duration_max_nights=3)
        self.assertEqual(say.say_understood(c),
                         "Ho capito: un viaggio di padel in Spagna tra il 1 ottobre 2026 e il "
                         "31 ottobre 2026, da 1 a 3 notti, per 2 persone.")
        self.assertEqual(say.say_understood(replace(c, language="en")),
                         "Got it: a padel trip in Spain between 1 October 2026 and "
                         "31 October 2026, 1 to 3 nights, for 2 people.")

    def test_understood_duration_forms(self):
        cases = [((4, 4), "4 notti", "4 nights"), ((1, 1), "1 notte", "1 night"),
                 ((3, None), "almeno 3 notti", "at least 3 nights"),
                 ((None, 5), "al massimo 5 notti", "at most 5 nights")]
        for (low, high), it, en in cases:
            with self.subTest(low=low, high=high):
                c = Criteria("padel", pax=2, duration_min_nights=low, duration_max_nights=high)
                self.assertEqual(say.say_understood(c), "Ho capito: un viaggio di padel, %s, per 2 persone." % it)
                self.assertIn(en, say.say_understood(replace(c, language="en")))

    def test_understood_duration_last_has_no_trailing_comma(self):
        c = Criteria("padel", duration_min_nights=6, duration_max_nights=8)
        self.assertEqual(say.say_understood(c), "Ho capito: un viaggio di padel, da 6 a 8 notti.")

    def test_understood_without_duration_is_unchanged(self):
        self.assertEqual(say.say_understood(Criteria("padel", SPAIN, pax=2)),
                         "Ho capito: un viaggio di padel in Spagna per 2 persone.")

    def test_discarded_duration(self):
        self.assertEqual(say.say_discarded((("duration", (4, 2)),), "it"),
                         "Non ho potuto usare 4 - 2 come durata in notti.")
        self.assertEqual(say.say_discarded((("duration", (0, None)),), "en"),
                         "I couldn't use 0 - ? as the length in nights.")

    def test_understood_says_the_budget_per_person_and_in_total(self):
        """RF-70: la lettura del budget, sempre."""
        c = Criteria("tennis", SPAIN, pax=3, budget=Decimal("1800"), budget_scope="per_person")
        self.assertEqual(say.say_understood(c),
                         "Ho capito: un viaggio di tennis in Spagna per 3 persone con un budget "
                         "di 600 euro a persona, 1800 in tutto.")
        self.assertEqual(say.say_understood(replace(c, language="en")),
                         "Got it: a tennis trip in Spain for 3 people with a budget of 600 euros "
                         "per person, 1800 in total.")

    def test_understood_says_a_total_budget(self):
        c = Criteria("tennis", SPAIN, pax=3, budget=Decimal("600"), budget_scope="total")
        self.assertEqual(say.say_understood(c),
                         "Ho capito: un viaggio di tennis in Spagna per 3 persone con un budget "
                         "di 600 euro in tutto.")
        self.assertEqual(say.say_understood(replace(c, language="en")),
                         "Got it: a tennis trip in Spain for 3 people with a budget of 600 euros "
                         "in total.")

    def test_understood_says_the_rooms_with_more_than_two_people(self):
        """M21-D (RF-54, RF-65): le camere dopo le persone; con 1 o 2 persone in 1 camera (il
        default) non si dicono (decisione M21-D)."""
        c = Criteria("padel", SPAIN, pax=5, rooms=3, budget=Decimal("3000"), budget_scope="total")
        self.assertEqual(say.say_understood(c),
                         "Ho capito: un viaggio di padel in Spagna per 5 persone in 3 camere con un "
                         "budget di 3000 euro in tutto.")
        self.assertEqual(say.say_understood(replace(c, language="en")),
                         "Got it: a padel trip in Spain for 5 people in 3 rooms with a budget of "
                         "3000 euros in total.")

    def test_understood_says_one_room_for_a_group(self):
        c = Criteria("padel", pax=5, rooms=1)
        self.assertEqual(say.say_understood(c), "Ho capito: un viaggio di padel per 5 persone in 1 camera.")
        self.assertEqual(say.say_understood(replace(c, language="en")),
                         "Got it: a padel trip for 5 people in 1 room.")

    def test_understood_says_two_rooms_for_two_people(self):
        self.assertEqual(say.say_understood(Criteria("padel", pax=2, rooms=2)),
                         "Ho capito: un viaggio di padel per 2 persone in 2 camere.")

    def test_understood_is_silent_on_the_default_room(self):
        for c in (Criteria("padel", pax=2, rooms=1), Criteria("padel", pax=1, rooms=1),
                  Criteria("padel", pax=4)):   # intento salvato prima di M21-D: nessuna camera
            with self.subTest(c=c):
                self.assertNotIn("camer", say.say_understood(c))
                self.assertNotIn("room", say.say_understood(replace(c, language="en")))

    def test_discarded_rooms(self):
        self.assertEqual(say.say_discarded((("rooms", 6),)), "Non ho potuto usare 6 come numero di camere.")
        self.assertEqual(say.say_discarded((("rooms", "tre"),), "en"),
                         "I couldn't use tre as the number of rooms.")

    def test_understood_budget_saved_before_m21e_is_a_total(self):
        c = Criteria("padel", pax=2, budget=Decimal("800"))
        self.assertTrue(say.say_understood(c).endswith("con un budget di 800 euro in tutto."))

    def test_understood_per_person_with_cents(self):
        c = Criteria("padel", pax=2, budget=Decimal("1001.00"), budget_scope="per_person")
        self.assertTrue(say.say_understood(c).endswith(
            "con un budget di 500,50 euro a persona, 1001 in tutto."))

    def test_discarded_budget_scope(self):
        self.assertEqual(say.say_discarded((("budget_scope", "each"),), "it"),
                         "Non ho potuto usare each come lettura del budget, a persona o in tutto.")
        self.assertEqual(say.say_discarded((("budget_scope", "each"),), "en"),
                         "I couldn't use each as the budget reading, per person or in total.")

    def test_direction_discarded_names_the_direction(self):
        self.assertIn("nord", say.say_discarded((("direction", "north"),), "it"))
        self.assertIn("north", say.say_discarded((("direction", "north"),), "en"))

    def test_untranslatable(self):
        self.assertIn("ho escluso solo la proposta di prima", say.say_untranslatable("it"))
        self.assertIn("only excluded the previous proposal", say.say_untranslatable("en"))

    def test_no_match_never_invites_to_rephrase(self):
        for lang in ("it", "en"):
            for criterion in (None, "rejected", "sport", "dates", "pax", "price"):
                with self.subTest(lang=lang, criterion=criterion):
                    s = say.say_no_match(criterion, Criteria(language=lang)).lower()
                    self.assertNotIn("riformul", s)
                    self.assertNotIn("rephras", s)


class SmsPhrasesTest(unittest.TestCase):
    def test_queued_announces_both_sms(self):
        self.assertEqual(say.say_queued(1, phone_tail="4567"),
                         "Ti ho messo in coda: tra circa un minuto il link di pagamento sarà pronto e "
                         "te lo mando per SMS al numero che finisce con 4567. Ti scrivo di nuovo "
                         "quando la prenotazione è confermata. Se vuoi sapere a che punto è, o se "
                         "l'SMS non arriva entro qualche minuto, chiedimi pure.")
        self.assertEqual(say.say_queued(12, "en", "4567"),
                         "You're in the queue: the payment link will be ready in about 12 minutes and "
                         "I'll text it to the number ending in 4567. I'll text you again when the "
                         "booking is confirmed. If you want to know how it's going, or the text "
                         "hasn't arrived in a few minutes, just ask me.")

    def test_queued_without_valid_phone_is_unchanged(self):
        self.assertIn("Chiedimi a che punto è", say.say_queued(1))

    def test_awaiting_payment_mentions_the_sms(self):
        s = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "it", Decimal("700"),
                           phone_tail="4567")
        self.assertEqual(s, "L'ordine è in attesa del pagamento di 700 euro: usa il link che ti ho "
                            "mandato, anche per SMS al numero che finisce con 4567.")
        en = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "en", Decimal("700"),
                            phone_tail="4567")
        self.assertEqual(en, "The order is waiting for payment of 700 euros: use the link I sent "
                             "you, also by text to the number ending in 4567.")

    def test_queued_status_passes_the_tail(self):
        s = say.say_status(OrderStatus.QUEUED, None, None, "it", Decimal("700"), minutes=3,
                           phone_tail="4567")                # dopo la conferma: arriva il link
        self.assertIn("finisce con 4567", s)
        before = say.say_status(OrderStatus.QUEUED, None, None, "it", minutes=3, phone_tail="4567")
        self.assertNotIn("4567", before)                     # prima del prezzo nessun SMS

    def test_sms_phrases_have_no_url(self):
        for text in (say.say_queued(5, "it", "4567"), say.say_queued(5, "en", "4567"),
                     say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "it", Decimal("1"),
                                    phone_tail="4567")):
            self.assertNotIn("http", text)


class PriceChangedSinceTest(unittest.TestCase):
    def test_italian(self):
        text = say.say_price_changed_since(Decimal("768"), Decimal("700"))
        self.assertIn("768", text)
        self.assertIn("700", text)
        self.assertIn("Confermi?", text)

    def test_english(self):
        text = say.say_price_changed_since(Decimal("768"), Decimal("700"), "en")
        self.assertIn("768", text)
        self.assertIn("you confirmed", text)
        self.assertIn("Do you confirm?", text)
