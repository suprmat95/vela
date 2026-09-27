"""Superficie REST (RF-40, RF-43): auth, esiti, errori RFC 7807, flusso completo in replay, RF-10."""
import random
import unittest
from dataclasses import replace
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
        body = new_intent(self.c, text="padel a ottobre, due camere", profile={"pax": 3})
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
        """M21-F (RF-75): senza motivo né tipo la risposta è la domanda chiusa, 200, con l'id della
        proposta che resta aperta; con `reject_kind` other è il rifiuto di prima."""
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"], headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)
        question = "Cosa non ti convince: il posto, l'hotel, le date o il prezzo?"
        self.assertEqual(r.json(), {"outcome": "question", "question": question, "say": question,
                                    "proposal_id": self.first["proposal_id"]})
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"], headers=AUTH,
                        json={"reject_kind": "other"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["outcome"], "proposal")

    def test_reject_kind_and_keep_product(self):
        """M21-F (RF-52, RF-74): stesso viaggio con un'altra partenza; `keep_product` di tipo
        sbagliato è un 422 come `wants_coaching`, un `reject_kind` fuori elenco è scartato e detto."""
        c, _ = make_client(products=[make_product(1, windows=(("2026-10-01", "2026-10-04"),
                                                              ("2026-10-08", "2026-10-11"))),
                                     make_product(2, price=900)])
        iid = new_intent(c, text="padel a ottobre, siamo in due")["intent_id"]
        first = proposal_for(c, iid)
        body = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                      json={"reason": "va bene il viaggio", "reject_kind": "dates",
                            "keep_product": True}).json()
        self.assertEqual((body["outcome"], body["product"]["product_id"], body["start_date"]),
                         ("proposal", "1", "2026-10-08"))
        r = c.post("/v1/proposals/%s/reject" % body["proposal_id"], headers=AUTH,
                   json={"keep_product": "forse"})
        self.assertEqual(r.status_code, 422)
        body = c.post("/v1/proposals/%s/reject" % body["proposal_id"], headers=AUTH,
                      json={"reason": "boh", "reject_kind": "meteo"}).json()
        self.assertEqual(body["outcome"], "question")
        self.assertTrue(body["say"].startswith("Non ho potuto usare meteo come tipo di rifiuto."))

    def test_reject_with_null_reason(self):
        r = self.c.post("/v1/proposals/%s/reject" % self.first["proposal_id"],
                        json={"reason": None}, headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)

    def test_reject_until_no_match(self):
        c, _ = make_client(products=[make_product(1)])
        iid = new_intent(c, text="padel a ottobre, siamo in due")["intent_id"]
        pid = proposal_for(c, iid)["proposal_id"]
        body = c.post("/v1/proposals/%s/reject" % pid, headers=AUTH, json={"reject_kind": "other"}).json()
        self.assertEqual(body["outcome"], "no_match")
        self.assertEqual(body["failed_criterion"], "rejected")

    def test_accept_returns_202_order_queued_with_location(self):
        r = self.c.post("/v1/proposals/%s/accept" % self.first["proposal_id"], json={}, headers=AUTH)
        self.assertEqual(r.status_code, 202, r.text)
        body = r.json()
        self.assertEqual(body, {"outcome": "order_queued", "order_id": body["order_id"],
                                "status": "queued", "position": 1, "wait_seconds": 2,
                                "say": body["say"]})
        self.assertEqual(r.headers["location"], "/v1/orders/%s" % body["order_id"])
        self.assertNotIn("http", body["say"])
        assert_single_product(self, body)

    def test_accept_returns_200_with_the_link_when_the_job_finishes_during_the_wait(self):
        """M20: il prezzo e poi il link arrivano nella risposta dell'accept, senza `Location`."""
        worker = inline_worker(self.vela)
        self.vela.accept_wait_seconds, self.vela.sleep = 5, lambda seconds: worker.drain()
        path = "/v1/proposals/%s/accept" % self.first["proposal_id"]
        priced = self.c.post(path, json={}, headers=AUTH)
        self.assertEqual(priced.status_code, 200, priced.text)
        self.assertEqual((priced.json()["outcome"], priced.json()["status"]), ("order_status", "awaiting_confirmation"))
        r = self.c.post(path, headers=AUTH)                    # la conferma
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual((body["outcome"], body["status"]), ("order_status", "awaiting_payment"))
        self.assertTrue(body["payment_url"].startswith("http://test/"))
        self.assertNotIn("location", r.headers)
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

    def test_openapi_lists_the_endpoints(self):
        paths = self.c.get("/openapi.json").json()["paths"]
        for path in ("/v1/intents", "/v1/intents/{intent_id}/proposal",
                     "/v1/proposals/{proposal_id}/details", "/v1/proposals/{proposal_id}/reject", "/v1/proposals/{proposal_id}/accept",
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
        c.app.state.worker.drain()                           # job d'acquisto: prezzo effettivo
        priced = call("get", "/v1/orders/%s" % order["order_id"], 200)
        self.assertEqual((priced["status"], priced["payment_url"]), ("awaiting_confirmation", None))
        confirmed = call("post", "/v1/proposals/%s/accept" % second["proposal_id"], 202)   # il sì
        self.assertEqual(confirmed["order_id"], order["order_id"])
        c.app.state.worker.drain()                           # link pronto
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
        pid = proposal_id(c)
        order = c.post("/v1/proposals/%s/accept" % pid, headers=AUTH).json()
        c.app.state.worker.drain()
        c.post("/v1/proposals/%s/accept" % pid, headers=AUTH)   # conferma del prezzo effettivo
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
            "pax": 30, "rooms": 2, "budget": 1000})
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
                   json={"text": "padel a ottobre", "pax": 3, "rooms": 2, "profile": {"pax": 2}})
        self.assertEqual(r.json()["criteria"]["pax"], 3)

    def test_no_match_after_reject_carries_rejected_proposal_id(self):
        c, _ = make_client(products=SIVIGLIA_MADRID[:1])
        intent = new_intent(c)
        first = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        d = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "no", "reject_kind": "other"}).json()
        self.assertEqual((d["outcome"], d["rejected_proposal_id"]), ("no_match", first["proposal_id"]))
        d = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "a novembre", "period_start": "2026-11-01",
                         "period_end": "2026-11-30"}).json()
        self.assertEqual(d["outcome"], "no_match")
        self.assertEqual(d["failed_criterion"], "dates")


