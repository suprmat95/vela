"""UC-F (M21-F, RF-71..75, RF-49, RF-55): rifiuti con motivo sempre capito, dal caso d'uso."""
import unittest
from datetime import date, timedelta

from support import NOW, FakeHofJ, StubPayments, assert_single_product, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.models import (Area, IntentQuestion, NoMatch, OrderQueued, OrderStatus, ProposalMade,
                                StructuredFields, TravelerProfile, Participant)
from vela.domain.usecases import Vela

INTENT = "padel in Spagna a ottobre, siamo in due"
QUESTION = "Cosa non ti convince: il posto, l'hotel, le date o il prezzo?"
FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_vela(products):
    repos = MemoryRepositories()
    repos.products.upsert_many(products)
    ids = iter("id%d" % i for i in range(1, 200))
    return Vela(repos, FakeHofJ(), StubPayments(), now=Clock(), new_id=lambda: next(ids))


def first_proposal(vela, text=INTENT):
    iid = vela.create_intent(text).intent_id
    return iid, vela.get_proposal(iid)


def rejection(vela, iid, proposal_id):
    return {r.proposal_id: r for r in vela.repos.rejections.list_for_intent(iid)}.get(proposal_id)


class HotelTest(unittest.TestCase):
    """F1 (RF-72)."""
    PRODUCTS = [make_product(1, price=300, destination="Valencia", hotel="Hotel Sole"),
                make_product(2, price=320, destination="Madrid", hotel="hotel  sole"),
                make_product(3, price=400, destination="Alicante", hotel="Hotel Luna")]

    def test_hotel_reason_excludes_every_product_of_that_hotel(self):
        vela = make_vela(self.PRODUCTS)
        iid, first = first_proposal(vela)
        self.assertEqual(first.product.product_id, "1")
        r = vela.reject_proposal(first.proposal.id, "L'hotel non mi piace")
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(r.product.product_id, "3")
        self.assertTrue(r.say.startswith("Ho escluso i viaggi con l'hotel Hotel Sole. Ho capito:"), r.say)
        self.assertEqual(rejection(vela, iid, first.proposal.id).kind, "hotel")
        assert_single_product(self, r.to_dict())

    def test_hotel_field_and_english(self):
        vela = make_vela(self.PRODUCTS)
        iid, first = first_proposal(vela, "padel in Spain in October, two of us")
        r = vela.reject_proposal(first.proposal.id, "hmm", StructuredFields(reject_kind="hotel"))
        self.assertEqual(r.product.product_id, "3")
        self.assertTrue(r.say.startswith("I've left out the trips at Hotel Sole."), r.say)

    def test_only_that_hotel_left_is_no_match_hotel(self):
        vela = make_vela(self.PRODUCTS[:2])
        iid, first = first_proposal(vela)
        r = vela.reject_proposal(first.proposal.id, "another hotel please")
        self.assertIsInstance(r, NoMatch)
        self.assertEqual((r.failed_criterion, r.rejected_proposal_id), ("hotel", first.proposal.id))

    def test_price_and_hotel_in_one_reason_keep_the_hotel_out(self):
        """Motivo con più tipi: registrato `price`, e l'hotel resta escluso (RF-72 dal motivo): senza
        l'esclusione arriverebbe il 5, stesso hotel, che parte prima del 6."""
        vela = make_vela([make_product(4, price=250, destination="Siviglia", hotel="Hotel Sole"),
                          make_product(5, price=240, destination="Madrid", hotel="Hotel Sole",
                                       windows=(("2026-10-08", "2026-10-11"),)),
                          make_product(6, price=230, destination="Valencia", hotel="Hotel Luna",
                                       windows=(("2026-10-15", "2026-10-18"),))])
        iid, first = first_proposal(vela)
        self.assertEqual(first.product.product_id, "4")
        r = vela.reject_proposal(first.proposal.id, "troppo caro e l'hotel non mi piace")
        self.assertEqual(rejection(vela, iid, first.proposal.id).kind, "price")
        self.assertEqual(r.product.product_id, "6")
        self.assertIn("Ho escluso i viaggi con l'hotel Hotel Sole.", r.say)


