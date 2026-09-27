"""Cache del prezzo con fanout (RF-84): hit, leader, agganciati, conferma senza carrello, ripiego.

Repository in memoria, HofJ finto, worker in linea; l'orologio avanza di un minuto per giro così
il token bucket (B = 8, 5 chiamate per acquisto) lascia passare un carrello dopo l'altro.
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, inline_worker, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import (Area, Criteria, Intent, JobKind, OrderQueued, OrderStatus,
                                OrderStatusResponse, Participant, Period, Proposal, QuoteKey,
                                QuoteStatus, TravelerProfile)
from vela.domain.usecases import Vela

CRITERIA = Criteria("padel", Area("country", "Spagna", "ES"),
                    Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39 333", 2, (Participant("Bo", "Bi"),))
START = date(2026, 10, 1)
KEY = QuoteKey("1", START, 2, 1, "EUR")


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


class World:
    def __init__(self, ttl=900, total=None, hofj=None):
        self.clock = Clock()
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many([make_product(1, price=350, destination="Valencia"),
                                         make_product(2, price=390, destination="Lanzarote")])
        self.hofj = hofj or FakeHofJ(total=total)
        self.payments = StubPayments()
        self.vela = Vela(self.repos, self.hofj, self.payments, DEFAULT_TRAVELER, now=self.clock,
                         price_quote_ttl_seconds=ttl)
        self.worker = inline_worker(self.vela)
        self.worker.processor.refresh_quota()          # il boot
        self.n = 0

    def traveler(self, product_id="1", start=START, pax=2):
        """Un intento e la sua proposta; restituisce l'id della proposta."""
        self.n += 1
        iid, pid = "i%d" % self.n, "p%d" % self.n
        self.repos.intents.add(Intent(iid, "padel", CRITERIA, PROFILE, NOW))
        self.repos.proposals.add(Proposal(pid, iid, product_id, start, start + timedelta(days=3), pax,
                                          Decimal("350"), "EUR", "Motivo.", NOW))
        return pid

    def accept(self, pid):
        return self.vela.accept_proposal(pid)

    def order(self, pid):
        return self.repos.orders.get_by_proposal(pid)

    def job(self, pid):
        return self.repos.jobs.active_for_order(self.order(pid).id, JobKind.PURCHASE)

    def carts(self):
        return sum(1 for c in self.hofj.calls if c[0] == "create_itinerary")

    def settle(self, rounds=6):
        for _ in range(rounds):
            self.worker.drain()
            self.clock.advance(60)


class LeaderAndFollowersTest(unittest.TestCase):
    def test_leader_then_followers_get_the_price_with_one_cart(self):
        w = World()
        pids = [w.traveler() for _ in range(3)]
        results = [w.accept(pid) for pid in pids]
        self.assertTrue(all(isinstance(r, OrderQueued) for r in results))
        self.assertIsNotNone(w.job(pids[0]))
        self.assertFalse(w.order(pids[0]).follows_quote)
        for pid in pids[1:]:
            self.assertIsNone(w.job(pid))
            self.assertTrue(w.order(pid).follows_quote)
        self.assertEqual(w.repos.quotes.get(KEY).status, QuoteStatus.PENDING)
        w.settle()
        for pid in pids:
            o = w.order(pid)
            self.assertEqual((o.status, o.total, o.follows_quote),
                             (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), False))
        self.assertEqual(w.carts(), 1)
        self.assertIsNotNone(w.order(pids[0]).itinerary_id)
        self.assertIsNone(w.order(pids[1]).itinerary_id)

    def test_hit_answers_at_once_without_job_or_calls(self):
        w = World()
        w.accept(w.traveler())
        w.settle()
        calls = len(w.hofj.calls)
        pid = w.traveler()
        result = w.accept(pid)
        self.assertIsInstance(result, OrderStatusResponse)
        self.assertEqual((result.status, result.total), (OrderStatus.AWAITING_CONFIRMATION, Decimal("700")))
        self.assertIn("700", result.say)
        self.assertIsNone(w.job(pid))
        self.assertEqual(len(w.hofj.calls), calls)

    def test_expired_quote_makes_a_new_leader(self):
        w = World()
        w.accept(w.traveler())
        w.settle()
        w.clock.advance(901)
        pid = w.traveler()
        self.assertIsInstance(w.accept(pid), OrderQueued)
        self.assertIsNotNone(w.job(pid))
        self.assertEqual(w.repos.quotes.get(KEY).leader_order_id, w.order(pid).id)

    def test_other_key_does_not_share(self):
        w = World()
        w.accept(w.traveler())
        other = w.traveler(start=START + timedelta(days=7))
        w.accept(other)
        self.assertIsNotNone(w.job(other))
        self.assertFalse(w.order(other).follows_quote)

    def test_unbookable_product_is_not_a_hit(self):
        w = World()
        w.accept(w.traveler())
        w.settle()
        w.repos.products.set_bookable("1", False, NOW)
        pid = w.traveler()
        self.assertIsInstance(w.accept(pid), OrderQueued)
        self.assertIsNotNone(w.job(pid))

    def test_follower_position_is_the_leaders(self):
        w = World()
        first, second = w.traveler(), w.traveler()
        leader = w.accept(first)
        follower = w.accept(second)
        self.assertEqual(follower.position, leader.position)
        self.assertIsNotNone(follower.position)

    def test_ttl_zero_is_todays_flow(self):
        w = World(ttl=0)
        pids = [w.traveler() for _ in range(2)]
        for pid in pids:
            w.accept(pid)
            self.assertIsNotNone(w.job(pid))
            self.assertFalse(w.order(pid).follows_quote)
        w.settle()
        self.assertIsNone(w.repos.quotes.get(KEY))
        self.assertEqual(w.carts(), 2)

    def test_lost_claim_after_publish_takes_the_price(self):
        """Il `claim` perde perché nel frattempo un leader ha pubblicato: niente attesa inutile."""
        w = World()
        w.accept(w.traveler())
        claim = w.repos.quotes.claim

        def publish_then_lose(key, order_id, now, fresh_after):
            w.repos.quotes.publish(key, "leader", Decimal("700"), now)
            return False

        w.repos.quotes.claim = publish_then_lose
        pid = w.traveler()
        w.accept(pid)
        w.repos.quotes.claim = claim
        o = w.order(pid)
        self.assertEqual((o.status, o.total, o.follows_quote),
                         (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), False))
        self.assertIsNone(w.job(pid))

    def test_leader_publishes_before_leaving_queued(self):
        """Al momento del `publish` il leader è ancora `queued`: un agganciato che controlla il
        leader in quell'istante non lo vede uscito."""
        w = World()
        leader_pid = w.traveler()
        w.accept(leader_pid)
        w.accept(w.traveler())
        seen = []
        publish = w.repos.quotes.publish

        def spy(key, leader_order_id, total, now):
            seen.append(w.repos.orders.get(leader_order_id).status)
            return publish(key, leader_order_id, total, now)

        w.repos.quotes.publish = spy
        w.settle()
        self.assertEqual(seen, [OrderStatus.QUEUED])


class SettingsTest(unittest.TestCase):
    def test_default_ttl_is_fifteen_minutes(self):
        self.assertEqual(Settings().price_quote_ttl_seconds, 900)
