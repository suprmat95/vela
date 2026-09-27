"""M21-E (UC-E, RF-69, RF-70): budget a testa o totale."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, make_product
from test_usecases import Clock
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.intent import (QUESTION_SPORT, parse_budget, parse_budget_scope, parse_intent,
                                read_budget, validate_fields)
from vela.domain.models import (Criteria, IntentCreated, IntentQuestion, Proposal,
                                StructuredFields)
from vela.domain.refine import refine
from vela.domain.usecases import Vela

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


# UC-E, regole 2-3: testo con tre persone → (tetto sul totale, lettura)
TABLE = [
    ("tennis in Spagna a maggio, siamo in tre, due camere, 600 euro a testa", (Decimal("1800"), "per_person")),
    ("tennis in Spagna a maggio, siamo in tre, due camere, 1.800 euro in tutto", (Decimal("1800"), "total")),
    ("tennis in Spagna a maggio, siamo in tre, due camere, non più di 600 a persona", (Decimal("1800"), "per_person")),
    ("tennis in Spagna a maggio, siamo in tre, due camere, budget totale 1.500", (Decimal("1500"), "total")),
    ("tennis in Spagna a maggio, siamo in tre, due camere, 1.500 euro complessivi", (Decimal("1500"), "total")),
    ("tennis in Spagna a maggio, siamo in tre, due camere, in totale 1500 euro", (Decimal("1500"), "total")),
    ("tennis in Spain in May, three of us, 600 euros each", (Decimal("1800"), "per_person")),
    ("tennis in Spain in May, three of us, 1,800 in total", (Decimal("1800"), "total")),
    ("tennis in Spain in May, three of us, up to 600 per person", (Decimal("1800"), "per_person")),
    ("tennis in Spain in May, three of us, total budget 1,500", (Decimal("1500"), "total")),
    ("tennis in Spain in May, three of us, 1500 euros altogether", (Decimal("1500"), "total")),
    ("tennis in Spain in May, three of us, 600 each", (Decimal("1800"), "per_person")),
]


class BudgetWordsTest(unittest.TestCase):
    """RF-69, regole 2-3: le parole del testo decidono la lettura."""

    def test_table(self):
        for text, expected in TABLE:
            with self.subTest(text=text):
                c = parse_intent(text, today=TODAY).criteria
                self.assertEqual(c.pax, 3)
                self.assertEqual((c.budget, c.budget_scope), expected)

    def test_scope_words(self):
        for text, scope in (("500 euro a testa", "per_person"), ("600 per head", "per_person"),
                            ("1800 in tutto", "total"), ("in total 1800", "total"),
                            ("massimo 800 euro", None)):
            with self.subTest(text=text):
                self.assertEqual(parse_budget_scope(text), scope)

    def test_people_in_total_is_not_a_budget_reading(self):
        """"Siamo 4 in tutto" parla delle persone, non del budget."""
        for text in ("siamo 4 in tutto, massimo 800 euro", "we are four in total, max 800 euros",
                     "3 persone in tutto, budget 900"):
            with self.subTest(text=text):
                self.assertIsNone(parse_budget_scope(text))

    def test_small_figure_before_the_words_is_not_money(self):
        self.assertIsNone(parse_budget("siamo 4 in tutto"))
        self.assertIsNone(parse_budget("we are 2 each"))

    def test_one_person_is_total(self):
        """Regola 5: con una persona le due letture coincidono."""
        c = parse_intent("padel a ottobre da solo, massimo 600 euro", today=TODAY).criteria
        self.assertEqual((c.pax, c.budget, c.budget_scope), (1, Decimal("600"), "total"))

    def test_bare_figure_with_a_group_and_no_catalog_is_total(self):
        c = parse_intent("padel a ottobre, siamo in tre, due camere, massimo 600 euro", today=TODAY).criteria
        self.assertEqual((c.budget, c.budget_scope), (Decimal("600"), "total"))

    def test_no_budget_no_scope(self):
        c = parse_intent("padel a ottobre, siamo in tre, due camere, a testa", today=TODAY).criteria
        self.assertEqual((c.budget, c.budget_scope), (None, None))


class BudgetScopeFieldPrecedenceTest(unittest.TestCase):
    """RF-69, regola 1: il campo vince sulle parole, il conflitto va nei log (RF-53)."""

    def parse(self, text, **fields):
        return parse_intent(text, today=TODAY, fields=StructuredFields(**fields))

    def test_field_beats_the_words(self):
        r = self.parse("padel, siamo in tre, due camere, 600 euro a testa", budget_scope="total")
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope), (Decimal("600"), "total"))
        self.assertIn(("budget_scope", "per_person", "total"), r.conflicts)

    def test_field_figure_and_field_scope(self):
        r = self.parse("padel a maggio", pax=3, rooms=2, budget=600, budget_scope="per_person")
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope),
                         (Decimal("1800.00"), "per_person"))
        self.assertEqual(r.conflicts, ())

    def test_field_figure_read_with_the_words(self):
        """L'agente passa la cifra detta; "a testa" nel testo la moltiplica."""
        r = self.parse("padel, siamo in tre, due camere, 600 euro a testa", pax=3, rooms=2, budget=600)
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope),
                         (Decimal("1800.00"), "per_person"))
        self.assertEqual(r.conflicts, ())

    def test_scope_without_budget_has_no_effect(self):
        r = self.parse("padel a maggio, siamo in tre, due camere", budget_scope="per_person")
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope), (None, None))
        self.assertEqual(r.discarded, ())

    def test_invalid_scope_is_discarded_and_the_words_decide(self):
        r = self.parse("padel, siamo in tre, due camere, 600 euro a testa", budget_scope="each")
        self.assertEqual(r.discarded, (("budget_scope", "each"),))
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope),
                         (Decimal("1800"), "per_person"))


