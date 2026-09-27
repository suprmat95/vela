import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import (NOW, FakeHofJ, StubPayments, assert_single_product, drain_to_link,
                     inline_worker, make_product)
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.intent import QUESTION_PAX
from vela.domain.models import (Area, IntentCreated, IntentQuestion, JobKind, JobStatus,
                                MissingTravelerData, NoMatch, OrderQueued, OrderStatus,
                                OrderStatusResponse, Participant, ProposalMade, TravelerProfile)
from vela.domain.usecases import NotFound, Vela
from vela.ports.payments import to_cents

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
        self.assertEqual(second.product.product_id, "1")                # più economico (M7)
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
        vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertEqual(vela.repos.intents.get(iid).criteria.budget, Decimal("560.00"))

    def test_too_expensive_gives_a_cheaper_proposal_even_outside_the_area(self):
        """§10.1 (decisione M7): in Spagna restano solo 390 e 450, più cari di 350: si passa
        all'Italia a 300, dichiarando che non è in Spagna."""
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)                  # prodotto 3, Valencia, 700 in totale
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertEqual(second.product.product_id, "1")                # Riccione, 600
        self.assertIn("Spagna", second.proposal.reason)
        assert_single_product(self, second.to_dict())

    def test_repeated_too_expensive_keeps_lowering_the_total(self):
        vela = make_vela([make_product(1, price=300, country="ES", destination="Valencia"),
                          make_product(2, price=400, country="ES", destination="Madrid"),
                          make_product(3, price=250, country="IT", destination="Firenze"),
                          make_product(4, price=100, country="IT", destination="Riccione")])
        iid = vela.create_intent(INTENT).intent_id
        totals = []
        r = vela.get_proposal(iid)
        while isinstance(r, ProposalMade):
            totals.append(r.proposal.total_from)
            r = vela.reject_proposal(r.proposal.id, "costa troppo")
        # Valencia 600; Madrid (800) è più cara, fuori area la più economica è Riccione (200)
        self.assertEqual(totals, [Decimal("600"), Decimal("200")])
        self.assertEqual(r.failed_criterion, "price")

    def test_nothing_cheaper_is_a_no_match_that_says_so(self):
        vela = make_vela([make_product(1, price=300, country="ES", destination="Valencia"),
                          make_product(2, price=450, country="ES", destination="Madrid")])
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        r = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "price")
        self.assertIn("più economico", r.say)

    def test_non_price_reason_sets_no_ceiling(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)                  # prodotto 3, 350
        second = vela.reject_proposal(first.proposal.id, "non mi piace")
        self.assertEqual(second.product.product_id, "4")                # 390, in Spagna

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


FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


def accepted_vela(hofj=None, payments=None):
    vela = make_vela(hofj=hofj, payments=payments)
    iid = vela.create_intent(INTENT).intent_id
    proposal = vela.get_proposal(iid)
    return vela, iid, proposal


def accept_second_intent(vela, text="padel a Valencia a ottobre, siamo in due"):
    """Un secondo ordine in coda, su un altro intento."""
    iid = vela.create_intent(text, FULL).intent_id
    return vela.accept_proposal(vela.get_proposal(iid).proposal.id)