def trip(pid, nights, price):
    """Prodotto a finestra fissa di `nights` notti dal 1 ottobre."""
    end = "2026-10-%02d" % (1 + nights)
    return replace(make_product(pid, price=price, windows=(("2026-10-01", end),)),
                   duration_days=nights + 1)


class DurationContractTest(unittest.TestCase):
    """M21-A (UC-A): `duration_min_nights`/`duration_max_nights` nel corpo JSON, `nights` nella
    proposta."""

    PRODUCTS = [trip(1, 7, 300), trip(2, 3, 400)]

    def test_fields_reach_the_intent(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={
            "text": "padel in Spagna a ottobre, siamo in due", "duration_min_nights": 6,
            "duration_max_nights": 8})
        self.assertEqual(r.status_code, 201, r.text)
        crit = r.json()["criteria"]
        self.assertEqual((crit["duration_min_nights"], crit["duration_max_nights"]), (6, 8))
        self.assertIn("da 6 a 8 notti", r.json()["say"])

    def test_wrong_type_is_422(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={"text": INTENT, "duration_min_nights": "tre"})
        self.assertEqual(r.status_code, 422)
        r = c.post("/v1/proposals/x/reject", headers=AUTH, json={"duration_max_nights": [3]})
        self.assertEqual(r.status_code, 422)

    def test_out_of_range_is_declared_not_422(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={
            "text": "padel a ottobre, siamo in due", "duration_min_nights": 5,
            "duration_max_nights": 2})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["say"].startswith("Non ho potuto usare 5 - 2 come durata in notti."))

    def test_weekend_then_reject_with_fields(self):
        # senza i campi la proposta successiva sarebbe l'altro weekend (id 3)
        c, _ = make_client(products=self.PRODUCTS + [trip(3, 2, 450)])
        intent = new_intent(c, text="un weekend di padel in Spagna a ottobre, siamo in due")
        first = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        assert_single_product(self, first)
        self.assertEqual((first["product"]["product_id"], first["nights"]), ("2", 3))
        r = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "no grazie", "duration_min_nights": 6})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        assert_single_product(self, d)
        self.assertEqual((d["product"]["product_id"], d["nights"]), ("1", 7))


