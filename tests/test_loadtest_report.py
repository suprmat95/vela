"""Report del load test (M13a): misure pure su registro del finto, eventi e statistiche Locust."""
import json
import os
import tempfile
import unittest

from loadtest.fake_hofj.log import max_in_window
from loadtest.report import (booking_measures, cost_measures, main, percentile, quota_measures,
                             read_stats, traveler_measures)

S = 1_000_000.0


def call(t, endpoint="GET /v1/quota", status=200, origin="vela", iid=None, executed=True, counted=True):
    return {"t": t, "endpoint": endpoint, "status": status, "origin": origin, "itinerary_id": iid,
            "executed": executed, "counted": counted}


class CostTest(unittest.TestCase):
    def test_calls_per_link_and_per_paid_order(self):
        """M19: chiamate del carrello per link, chiamate di cliente, pax e booking per ordine
        prenotato; il sync e la quota non contano."""
        by_endpoint = {"POST /v1/itineraries": 10, "GET /v1/itineraries/{id}": 10,
                       "PUT /v1/itineraries/{id}/customer": 2, "PUT /v1/itineraries/{id}/pax": 2,
                       "GET /v1/itineraries/{id}/pax": 1, "POST /v1/bookings": 2,
                       "GET /v1/quota": 3, "GET /v1/products": 5}
        c = cost_measures(by_endpoint, links=8, booked=2)
        self.assertEqual((c["purchase_calls"], c["booking_calls"]), (20, 7))
        self.assertEqual((c["calls_per_link"], c["calls_per_paid_order"]), (2.5, 3.5))

    def test_no_links_no_ratio(self):
        c = cost_measures({}, links=0, booked=0)
        self.assertEqual((c["calls_per_link"], c["calls_per_paid_order"]), (None, None))


class WindowTest(unittest.TestCase):
    def test_max_in_any_sixty_seconds(self):
        self.assertEqual(max_in_window([0, 10, 59.9, 60, 61, 119.95]), 4)   # 10, 59.9, 60, 61
        self.assertEqual(max_in_window([]), 0)

    def test_percentile_nearest_rank(self):
        self.assertEqual(percentile(range(1, 101), 95), 95)
        self.assertEqual(percentile([3], 95), 3)
        self.assertIsNone(percentile([], 95))


class QuotaTest(unittest.TestCase):
    def test_counts_only_the_run_window_and_splits_origins(self):
        calls = [call(S - 30), call(S + 1), call(S + 2, status=429), call(S + 3, origin="background"),
                 call(S + 61, "POST /v1/itineraries", iid="a"), call(S + 5, counted=False, status=401),
                 call(S + 200)]
        q = quota_measures(calls, S, S + 120)
        self.assertEqual((q["calls_before_run"], q["calls_vela"], q["status_429"]), (1, 3, 1))
        self.assertEqual((q["max_in_60s_vela"], q["max_in_60s_total"]), (2, 3))
        self.assertEqual([m["vela"] for m in q["per_minute"]], [2, 1])
        self.assertEqual([m["itineraries"] for m in q["per_minute"]], [0, 1])
        self.assertEqual(q["by_endpoint"], {"GET /v1/quota": 2, "POST /v1/itineraries": 1})


class BookingTest(unittest.TestCase):
    def test_orphans_and_bookings_per_itinerary(self):
        calls = [call(S, "POST /v1/itineraries", iid="a"), call(S + 5, "PUT /v1/itineraries/{id}/customer", iid="a"),
                 call(S + 6, "POST /v1/bookings", iid="a"), call(S + 30, "POST /v1/bookings", iid="a"),
                 call(S + 1, "POST /v1/itineraries", iid="orphan"),
                 call(S + 290, "POST /v1/itineraries", iid="too-recent"),
                 call(S + 7, "POST /v1/bookings", iid="b", executed=False)]
        b = booking_measures(calls, S + 300)
        self.assertEqual((b["itineraries"], b["orphan_itineraries"]), (3, 1))
        self.assertEqual((b["booking_posts_max_per_itinerary"], b["itineraries_booked_more_than_once"]), (2, 1))


