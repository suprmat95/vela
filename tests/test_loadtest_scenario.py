"""Scenario del load test (M13a): arrivi aperti, imbuto con seme, sentinelle, frasi valide."""
import unittest

from loadtest.scenario import INTENTS, PROFILE, REASON, Funnel, arrivals, travelers
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.models import NoMatch, ProposalMade, profile_from_dict
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
        share = lambda flag: sum(1 for t in crowd if getattr(t, flag)) / len(crowd)
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


if __name__ == "__main__":
    unittest.main()
