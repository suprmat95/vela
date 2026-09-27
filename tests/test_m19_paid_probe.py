import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import m19_paid_probe  # noqa: E402

STAGING = "https://staging.api.hofj.com"


def itinerary(amount="1156"):
    money = {"amount": amount, "currency": "EUR"}
    return {"data": {"totalPrice": {"amount": amount + ".00", "currency": "EUR"},
                     "checkout": {"openAmount": money, "total": money, "originalTotal": money,
                                  "status": "BookingInitiated"}}, "meta": {"now": 1}}


class FakeResponse(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Fake:
    """HofJ e Stripe insieme: registra (servizio, metodo, path, corpo, header)."""

    def __init__(self, fail=None, intent_status="succeeded"):
        self.fail = fail or {}          # tag → status HTTP
        self.intent_status = intent_status
        self.calls = []

    def __call__(self, req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        method = req.get_method()
        if url.netloc == "api.stripe.com":
            body = dict(urllib.parse.parse_qsl(req.data.decode()))
            self.calls.append(("stripe", method, url.path, body, dict(req.header_items())))
            if "intent" in self.fail:
                return self._error(self.fail["intent"])
            return FakeResponse(200, {"id": "pi_test_1", "status": self.intent_status,
                                      "amount": int(body["amount"]), "livemode": False})
        body = json.loads(req.data) if req.data else None
        self.calls.append(("hofj", method, url.path, body, dict(req.header_items())))
        tag = {("POST", "/v1/itineraries"): "create", ("POST", "/v1/bookings"): "booking"}.get(
            (method, url.path)) or ("customer" if url.path.endswith("/customer") else
                                    "pax" if url.path.endswith("/pax") else "get")
        if tag in self.fail:
            return self._error(self.fail[tag])
        if tag == "create":
            return FakeResponse(200, {"data": {"itineraryId": "itn1"}, "meta": {"now": 1}})
        if tag == "get":
            return FakeResponse(200, itinerary())
        if tag == "booking":
            return FakeResponse(200, {"data": "itn1", "meta": {"now": 1}})
        return FakeResponse(200, {"data": {"now": 1}, "meta": {}})

    def _error(self, status):
        raise urllib.error.HTTPError("u", status, "err", {}, io.BytesIO(
            json.dumps({"status": status, "title": "err"}).encode()))

    def plan(self):
        return [(s, m, p.replace("/itn1", "/{id}")) for s, m, p, _, _ in self.calls]


ENV = {"HOFJ_API_KEY": "hofj-secret", "STRIPE_SECRET_KEY": "rk_test_secret", "HOFJ_BASE_URL": STAGING}


class PaidProbeTest(unittest.TestCase):
    def run_probe(self, fake, env=ENV, *extra):
        out = tempfile.mkdtemp()
        stdout = io.StringIO()
        code = m19_paid_probe.main(["--out", out, "--gap", "0", *extra], env=env, opener=fake,
                                   sleep=lambda s: None, stdout=stdout)
        path = os.path.join(out, "findings.json")
        findings = None
        if os.path.exists(path):
            with open(path) as f:
                findings = json.load(f)
        return code, findings, stdout.getvalue()

    def test_the_declared_seven_calls_in_order(self):
        fake = Fake()
        code, findings, out = self.run_probe(fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.plan(), [
            ("hofj", "POST", "/v1/itineraries"),
            ("hofj", "GET", "/v1/itineraries/{id}"),
            ("stripe", "POST", "/v1/payment_intents"),
            ("hofj", "PUT", "/v1/itineraries/{id}/customer"),
            ("hofj", "PUT", "/v1/itineraries/{id}/pax"),
            ("hofj", "GET", "/v1/itineraries/{id}"),
            ("hofj", "POST", "/v1/bookings"),
        ])
        for secret in ("hofj-secret", "rk_test_secret"):
            self.assertNotIn(secret, out)
            self.assertNotIn(secret, json.dumps(findings))
        self.assertEqual(findings["booking"], "itn1")
        self.assertEqual(findings["changed"], [])

    def test_payment_intent_mirrors_the_vela_link(self):
        fake = Fake()
        self.run_probe(fake)
        _, _, _, body, headers = fake.calls[2]
        self.assertEqual(body["amount"], "115600")          # openAmount in centesimi
        self.assertEqual(body["currency"], "eur")
        self.assertEqual(body["confirm"], "true")
        self.assertEqual(body["payment_method"], "pm_card_visa")
        self.assertEqual(body["payment_method_types[]"], "card")
        self.assertEqual(body["metadata[checkoutRefId]"], "itn1")
        self.assertEqual(body["metadata[itinerary_id]"], "itn1")
        self.assertEqual(headers["Idempotency-key"], "vela-m19-paid-probe-itn1")

    def test_booking_forwards_the_payment_intent(self):
        fake = Fake()
        self.run_probe(fake)
        self.assertEqual(fake.calls[-1][3], {"itineraryId": "itn1", "paymentType": "full",
                                             "paymentIntentId": "pi_test_1",
                                             "paymentStatus": "succeeded"})

    def test_rejected_customer_after_payment_stops_before_booking(self):
        fake = Fake(fail={"customer": 409})
        code, findings, out = self.run_probe(fake)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(fake.calls), 4)
        self.assertEqual(findings["rejected"], {"step": "customer", "status": 409})
        self.assertNotIn(("hofj", "POST", "/v1/bookings"), fake.plan())

    def test_rejected_pax_after_payment_stops_before_booking(self):
        fake = Fake(fail={"pax": 422})
        code, findings, _ = self.run_probe(fake)
        self.assertEqual(len(fake.calls), 5)
        self.assertEqual(findings["rejected"], {"step": "pax", "status": 422})

    def test_payment_not_succeeded_stops_before_the_puts(self):
        fake = Fake(intent_status="requires_action")
        code, findings, _ = self.run_probe(fake)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(fake.calls), 3)

    def test_refuses_live_stripe_keys_without_any_call(self):
        for key in ("sk_live_x", "rk_live_x", "pk_test_x", ""):
            fake = Fake()
            code, _, out = self.run_probe(fake, {**ENV, "STRIPE_SECRET_KEY": key})
            self.assertNotEqual(code, 0, key)
            self.assertEqual(fake.calls, [], key)

    def test_refuses_a_non_staging_hofj_host_without_any_call(self):
        fake = Fake()
        code, _, _ = self.run_probe(fake, {**ENV, "HOFJ_BASE_URL": "https://api.hofj.com"})
        self.assertNotEqual(code, 0)
        self.assertEqual(fake.calls, [])

    def test_stops_on_quota_or_auth_errors(self):
        for status in (401, 403, 429, 500):
            fake = Fake(fail={"get": status})
            code, _, _ = self.run_probe(fake)
            self.assertNotEqual(code, 0)
            self.assertEqual(len(fake.calls), 2, status)

    def test_dry_run_calls_nothing_and_prints_the_plan(self):
        fake = Fake()
        stdout = io.StringIO()
        code = m19_paid_probe.main(["--out", tempfile.mkdtemp(), "--dry-run"], env={}, opener=fake,
                                   sleep=lambda s: None, stdout=stdout)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])
        plan = [line for line in stdout.getvalue().splitlines() if line[:2].strip().isdigit()]
        self.assertEqual(len(plan), 7)


if __name__ == "__main__":
    unittest.main()