class TravelerTest(unittest.TestCase):
    def test_links_waits_sentinels_and_queue_age(self):
        travelers = [
            {"index": 0, "t_accept": 10, "wait_seconds": 50, "t_link": 70, "t_paid": 71,
             "t_confirmed": 100, "final": "confirmed", "role": "marco", "proposal_ms": 12},
            {"index": 1, "t_accept": 20, "wait_seconds": 30, "t_link": 65, "final": "link_unpaid"},
            {"index": 2, "t_accept": 30, "wait_seconds": 10, "final": "open_queued"},
            {"index": 3, "t_accept": 40, "final": "replaced", "t_end": 90},
            {"index": 4, "final": "browsed", "role": "anna", "proposal_ms": 40},
        ]
        t = traveler_measures(travelers, 180)
        self.assertEqual((t["accepted"], t["links"], t["paid"], t["confirmed"]), (4, 2, 1, 1))
        self.assertEqual(t["links_per_minute"], [0, 2, 0])
        self.assertEqual(t["wait_gap_p95"], 15)            # gap: 10 e 15
        self.assertEqual(t["paid_to_confirmed_p95"], 29)
        self.assertEqual(t["still_queued_at_end"], 1)
        self.assertEqual([a["waiting"] for a in t["queue_age"]], [4, 1, 1])
        self.assertEqual(t["queue_age"][2]["oldest_seconds"], 150)
        self.assertTrue(t["marco"]["confirmed_by_minute_7"])
        self.assertEqual(t["marco"]["paid_to_confirmed"], 29)
        self.assertFalse(t["anna"]["confirmed_by_minute_7"])


class EndToEndTest(unittest.TestCase):
    def test_files_to_markdown_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {name: os.path.join(tmp, name) for name in ("calls.jsonl", "ev.jsonl", "s_stats.csv")}
            with open(paths["calls.jsonl"], "w") as fh:
                for c in (call(S + 1), call(S + 2, "POST /v1/itineraries", iid="a")):
                    fh.write(json.dumps(c) + "\n")
            with open(paths["ev.jsonl"], "w") as fh:
                fh.write(json.dumps({"type": "run", "epoch_start": S, "travelers": 1,
                                     "arrival_minutes": 1, "tail_minutes": 1, "seed": 1}) + "\n")
                fh.write(json.dumps({"type": "traveler", "index": 0, "role": "marco", "final": "browsed"}) + "\n")
            with open(paths["s_stats.csv"], "w") as fh:
                fh.write("Type,Name,Request Count,Failure Count,50%,95%,99%\n"
                         "POST,create_intent,10,0,20,45,60\n,Aggregated,10,0,20,45,60\n")
            self.assertEqual(read_stats(paths["s_stats.csv"])["create_intent"]["p95"], 45.0)
            out = os.path.join(tmp, "report")
            with open(os.devnull, "w") as devnull:
                import contextlib
                with contextlib.redirect_stdout(devnull):
                    main(["--calls", paths["calls.jsonl"], "--events", paths["ev.jsonl"],
                          "--stats", paths["s_stats.csv"], "--label", "prova", "--out", out])
            with open(out + ".md") as fh:
                text = fh.read()
            with open(out + ".json") as fh:
                data = json.load(fh)
        self.assertIn("## prova", text)
        self.assertIn("`create_intent` | 10 | 0 | 20 | 45 | 60", text)
        self.assertIn("Marco", text)
        self.assertEqual(data["quota"]["calls_vela"], 2)
        self.assertEqual(data["cost"]["purchase_calls"], 1)
        self.assertIn("Chiamate per link", text)


if __name__ == "__main__":
    unittest.main()
