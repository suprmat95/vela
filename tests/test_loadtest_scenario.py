"""Scenario del load test (M13a): arrivi aperti, imbuto con seme, sentinelle, frasi valide."""
import unittest
from datetime import date
from decimal import Decimal

from support import NOW, FakeHofJ, inline_worker
from loadtest.scenario import INTENTS, PROFILE, REASON, Funnel, arrivals, travelers
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.models import Criteria, NoMatch, Proposal, ProposalMade, profile_from_dict
from vela.domain.refine import refine
from vela.domain.usecases import Vela


class ScenarioTest(unittest.TestCase):
    def test_same_seed_same_scenario(self):
        self.assertEqual(travelers(500, seed=4), travelers(500, seed=4))
        self.assertNotEqual(travelers(500, seed=4), travelers(500, seed=5))

    def test_arrivals_spread_over_the_window(self):
        import random
        times = arrivals(10_000, 10, random.Random(1))
        self.assertEqual(len(times), 10_000)
        self.assertTrue(0 <= times[0] and times[-1] < 600)
        per_minute = [sum(1 for t in times if m * 60 <= t < (m + 1) * 60) for m in range(10)]
        for count in per_minute:
            self.assertAlmostEqual(count, 1000, delta=120)

    def test_funnel_fractions(self):
        crowd = [t for t in travelers(20_000, seed=2) if t.role is None]
        def share(flag):
            return sum(1 for t in crowd if getattr(t, flag)) / len(crowd)
        self.assertAlmostEqual(share("rejects"), 0.30, delta=0.02)
        self.assertAlmostEqual(share("accepts"), 0.20, delta=0.02)
        self.assertAlmostEqual(share("pays"), 0.60, delta=0.02)
        self.assertEqual({t.poll for t in crowd}, {Funnel().poll})

    def test_sentinels(self):
        roles = {t.role: t for t in travelers(100) if t.role}
        marco, anna = roles["marco"], roles["anna"]
        self.assertEqual((marco.arrival, marco.accept_at, marco.accepts, marco.pays), (55.0, 60.0, True, True))
        self.assertEqual((anna.arrival, anna.rejects, anna.accepts), (360.0, True, True))
        self.assertEqual(len(travelers(100)), 102)
        self.assertEqual(len(travelers(100, sentinels=False)), 100)

    def test_sentinels_outside_a_short_window_are_left_out(self):
        self.assertEqual([t.role for t in travelers(10, minutes=0.5) if t.role], ["anna"])

    def test_anna_arrives_at_sixty_percent_of_the_window(self):
        def anna(m):
            return next(t for t in travelers(10, minutes=m) if t.role == "anna").arrival
        self.assertEqual((anna(10), anna(5)), (360.0, 180.0))


class IntentsTest(unittest.TestCase):
    """Le frasi devono dare una proposta e, dopo "troppo caro", un'altra: altrimenti l'imbuto
    del load test si fermerebbe prima dell'accettazione."""

    def test_every_intent_reaches_a_second_proposal(self):
        repos = MemoryRepositories()
        hofj = ReplayHofJ()
        repos.products.upsert_many(hofj.load_catalog())
        vela = Vela(repos, hofj, FakePayments(), DEFAULT_TRAVELER)
        for text, sport in INTENTS:
            with self.subTest(text):
                created = vela.create_intent(text, profile_from_dict(PROFILE))
                first = vela.get_proposal(created.intent_id)
                self.assertIsInstance(first, ProposalMade)
                self.assertEqual(repos.products.get(first.product.product_id).sport, sport)
                second = vela.reject_proposal(first.proposal.id, REASON)
                self.assertNotIsInstance(second, NoMatch)
                self.assertIsInstance(second, ProposalMade)


class RejectionKindTest(unittest.TestCase):
    """M21-F: il "troppo caro" del 30% del load test resta un rifiuto `price`, mai una domanda, e
    il viaggio con il rifiuto spende su HofJ quanto quello senza (il rifiuto non chiama HofJ)."""

    def journey(self, text, rejects):
        repos = MemoryRepositories()
        repos.products.upsert_many(ReplayHofJ().load_catalog())
        hofj = FakeHofJ()
        vela = Vela(repos, hofj, FakePayments(), DEFAULT_TRAVELER)
        worker = inline_worker(vela)
        worker.processor.refresh_quota()
        created = vela.create_intent(text, profile_from_dict(PROFILE))
        proposal = vela.get_proposal(created.intent_id)
        if rejects:
            before = len(hofj.calls)
            proposal = vela.reject_proposal(proposal.proposal.id, REASON)
            self.assertIsInstance(proposal, ProposalMade)
            self.assertEqual(len(hofj.calls), before)   # il rifiuto non chiama HofJ
            kinds = {r.kind for r in repos.rejections.list_for_intent(created.intent_id)}
            self.assertEqual(kinds, {"price"})
        vela.accept_proposal(proposal.proposal.id)
        worker.drain()
        return [c[0] for c in hofj.calls if c[0] != "get_quota"]

    def test_too_expensive_is_price_and_costs_no_hofj_call(self):
        proposal = Proposal("p", "i", "1", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("350"),
                            "EUR", "r", NOW)
        r = refine(Criteria("padel", pax=2, rooms=1), REASON, proposal, None, NOW.date())
        self.assertEqual((r.kind, r.ask, r.keep_product), ("price", None, False))
        for text, _ in INTENTS:
            with self.subTest(text):
                calls = self.journey(text, rejects=True)
                self.assertEqual(len(calls), 5)   # i cinque passi fino al prezzo effettivo
                self.assertEqual(calls, self.journey(text, rejects=False))


if __name__ == "__main__":
    unittest.main()