class AcceptProposalTest(unittest.TestCase):
    """RF-45, RF-19: l'accettazione mette in coda, non chiama né HofJ né il pagamento."""

    def test_missing_data_creates_nothing(self):
        vela, _, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, TravelerProfile(first_name="Anna"))
        self.assertIsInstance(r, MissingTravelerData)
        self.assertEqual(r.missing, ("last_name", "email", "phone",
                                     "participants[0].first_name", "participants[0].last_name"))
        self.assertIn("cognome", r.say)
        self.assertEqual(vela.hofj.calls, [])
        self.assertIsNone(vela.repos.orders.get_by_proposal(proposal.proposal.id))
        self.assertFalse(vela.repos.jobs.purchase_waiting())
        assert_single_product(self, r.to_dict())

    def test_accept_returns_queued_without_calling_ports(self):
        vela, _, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        self.assertIsInstance(r, OrderQueued)
        self.assertEqual((r.status, r.position, r.wait_seconds), (OrderStatus.QUEUED, 1, 2))   # 60 ÷ 46,5 per eccesso (M19)
        self.assertEqual(r.to_dict(), {"order_id": r.order_id, "status": "queued", "position": 1,
                                       "wait_seconds": 2, "say": r.say})
        self.assertIn("prezzo effettivo", r.say)
        self.assertIn("un minuto", r.say)
        self.assertEqual(vela.hofj.calls, [])
        self.assertEqual(vela.payments.links, [])
        assert_single_product(self, r.to_dict())

    def test_accept_enqueues_purchase_job(self):
        vela, iid, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        order = vela.repos.orders.get(r.order_id)
        self.assertEqual((order.status, order.total, order.itinerary_id), (OrderStatus.QUEUED, None, None))
        self.assertEqual(order.traveler.email, "anna@x.it")
        job = vela.repos.jobs.active_for_order(r.order_id, JobKind.PURCHASE)
        self.assertEqual((job.status, job.step, job.enqueued_at), (JobStatus.PENDING, 0, order.enqueued_at))

    def test_double_accept_returns_same_order(self):
        vela, _, proposal = accepted_vela()
        a = vela.accept_proposal(proposal.proposal.id, FULL)
        b = vela.accept_proposal(proposal.proposal.id)
        self.assertIsInstance(b, OrderStatusResponse)
        self.assertEqual((b.order_id, b.status, b.position), (a.order_id, OrderStatus.QUEUED, 1))
        jobs = [j for j in vela.repos.jobs._jobs.values() if j.kind == JobKind.PURCHASE]
        self.assertEqual(len(jobs), 1)

    def test_position_grows_with_the_queue(self):
        vela, _, proposal = accepted_vela()
        first = vela.accept_proposal(proposal.proposal.id, FULL)
        second = accept_second_intent(vela)
        self.assertEqual((first.position, second.position), (1, 2))
        self.assertEqual(second.wait_seconds, 3)             # 2 × 60 ÷ 46,5 per eccesso (M19)

    def test_profile_from_intent_is_enough(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT, FULL).intent_id
        proposal = vela.get_proposal(iid)
        self.assertIsInstance(vela.accept_proposal(proposal.proposal.id), OrderQueued)

    def test_get_proposal_after_accept_returns_same_proposal(self):
        vela, iid, proposal = accepted_vela()
        vela.accept_proposal(proposal.proposal.id, FULL)
        again = vela.get_proposal(iid)
        self.assertEqual(again.proposal.id, proposal.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 1)

    def test_unknown_proposal(self):
        with self.assertRaises(NotFound):
            make_vela().accept_proposal("nope", FULL)

    def test_the_job_prepares_itinerary_and_link_then_booking_sends_customer_and_pax(self):
        """M19: 2 chiamate prima del link; cliente e passeggeri nel job di prenotazione."""
        vela, _, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        worker = inline_worker(vela)
        worker.drain()
        order = vela.repos.orders.get(r.order_id)            # si ferma al prezzo effettivo
        self.assertEqual((order.status, order.total, order.payment_url),
                         (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), None))
        self.assertEqual(vela.payments.links, [])
        vela.accept_proposal(proposal.proposal.id)           # la conferma
        worker.drain()
        calls = [c[0] for c in vela.hofj.calls]
        self.assertEqual(calls, ["get_quota", "create_itinerary", "get_itinerary"])   # il link non chiama HofJ
        self.assertEqual(vela.hofj.calls[1][1:], ("3", date(2026, 10, 1), 2, 1, "EUR"))
        order = vela.repos.orders.get(r.order_id)
        self.assertEqual((order.status, order.itinerary_id, order.total, order.payment_ref),
                         (OrderStatus.AWAITING_PAYMENT, "it-3", Decimal("700"), "pi_" + r.order_id))
        product = vela.repos.products.get(proposal.proposal.product_id)
        self.assertEqual(vela.payments.descriptions, [product.title])
        vela.orders.mark_paid(r.order_id, "pi_" + r.order_id)
        worker.drain()
        calls = [c[0] for c in vela.hofj.calls]
        self.assertEqual(calls[3:], ["set_customer", "set_pax", "create_booking"])
        customer = vela.hofj.calls[3][2]
        self.assertEqual((customer.first_name, customer.email), ("Anna", "anna@x.it"))
        self.assertEqual((customer.city, customer.country_code),
                         (DEFAULT_TRAVELER.city, DEFAULT_TRAVELER.country_code))
        pax = vela.hofj.calls[4][2]
        self.assertEqual([(p.ref_id, p.first_name, p.last_name) for p in pax],
                         [("pax-1", "Anna", "Rossi"), ("pax-2", "Bo", "Bi")])
        self.assertEqual(vela.repos.orders.get(r.order_id).status, OrderStatus.CONFIRMED)

    def test_accept_on_replacement_inherits_enqueued_at(self):
        """RF-17: il nuovo ordine sulla proposta sostitutiva passa davanti a chi è arrivato dopo."""
        from vela.ports.hofj import ProductError
        vela, _, proposal = accepted_vela(hofj=FakeHofJ(fail_at={"create_itinerary": [ProductError("404")]}))
        first = vela.accept_proposal(proposal.proposal.id, FULL)
        first_order = vela.repos.orders.get(first.order_id)
        inline_worker(vela).drain()                       # errore del prodotto: ordine sostituito
        replaced = vela.repos.orders.get(first.order_id)
        self.assertEqual(replaced.status, OrderStatus.REPLACED)
        later = accept_second_intent(vela)                # arrivato dopo il primo
        again = vela.accept_proposal(replaced.replacement_proposal_id)
        self.assertEqual(vela.repos.orders.get(again.order_id).enqueued_at, first_order.enqueued_at)
        self.assertEqual((again.position, vela.get_order_status(later.order_id).position), (1, 2))