class PlaceTest(unittest.TestCase):
    """F2 (RF-73)."""
    PRODUCTS = [make_product(1, price=300, destination="Estepona", hotel="A"),
                make_product(2, price=320, destination="Marbella", hotel="B"),
                make_product(3, price=400, destination="Valencia", hotel="C")]

    def test_negated_place_is_excluded_and_spain_kept(self):
        vela = make_vela(self.PRODUCTS)
        iid, first = first_proposal(vela)
        self.assertEqual(first.product.product_id, "1")
        r = vela.reject_proposal(first.proposal.id, "Estepona no, ma la Spagna va bene")
        self.assertEqual(r.product.product_id, "2")
        criteria = vela.repos.intents.get(iid).criteria
        self.assertEqual((criteria.area.name, criteria.excluded_areas),
                         ("Spagna", (Area("city", "Estepona", "ES"),)))
        self.assertIn("Ho capito: un viaggio di padel in Spagna, esclusi i viaggi a Estepona,", r.say)
        self.assertEqual(rejection(vela, iid, first.proposal.id).kind, "place")

    def test_marbella_no_then_nothing_left(self):
        vela = make_vela(self.PRODUCTS[:2])
        iid, first = first_proposal(vela)
        second = vela.reject_proposal(first.proposal.id, "Estepona no")
        self.assertEqual(second.product.product_id, "2")
        r = vela.reject_proposal(second.proposal.id, "Marbella no")
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "place")
        self.assertIn("Esclusi i viaggi a Estepona e a Marbella", r.say)

    def test_place_kind_without_area_excludes_the_product_place(self):
        vela = make_vela(self.PRODUCTS)
        iid, first = first_proposal(vela)
        r = vela.reject_proposal(first.proposal.id, "boh", StructuredFields(reject_kind="place"))
        self.assertEqual(r.product.product_id, "2")
        self.assertEqual(vela.repos.intents.get(iid).criteria.excluded_areas, (Area("city", "Estepona", "ES"),))

    def test_place_kind_with_area_moves_as_before(self):
        vela = make_vela(self.PRODUCTS)
        iid, first = first_proposal(vela)
        r = vela.reject_proposal(first.proposal.id, "boh", StructuredFields(reject_kind="place", area="Valencia"))
        self.assertEqual(r.product.product_id, "3")
        self.assertEqual(vela.repos.intents.get(iid).criteria.excluded_areas, ())


class SameTripTest(unittest.TestCase):
    """F3 (RF-74, RF-55)."""
    WINDOWS = (("2026-10-01", "2026-10-04"), ("2026-10-08", "2026-10-11"), ("2026-10-15", "2026-10-18"),
               ("2026-11-05", "2026-11-08"))

    def products(self):
        return [make_product(1, price=300, destination="Valencia", windows=self.WINDOWS[:3], hotel="A"),
                make_product(2, price=400, destination="Madrid", hotel="B")]

    def test_same_product_next_window_then_no_match_then_another_trip(self):
        vela = make_vela(self.products())
        iid, first = first_proposal(vela)
        self.assertEqual((first.product.product_id, first.proposal.start_date), ("1", date(2026, 10, 1)))
        second = vela.reject_proposal(first.proposal.id, "Questo mi piace ma non posso in quelle date")
        self.assertEqual((second.product.product_id, second.proposal.start_date), ("1", date(2026, 10, 8)))
        self.assertIn("per 2 persone. Stesso viaggio, con un'altra partenza. Ti propongo Padel a Valencia 1",
                      second.say)
        stored = rejection(vela, iid, first.proposal.id)
        self.assertEqual((stored.kind, stored.keep_product), ("dates", True))
        third = vela.reject_proposal(second.proposal.id, "same trip, other dates")
        self.assertEqual(third.proposal.start_date, date(2026, 10, 15))
        none = vela.reject_proposal(third.proposal.id, "", StructuredFields(reject_kind="dates", keep_product=True))
        self.assertIsInstance(none, NoMatch)
        self.assertEqual((none.failed_criterion, none.rejected_proposal_id), ("dates", third.proposal.id))
        self.assertIn("Questo viaggio non ha altre partenze tra il 1 ottobre 2026 e il 31 ottobre 2026. "
                      "Vuoi che cerchi un altro viaggio?", none.say)
        other = vela.reject_proposal(third.proposal.id, "sì, cerca un altro viaggio",
                                     StructuredFields(keep_product=False))
        self.assertEqual(other.product.product_id, "2")
        stored = rejection(vela, iid, third.proposal.id)
        self.assertEqual((stored.kind, stored.keep_product), ("dates", False))
        self.assertEqual(len(vela.repos.rejections.list_for_intent(iid)), 3)   # nessun rifiuto in più

    def test_new_period_in_the_reason_gives_the_first_window_there(self):
        products = self.products()
        products[0] = make_product(1, price=300, destination="Valencia", windows=self.WINDOWS, hotel="A")
        vela = make_vela(products)
        iid, first = first_proposal(vela)
        r = vela.reject_proposal(first.proposal.id, "stesso viaggio ma a novembre")
        self.assertEqual((r.product.product_id, r.proposal.start_date), ("1", date(2026, 11, 5)))

    def test_dates_without_keep_excludes_the_product(self):
        vela = make_vela(self.products())
        iid, first = first_proposal(vela)
        r = vela.reject_proposal(first.proposal.id, "non posso in quelle date")
        self.assertEqual(r.product.product_id, "2")
        self.assertEqual(rejection(vela, iid, first.proposal.id).keep_product, False)


