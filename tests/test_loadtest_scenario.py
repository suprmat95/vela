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
        def share(flag):
            return sum(1 for t in crowd if getattr(t, flag)) / len(crowd)
        self.assertAlmostEqual(share("rejects"), 0.30, delta=0.02)
        self.assertAlmostEqual(share("accepts"), 0.20, delta=0.02)
        self.assertAlmostEqual(share("pays"), 0.60, delta=0.02)
        self.assertEqual({t.poll for t in crowd}, {Funnel().poll})

    def test_pay_share_changes_only_who_pays(self):
        """M19: `--pay` cambia chi paga, non arrivi, frasi né chi accetta: giri confrontabili."""
        base = travelers(20_000, seed=2)
        few = travelers(20_000, seed=2, funnel=Funnel(pay=0.02))
        strip = lambda ts: [(t.arrival, t.text, t.rejects, t.accepts, t.role) for t in ts]   # noqa: E731
        self.assertEqual(strip(few), strip(base))
        crowd = [t for t in few if t.role is None]
        self.assertAlmostEqual(sum(t.pays for t in crowd) / len(crowd), 0.02, delta=0.005)
        self.assertTrue(all(t.pays for t in few if t.role))                  # le sentinelle pagano

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


if __name__ == "__main__":
    unittest.main()