class PriceConfirmationTest(unittest.TestCase):
    """Decisione 2026-09-26: accept aspetta il prezzo effettivo, la seconda accettazione è la
    conferma e solo allora nasce il link."""

    def waiting_vela(self, hofj=None, wait=5):
        vela, iid, proposal = accepted_vela(hofj=hofj)
        worker = inline_worker(vela)
        slept = []

        def sleep(seconds):          # mentre il caso d'uso aspetta, il worker lavora
            slept.append(seconds)
            worker.drain()

        vela.accept_wait_seconds, vela.accept_poll_seconds, vela.sleep = wait, 1, sleep
        return vela, proposal.proposal.id, slept

    def test_accept_waits_for_the_actual_price(self):
        vela, pid, slept = self.waiting_vela(hofj=FakeHofJ(total=750))
        r = vela.accept_proposal(pid, FULL)
        self.assertIsInstance(r, OrderStatusResponse)
        d = r.to_dict()
        self.assertEqual((d["status"], d["total"], d["price_from_total"], d["total_differs"], d["payment_url"]),
                         ("awaiting_confirmation", "750.00", "700.00", True, None))
        self.assertEqual(r.say, "Il prezzo effettivo è 750 euro in totale per 2 persone, più dei 700 "
                                "stimati. Confermi? Se mi dici di sì preparo il link di pagamento.")
        self.assertEqual(slept, [1])
        self.assertEqual(vela.payments.links, [])
        assert_single_product(self, d)

    def test_second_accept_confirms_and_waits_for_the_link(self):
        vela, pid, _ = self.waiting_vela()
        oid = vela.accept_proposal(pid, FULL).order_id
        r = vela.accept_proposal(pid)
        self.assertEqual((r.status, r.payment_url, r.total), (OrderStatus.AWAITING_PAYMENT,
                                                               "http://pay.test/" + oid, Decimal("700")))
        purchases = [j for j in vela.repos.jobs._jobs.values() if j.kind == JobKind.PURCHASE]
        # il primo job si chiude al prezzo (passo 4), il secondo parte dal link e finisce
        self.assertEqual([(j.step, j.status) for j in purchases], [(4, JobStatus.DONE), (5, JobStatus.DONE)])
        self.assertEqual(len([c for c in vela.hofj.calls if c[0] == "create_itinerary"]), 1)

    def test_confirmation_enqueues_a_link_job_only_once(self):
        vela, pid, _ = self.waiting_vela()
        vela.accept_proposal(pid, FULL)
        vela.accept_wait_seconds = 0                     # nessun worker: la conferma resta in coda
        first = vela.accept_proposal(pid)
        again = vela.accept_proposal(pid)
        self.assertEqual((first.status, again.status), (OrderStatus.QUEUED, OrderStatus.QUEUED))
        pending = [j for j in vela.repos.jobs._jobs.values()
                   if j.kind == JobKind.PURCHASE and j.status == JobStatus.PENDING]
        self.assertEqual([j.step for j in pending], [4])
        self.assertIn("il link di pagamento sarà pronto", first.say)   # dopo la conferma: il link

    def test_wait_over_the_ceiling_answers_queued_for_the_price(self):
        vela, pid, slept = self.waiting_vela(wait=3)
        vela.sleep = slept.append                        # il worker non avanza
        r = vela.accept_proposal(pid, FULL)
        self.assertIsInstance(r, OrderQueued)
        self.assertEqual(slept, [1, 1, 1])
        self.assertIn("prezzo effettivo", r.say)
        self.assertNotIn("SMS", r.say)

    def test_replacement_during_the_wait_returns_the_new_proposal(self):
        """M20: il job sostituisce il prodotto mentre accept aspetta; nessuna attesa oltre."""
        from vela.ports.hofj import ProductError
        vela, pid, slept = self.waiting_vela(hofj=FakeHofJ(fail_at={"create_itinerary": [ProductError("404")]}))
        r = vela.accept_proposal(pid, FULL)
        self.assertEqual(r.status, OrderStatus.REPLACED)
        self.assertNotEqual(r.proposal.proposal.id, pid)
        self.assertEqual(slept, [1])
        assert_single_product(self, r.to_dict())

    def test_failure_during_the_wait_returns_the_reason(self):
        """M20: un ordine che esce da `queued` come `failed` chiude subito l'attesa."""
        from dataclasses import replace
        vela, pid, slept = self.waiting_vela()

        def fail(seconds):
            slept.append(seconds)
            order = next(iter(vela.repos.orders._items.values()))
            vela.repos.orders.save(replace(order, status=OrderStatus.FAILED, failure_reason="fornitore giù"))

        vela.sleep = fail
        r = vela.accept_proposal(pid, FULL)
        self.assertEqual((r.status, r.failure_reason), (OrderStatus.FAILED, "fornitore giù"))
        self.assertEqual(slept, [1])

    def test_second_accept_during_the_wait_reuses_the_order(self):
        """M20: un doppio accept mentre il primo aspetta non crea un secondo ordine né un job."""
        vela, pid, _ = self.waiting_vela()
        worker = inline_worker(vela)
        seen = []

        def sleep(seconds):
            if not seen:
                seen.append(vela.accept_proposal(pid))   # l'ordine è ancora in coda
            else:
                worker.drain()

        vela.sleep = sleep
        r = vela.accept_proposal(pid, FULL)
        self.assertEqual(r.status, OrderStatus.AWAITING_CONFIRMATION)
        self.assertEqual((seen[0].order_id, seen[0].status), (r.order_id, OrderStatus.QUEUED))
        self.assertEqual(len(vela.repos.orders._items), 1)
        purchases = [j for j in vela.repos.jobs._jobs.values() if j.kind == JobKind.PURCHASE]
        self.assertEqual(len(purchases), 1)

    def test_status_while_awaiting_confirmation_repeats_the_question(self):
        vela, pid, _ = self.waiting_vela()
        oid = vela.accept_proposal(pid, FULL).order_id
        r = vela.get_order_status(oid)
        self.assertEqual((r.status, r.total, r.payment_url), (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), None))
        self.assertIn("come stimato. Confermi?", r.say)

    def test_reject_awaiting_confirmation_cancels_without_a_link(self):
        vela, pid, _ = self.waiting_vela()
        oid = vela.accept_proposal(pid, FULL).order_id
        r = vela.reject_proposal(pid, "no grazie")
        self.assertTrue(r.say.startswith("Ho annullato l'ordine. "))
        self.assertEqual(vela.get_order_status(oid).status, OrderStatus.CANCELLED)
        self.assertEqual(vela.payments.links, [])

    def test_too_expensive_on_the_actual_price_uses_it_as_ceiling(self):
        """Stimato 700, effettivo 900: Madrid (780) costa più della stima ma meno del prezzo
        rifiutato davvero, quindi è ammessa."""
        products = [make_product(3, price=350, country="ES", destination="Valencia"),
                    make_product(4, price=390, country="ES", destination="Madrid")]
        vela = make_vela(products, hofj=FakeHofJ(total=900))
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        vela.accept_proposal(first.proposal.id, FULL)
        inline_worker(vela).drain()
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertIsInstance(second, ProposalMade)
        self.assertEqual(second.product.product_id, "4")

    def test_too_expensive_without_an_order_keeps_the_estimate_as_ceiling(self):
        products = [make_product(3, price=350, country="ES", destination="Valencia"),
                    make_product(4, price=390, country="ES", destination="Madrid")]
        vela = make_vela(products)
        first = vela.get_proposal(vela.create_intent(INTENT).intent_id)
        self.assertIsInstance(vela.reject_proposal(first.proposal.id, "troppo caro"), NoMatch)


