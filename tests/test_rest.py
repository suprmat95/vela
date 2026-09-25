"""Superficie REST (RF-40, RF-43): auth, esiti, errori RFC 7807, flusso completo in replay, RF-10."""
import random
import unittest
from datetime import timedelta

from fastapi.testclient import TestClient

from support import NOW, assert_problem, assert_single_product, make_product
from vela.adapters.background import InlineRunner
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


def make_client(products=None, token=TOKEN):
    """App con repository in memoria, adapter replay e runner sincrono. `products=None` = fixture."""
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    repos.products.upsert_many(hofj.load_catalog() if products is None else products)
    vela = Vela(repos, hofj, FakePayments("http://test"), DEFAULT_TRAVELER, now=Clock())
    settings = Settings(vela_upstream_mode="replay", vela_public_url="http://test",
                        vela_api_token=token)
    app = create_app(settings, vela=vela, runner=InlineRunner(vela.orders))
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
