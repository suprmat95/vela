import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, assert_single_product, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.intent import QUESTION_PAX
from vela.domain.models import (IntentCreated, IntentQuestion, NoMatch, ProposalMade,
                                TravelerProfile)
from vela.domain.usecases import NotFound, Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"


class Clock:
    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_vela(products=None, hofj=None, payments=None):
    repos = MemoryRepositories()
    repos.products.upsert_many(products if products is not None else [
        make_product(1, price=300, country="IT", destination="Riccione"),
        make_product(2, price=450, country="ES", destination="Madrid"),
        make_product(3, price=350, country="ES", destination="Valencia"),
        make_product(4, price=390, country="ES", destination="Lanzarote"),
    ])
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, hofj or FakeHofJ(), payments or StubPayments(), now=Clock(),
                new_id=lambda: next(ids))


class CreateIntentTest(unittest.TestCase):
    def test_creates_and_persists(self):
        vela = make_vela()
        r = vela.create_intent(INTENT)
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(r.intent_id, "id1")
        self.assertEqual(r.criteria.pax, 2)
        self.assertEqual(vela.repos.intents.get("id1").text, INTENT)
        assert_single_product(self, r.to_dict())

    def test_question_persists_nothing(self):
        vela = make_vela()
        r = vela.create_intent("padel a ottobre")
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.question, QUESTION_PAX)
        self.assertEqual(r.say, QUESTION_PAX)
        self.assertIsNone(vela.repos.intents.get("id1"))
        assert_single_product(self, r.to_dict())

    def test_profile_is_stored_and_provides_pax(self):
        vela = make_vela()
        r = vela.create_intent("padel a ottobre", TravelerProfile(first_name="Anna", pax=2))
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(vela.repos.intents.get(r.intent_id).profile.first_name, "Anna")


class GetProposalTest(unittest.TestCase):
    def test_single_proposal_best_match(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        r = vela.get_proposal(iid)
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(r.product.product_id, "3")
        self.assertEqual(r.proposal.pax, 2)
        self.assertEqual(r.proposal.start_date, date(2026, 10, 1))
        self.assertFalse(r.replaced)
        assert_single_product(self, r.to_dict())
        self.assertEqual(vela.repos.proposals.get(r.proposal.id).product_id, "3")

    def test_get_twice_returns_same_proposal(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        second = vela.get_proposal(iid)
        self.assertEqual(first.proposal.id, second.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 1)

    def test_no_match_names_criterion(self):
        vela = make_vela(products=[make_product(1, sport="tennis")])
        iid = vela.create_intent(INTENT).intent_id
        r = vela.get_proposal(iid)
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "sport")
        self.assertEqual(vela.repos.proposals.list_for_intent(iid), [])
        assert_single_product(self, r.to_dict())

    def test_unknown_intent(self):
        with self.assertRaises(NotFound) as ctx:
            make_vela().get_proposal("nope")
        self.assertEqual((ctx.exception.kind, ctx.exception.id), ("intent", "nope"))


class RejectProposalTest(unittest.TestCase):
    def test_reject_gives_a_different_product(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertIsInstance(second, ProposalMade)
        self.assertNotEqual(second.product.product_id, first.product.product_id)
        self.assertEqual(second.product.product_id, "4")
        self.assertEqual(vela.repos.rejections.product_ids_for_intent(iid), {"3"})
        assert_single_product(self, second.to_dict())

    def test_never_proposes_a_rejected_product_again(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        seen = []
        r = vela.get_proposal(iid)
        while isinstance(r, ProposalMade):
            self.assertNotIn(r.product.product_id, seen)
            seen.append(r.product.product_id)
            r = vela.reject_proposal(r.proposal.id, "no")
        self.assertEqual(seen, ["3", "4", "2", "1"])
        self.assertEqual(r.failed_criterion, "rejected")

    def test_reject_twice_same_proposal_is_idempotent(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        a = vela.reject_proposal(first.proposal.id, "no")
        b = vela.reject_proposal(first.proposal.id, "no")
        self.assertEqual(a.proposal.id, b.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 2)

    def test_unknown_proposal(self):
        with self.assertRaises(NotFound):
            make_vela().reject_proposal("nope", "x")
