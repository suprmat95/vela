"""Flusso REST cronometrato (scripts/rest_flow.py, M7): criteri 3 e 4 di spec §10 e latenza per M13.

L'app vera in replay (repository in memoria, worker senza thread) per i flussi completi; un
`httpx.MockTransport` con risposte scritte a mano per i casi che il dominio non produce.
"""
import contextlib
import io
import os
import random
import sys
import unittest
from urllib.parse import urlparse

import httpx
from fastapi.testclient import TestClient

from support import inline_worker
from test_rest import Clock
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.usecases import Vela
from vela.ports.hofj import ProductError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import rest_flow  # noqa: E402

TOKEN = "tok-segreto-rest-flow"


class FirstCartFailsHofJ(ReplayHofJ):
    """Il primo carrello fallisce come la trappola su HofJ (502 con upstream 404 → ProductError)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.failed = []

    def create_itinerary(self, product, *args, **kw):
        if not self.failed:
            self.failed.append(product.id)
            raise ProductError("HofJ POST /v1/itineraries: 502 upstream returned 404")
        return super().create_itinerary(product, *args, **kw)


def make_app(hofj=None):
    repos = MemoryRepositories()
    hofj = hofj or ReplayHofJ(rng=random.Random(7))
    repos.products.upsert_many(ReplayHofJ().load_catalog())
    vela = Vela(repos, hofj, FakePayments("http://testserver"), DEFAULT_TRAVELER, now=Clock())
    app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://testserver",
                              vela_api_token=TOKEN),
                     vela=vela, worker=inline_worker(vela), catalog_loader=None)
    return app, vela


def authed(app):
    return TestClient(app, headers={"Authorization": "Bearer " + TOKEN})


class FakeClock:
    """Orologio finto: `sleep` lo fa avanzare, così i timeout si provano senza attese."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def canned(routes):
    """Client httpx con risposte scritte a mano: {(metodo, path): [json, json, ...]}."""
    queues = {key: list(values) for key, values in routes.items()}

    def handler(request):
        key = (request.method, request.url.path)
        if key not in queues or not queues[key]:
            return httpx.Response(404, json={"title": "non previsto: %s %s" % key})
        body = queues[key].pop(0) if len(queues[key]) > 1 else queues[key][0]
        status = 202 if body.get("outcome") == "order_queued" else 200
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://vela.test")


def proposal(pid, product_id, total):
    return {"outcome": "proposal", "proposal_id": pid, "product": {"product_id": product_id,
                                                                    "title": "Prodotto " + product_id},
            "total_from": total, "currency": "EUR", "say": "Ti propongo " + product_id}


def status(status, **fields):
    body = {"outcome": "order_status", "order_id": "o1", "status": status, "position": None,
            "wait_seconds": None, "total": None, "currency": None, "payment_url": None,
            "booking_code": None, "failure_reason": None, "proposal_changed": False,
            "proposal": None, "say": "stato " + status}
    body.update(fields)
    return body


BASE_ROUTES = {
    ("POST", "/v1/intents"): [{"outcome": "intent_created", "intent_id": "i1", "say": "ok"}],
    ("GET", "/v1/intents/i1/proposal"): [proposal("p1", "118", "600.00")],
    ("POST", "/v1/proposals/p1/reject"): [proposal("p2", "119", "480.00")],
    ("POST", "/v1/proposals/p2/accept"): [{"outcome": "order_queued", "order_id": "o1",
                                          "status": "queued", "position": 1, "wait_seconds": 4,
                                          "say": "in coda"}],
    ("POST", "/v1/proposals/p1/accept"): [{"outcome": "order_queued", "order_id": "o1",
                                          "status": "queued", "position": 1, "wait_seconds": 4,
                                          "say": "in coda"}],
}


def run_canned(routes, **kw):
    clock = FakeClock()
    kw.setdefault("timeout", 30)
    return rest_flow.run_flow(canned(routes), open_url=lambda url: None, clock=clock,
                              sleep=clock.sleep, poll=1, **kw)