class Cheapest:
    """`cheapest_total` finto che ricorda con quali criteri è stato chiamato."""

    def __init__(self, total):
        self.total, self.calls = total, []

    def __call__(self, criteria):
        self.calls.append(criteria)
        return self.total


class RuleFourTest(unittest.TestCase):
    """RF-69, regola 4: cifra sola con più persone, letta col prodotto compatibile più economico."""

    def read(self, cheapest, budget="600", pax=3, scope=None):
        c = Criteria("padel", pax=pax, budget=Decimal(budget), budget_scope=scope)
        return read_budget(c, Cheapest(cheapest) if not callable(cheapest) else cheapest)

    def reading(self, c):
        return (c.budget, c.budget_scope)

    def test_uc_e_examples(self):
        # il più economico costa 400 a persona: 600 in tutto non basta, 600 a testa sì
        self.assertEqual(self.reading(self.read(Decimal("1200"))), (Decimal("1800"), "per_person"))
        # il più economico costa 150 a persona: 600 in tutto basta
        self.assertEqual(self.reading(self.read(Decimal("450"))), (Decimal("600"), "total"))

    def test_edges(self):
        self.assertEqual(self.read(Decimal("600")).budget_scope, "total")         # copre esatto
        self.assertEqual(self.read(Decimal("1800")).budget_scope, "per_person")   # a testa esatto
        self.assertEqual(self.read(Decimal("1801")).budget_scope, "total")        # nessuna copre
        self.assertEqual(self.read(None).budget_scope, "total")                   # niente di compatibile

    def test_catalog_not_needed(self):
        for kwargs in ({"pax": 1}, {"scope": "total"}, {"scope": "per_person"}):
            with self.subTest(**kwargs):
                cheapest = Cheapest(Decimal("1200"))
                self.read(cheapest, **kwargs)
                self.assertEqual(cheapest.calls, [])
        cheapest = Cheapest(Decimal("1200"))
        self.assertIsNone(read_budget(Criteria("padel", pax=3), cheapest).budget_scope)
        self.assertEqual(cheapest.calls, [])

    def test_parse_intent_passes_the_criteria(self):
        cheapest = Cheapest(Decimal("1200"))
        r = parse_intent("padel in Spagna a ottobre, siamo in tre, due camere, massimo 600 euro", today=TODAY,
                         cheapest_total=cheapest)
        self.assertEqual((r.criteria.budget, r.criteria.budget_scope), (Decimal("1800"), "per_person"))
        (asked,) = cheapest.calls
        self.assertEqual((asked.sport, asked.pax, asked.period.start), ("padel", 3, date(2026, 10, 1)))

    def test_no_catalog_read_when_a_question_is_asked(self):
        cheapest = Cheapest(Decimal("1200"))
        r = parse_intent("in Spagna a ottobre, siamo in tre, due camere, massimo 600 euro", today=TODAY,
                         cheapest_total=cheapest)
        self.assertEqual(r.question, QUESTION_SPORT)
        self.assertEqual(cheapest.calls, [])


