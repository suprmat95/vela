import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import m19_probe  # noqa: E402


def money(amount):
    return {"amount": amount, "currency": "EUR"}


def itinerary(open_amount, total=None):
    total = open_amount if total is None else total
    return {"data": {"totalPrice": money(total + ".00"),
                     "checkout": {"openAmount": money(open_amount), "total": money(total),
                                  "originalTotal": money(open_amount), "status": "BookingInitiated"}},
            "meta": {"now": 1}}


class FakeResponse(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeHofJ:
    """Risponde per (metodo, path) nell'ordine delle chiamate; registra metodo, url e corpo."""

    def __init__(self, before="1156", after="1156", create_status=200, pax_status=200):
        self.before, self.after = before, after
        self.create_status, self.pax_status = create_status, pax_status
        self.calls, self.reads = [], 0

    def __call__(self, req, timeout=None, context=None):
        body = json.loads(req.data) if req.data else None
        self.calls.append((req.get_method(), req.full_url, body))
        method, path = req.get_method(), req.full_url.split("?")[0].split(".com")[-1]
        if method == "POST" and path == "/v1/itineraries":
            if self.create_status != 200:
                return self._error(self.create_status)
            return FakeResponse(200, {"data": {"itineraryId": "itn1"}, "meta": {"now": 1}})
        if method == "GET":
            self.reads += 1
            return FakeResponse(200, itinerary(self.before if self.reads == 1 else self.after))
        if path.endswith("/pax") and self.pax_status != 200:
            return self._error(self.pax_status)
        return FakeResponse(200, {"data": {"now": 1}, "meta": {}})

    def _error(self, status):
        raise urllib.error.HTTPError("u", status, "err", {}, io.BytesIO(
            json.dumps({"status": status, "title": "err"}).encode()))


class ProbeTest(unittest.TestCase):
    def run_probe(self, fake, *extra):
        out = tempfile.mkdtemp()
        env = {"HOFJ_API_KEY": "secret-key"}
        stdout = io.StringIO()
        code = m19_probe.main(["--out", out, "--gap", "0", *extra], env=env, opener=fake,
                              sleep=lambda s: None, stdout=stdout)
        findings = None
        path = os.path.join(out, "findings.json")
        if os.path.exists(path):
            with open(path) as f:
                findings = json.load(f)
        return code, findings, stdout.getvalue()

    def test_exactly_the_five_declared_calls_in_order(self):
        fake = FakeHofJ()
        code, findings, out = self.run_probe(fake)
        self.assertEqual(code, 0)
        self.assertEqual([(m, u.split("?")[0].split(".com")[-1]) for m, u, _ in fake.calls], [
            ("POST", "/v1/itineraries"),
            ("GET", "/v1/itineraries/itn1"),
            ("PUT", "/v1/itineraries/itn1/customer"),
            ("PUT", "/v1/itineraries/itn1/pax"),
            ("GET", "/v1/itineraries/itn1"),
        ])
        self.assertNotIn("secret-key", out)
        self.assertEqual(len(findings["calls"]), 5)

    def test_never_touches_payment_booking_or_quota(self):
        fake = FakeHofJ()
        self.run_probe(fake)
        for _, url, _ in fake.calls:
            for forbidden in ("/v1/bookings", "/payment", "/v1/quota"):
                self.assertNotIn(forbidden, url)

    def test_create_body_and_pax_keep_the_known_ref_ids(self):
        fake = FakeHofJ()
        self.run_probe(fake)
        create = fake.calls[0][2]
        self.assertEqual(create, {"productId": 124, "startDate": "2026-10-08", "adults": 2,
                                  "rooms": 1, "currency": "EUR"})
        self.assertIn("brand=staging.weebora.com", fake.calls[0][1])
        self.assertIn("locale=en", fake.calls[0][1])
        self.assertEqual([p["refId"] for p in fake.calls[3][2]], ["pax-1", "pax-2"])
        self.assertEqual(set(fake.calls[2][2]["address"]),
                         {"street1", "postalCode", "city", "region", "countryCode"})

    def test_same_amounts_before_and_after(self):
        code, findings, _ = self.run_probe(FakeHofJ("1156", "1156"))
        self.assertEqual(findings["before"]["openAmount"], "1156")
        self.assertEqual(findings["after"]["openAmount"], "1156")
        self.assertEqual(findings["changed"], [])

    def test_reports_every_amount_that_changes(self):
        code, findings, _ = self.run_probe(FakeHofJ("1156", "1100"))
        self.assertIn("openAmount", findings["changed"])
        self.assertIn("totalPrice", findings["changed"])

    def test_stops_after_a_failed_create(self):
        fake = FakeHofJ(create_status=502)
        code, findings, _ = self.run_probe(fake)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(fake.calls), 1)

    def test_rejected_pax_still_rereads_within_five_calls(self):
        fake = FakeHofJ(pax_status=400)
        code, findings, _ = self.run_probe(fake)
        self.assertEqual(len(fake.calls), 5)
        self.assertEqual(findings["calls"][3]["status"], 400)

    def test_stops_on_quota_or_auth_errors(self):
        for status in (401, 403, 429, 500):
            fake = FakeHofJ(pax_status=status)
            code, _, _ = self.run_probe(fake)
            self.assertNotEqual(code, 0)
            self.assertEqual(len(fake.calls), 4, status)

    def test_dry_run_calls_nothing_and_prints_the_plan(self):
        fake = FakeHofJ()
        out = tempfile.mkdtemp()
        stdout = io.StringIO()
        code = m19_probe.main(["--out", out, "--dry-run"], env={}, opener=fake,
                              sleep=lambda s: None, stdout=stdout)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])
        plan = [line for line in stdout.getvalue().splitlines() if line[:2].strip().isdigit()]
        self.assertEqual(len(plan), 5)


if __name__ == "__main__":
    unittest.main()