class FullFlowTest(unittest.TestCase):
    def test_replay_flow_reaches_confirmed_with_a_cheaper_second_proposal(self):
        app, _ = make_app()
        opened = []
        with authed(app) as client:
            def open_url(url):
                opened.append(url)
                self.assertEqual(client.get(urlparse(url).path).status_code, 200)   # paga il replay

            summary = rest_flow.run_flow(client, open_url=open_url, tick=app.state.worker.drain,
                                         sleep=lambda s: None, poll=0)
        self.assertEqual(summary["status"], "confirmed")
        self.assertRegex(summary["booking_code"], r"^R-\d{6}$")
        self.assertLess(float(summary["second_total"]), float(summary["first_total"]))
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].startswith("http://testserver/replay/checkout/"))
        steps = [name for name, _ in summary["timings"]]
        self.assertEqual(steps, ["intento", "proposta", "rifiuto", "accept", "accept → link",
                                 "link → confirmed", "totale"])

    def test_timings_come_from_the_clock(self):
        clock = FakeClock()
        routes = dict(BASE_ROUTES)
        link = status("awaiting_payment", total="480.00", payment_url="https://checkout.stripe.com/c/x")
        # t=0 queued, t=2 queued, t=4 link; poi t=4 ancora da pagare, t=6 confirmed
        routes[("GET", "/v1/orders/o1")] = [status("queued"), status("queued"), link, link,
                                            status("confirmed", booking_code="abc123")]
        summary = rest_flow.run_flow(canned(routes), open_url=lambda url: None, clock=clock,
                                     sleep=clock.sleep, poll=2, timeout=60)
        timings = dict(summary["timings"])
        self.assertEqual((timings["accept → link"], timings["link → confirmed"], timings["totale"]),
                         (4.0, 2.0, 6.0))
        self.assertEqual(summary["booking_code"], "abc123")

    def test_link_never_ready_fails_after_the_timeout(self):
        app, _ = make_app()
        clock = FakeClock()
        with authed(app) as client, self.assertRaises(rest_flow.FlowFailure) as ctx:
            rest_flow.run_flow(client, open_url=lambda url: None, clock=clock, sleep=clock.sleep,
                               poll=5, timeout=30)          # senza tick la coda non avanza
        self.assertIn("queued", str(ctx.exception))
        self.assertIn("30", str(ctx.exception))

    def test_terminal_status_fails_at_once_with_the_reason(self):
        routes = dict(BASE_ROUTES)
        routes[("GET", "/v1/orders/o1")] = [status("failed", failure_reason="fornitore non raggiungibile")]
        with self.assertRaises(rest_flow.FlowFailure) as ctx:
            run_canned(routes)
        self.assertIn("failed", str(ctx.exception))
        self.assertIn("fornitore non raggiungibile", str(ctx.exception))


class ChecksTest(unittest.TestCase):
    def test_a_response_with_two_products_fails(self):
        routes = dict(BASE_ROUTES)
        two = proposal("p1", "118", "600.00")
        two["other"] = {"product_id": "119"}
        routes[("GET", "/v1/intents/i1/proposal")] = [two]
        with self.assertRaises(rest_flow.FlowFailure) as ctx:
            run_canned(routes)
        self.assertIn("più di un prodotto", str(ctx.exception))

    def test_second_proposal_not_cheaper_fails(self):
        routes = dict(BASE_ROUTES)
        routes[("POST", "/v1/proposals/p1/reject")] = [proposal("p2", "119", "600.00")]
        with self.assertRaises(rest_flow.FlowFailure) as ctx:
            run_canned(routes)
        self.assertIn("più economica", str(ctx.exception))

    def test_http_error_fails_with_the_problem_title(self):
        routes = dict(BASE_ROUTES)
        del routes[("POST", "/v1/intents")]
        with self.assertRaises(rest_flow.FlowFailure) as ctx:
            run_canned(routes)
        self.assertIn("404", str(ctx.exception))