class CountingProducts:
    """Il repository dei prodotti che conta le letture del catalogo."""

    def __init__(self, inner):
        self.inner, self.list_calls = inner, 0

    def list_all(self):
        self.list_calls += 1
        return self.inner.list_all()

    def __getattr__(self, name):
        return getattr(self.inner, name)


def make_vela(price):
    repos = MemoryRepositories()
    repos.products.upsert_many([make_product(1, price=price, destination="Siviglia"),
                                make_product(2, price=price + 100, destination="Madrid")])
    repos.products = CountingProducts(repos.products)
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, FakeHofJ(), StubPayments(), now=Clock(), new_id=lambda: next(ids))


class CreateIntentRuleFourTest(unittest.TestCase):
    TEXT = "Padel in Spagna a ottobre, siamo in tre, due camere, massimo 600 euro"

    def test_per_person_when_the_total_cannot_cover_the_cheapest(self):
        vela = make_vela(400)
        r = vela.create_intent(self.TEXT)
        self.assertIsInstance(r, IntentCreated)
        c = vela.repos.intents.get(r.intent_id).criteria
        self.assertEqual((c.budget, c.budget_scope), (Decimal("1800"), "per_person"))
        self.assertEqual(vela.repos.products.list_calls, 1)

    def test_total_when_it_covers_the_cheapest(self):
        vela = make_vela(150)
        c = vela.create_intent(self.TEXT).criteria
        self.assertEqual((c.budget, c.budget_scope), (Decimal("600"), "total"))

    def test_field_budget_goes_through_the_rule(self):
        vela = make_vela(400)
        c = vela.create_intent("Padel in Spagna a ottobre", fields=StructuredFields(
            sport="padel", pax=3, rooms=2, budget=600)).criteria
        self.assertEqual((c.budget, c.budget_scope), (Decimal("1800.00"), "per_person"))

    def test_catalog_read_only_for_rule_four(self):
        for text in ("Padel in Spagna a ottobre, siamo in tre, due camere",                     # senza budget
                     "Padel in Spagna a ottobre, da solo, massimo 600 euro",        # una persona
                     "Padel in Spagna a ottobre, siamo in tre, due camere, 600 euro a testa",   # parole
                     "Padel in Spagna a ottobre, siamo in tre, due camere, 1800 euro in tutto",
                     "In Spagna a ottobre, siamo in tre, due camere, massimo 600 euro"):         # domanda
            with self.subTest(text=text):
                vela = make_vela(400)
                r = vela.create_intent(text)
                self.assertIsInstance(r, (IntentCreated, IntentQuestion))
                self.assertEqual(vela.repos.products.list_calls, 0)


THREE = Criteria("padel", pax=3, budget=Decimal("600"), budget_scope="total")
EACH = Criteria("padel", pax=3, budget=Decimal("1800"), budget_scope="per_person")
PROPOSAL = Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 3, Decimal("250"),
                    "EUR", "Motivo.", NOW)   # totale 750 → 80% = 600


