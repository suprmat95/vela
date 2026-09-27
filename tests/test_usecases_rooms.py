"""M21-D (UC-D, RF-65..68): persone e camere nei cinque casi d'uso."""
import unittest
from datetime import timedelta

from support import NOW, FakeHofJ, StubPayments, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.intent import QUESTION_ROOMS
from vela.domain.models import (Criteria, Intent, IntentCreated, IntentQuestion, NoMatch,
                                OrderQueued, Participant, ProposalMade, StructuredFields,
                                TravelerProfile)
from vela.domain.usecases import Vela

FIVE = TravelerProfile("Anna", "Rossi", "a@x.it", "+390000", participants=tuple(
    Participant("P%d" % i, "Rossi") for i in range(4)))
TWO_PER_ROOM = make_product(1, price=300, max_pax_per_room=2)
NO_LIMIT = make_product(2, price=400)


class Clock:
    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_vela(products):
    repos = MemoryRepositories()
    repos.products.upsert_many(products)
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, FakeHofJ(), StubPayments(), now=Clock(), new_id=lambda: next(ids))


def proposal_for(vela, text, **fields):
    intent = vela.create_intent(text, fields=StructuredFields(**fields) if fields else None)
    assert isinstance(intent, IntentCreated), intent
    return intent, vela.get_proposal(intent.intent_id)


class RoomsQuestionTest(unittest.TestCase):
    def test_five_without_rooms_asks_and_saves_nothing(self):
        vela = make_vela([NO_LIMIT])
        r = vela.create_intent("padel in Portogallo a novembre, siamo in cinque")
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual((r.question, r.say), (QUESTION_ROOMS, QUESTION_ROOMS))
        self.assertIsNone(vela.repos.intents.get("id1"))   # il primo id, se fosse stato salvato

    def test_two_default_to_one_room(self):
        vela = make_vela([NO_LIMIT])
        r = vela.create_intent("padel a Valencia, siamo in due")
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(vela.repos.intents.get(r.intent_id).criteria.rooms, 1)


class ProposalRoomsTest(unittest.TestCase):
    def test_proposal_reports_the_rooms(self):
        vela = make_vela([TWO_PER_ROOM])
        _, p = proposal_for(vela, "padel, siamo in cinque, tre camere")
        self.assertIsInstance(p, ProposalMade)
        self.assertEqual(p.to_dict()["rooms"], 3)
        self.assertIn("per 5 persone in 3 camere", p.say)
        self.assertIn("per 5 servono almeno 3 camere, come hai chiesto", p.say)

    def test_proposal_for_two_is_silent_on_rooms(self):
        vela = make_vela([TWO_PER_ROOM])
        _, p = proposal_for(vela, "padel, siamo in due")
        self.assertEqual(p.to_dict()["rooms"], 1)
        self.assertNotIn("camer", p.say)

    def test_no_match_rooms_says_the_minimum(self):
        vela = make_vela([TWO_PER_ROOM])
        _, r = proposal_for(vela, "padel, siamo in cinque, una camera")
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "rooms")
        self.assertEqual(r.say, "I viaggi compatibili hanno camere da massimo 2 persone: per 5 "
                                "persone servono almeno 3 camere. Vuoi cambiare il numero di camere?")

    def test_alone_with_trips_from_two_people(self):
        vela = make_vela([make_product(3, min_pax=2)])
        _, r = proposal_for(vela, "padel, vado da solo")
        self.assertEqual(r.failed_criterion, "pax")
        self.assertEqual(r.say, "I viaggi di padel compatibili partono da 2 persone: da solo non "
                                "posso prenotarli. Vuoi cambiare qualcosa?")


