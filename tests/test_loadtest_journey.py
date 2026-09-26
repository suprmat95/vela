"""Percorso del viaggiatore (M13a) contro una REST finta a copione, con orologio finto."""
import unittest

from loadtest.journey import run_journey
from loadtest.scenario import Traveler

TEXT = "padel a Lanzarote a novembre, siamo in due"


class Script:
    """Risposte in ordine per nome di richiesta; l'orologio avanza con `sleep` e 0,1 s a chiamata."""

    def __init__(self, **responses):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.t = 0.0
        self.calls = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s

    def __call__(self, method, path, name, json=None):
        self.calls.append((name, path, json))
        self.t += 0.1
        seq = self.responses[name]
        return seq.pop(0) if len(seq) > 1 else seq[0]


INTENT = (201, {"outcome": "intent_created", "intent_id": "i1"})
PROPOSAL = (200, {"outcome": "proposal", "proposal_id": "p1"})
SECOND = (200, {"outcome": "proposal", "proposal_id": "p2"})
QUEUED = (202, {"outcome": "order_queued", "order_id": "o1", "status": "queued", "position": 40,
                "wait_seconds": 700})


def status(s, **extra):
    return 200, dict({"outcome": "order_status", "status": s}, **extra)


class JourneyTest(unittest.TestCase):
    def test_browser_stops_after_the_proposal(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", False, False, False), s, s.clock, s.sleep, 900, {})
        self.assertEqual(rec["final"], "browsed")
        self.assertEqual(rec["t_end"], round(s.t, 3))
        self.assertEqual(s.calls[0][2]["sport"], "padel")
        self.assertIn("proposal_ms", rec)

    def test_reject_then_accept_pay_and_confirm(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL], reject_proposal=[SECOND],
                   accept_proposal=[QUEUED],
                   get_order_status=[status("queued"),
                                     status("awaiting_payment", payment_url="http://vela:8000/replay/checkout/o1"),
                                     status("paid_pending_booking"), status("confirmed")],
                   replay_checkout=[(200, {"status": "paid_pending_booking"})])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", True, True, True, poll=(30, 30)),
                          s, s.clock, s.sleep, 900, {})
        self.assertEqual(rec["final"], "confirmed")
        self.assertEqual([c[0] for c in s.calls if c[0] != "get_order_status"],
                         ["create_intent", "get_proposal", "reject_proposal", "accept_proposal",
                          "replay_checkout"])
        self.assertIn("/v1/proposals/p2/accept", [c[1] for c in s.calls])
        self.assertIn("/replay/checkout/o1", [c[1] for c in s.calls])
        self.assertEqual((rec["position"], rec["wait_seconds"]), (40, 700))
        self.assertLess(rec["t_accept"], rec["t_link"])
        self.assertLessEqual(rec["t_link"], rec["t_paid"])
        self.assertLess(rec["t_paid"], rec["t_confirmed"])

    def test_non_payer_leaves_at_the_link(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL], accept_proposal=[QUEUED],
                   get_order_status=[status("awaiting_payment", payment_url="http://x/replay/checkout/o1")])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", False, True, False), s, s.clock, s.sleep, 900, {})
        self.assertEqual(rec["final"], "link_unpaid")
        self.assertNotIn("replay_checkout", [c[0] for c in s.calls])

    def test_marco_waits_to_accept_at_sixty_seconds(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL], accept_proposal=[QUEUED],
                   get_order_status=[status("queued")])
        s.t = 55.0
        rec = run_journey(Traveler(1, 55, TEXT, "padel", False, True, True, role="marco",
                                   accept_at=60.0, poll=(5, 5)), s, s.clock, s.sleep, 120, {})
        self.assertAlmostEqual(rec["t_accept"], 60.1, places=3)
        self.assertEqual(rec["final"], "open_queued")
        self.assertLessEqual(s.t, 120.1)

    def test_still_queued_at_the_deadline_is_open(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL], accept_proposal=[QUEUED],
                   get_order_status=[status("queued")])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", False, True, True), s, s.clock, s.sleep, 300, {})
        self.assertEqual(rec["final"], "open_queued")

    def test_no_match_after_reject_ends_the_journey(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL],
                   reject_proposal=[(200, {"outcome": "no_match"})])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", True, True, True), s, s.clock, s.sleep, 900, {})
        self.assertEqual(rec["final"], "no_match_after_reject")

    def test_terminal_failure_is_reported(self):
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL], accept_proposal=[QUEUED],
                   get_order_status=[status("replaced")])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", False, True, True), s, s.clock, s.sleep, 900, {})
        self.assertEqual(rec["final"], "replaced")


if __name__ == "__main__":
    unittest.main()