def rejected(criteria, reason="", cheapest=None, **fields):
    return refine(criteria, reason, PROPOSAL, None, TODAY, StructuredFields(**fields),
                  cheapest_total=cheapest)


class RejectBudgetTest(unittest.TestCase):
    """UC-E sul rifiuto: stesse regole per una cifra nuova; `budget_scope` o persone cambiate
    rileggono la cifra già detta (decisioni M21-E 1 e 3); "troppo caro" legge in totale (2)."""

    def reading(self, r):
        return (r.criteria.budget, r.criteria.budget_scope)

    def test_scope_field_rereads_the_figure(self):
        self.assertEqual(self.reading(rejected(THREE, budget_scope="per_person")),
                         (Decimal("1800"), "per_person"))
        self.assertEqual(self.reading(rejected(EACH, budget_scope="total")), (Decimal("600"), "total"))

    def test_scope_words_reread_the_figure(self):
        r = rejected(THREE, "intendevo a testa")
        self.assertEqual(self.reading(r), (Decimal("1800"), "per_person"))
        self.assertTrue(r.understood)

    def test_intent_saved_before_m21e_reads_as_total(self):
        old = replace(THREE, budget_scope=None)
        self.assertEqual(self.reading(rejected(old, budget_scope="per_person")),
                         (Decimal("1800"), "per_person"))

    def test_new_figure_goes_through_rule_four(self):
        r = rejected(THREE, "massimo 500 euro", Cheapest(Decimal("1200")))
        self.assertEqual(self.reading(r), (Decimal("1500"), "per_person"))
        r = rejected(THREE, "massimo 500 euro", Cheapest(Decimal("450")))
        self.assertEqual(self.reading(r), (Decimal("500"), "total"))

    def test_rule_four_uses_the_refined_criteria(self):
        cheapest = Cheapest(Decimal("1200"))
        rejected(THREE, "a novembre, massimo 500 euro, siamo in 4", cheapest)
        (asked,) = cheapest.calls
        self.assertEqual((asked.pax, asked.period.start), (4, date(2026, 11, 1)))

    def test_new_figure_with_words_or_field(self):
        cheapest = Cheapest(Decimal("450"))
        self.assertEqual(self.reading(rejected(THREE, "700 a testa", cheapest)),
                         (Decimal("2100"), "per_person"))
        self.assertEqual(self.reading(rejected(EACH, "", cheapest, budget=500, budget_scope="total")),
                         (Decimal("500.00"), "total"))
        self.assertEqual(cheapest.calls, [])

    def test_scope_field_beats_the_words_with_conflict(self):
        r = rejected(THREE, "700 a testa", budget_scope="total")
        self.assertEqual(self.reading(r), (Decimal("700"), "total"))
        self.assertIn(("budget_scope", "per_person", "total"), r.conflicts)

    def test_more_people_per_person_raises_the_cap(self):
        """Decisione 1: 600 a testa in 3, poi "siamo in 4" → 2400."""
        self.assertEqual(self.reading(rejected(EACH, "siamo in 4")), (Decimal("2400"), "per_person"))
        self.assertEqual(self.reading(rejected(EACH, pax=2)), (Decimal("1200"), "per_person"))

    def test_more_people_total_keeps_the_cap(self):
        self.assertEqual(self.reading(rejected(THREE, "siamo in 4")), (Decimal("600"), "total"))

    def test_too_expensive_reads_as_total(self):
        """Decisione 2: il budget abbassato all'80% è un totale."""
        r = rejected(EACH, "troppo caro")
        self.assertEqual(self.reading(r), (Decimal("600.00"), "total"))

    def test_scope_without_budget_has_no_effect(self):
        """Decisione 3: nessun budget da rileggere, nessun cambiamento, nessun criterio capito."""
        r = rejected(replace(THREE, budget=None, budget_scope=None), "non mi convince",
                     budget_scope="per_person")
        self.assertEqual(self.reading(r), (None, None))
        self.assertEqual(r.discarded, ())
        self.assertFalse(r.understood)

    def test_unrelated_reason_keeps_the_reading(self):
        r = rejected(EACH, "a novembre")
        self.assertEqual(self.reading(r), (Decimal("1800"), "per_person"))

    def test_unrelated_reason_leaves_an_old_intent_alone(self):
        old = replace(THREE, budget_scope=None)
        self.assertEqual(self.reading(rejected(old, "a novembre")), (Decimal("600"), None))


