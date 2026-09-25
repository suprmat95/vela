"""Errori RFC 7807 della superficie REST: solo sotto /v1, mai dettagli interni."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from support import assert_problem
from vela.domain.orders import NotFound
from vela.surfaces.problems import install_problem_handlers, not_found, unauthorized


class Body(BaseModel):
    text: str


def make_client():
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/v1/problem")
    def problem():
        raise unauthorized()

    @app.get("/v1/missing")
    def missing():
        raise NotFound("order", "o-1")

    @app.get("/v1/boom")
    def boom():
        raise RuntimeError("segreto interno")

    @app.post("/v1/echo")
    def echo(body: Body):
        return {"text": body.text}

    @app.post("/other/echo")
    def other_echo(body: Body):
        return {"text": body.text}

    @app.get("/other/boom")
    def other_boom():
        raise RuntimeError("segreto interno")

    return TestClient(app, raise_server_exceptions=False)


class ProblemTest(unittest.TestCase):
    def setUp(self):
        self.c = make_client()

    def test_problem_exception_is_7807(self):
        r = self.c.get("/v1/problem")
        body = assert_problem(self, r, 401, "unauthorized")
        self.assertEqual(body["instance"], "/v1/problem")
        self.assertEqual(r.headers["www-authenticate"], "Bearer")

    def test_domain_not_found_is_404(self):
        body = assert_problem(self, self.c.get("/v1/missing"), 404, "not-found")
        self.assertIn("ordine", body["detail"])
        self.assertIn("o-1", body["detail"])

    def test_not_found_labels_every_kind(self):
        self.assertIn("intento", not_found("intent", "x").detail)
        self.assertIn("proposta", not_found("proposal", "x").detail)

    def test_unknown_route_under_v1_is_404_problem(self):
        assert_problem(self, self.c.get("/v1/nope"), 404, "not-found")

    def test_method_not_allowed_keeps_allow_header(self):
        r = self.c.get("/v1/echo")
        assert_problem(self, r, 405, "method-not-allowed")
        self.assertEqual(r.headers["allow"], "POST")

    def test_validation_error_is_invalid_request(self):
        body = assert_problem(self, self.c.post("/v1/echo", json={}), 422, "invalid-request")
        self.assertEqual(body["errors"][0]["loc"], ["body", "text"])
        self.assertTrue(body["errors"][0]["msg"])

    def test_malformed_json_is_invalid_request(self):
        r = self.c.post("/v1/echo", content="{non json", headers={"content-type": "application/json"})
        assert_problem(self, r, 422, "invalid-request")

    def test_unexpected_error_is_500_without_leak(self):
        r = self.c.get("/v1/boom")
        assert_problem(self, r, 500, "internal-error")
        self.assertNotIn("segreto", r.text)
        self.assertNotIn("Traceback", r.text)

    def test_other_paths_keep_default_format(self):
        r = self.c.get("/other/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {"detail": "Not Found"})
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        r = self.c.post("/other/echo", json={})
        self.assertEqual(r.status_code, 422)
        self.assertIsInstance(r.json()["detail"], list)
        r = self.c.get("/other/boom")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.text, "Internal Server Error")

    def test_prefix_match_is_exact(self):
        r = self.c.get("/v1x/nope")
        self.assertEqual(r.json(), {"detail": "Not Found"})