class QuestionTest(unittest.TestCase):
    """F4 (RF-75, RF-49)."""

    def setUp(self):
        self.vela = make_vela([make_product(1, price=300, destination="Valencia", hotel="A"),
                               make_product(2, price=400, destination="Madrid", hotel="B")])
        self.iid, self.first = first_proposal(self.vela)

    def test_unclassified_reason_asks_and_changes_nothing(self):
        before = self.vela.repos.intents.get(self.iid).criteria
        for reason in ("Non mi convince", "mah, non so", "not for me", ""):
            with self.subTest(reason=reason):
                r = self.vela.reject_proposal(self.first.proposal.id, reason)
                self.assertIsInstance(r, IntentQuestion)
                self.assertEqual((r.question, r.say, r.proposal_id), (QUESTION, QUESTION, self.first.proposal.id))
                self.assertEqual(r.to_dict(), {"question": QUESTION, "say": QUESTION,
                                               "proposal_id": self.first.proposal.id})
        self.assertEqual(self.vela.repos.rejections.list_for_intent(self.iid), [])
        self.assertEqual(self.vela.repos.intents.get(self.iid).criteria, before)
        # la proposta resta aperta e accettabile
        self.assertEqual(self.vela.get_proposal(self.iid).proposal.id, self.first.proposal.id)

    def test_english_question(self):
        vela = make_vela([make_product(1)])
        iid, first = first_proposal(vela, "padel in Spain in October, two of us")
        r = vela.reject_proposal(first.proposal.id, "meh")
        self.assertEqual(r.question, "What doesn't convince you: the place, the hotel, the dates or the price?")

    def test_queued_order_stays_queued(self):
        queued = self.vela.accept_proposal(self.first.proposal.id, FULL)
        self.assertIsInstance(queued, OrderQueued)
        r = self.vela.reject_proposal(self.first.proposal.id, "non mi convince")
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(self.vela.repos.orders.get(queued.order_id).status, OrderStatus.QUEUED)

    def test_second_call_with_the_answer_registers_the_kind(self):
        self.vela.reject_proposal(self.first.proposal.id, "non mi convince")
        r = self.vela.reject_proposal(self.first.proposal.id, "non mi convince, l'hotel")
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(rejection(self.vela, self.iid, self.first.proposal.id).kind, "hotel")

    def test_explicit_other_behaves_as_before(self):
        r = self.vela.reject_proposal(self.first.proposal.id, "non mi convince",
                                      StructuredFields(reject_kind="other"))
        self.assertEqual(r.product.product_id, "2")
        self.assertIn("Non so scegliere in base a questo: ho escluso solo la proposta di prima.", r.say)
        self.assertEqual(rejection(self.vela, self.iid, self.first.proposal.id).kind, "other")

    def test_invalid_kind_is_said_and_the_question_follows(self):
        r = self.vela.reject_proposal(self.first.proposal.id, "boh", StructuredFields(reject_kind="weather"))
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.say, "Non ho potuto usare weather come tipo di rifiuto. " + QUESTION)

    def test_after_a_no_match_the_same_proposal_does_not_ask_again(self):
        """RF-55: la proposta è già rifiutata; un nuovo motivo senza tipo non la riapre."""
        vela = make_vela([make_product(1, price=300, destination="Valencia")])
        iid, first = first_proposal(vela)
        none = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertIsInstance(none, NoMatch)
        again = vela.reject_proposal(first.proposal.id, "ok")
        self.assertIsInstance(again, NoMatch)
        self.assertEqual(rejection(vela, iid, first.proposal.id).kind, "price")


if __name__ == "__main__":
    unittest.main()