class RejectReadsTheCatalogOnceTest(unittest.TestCase):
    """Decisione M21-E: nel rifiuto regola 4 e `choose` condividono una sola lettura."""

    def test_one_read_with_rule_four(self):
        vela = make_vela(400)
        intent = vela.create_intent("Padel in Spagna a ottobre, siamo in tre, due camere, 1800 euro in tutto")
        proposal = vela.get_proposal(intent.intent_id)
        vela.repos.products.list_calls = 0
        r = vela.reject_proposal(proposal.proposal.id, "massimo 500 euro")
        self.assertEqual(r.failed_criterion, "price")   # tetto M7: il rifiutato costava 1200
        c = vela.repos.intents.get(intent.intent_id).criteria
        self.assertEqual((c.budget, c.budget_scope), (Decimal("1500"), "per_person"))
        self.assertEqual(vela.repos.products.list_calls, 1)

    def test_one_read_without_rule_four(self):
        vela = make_vela(400)
        intent = vela.create_intent("Padel in Spagna a ottobre, siamo in tre, due camere")
        proposal = vela.get_proposal(intent.intent_id)
        vela.repos.products.list_calls = 0
        vela.reject_proposal(proposal.proposal.id, "a novembre")
        self.assertEqual(vela.repos.products.list_calls, 1)


class SayTest(unittest.TestCase):
    """RF-70: `create_intent` e `reject_proposal` dichiarano sempre la lettura del budget."""

    def test_create_intent_says_the_reading_whatever_the_rule(self):
        cases = [("Padel in Spagna a ottobre, siamo in tre, due camere, massimo 600 euro", 400,       # regola 4
                  "600 euro a persona, 1800 in tutto"),
                 ("Padel in Spagna a ottobre, siamo in tre, due camere, massimo 600 euro", 150,
                  "600 euro in tutto"),
                 ("Padel in Spagna a ottobre, siamo in tre, due camere, 600 euro a testa", 150,       # regola 2
                  "600 euro a persona, 1800 in tutto"),
                 ("Padel in Spagna a ottobre, siamo in tre, due camere, 1800 euro in tutto", 400,     # regola 3
                  "1800 euro in tutto"),
                 ("Padel in Spagna a ottobre, da solo, massimo 600 euro", 400,            # regola 5
                  "600 euro in tutto")]
        for text, price, reading in cases:
            with self.subTest(text=text, price=price):
                r = make_vela(price).create_intent(text)
                self.assertIn("con un budget di %s." % reading, r.say)

    def test_field_scope_is_said(self):
        r = make_vela(150).create_intent("Padel in Spagna a ottobre", fields=StructuredFields(
            sport="padel", pax=3, rooms=2, budget=600, budget_scope="per_person"))
        self.assertIn("con un budget di 600 euro a persona, 1800 in tutto.", r.say)

    def test_reject_says_the_new_reading(self):
        vela = make_vela(150)
        intent = vela.create_intent("Padel in Spagna a ottobre, siamo in tre, due camere, massimo 600 euro")
        proposal = vela.get_proposal(intent.intent_id)
        r = vela.reject_proposal(proposal.proposal.id, "intendevo a testa",
                                 StructuredFields(budget_scope="per_person"))
        self.assertIn("con un budget di 600 euro a persona, 1800 in tutto.", r.say)

    def test_scope_without_budget_is_not_said(self):
        r = make_vela(150).create_intent("Padel in Spagna a ottobre, siamo in tre, due camere",
                                         fields=StructuredFields(budget_scope="per_person"))
        self.assertNotIn("budget", r.say)
