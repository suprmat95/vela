"""Superficie REST (RF-40, RF-43): auth, esiti, errori RFC 7807, flusso completo in replay, RF-10."""
import random
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from support import NOW, assert_problem, assert_single_product, inline_worker, make_product
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.usecases import Vela

TOKEN = "tok-test"
AUTH = {"Authorization": "Bearer " + TOKEN}
INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
FULL = {"first_name": "Anna", "last_name": "Rossi", "email": "anna@x.it", "phone": "+390000",
        "participants": [{"first_name": "Bo", "last_name": "Bi"}]}


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_client(products=None, token=TOKEN, payments=None):
    """App con repository in memoria, adapter replay e worker senza thread (`drain`). `products=None` = fixture."""
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    repos.products.upsert_many(hofj.load_catalog() if products is None else products)
    vela = Vela(repos, hofj, payments or FakePayments("http://test"), DEFAULT_TRAVELER,
                now=Clock())
    settings = Settings(vela_upstream_mode="replay", vela_public_url="http://test",
                        vela_api_token=token)
    app = create_app(settings, vela=vela, worker=inline_worker(vela))
    return TestClient(app, raise_server_exceptions=False), vela


def new_intent(c, text=INTENT, profile=FULL):
    body = {"text": text}
    if profile is not None:
        body["profile"] = profile
    r = c.post("/v1/intents", json=body, headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.c, _ = make_client()

    def test_missing_token_is_401(self):
        r = self.c.post("/v1/intents", json={"text": INTENT})
        assert_problem(self, r, 401, "unauthorized")
        self.assertEqual(r.headers["www-authenticate"], "Bearer")

    def test_wrong_token_is_not_echoed(self):
        r = self.c.post("/v1/intents", json={"text": INTENT},
                        headers={"Authorization": "Bearer sbagliato-123"})
        assert_problem(self, r, 401, "unauthorized")
        self.assertNotIn("sbagliato-123", r.text)

    def test_non_bearer_scheme_is_401(self):
        r = self.c.post("/v1/intents", json={"text": INTENT},
                        headers={"Authorization": "Basic " + TOKEN})
        assert_problem(self, r, 401, "unauthorized")

    def test_scheme_is_case_insensitive(self):
        r = self.c.post("/v1/intents", json={"text": INTENT},
                        headers={"Authorization": "bearer " + TOKEN})
        self.assertEqual(r.status_code, 201, r.text)

    def test_unconfigured_token_is_503(self):
        c, _ = make_client(token=None)
        assert_problem(self, c.post("/v1/intents", json={"text": INTENT}), 503, "rest-not-configured")
        r = c.post("/v1/intents", json={"text": INTENT}, headers=AUTH)
        assert_problem(self, r, 503, "rest-not-configured")

    def test_auth_is_checked_before_validation(self):
        assert_problem(self, self.c.post("/v1/intents", json={}), 401, "unauthorized")

    def test_auth_is_checked_before_domain(self):
        c = TestClient(create_app(Settings(vela_api_token=TOKEN)))   # nessun DATABASE_URL
        assert_problem(self, c.post("/v1/intents", json={"text": INTENT}), 401, "unauthorized")
        r = c.post("/v1/intents", json={"text": INTENT}, headers=AUTH)
        assert_problem(self, r, 503, "domain-unavailable")

    def test_health_and_replay_need_no_token(self):
        self.assertNotEqual(self.c.get("/health").status_code, 401)
        self.assertEqual(self.c.get("/replay/checkout/nope").status_code, 404)


class IntentEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.c, self.vela = make_client()

    def test_create_intent_is_201_intent_created(self):
        r = self.c.post("/v1/intents", json={"text": INTENT, "profile": FULL}, headers=AUTH)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        body = r.json()
        self.assertEqual(body["outcome"], "intent_created")
        self.assertTrue(body["intent_id"])
        self.assertEqual(body["criteria"]["sport"], "padel")
        self.assertEqual(body["criteria"]["pax"], 2)
        self.assertEqual(body["criteria"]["budget"], "800.00")
        assert_single_product(self, body)

    def test_question_is_200_and_persists_nothing(self):
        r = self.c.post("/v1/intents", json={"text": "ciao"}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "question")
        self.assertNotIn("intent_id", body)
        self.assertEqual(body["say"], body["question"])

    def test_profile_is_passed_to_the_domain(self):
        body = new_intent(self.c, text="padel a ottobre", profile={"pax": 3})
        self.assertEqual(body["criteria"]["pax"], 3)

    def test_blank_text_is_422(self):
        r = self.c.post("/v1/intents", json={"text": "   "}, headers=AUTH)
        body = assert_problem(self, r, 422, "invalid-request")
        self.assertEqual(body["errors"][0]["loc"], ["body", "text"])

    def test_zero_pax_is_422(self):
        r = self.c.post("/v1/intents", json={"text": INTENT, "profile": {"pax": 0}}, headers=AUTH)
        assert_problem(self, r, 422, "invalid-request")

    def test_missing_body_is_422(self):
        assert_problem(self, self.c.post("/v1/intents", headers=AUTH), 422, "invalid-request")

    def test_extra_fields_are_ignored(self):
        r = self.c.post("/v1/intents", json={"text": INTENT, "channel": "voce"}, headers=AUTH)
        self.assertEqual(r.status_code, 201)

    def test_get_proposal_is_a_single_product(self):
        iid = new_intent(self.c)["intent_id"]
        r = self.c.get("/v1/intents/%s/proposal" % iid, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "proposal")
        self.assertEqual(body["intent_id"], iid)
        self.assertTrue(body["product"]["product_id"])
        assert_single_product(self, body)
        again = self.c.get("/v1/intents/%s/proposal" % iid, headers=AUTH).json()
        self.assertEqual(again["proposal_id"], body["proposal_id"])

    def test_no_match_is_200(self):
        c, _ = make_client(products=[make_product(1, sport="tennis")])
        iid = new_intent(c, text="padel a ottobre, siamo in due")["intent_id"]
        r = c.get("/v1/intents/%s/proposal" % iid, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "no_match")
        self.assertEqual(body["failed_criterion"], "sport")
        assert_single_product(self, body)

    def test_unknown_intent_is_404(self):
        body = assert_problem(self, self.c.get("/v1/intents/nope/proposal", headers=AUTH),
                              404, "not-found")
        self.assertIn("intento", body["detail"])
        self.assertIn("nope", body["detail"])


ENDPOINTS = [("post", "/v1/intents"), ("get", "/v1/intents/i/proposal"),
             ("post", "/v1/proposals/p/reject"), ("post", "/v1/proposals/p/accept"),
             ("get", "/v1/orders/o")]


class EveryEndpointAuthTest(unittest.TestCase):
    def test_every_endpoint_requires_token(self):
        c, _ = make_client()
        for method, path in ENDPOINTS:
            with self.subTest(path=path):
                assert_problem(self, getattr(c, method)(path), 401, "unauthorized")


def proposal_for(c, iid):
    r = c.get("/v1/intents/%s/proposal" % iid, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


class ProposalEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.c, self.vela = make_client()
        self.iid = new_intent(self.c)["intent_id"]
        self.first = proposal_for(self.c, self.iid)

    def test_reject_returns_a_different_product(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"],
                        json={"reason": "troppo caro"}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "proposal")
        self.assertNotEqual(body["product"]["product_id"], self.first["product"]["product_id"])
        assert_single_product(self, body)

    def test_reject_without_body(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"], headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["outcome"], "proposal")

    def test_reject_with_null_reason(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"],
                        json={"reason": None}, headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)

    def test_reject_until_no_match(self):
        c, _ = make_client(products=[make_product(1)])
        iid = new_intent(c, text="padel a ottobre, siamo in due")["intent_id"]
        pid = proposal_for(c, iid)["proposal_id"]
        body = c.post("/v1/proposals/%s/reject" % pid, headers=AUTH).json()
        self.assertEqual(body["outcome"], "no_match")
        self.assertEqual(body["failed_criterion"], "rejected")

    def test_accept_returns_202_order_queued_with_location(self):
        r = self.c.post("/v1/proposals/%s/accept" % self.first["proposal_id"], json={}, headers=AUTH)
        self.assertEqual(r.status_code, 202, r.text)
        body = r.json()
        self.assertEqual(body, {"outcome": "order_queued", "order_id": body["order_id"],
                                "status": "queued", "position": 1, "wait_seconds": 4,
                                "say": body["say"]})
        self.assertEqual(r.headers["location"], "/v1/orders/%s" % body["order_id"])
        self.assertNotIn("http", body["say"])
        assert_single_product(self, body)

    def test_double_accept_returns_200_order_status(self):
        path = "/v1/proposals/%s/accept" % self.first["proposal_id"]
        r1 = self.c.post(path, json={}, headers=AUTH)
        r2 = self.c.post(path, headers=AUTH)
        self.assertEqual((r1.status_code, r2.status_code), (202, 200))
        self.assertEqual(r2.json()["outcome"], "order_status")
        self.assertEqual((r2.json()["order_id"], r2.json()["status"]), (r1.json()["order_id"], "queued"))

    def test_missing_traveler_data_then_complete(self):
        iid = new_intent(self.c, profile=None)["intent_id"]
        path = "/v1/proposals/%s/accept" % proposal_for(self.c, iid)["proposal_id"]
        r = self.c.post(path, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "missing_traveler_data")
        self.assertIn("email", body["missing"])
        self.assertIn("participants[0].last_name", body["missing"])
        assert_single_product(self, body)
        r = self.c.post(path, json={"traveler": FULL}, headers=AUTH)
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(r.json()["outcome"], "order_queued")

    def test_order_status_new_contract(self):
        order = self.c.post("/v1/proposals/%s/accept" % self.first["proposal_id"],
                            headers=AUTH).json()
        r = self.c.get("/v1/orders/%s" % order["order_id"], headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body), {"outcome", "order_id", "status", "position", "wait_seconds",
                                     "total", "currency", "price_from_total", "total_differs",
                                     "payment_url", "booking_code", "failure_reason",
                                     "proposal_changed", "proposal", "say"})
        self.assertEqual((body["outcome"], body["status"], body["position"], body["booking_code"]),
                         ("order_status", "queued", 1, None))
        assert_single_product(self, body)

    def test_unknown_ids_are_404(self):
        cases = [("post", "/v1/proposals/nope/reject", "proposta"),
                 ("post", "/v1/proposals/nope/accept", "proposta"),
                 ("get", "/v1/orders/nope", "ordine")]
        for method, path, label in cases:
            with self.subTest(path=path):
                body = assert_problem(self, getattr(self.c, method)(path, headers=AUTH),
                                      404, "not-found")
                self.assertIn(label, body["detail"])

    def test_invalid_traveler_is_422(self):
        r = self.c.post("/v1/proposals/%s/accept" % self.first["proposal_id"],
                        json={"traveler": {"participants": "Bo"}}, headers=AUTH)
        assert_problem(self, r, 422, "invalid-request")

    def test_unexpected_domain_error_is_500_problem(self):
        def boom(order_id):
            raise RuntimeError("segreto interno")
        self.vela.get_order_status = boom
        r = self.c.get("/v1/orders/x", headers=AUTH)
        assert_problem(self, r, 500, "internal-error")
        self.assertNotIn("segreto", r.text)

    def test_openapi_lists_the_five_endpoints(self):
        paths = self.c.get("/openapi.json").json()["paths"]
        for path in ("/v1/intents", "/v1/intents/{intent_id}/proposal",
                     "/v1/proposals/{proposal_id}/reject", "/v1/proposals/{proposal_id}/accept",
                     "/v1/orders/{order_id}"):
            self.assertIn(path, paths)


class FullFlowTest(unittest.TestCase):
    def test_intent_to_confirmed_over_rest(self):
        """§10.3 in replay: intento → proposta → rifiuto → altra → accetta ×2 → checkout → confirmed."""
        c, vela = make_client()
        bodies = []

        def call(method, path, expected, **kw):
            r = getattr(c, method)(path, headers=AUTH, **kw)
            self.assertEqual(r.status_code, expected, r.text)
            bodies.append(r.json())
            return r.json()

        intent = call("post", "/v1/intents", 201, json={"text": INTENT, "profile": FULL})
        first = call("get", "/v1/intents/%s/proposal" % intent["intent_id"], 200)
        second = call("post", "/v1/proposals/%s/reject" % first["proposal_id"], 200,
                      json={"reason": "troppo caro"})
        self.assertNotEqual(second["product"]["product_id"], first["product"]["product_id"])
        order = call("post", "/v1/proposals/%s/accept" % second["proposal_id"], 202)
        self.assertEqual(order["status"], "queued")
        again = call("post", "/v1/proposals/%s/accept" % second["proposal_id"], 200)
        self.assertEqual(again["order_id"], order["order_id"])
        c.app.state.worker.drain()                           # job d'acquisto: link pronto
        status = call("get", "/v1/orders/%s" % order["order_id"], 200)
        self.assertEqual(status["status"], "awaiting_payment")

        paid = c.get(urlparse(status["payment_url"]).path)  # checkout replay: nessun token
        self.assertEqual(paid.status_code, 200)
        c.app.state.worker.drain()                           # il job di prenotazione

        final = call("get", "/v1/orders/%s" % order["order_id"], 200)
        self.assertEqual(final["status"], "confirmed")
        self.assertRegex(final["booking_code"], r"^R-\d{6}$")
        self.assertIn(final["booking_code"], final["say"])
        for body in bodies:                                   # RF-10 su ogni risposta
            assert_single_product(self, body)


def proposal_id(c):
    iid = new_intent(c)["intent_id"]
    return c.get("/v1/intents/%s/proposal" % iid, headers=AUTH).json()["proposal_id"]


class OrderStatusPaymentTest(unittest.TestCase):
    def test_awaiting_payment_status_has_link_and_amount(self):
        c, _ = make_client()
        order = c.post("/v1/proposals/%s/accept" % proposal_id(c), headers=AUTH).json()
        c.app.state.worker.drain()
        r = c.get("/v1/orders/%s" % order["order_id"], headers=AUTH).json()
        self.assertEqual((r["outcome"], r["status"]), ("order_status", "awaiting_payment"))
        self.assertTrue(r["payment_url"].startswith("http://test/replay/checkout/"))
        self.assertEqual((r["currency"], r["total_differs"]), ("EUR", False))
        self.assertEqual(r["total"], r["price_from_total"])
        assert_single_product(self, r)


SIVIGLIA_MADRID = [make_product(1, price=300, destination="Siviglia"),
                   make_product(2, price=450, destination="Madrid")]


class AgentToolContractTest(unittest.TestCase):
    """M17: gli stessi campi strutturati del tool MCP nel corpo JSON (RF-40, RF-52)."""

    def test_uc1_fields_reach_the_intent(self):
        c, vela = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={
            "text": INTENT, "sport": "padel", "area": "Spagna", "period_start": "2026-10-01",
            "period_end": "2026-10-31", "pax": 2, "budget": 800})
        self.assertEqual(r.status_code, 201, r.text)
        crit = r.json()["criteria"]
        self.assertEqual((crit["sport"], crit["area"]["name"], crit["pax"], crit["budget"]),
                         ("padel", "Spagna", 2, "800.00"))

    def test_uc4_reject_with_direction_keeps_the_intent(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        intent = new_intent(c)
        first = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        self.assertEqual(first["product"]["destination"], "Siviglia")
        r = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "Troppo caldo, vorrei un posto più fresco", "direction": "north"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["outcome"], d["intent_id"]), ("proposal", intent["intent_id"]))
        self.assertEqual(d["product"]["destination"], "Madrid")

    def test_uc7_invalid_values_are_declared_not_422(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={
            "text": "Padel a Atlantide, siamo in tre.", "sport": "padel", "area": "Atlantide",
            "pax": 30, "budget": 1000})
        self.assertEqual(r.status_code, 201, r.text)
        d = r.json()
        self.assertIsNone(d["criteria"]["area"])
        self.assertEqual(d["criteria"]["pax"], 3)
        self.assertTrue(d["say"].startswith("Non conosco il luogo Atlantide."))
        self.assertIn("30", d["say"])

    def test_wrong_json_type_is_422(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={"text": INTENT, "pax": "tre"})
        self.assertEqual(r.status_code, 422)

    def test_uc8_field_wins_over_text(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        with self.assertLogs("vela.domain.usecases", "INFO"):
            r = c.post("/v1/intents", headers=AUTH,
                       json={"text": "Tennis a Roma a maggio, siamo in due", "sport": "padel"})
        self.assertEqual(r.json()["criteria"]["sport"], "padel")

    def test_profile_pax_stays_the_default(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH,
                   json={"text": "padel a ottobre", "pax": 3, "profile": {"pax": 2}})
        self.assertEqual(r.json()["criteria"]["pax"], 3)

    def test_no_match_after_reject_carries_rejected_proposal_id(self):
        c, _ = make_client(products=SIVIGLIA_MADRID[:1])
        intent = new_intent(c)
        first = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        d = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "no"}).json()
        self.assertEqual((d["outcome"], d["rejected_proposal_id"]), ("no_match", first["proposal_id"]))
        d = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "a novembre", "period_start": "2026-11-01",
                         "period_end": "2026-11-30"}).json()
        self.assertEqual(d["outcome"], "no_match")
        self.assertEqual(d["failed_criterion"], "dates")