class BudgetScopeContractTest(unittest.TestCase):
    """M21-E (UC-E): `budget_scope` nel corpo JSON e nei criteri."""

    # il più economico costa 450 in tre: senza campo 600 si leggerebbe in tutto (regola 4)
    PRODUCTS = [make_product(1, price=150), make_product(2, price=250)]
    THREE = "padel in Spagna a ottobre, siamo in tre, due camere"

    def test_field_reaches_the_intent(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={
            "text": self.THREE + ", 600 euro", "budget": 600, "budget_scope": "per_person"})
        self.assertEqual(r.status_code, 201, r.text)
        crit = r.json()["criteria"]
        self.assertEqual((crit["budget"], crit["budget_scope"]), ("1800.00", "per_person"))
        self.assertIn("600 euro a persona, 1800 in tutto", r.json()["say"])

    def test_invalid_is_declared_not_422(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={"text": self.THREE, "budget_scope": "each"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["say"].startswith("Non ho potuto usare each come lettura del budget"))

    def test_wrong_type_is_422(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={"text": INTENT, "budget_scope": ["total"]})
        self.assertEqual(r.status_code, 422)

    def test_reject_with_budget_scope(self):
        c, _ = make_client(products=self.PRODUCTS)
        intent = new_intent(c, text=self.THREE + ", 1800 euro in tutto")
        first = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        r = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "no", "budget_scope": "per_person"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("1800 euro a persona, 5400 in tutto", r.json()["say"])


class RoomsContractTest(unittest.TestCase):
    """M21-D (UC-D, RF-65): `rooms` nel corpo di `POST /v1/intents` e del rifiuto; con più di 2
    persone senza camere la risposta è `question` e nessun intento viene salvato."""

    FIVE = "padel in Portogallo a novembre, siamo in cinque"

    def test_five_without_rooms_is_a_question(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={"text": self.FIVE, "pax": 5})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual((body["outcome"], body["question"]), ("question", "In quante camere?"))
        self.assertNotIn("intent_id", body)

    def test_five_with_rooms_is_created(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={"text": self.FIVE, "pax": 5, "rooms": 3})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual((body["criteria"]["pax"], body["criteria"]["rooms"]), (5, 3))
        self.assertIn("per 5 persone in 3 camere", body["say"])

    def test_two_without_rooms_default_to_one(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        body = new_intent(c)
        self.assertEqual(body["criteria"]["rooms"], 1)
        self.assertNotIn("camer", body["say"])

    def test_invalid_rooms_is_declared_not_422(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={"text": INTENT, "rooms": 0})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["say"].startswith("Non ho potuto usare 0 come numero di camere."))

    def test_wrong_type_is_422(self):
        c, _ = make_client(products=SIVIGLIA_MADRID)
        r = c.post("/v1/intents", headers=AUTH, json={"text": INTENT, "rooms": "tre"})
        self.assertEqual(r.status_code, 422)

    FIVE_TRAVELERS = dict(FULL, participants=[{"first_name": "P%d" % i, "last_name": "Rossi"}
                                              for i in range(4)])

    FIVE_OCT = "padel a ottobre, siamo in cinque"   # il prodotto sintetico parte a ottobre

    def five_proposal(self, c):
        r = c.post("/v1/intents", headers=AUTH, json={"text": self.FIVE_OCT, "pax": 5, "rooms": 3,
                                                       "profile": self.FIVE_TRAVELERS})
        self.assertEqual(r.status_code, 201, r.text)
        return c.get("/v1/intents/%s/proposal" % r.json()["intent_id"], headers=AUTH).json()

    def test_proposal_reports_the_rooms(self):
        c, _ = make_client(products=[make_product(1, price=300, max_pax_per_room=2)])
        proposal = self.five_proposal(c)
        self.assertEqual((proposal["outcome"], proposal["rooms"]), ("proposal", 3))

    def test_accept_below_the_minimum_is_200_question_without_an_order(self):
        c, vela = make_client(products=[make_product(1, price=300, max_pax_per_room=2)])
        proposal = self.five_proposal(c)
        r = c.post("/v1/proposals/%s/accept" % proposal["proposal_id"], headers=AUTH, json={"rooms": 2})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual((body["outcome"], body["question"]), ("question", "In quante camere?"))
        self.assertIsNone(vela.repos.orders.get_by_proposal(proposal["proposal_id"]))

    def test_accept_with_a_rooms_correction(self):
        c, vela = make_client(products=[make_product(1, price=300, max_pax_per_room=2)])
        proposal = self.five_proposal(c)
        r = c.post("/v1/proposals/%s/accept" % proposal["proposal_id"], headers=AUTH, json={"rooms": 4})
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(vela.repos.orders.get_by_proposal(proposal["proposal_id"]).rooms, 4)

    def test_accept_wrong_rooms_type_is_422(self):
        c, _ = make_client(products=[make_product(1, price=300, max_pax_per_room=2)])
        proposal = self.five_proposal(c)
        r = c.post("/v1/proposals/%s/accept" % proposal["proposal_id"], headers=AUTH, json={"rooms": "due"})
        self.assertEqual(r.status_code, 422)


class LevelContractTest(unittest.TestCase):
    """M21-C (UC-C, RF-52, RF-62): `level` e `wants_coaching` nel corpo e nei criteri."""

    UC_C = "Siamo principianti, vorremmo lezioni di padel in Spagna a ottobre, in due."
    PRODUCTS = [replace(make_product(1, price=300), levels=frozenset({"intermediate", "advanced"})),
                replace(make_product(2, price=400), levels=frozenset({"beginner"}), coaching=True)]

    def test_fields_reach_the_criteria_and_the_proposal(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={"text": self.UC_C, "level": "beginner",
                                                      "wants_coaching": True})
        self.assertEqual(r.status_code, 201, r.text)
        crit = r.json()["criteria"]
        self.assertEqual((crit["level"], crit["wants_coaching"]), ("beginner", True))
        p = c.get("/v1/intents/%s/proposal" % r.json()["intent_id"], headers=AUTH).json()
        self.assertEqual(p["product"]["product_id"], "2")
        self.assertIn("pensato per principianti", p["say"])

    def test_invalid_level_is_declared_not_422(self):
        c, _ = make_client(products=self.PRODUCTS)
        r = c.post("/v1/intents", headers=AUTH, json={"text": INTENT, "level": "expert"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["say"].startswith("Non ho potuto usare expert come livello di gioco"))

    def test_wrong_types_are_422(self):
        c, _ = make_client(products=self.PRODUCTS)
        for body in ({"text": INTENT, "wants_coaching": "forse"}, {"text": INTENT, "level": ["beginner"]}):
            with self.subTest(body=body):
                self.assertEqual(c.post("/v1/intents", headers=AUTH, json=body).status_code, 422)

    def test_reject_with_wants_coaching(self):
        c, _ = make_client(products=self.PRODUCTS)
        intent = new_intent(c, text="padel in Spagna a ottobre, in due")
        first = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        r = c.post("/v1/proposals/%s/reject" % first["proposal_id"], headers=AUTH,
                   json={"reason": "vorremmo un maestro", "wants_coaching": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("con lezioni", r.json()["say"])

    def test_replay_fixture_uc_c(self):
        """UC-C sul catalogo delle fixture: la proposta dice se rispetta livello e lezioni."""
        c, _ = make_client()
        r = c.post("/v1/intents", headers=AUTH, json={"text": self.UC_C})
        self.assertEqual(r.status_code, 201, r.text)
        p = c.get("/v1/intents/%s/proposal" % r.json()["intent_id"], headers=AUTH).json()
        self.assertEqual(p["outcome"], "proposal")
        self.assertTrue("Il programma" in p["say"] or "Non ho trovato viaggi per principianti" in p["say"],
                        p["say"])
