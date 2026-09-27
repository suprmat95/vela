"""Cache del prezzo con fanout (RF-84): hit, leader, agganciati, conferma senza carrello, ripiego.

Repository in memoria, HofJ finto, worker in linea; l'orologio avanza di un minuto per giro così
il token bucket (B = 8, 5 chiamate per acquisto) lascia passare un carrello dopo l'altro.
"""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, inline_worker, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import (Area, Criteria, Intent, JobKind, OrderQueued, OrderStatus,
                                OrderStatusResponse, Participant, Period, Proposal, QuoteKey,
                                QuoteStatus, TravelerProfile)
from vela.domain.usecases import Vela
from vela.ports.hofj import ConfigError, ProductError

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


class ConfirmWithoutCartTest(unittest.TestCase):
    def hit(self, w):
        w.accept(w.traveler())
        w.settle()
        pid = w.traveler()
        w.accept(pid)
        return pid

    def test_confirm_without_cart_goes_to_the_link_when_the_price_matches(self):
        w = World()
        pid = self.hit(w)
        w.accept(pid)                                        # il sì
        o = w.order(pid)
        self.assertEqual((o.status, o.confirmed_total), (OrderStatus.QUEUED, Decimal("700")))
        self.assertEqual(w.job(pid).step, 0)                 # il carrello non c'è ancora
        w.settle()
        o = w.order(pid)
        self.assertEqual((o.status, o.total), (OrderStatus.AWAITING_PAYMENT, Decimal("700")))
        self.assertIsNotNone(o.itinerary_id)
        self.assertEqual(w.carts(), 2)

    def test_confirm_without_cart_asks_again_when_price_changed(self):
        w = World()
        pid = self.hit(w)
        w.accept(pid)
        w.hofj.total = Decimal("768")
        w.settle()
        o = w.order(pid)
        self.assertEqual((o.status, o.total, o.confirmed_total),
                         (OrderStatus.AWAITING_CONFIRMATION, Decimal("768"), Decimal("700")))
        self.assertEqual(w.payments.links, [])
        status = w.vela.get_order_status(o.id)
        self.assertIn("768", status.say)
        self.assertIn("700", status.say)
        self.assertEqual(w.repos.quotes.get(KEY).total, Decimal("768"))
        carts = w.carts()
        w.accept(pid)                                        # il secondo sì
        self.assertEqual(w.job(pid).step, 4)                 # dal link: il carrello c'è
        w.settle()
        self.assertEqual(w.order(pid).status, OrderStatus.AWAITING_PAYMENT)
        self.assertTrue(w.payments.links[-1].url.endswith(o.id))
        self.assertEqual(w.carts(), carts)

    def test_leader_confirm_still_starts_from_the_link(self):
        w = World()
        pid = w.traveler()
        w.accept(pid)
        w.settle()
        w.accept(pid)
        self.assertEqual(w.job(pid).step, 4)
        self.assertIsNone(w.order(pid).confirmed_total)


class FallbackTest(unittest.TestCase):
    def three(self, **hofj):
        w = World(hofj=FakeHofJ(**hofj)) if hofj else World()
        pids = [w.traveler() for _ in range(3)]
        for pid in pids:
            w.accept(pid)
        return w, pids

    def assert_released(self, w, followers):
        """Riga sparita, agganciati sganciati; dopo qualche giro ognuno ha il suo carrello."""
        self.assertIsNone(w.repos.quotes.get(KEY))
        for pid in followers:
            self.assertFalse(w.order(pid).follows_quote)
        w.settle()
        for pid in followers:
            o = w.order(pid)
            self.assertEqual(o.status, OrderStatus.AWAITING_CONFIRMATION, pid)
            self.assertIsNotNone(o.itinerary_id, pid)

    def test_failed_leader_hands_followers_their_own_jobs(self):
        w, pids = self.three(fail_at={"create_itinerary": [ConfigError("401")]})
        w.worker.drain()
        self.assertEqual(w.order(pids[0]).status, OrderStatus.FAILED)
        self.assert_released(w, pids[1:])

    def test_unbookable_leader_hands_followers_their_own_jobs(self):
        w, pids = self.three(fail_at={"create_itinerary": [ProductError("502")]})
        w.worker.drain()
        self.assertNotEqual(w.order(pids[0]).status, OrderStatus.QUEUED)   # replaced o failed
        self.assert_released(w, pids[1:])

    def test_cancelled_leader_hands_followers_their_own_jobs_in_their_place(self):
        w, pids = self.three()
        w.vela._cancel_unpaid_order(pids[0])   # RF-49, senza passare dal chooser di reject_proposal
        self.assertEqual(w.order(pids[0]).status, OrderStatus.CANCELLED)
        for pid in pids[1:]:                   # prima di ogni drain: il job c'è, al suo posto
            o = w.order(pid)
            job = w.repos.jobs.active_for_order(o.id, JobKind.PURCHASE)
            self.assertEqual(job.enqueued_at, o.enqueued_at)
        self.assert_released(w, pids[1:])

    def test_follower_unsticks_when_leader_left_without_release(self):
        w, pids = self.three()
        leader = w.order(pids[0])
        w.repos.orders.save(replace(leader, status=OrderStatus.FAILED))   # uscita senza rilascio
        w.vela.get_order_status(w.order(pids[1]).id)
        self.assert_released(w, pids[1:])

    def test_release_by_a_follower_changes_nothing(self):
        from vela.domain.quotes import release_quote
        w, pids = self.three()
        self.assertEqual(release_quote(w.repos, w.order(pids[1]), NOW, lambda: "x"), 0)
        self.assertEqual(w.repos.quotes.get(KEY).status, QuoteStatus.PENDING)
        self.assertTrue(w.order(pids[2]).follows_quote)

    def test_cancelled_follower_is_left_out_of_the_fanout(self):
        w, pids = self.three()
        w.vela._cancel_unpaid_order(pids[1])
        w.settle()
        self.assertEqual(w.order(pids[1]).status, OrderStatus.CANCELLED)
        self.assertEqual(w.order(pids[2]).status, OrderStatus.AWAITING_CONFIRMATION)


class SettingsTest(unittest.TestCase):
    def test_default_ttl_is_fifteen_minutes(self):
        self.assertEqual(Settings().price_quote_ttl_seconds, 900)