class ToCentsTest(unittest.TestCase):
    def test_to_cents(self):
        self.assertEqual(to_cents(Decimal("700")), 70000)
        self.assertEqual(to_cents(Decimal("799.9")), 79990)
        self.assertEqual(to_cents(Decimal("0.01")), 1)


class RejectQueuedTest(unittest.TestCase):
    """RF-49: la rinuncia annulla l'ordine finché non c'è un pagamento."""

    def test_reject_queued_order_cancels_and_proposes_next(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        r = vela.reject_proposal(proposal.proposal.id, "ci ho ripensato")
        self.assertIsInstance(r, ProposalMade)
        self.assertNotEqual(r.proposal.product_id, proposal.proposal.product_id)
        self.assertTrue(r.say.startswith("Ho annullato l'ordine. "))
        self.assertEqual(vela.get_order_status(oid).status, OrderStatus.CANCELLED)
        inline_worker(vela).drain()
        self.assertEqual([c[0] for c in vela.hofj.calls], ["get_quota"])   # il job non chiama HofJ
        assert_single_product(self, r.to_dict())

    def test_reject_awaiting_payment_cancels(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
        self.assertEqual(vela.get_order_status(oid).status, OrderStatus.AWAITING_PAYMENT)
        vela.reject_proposal(proposal.proposal.id, "no")
        self.assertEqual(vela.get_order_status(oid).status, OrderStatus.CANCELLED)
        self.assertIsNone(vela.get_order_status(oid).payment_url)

    def test_reject_after_payment_leaves_order(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
        vela.orders.mark_paid(oid, "pi")
        r = vela.reject_proposal(proposal.proposal.id, "no")
        self.assertNotIn("annullato", r.say)
        self.assertEqual(vela.get_order_status(oid).status, OrderStatus.PAID_PENDING_BOOKING)

    def test_english_cancellation(self):
        vela = make_vela()
        iid = vela.create_intent("a padel weekend in Spain in October, we are two, max 800 euros", FULL).intent_id
        proposal = vela.get_proposal(iid)
        vela.accept_proposal(proposal.proposal.id)
        self.assertTrue(vela.reject_proposal(proposal.proposal.id, "no").say.startswith("I've cancelled the order. "))


class OrderStatusTest(unittest.TestCase):
    """RF-25, RF-39, RF-48: stessi campi per ogni stato, `null` quando non pertinenti."""
    KEYS = {"order_id", "status", "position", "wait_seconds", "total", "currency", "price_from_total",
            "total_differs", "payment_url", "booking_code", "failure_reason", "proposal_changed",
            "proposal", "say"}

    def test_queued_has_position_and_wait(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        d = vela.get_order_status(oid).to_dict()
        self.assertEqual(set(d), self.KEYS)
        self.assertEqual((d["status"], d["position"], d["wait_seconds"], d["total"], d["payment_url"],
                          d["proposal_changed"], d["proposal"]), ("queued", 1, 2, None, None, False, None))
        self.assertIn("un minuto", d["say"])
        assert_single_product(self, d)

    def test_status_recomputes_wait_on_each_call(self):
        vela, _, proposal = accepted_vela()
        vela.accept_proposal(proposal.proposal.id, FULL)
        second = accept_second_intent(vela)
        self.assertEqual(vela.get_order_status(second.order_id).position, 2)
        worker = inline_worker(vela)
        worker.processor.run_once()                       # il primo acquisto è fatto
        r = vela.get_order_status(second.order_id)
        self.assertEqual((r.position, r.wait_seconds), (1, 2))

    def test_queued_in_progress_has_no_position(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        vela.repos.jobs.claim(vela.now(), 120)
        r = vela.get_order_status(oid)
        self.assertEqual((r.status, r.position, r.wait_seconds), (OrderStatus.QUEUED, None, None))
        self.assertIn("Sto preparando il pagamento", r.say)

    def test_status_awaiting_payment_has_link_and_total_differs(self):
        vela, _, proposal = accepted_vela(hofj=FakeHofJ(total=750))
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
        r = vela.get_order_status(oid)
        d = r.to_dict()
        self.assertEqual((d["status"], d["total"], d["currency"], d["price_from_total"], d["total_differs"],
                          d["payment_url"]),
                         ("awaiting_payment", "750.00", "EUR", "700.00", True, "http://pay.test/" + oid))
        self.assertTrue(r.say.startswith("Il totale reale è 750 euro, non i 700 stimati."))
        self.assertNotIn("http", r.say)
        assert_single_product(self, d)

    def test_status_brings_the_payment_check_forward(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
        check = vela.repos.jobs.active_for_order(oid, JobKind.PAYMENT_CHECK)
        self.assertGreater(check.run_after, vela.now())
        vela.get_order_status(oid)
        self.assertLessEqual(vela.repos.jobs.active_for_order(oid, JobKind.PAYMENT_CHECK).run_after, vela.now())

    def test_status_replaced_has_proposal_and_flag(self):
        from vela.ports.hofj import ProductError
        vela, _, proposal = accepted_vela(hofj=FakeHofJ(fail_at={"create_itinerary": [ProductError("404")]}))
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        inline_worker(vela).drain()
        r = vela.get_order_status(oid)
        d = r.to_dict()
        self.assertEqual((d["status"], d["proposal_changed"]), ("replaced", True))
        self.assertNotEqual(d["proposal"]["product"]["product_id"], proposal.proposal.product_id)
        self.assertTrue(r.say.startswith("Quel viaggio non è più prenotabile"))
        self.assertNotIn("404", r.say)
        assert_single_product(self, d)

    def test_status_failed_has_reason(self):
        from vela.domain import say
        from vela.ports.hofj import ConfigError
        vela, _, proposal = accepted_vela(hofj=FakeHofJ(fail_at={"create_itinerary": [ConfigError("403")]}))
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        inline_worker(vela).drain()
        d = vela.get_order_status(oid).to_dict()
        self.assertEqual((d["status"], d["failure_reason"]), ("failed", say.failure_reason("config")))
        self.assertIn(say.failure_reason("config"), d["say"])

    def test_link_is_hidden_once_not_payable(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
        vela.orders.expire(oid)
        r = vela.get_order_status(oid)
        self.assertEqual(r.status, OrderStatus.EXPIRED)
        self.assertIsNone(r.payment_url)
        self.assertIsNone(r.to_dict()["payment_url"])
        self.assertIn("scaduto", r.say)

    def test_confirmed_keeps_total(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        worker = drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
        vela.orders.mark_paid(oid, "pi_1")
        worker.drain()
        r = vela.get_order_status(oid)
        self.assertEqual((r.status, r.total, r.payment_url, r.booking_code),
                         (OrderStatus.CONFIRMED, Decimal("700"), None, "R-000001"))

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
        self.assertIsInstance(accepted, OrderQueued)
        worker = inline_worker(vela)
        worker.drain()                                     # job d'acquisto: prezzo effettivo
        priced = vela.get_order_status(accepted.order_id)
        responses.append(priced)
        self.assertEqual(priced.status, OrderStatus.AWAITING_CONFIRMATION)
        self.assertIn("Confermi?", priced.say)
        confirmed = vela.accept_proposal(second.proposal.id)
        responses.append(confirmed)
        worker.drain()                                     # conferma: link pronto
        awaiting = vela.get_order_status(accepted.order_id)
        responses.append(awaiting)
        self.assertEqual(awaiting.payment_url, "https://vela.test/replay/checkout/" + accepted.order_id)
        # pagamento simulato: ciò che fa GET /replay/checkout/{order_id}
        order = vela.repos.orders.get(accepted.order_id)
        vela.orders.settle_payment(order.id, vela.payments.pay(order))
        worker.drain()
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
        drain_to_link(vela, inline_worker(vela), proposal.proposal.id)
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
        self.assertIn("actual price", accepted.say)
        worker = inline_worker(vela)
        worker.drain()
        self.assertIn("Do you confirm?", vela.get_order_status(accepted.order_id).say)
        drain_to_link(vela, worker, proposal.proposal.id)
        self.assertIn("waiting for payment", vela.get_order_status(accepted.order_id).say)

    def test_english_no_match(self):
        vela = make_vela([])                       # catalogo vuoto: si ferma al filtro "archived"
        iid = vela.create_intent("tennis in October, we are two").intent_id
        self.assertIn("try again later", vela.get_proposal(iid).say)