class TrapFlowTest(unittest.TestCase):
    def test_product_failing_at_the_cart_is_replaced_by_a_different_proposal(self):
        hofj = FirstCartFailsHofJ(rng=random.Random(7))
        app, vela = make_app(hofj)
        with authed(app) as client:
            summary = rest_flow.run_flow(client, open_url=lambda url: None, trap=True,
                                         tick=app.state.worker.drain, sleep=lambda s: None, poll=0)
        self.assertEqual(summary["status"], "replaced")
        self.assertEqual(summary["trap_product"], hofj.failed[0])
        self.assertNotEqual(summary["replacement_product"], hofj.failed[0])
        self.assertEqual([name for name, _ in summary["timings"]],
                         ["intento", "proposta", "accept", "accept → sostituzione", "totale"])

    def test_trap_that_does_not_fail_is_reported(self):
        app, _ = make_app()
        with authed(app) as client, self.assertRaises(rest_flow.FlowFailure) as ctx:
            rest_flow.run_flow(client, open_url=lambda url: None, trap=True,
                               tick=app.state.worker.drain, sleep=lambda s: None, poll=0)
        self.assertIn("awaiting_payment", str(ctx.exception))

    def test_replacement_that_shows_a_technical_error_fails(self):
        routes = dict(BASE_ROUTES)
        routes[("GET", "/v1/orders/o1")] = [status(
            "replaced", proposal_changed=True, proposal=proposal("p3", "120", "500.00"),
            say="Errore HofJ 502: ti propongo un'altra cosa")]
        with self.assertRaises(rest_flow.FlowFailure) as ctx:
            run_canned(routes, trap=True)
        self.assertIn("errore", str(ctx.exception).lower())

    def test_replacement_with_the_same_product_fails(self):
        routes = dict(BASE_ROUTES)
        routes[("GET", "/v1/orders/o1")] = [status(
            "replaced", proposal_changed=True, proposal=proposal("p3", "118", "500.00"),
            say="Quel viaggio non è più disponibile, ti propongo questo")]
        with self.assertRaises(rest_flow.FlowFailure) as ctx:
            run_canned(routes, trap=True)
        self.assertIn("stesso prodotto", str(ctx.exception))


def run_main(argv, env, factory=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = rest_flow.main(argv, env=env, client_factory=factory)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_missing_token_exits_before_any_call(self):
        def factory(url, token):
            raise AssertionError("nessuna chiamata senza token")

        code, _, err = run_main(["https://vela.test"], {}, factory)
        self.assertEqual(code, 2)
        self.assertIn("VELA_API_TOKEN", err)

    def test_trap_run_prints_the_table_and_never_the_token(self):
        hofj = FirstCartFailsHofJ(rng=random.Random(7))
        app, _ = make_app(hofj)
        seen = []

        def factory(url, token):
            seen.append((url, token))
            return authed(app)

        with mock_tick(app):
            code, out, err = run_main(["http://testserver", "--trap", "--poll", "0"],
                                      {"VELA_API_TOKEN": TOKEN}, factory)
        self.assertEqual(code, 0, err)
        self.assertEqual(seen, [("http://testserver", TOKEN)])
        self.assertIn("| accept → sostituzione |", out)
        self.assertIn("replaced", out)
        self.assertNotIn(TOKEN, out + err)

    def test_failure_exits_1_with_the_reason(self):
        app, _ = make_app()
        code, _, err = run_main(["http://testserver", "--timeout", "0", "--poll", "0"],
                                {"VELA_API_TOKEN": TOKEN}, lambda url, token: authed(app))
        self.assertEqual(code, 1)
        self.assertIn("FALLITO", err)

    def test_format_table(self):
        self.assertEqual(rest_flow.format_table([("intento", 0.25), ("totale", 12.0)]),
                         "| Passo | Secondi |\n|---|---|\n| intento | 0.25 |\n| totale | 12.00 |")


@contextlib.contextmanager
def mock_tick(app):
    """Contro un server vero il worker gira nei suoi thread; in-process la coda avanza a ogni sleep."""
    from unittest import mock
    with mock.patch.object(rest_flow.time, "sleep", lambda s: app.state.worker.drain()):
        yield


if __name__ == "__main__":
    unittest.main()