class RejectRoomsTest(unittest.TestCase):
    def test_more_people_without_rooms_keep_one_room_and_filter(self):
        """Decisione M21-D, 1: 2 persone in 1 camera, poi "siamo in 5" senza camere → il say dice
        "in 1 camera" e i prodotti con massimo 2 per camera sono esclusi."""
        vela = make_vela([TWO_PER_ROOM, NO_LIMIT])
        _, first = proposal_for(vela, "padel, siamo in due")
        self.assertEqual(first.product.product_id, "1")
        r = vela.reject_proposal(first.proposal.id, "siamo in 5")
        self.assertIsInstance(r, ProposalMade)
        self.assertIn("per 5 persone in 1 camera", r.say)
        self.assertEqual((r.product.product_id, r.to_dict()["rooms"]), ("2", 1))

    def test_rooms_field_on_reject_lets_a_limited_product_through(self):
        other = make_product(3, price=350, max_pax_per_room=2)   # passa solo con 3 camere
        vela = make_vela([TWO_PER_ROOM, NO_LIMIT, other])
        _, first = proposal_for(vela, "padel, siamo in due")
        r = vela.reject_proposal(first.proposal.id, "siamo in 5", StructuredFields(rooms=3))
        self.assertIn("per 5 persone in 3 camere", r.say)
        self.assertEqual((r.product.product_id, r.to_dict()["rooms"]), ("3", 3))


class AcceptRoomsTest(unittest.TestCase):
    def setUp(self):
        self.vela = make_vela([TWO_PER_ROOM])
        self.intent, self.proposal = proposal_for(self.vela, "padel, siamo in cinque, tre camere")

    def order(self):
        return self.vela.repos.orders.get_by_proposal(self.proposal.proposal.id)

    def test_order_takes_the_rooms_from_the_intent(self):
        r = self.vela.accept_proposal(self.proposal.proposal.id, FIVE)
        self.assertIsInstance(r, OrderQueued)
        self.assertEqual((self.order().pax, self.order().rooms), (5, 3))

    def test_below_the_minimum_asks_and_creates_nothing(self):
        r = self.vela.accept_proposal(self.proposal.proposal.id, FIVE, rooms=2)
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.question, QUESTION_ROOMS)
        self.assertEqual(r.say, "Le camere di questo viaggio ospitano al massimo 2 persone: per 5 "
                                "servono almeno 3 camere. In quante camere?")
        self.assertIsNone(self.order())
        self.assertEqual(self.vela.repos.intents.get(self.intent.intent_id).criteria.rooms, 3)

    def test_correction_updates_order_and_intent(self):
        """Decisione M21-D, 3: la correzione vale anche per una sostituzione RF-17."""
        r = self.vela.accept_proposal(self.proposal.proposal.id, FIVE, rooms=4)
        self.assertIsInstance(r, OrderQueued)
        self.assertEqual(self.order().rooms, 4)
        self.assertEqual(self.vela.repos.intents.get(self.intent.intent_id).criteria.rooms, 4)

    def test_rooms_above_the_people_is_discarded_and_said(self):
        r = self.vela.accept_proposal(self.proposal.proposal.id, FIVE, rooms=9)
        self.assertIsInstance(r, OrderQueued)
        self.assertTrue(r.say.startswith("Non ho potuto usare 9 come numero di camere. "), r.say)
        self.assertEqual(self.order().rooms, 3)

    def test_second_accept_ignores_the_rooms(self):
        self.vela.accept_proposal(self.proposal.proposal.id, FIVE)
        self.vela.accept_proposal(self.proposal.proposal.id, FIVE, rooms=4)
        self.assertEqual(self.order().rooms, 3)

    def test_missing_traveler_data_comes_before_the_rooms_check(self):
        r = self.vela.accept_proposal(self.proposal.proposal.id, TravelerProfile("Anna"), rooms=2)
        self.assertEqual(type(r).__name__, "MissingTravelerData")
        self.assertIsNone(self.order())

    def test_old_intent_without_rooms_orders_one_room(self):
        vela = make_vela([NO_LIMIT])
        vela.repos.intents.add(Intent("old", "padel", Criteria("padel", pax=2), TravelerProfile(), NOW))
        p = vela.get_proposal("old")
        self.assertEqual(p.to_dict()["rooms"], 1)
        two = TravelerProfile("Anna", "Rossi", "a@x.it", "+390000", participants=(Participant("Bo", "Bi"),))
        vela.accept_proposal(p.proposal.id, two)
        self.assertEqual(vela.repos.orders.get_by_proposal(p.proposal.id).rooms, 1)


if __name__ == "__main__":
    unittest.main()
