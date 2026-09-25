import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import (NOW, FakeHofJ, FlakyPayments, StubPayments, assert_single_product,
                     inline_worker, make_product)
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.intent import QUESTION_PAX
from vela.domain.models import (Area, IntentCreated, IntentQuestion, NoMatch, ProposalMade,
                                TravelerProfile)
from vela.domain.usecases import NotFound, Vela
from vela.ports.payments import PaymentsError, to_cents

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


    def test_fallback_extractor_is_used(self):
        class Fx:
            calls = 0

            def extract(self, text, today):
                Fx.calls += 1
                return {"sport": "padel", "area": None, "period_start": "2026-10-01",
                        "period_end": "2026-10-31", "pax": None, "budget": None}
        vela = make_vela()
        vela.extractor = Fx()
        r = vela.create_intent("una vacanza con la racchetta in Spagna per due")
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(r.criteria.sport, "padel")
        self.assertEqual(Fx.calls, 1)

    def test_default_has_no_extractor(self):
        self.assertIsNone(make_vela().extractor)


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

    def test_product_unbookable_for_more_than_24h_is_proposed_again(self):
        """RF-34: il caso d'uso passa l'ora corrente al chooser."""
        from dataclasses import replace
        stale = replace(make_product(3, price=350, country="ES", destination="Valencia"),
                        bookable=False, bookable_checked_at=NOW - timedelta(hours=25))
        fresh = replace(make_product(4, price=390, country="ES", destination="Lanzarote"),
                        bookable=False, bookable_checked_at=NOW - timedelta(hours=1))
        vela = make_vela(products=[stale, fresh])
        r = vela.get_proposal(vela.create_intent(INTENT).intent_id)
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(r.product.product_id, "3")

    def test_no_match_names_criterion(self):
        vela = make_vela(products=[make_product(1, sport="tennis")])
        iid = vela.create_intent(INTENT).intent_id
        r = vela.get_proposal(iid)
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "sport")
        self.assertIn("di padel", r.say)
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

    def test_too_expensive_lowers_budget(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)                  # prodotto 3, 350 × 2 = 700
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertEqual(vela.repos.intents.get(iid).criteria.budget, Decimal("560.00"))
        self.assertEqual(second.product.product_id, "4")
        self.assertIn("più economica", second.proposal.reason)

    def test_double_reject_does_not_lower_twice(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        vela.reject_proposal(first.proposal.id, "troppo caro")
        vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertEqual(vela.repos.intents.get(iid).criteria.budget, Decimal("560.00"))

    def test_further_south_changes_area(self):
        vela = make_vela([
            make_product(1, price=350, country="ES", destination="Valencia"),
            make_product(2, price=380, country="ES", destination="Barcellona"),
            make_product(3, price=600, country="ES", destination="Alicante"),
        ])
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        self.assertEqual(first.product.product_id, "1")
        second = vela.reject_proposal(first.proposal.id, "più a sud")
        self.assertEqual(vela.repos.intents.get(iid).criteria.area, Area("city", "Alicante", "ES"))
        self.assertEqual(second.product.product_id, "3")

    def test_new_period_in_reason(self):
        vela = make_vela([
            make_product(1, price=350, country="ES", destination="Valencia"),
            make_product(2, price=450, country="ES", destination="Madrid",
                         windows=(("2026-11-05", "2026-11-08"),)),
        ])
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        second = vela.reject_proposal(first.proposal.id, "a novembre")
        self.assertEqual(second.product.product_id, "2")
        self.assertEqual(second.proposal.start_date, date(2026, 11, 5))

    def test_unknown_reason_keeps_criteria(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        before = vela.repos.intents.get(iid).criteria
        first = vela.get_proposal(iid)
        vela.reject_proposal(first.proposal.id, "più vicino")
        self.assertEqual(vela.repos.intents.get(iid).criteria, before)


from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.models import (AcceptResponse, MissingTravelerData, OrderStatus,
                                OrderStatusResponse, Participant)

FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


def accepted_vela(hofj=None, payments=None):
    vela = make_vela(hofj=hofj, payments=payments)
    iid = vela.create_intent(INTENT).intent_id
    proposal = vela.get_proposal(iid)
    return vela, iid, proposal


class AcceptProposalTest(unittest.TestCase):
    def test_missing_data_creates_nothing(self):
        vela, _, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, TravelerProfile(first_name="Anna"))
        self.assertIsInstance(r, MissingTravelerData)
        self.assertEqual(r.missing, ("last_name", "email", "phone",
                                     "participants[0].first_name", "participants[0].last_name"))
        self.assertIn("cognome", r.say)
        self.assertEqual(vela.hofj.calls, [])
        self.assertIsNone(vela.repos.orders.get_by_proposal(proposal.proposal.id))
        assert_single_product(self, r.to_dict())

    def test_accept_creates_itinerary_customer_pax_and_order(self):
        vela, iid, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        self.assertIsInstance(r, AcceptResponse)
        self.assertEqual(r.status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(r.total, Decimal("700"))
        self.assertFalse(r.total_differs)
        self.assertEqual(r.payment_url, "http://pay.test/" + r.order_id)
        self.assertNotIn("http", r.say)
        assert_single_product(self, r.to_dict())
        calls = [c[0] for c in vela.hofj.calls]
        self.assertEqual(calls, ["create_itinerary", "set_customer", "get_pax", "set_pax", "get_itinerary"])
        self.assertEqual(vela.hofj.calls[0][1:], ("3", date(2026, 10, 1), 2, 1, "EUR"))
        customer = vela.hofj.calls[1][2]
        self.assertEqual((customer.first_name, customer.email), ("Anna", "anna@x.it"))
        self.assertEqual((customer.city, customer.country_code), (DEFAULT_TRAVELER.city, DEFAULT_TRAVELER.country_code))
        pax = vela.hofj.calls[3][2]
        self.assertEqual([(p.ref_id, p.first_name, p.last_name) for p in pax],
                         [("ref-0", "Anna", "Rossi"), ("ref-1", "Bo", "Bi")])
        order = vela.repos.orders.get(r.order_id)
        self.assertEqual((order.itinerary_id, order.payment_ref), ("it-3", "pi_" + r.order_id))
        self.assertEqual(order.traveler.email, "anna@x.it")

    def test_real_total_is_declared_when_different(self):
        vela, _, proposal = accepted_vela(hofj=FakeHofJ(total=750))
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        self.assertTrue(r.total_differs)
        self.assertEqual((r.total, r.price_from_total), (Decimal("750"), Decimal("700")))
        self.assertLess(r.say.index("750 euro"), r.say.index("link"))

    def test_double_accept_returns_same_order(self):
        vela, _, proposal = accepted_vela()
        a = vela.accept_proposal(proposal.proposal.id, FULL)
        b = vela.accept_proposal(proposal.proposal.id)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(len([c for c in vela.hofj.calls if c[0] == "create_itinerary"]), 1)
        self.assertEqual(len(vela.payments.links), 1)

    def test_profile_from_intent_is_enough(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT, FULL).intent_id
        proposal = vela.get_proposal(iid)
        self.assertIsInstance(vela.accept_proposal(proposal.proposal.id), AcceptResponse)

    def test_get_proposal_after_accept_returns_same_proposal(self):
        vela, iid, proposal = accepted_vela()
        vela.accept_proposal(proposal.proposal.id, FULL)
        again = vela.get_proposal(iid)
        self.assertEqual(again.proposal.id, proposal.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 1)

    def test_unknown_proposal(self):
        with self.assertRaises(NotFound):
            make_vela().accept_proposal("nope", FULL)

    def test_link_description_is_the_product_title(self):
        vela, _, proposal = accepted_vela()
        vela.accept_proposal(proposal.proposal.id, FULL)
        product = vela.repos.products.get(proposal.proposal.product_id)
        self.assertEqual(vela.payments.descriptions, [product.title])

    def test_payments_error_then_retry_creates_the_link_once(self):
        vela, _, proposal = accepted_vela(payments=FlakyPayments(failures=1))
        with self.assertRaises(PaymentsError):
            vela.accept_proposal(proposal.proposal.id, FULL)
        order = vela.repos.orders.get_by_proposal(proposal.proposal.id)
        self.assertIsNone(order.payment_url)
        r = vela.accept_proposal(proposal.proposal.id)
        self.assertEqual(r.order_id, order.id)
        self.assertEqual(r.payment_url, "http://pay.test/" + order.id)
        self.assertEqual(vela.repos.orders.get(order.id).payment_url, r.payment_url)
        self.assertEqual(len([c for c in vela.hofj.calls if c[0] == "create_itinerary"]), 1)
        self.assertEqual(len(vela.payments.links), 1)
        self.assertEqual(vela.payments.attempts, 2)

    def test_existing_link_is_not_recreated(self):
        vela, _, proposal = accepted_vela()
        vela.accept_proposal(proposal.proposal.id, FULL)
        vela.accept_proposal(proposal.proposal.id)
        self.assertEqual(len(vela.payments.descriptions), 1)


class ToCentsTest(unittest.TestCase):
    def test_to_cents(self):
        self.assertEqual(to_cents(Decimal("700")), 70000)
        self.assertEqual(to_cents(Decimal("799.9")), 79990)
        self.assertEqual(to_cents(Decimal("0.01")), 1)


class OrderStatusTest(unittest.TestCase):
    def test_awaiting_payment(self):
        vela, _, proposal = accepted_vela()
        accepted = vela.accept_proposal(proposal.proposal.id, FULL)
        r = vela.get_order_status(accepted.order_id)
        self.assertIsInstance(r, OrderStatusResponse)
        self.assertEqual((r.status, r.booking_code), (OrderStatus.AWAITING_PAYMENT, None))
        self.assertEqual((r.total, r.currency, r.payment_url),
                         (Decimal("700"), "EUR", "http://pay.test/" + accepted.order_id))
        self.assertIn("attesa", r.say)
        self.assertIn("700 euro", r.say)
        d = r.to_dict()
        self.assertEqual((d["total"], d["currency"], d["payment_url"]),
                         ("700.00", "EUR", "http://pay.test/" + accepted.order_id))
        assert_single_product(self, d)

    def test_link_is_hidden_once_not_payable(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        vela.orders.expire(oid)
        r = vela.get_order_status(oid)
        self.assertEqual(r.status, OrderStatus.EXPIRED)
        self.assertIsNone(r.payment_url)
        self.assertIsNone(r.to_dict()["payment_url"])
        self.assertIn("scaduto", r.say)

    def test_confirmed_keeps_total(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        vela.orders.mark_paid(oid, "pi_1")
        inline_worker(vela).drain()
        r = vela.get_order_status(oid)
        self.assertEqual((r.status, r.total, r.payment_url),
                         (OrderStatus.CONFIRMED, Decimal("700"), None))

    def test_unknown(self):
        with self.assertRaises(NotFound):
            make_vela().get_order_status("nope")


class FullReplayFlowTest(unittest.TestCase):
    """Il flusso della roadmap M2 con gli adapter replay veri e il catalogo della fixture."""

    def make(self, repos=None, at=NOW):
        repos = repos or MemoryRepositories()
        hofj = ReplayHofJ()
        if repos.products.count() == 0:
            repos.products.upsert_many(hofj.load_catalog())
        return Vela(repos, hofj, FakePayments("https://vela.test"), DEFAULT_TRAVELER, now=Clock(at))

    def test_intent_to_confirmed(self):
        vela = self.make()
        responses = []
        created = vela.create_intent(INTENT)
        responses.append(created)
        first = vela.get_proposal(created.intent_id)
        responses.append(first)
        self.assertIsInstance(first, ProposalMade)
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        responses.append(second)
        self.assertIsInstance(second, ProposalMade)
        self.assertNotEqual(second.product.product_id, first.product.product_id)
        accepted = vela.accept_proposal(second.proposal.id, FULL)
        responses.append(accepted)
        self.assertIsInstance(accepted, AcceptResponse)
        self.assertEqual(accepted.payment_url, "https://vela.test/replay/checkout/" + accepted.order_id)
        # pagamento simulato: ciò che fa GET /replay/checkout/{order_id}
        vela.orders.mark_paid(accepted.order_id, "pi_replay_" + accepted.order_id)
        inline_worker(vela).drain()
        status = vela.get_order_status(accepted.order_id)
        responses.append(status)
        self.assertEqual(status.status, OrderStatus.CONFIRMED)
        self.assertRegex(status.booking_code, r"^R-\d{6}$")
        self.assertIn(status.booking_code, status.say)
        again = vela.accept_proposal(second.proposal.id, FULL)
        self.assertEqual(again.order_id, accepted.order_id)
        for r in responses:
            assert_single_product(self, r.to_dict())

    def test_resume_at_boot_completes_pending_booking(self):
        repos = MemoryRepositories()
        vela = self.make(repos)
        iid = vela.create_intent(INTENT, FULL).intent_id
        proposal = vela.get_proposal(iid)
        oid = vela.accept_proposal(proposal.proposal.id).order_id
        vela.orders.mark_paid(oid, "pi")   # pagato, ma il processo "muore" prima della prenotazione
        restarted = self.make(repos, at=NOW + timedelta(hours=1))   # nuovo processo, più tardi
        self.assertEqual(restarted.orders.resume_bookings(), [])   # il job è già in coda (RF-27)
        inline_worker(restarted).drain()
        self.assertEqual(restarted.get_order_status(oid).status, OrderStatus.CONFIRMED)


class LanguageFlowTest(unittest.TestCase):
    def test_english_intent_gets_english_answers(self):
        from vela.domain.models import Participant
        vela = make_vela()
        created = vela.create_intent("a padel weekend in Spain in October, we are two, max 800 euros")
        self.assertIn("Spain", created.say)
        proposal = vela.get_proposal(created.intent_id)
        self.assertIn("per person", proposal.say)
        missing = vela.accept_proposal(proposal.proposal.id)
        self.assertIn("To book", missing.say)
        accepted = vela.accept_proposal(proposal.proposal.id, TravelerProfile(
            "Anna", "Rossi", "a@x.it", "+39", participants=(Participant("Bo", "Bi"),)))
        self.assertIn("payment link", accepted.say)
        self.assertIn("waiting for payment", vela.get_order_status(accepted.order_id).say)

    def test_english_no_match(self):
        vela = make_vela([])                       # catalogo vuoto: si ferma al filtro "archived"
        iid = vela.create_intent("tennis in October, we are two").intent_id
        self.assertIn("try again later", vela.get_proposal(iid).say)
