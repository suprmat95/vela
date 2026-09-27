"""`/mcp` montato nell'app FastAPI: JSON-RPC su HTTP, stateless, protezione Host/Origin."""
import unittest

from fastapi.testclient import TestClient

from support import NOW, FakeHofJ, StubPayments, inline_worker, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.app import create_app
from vela.config import Settings
from vela.domain import say
from vela.domain.usecases import Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"}}


def make_app(public_url="http://test", with_domain=True):
    vela = None
    worker = None
    if with_domain:
        repos = MemoryRepositories()
        repos.products.upsert_many([make_product(3, price=350, country="ES", destination="Valencia")])
        vela = Vela(repos, FakeHofJ(), StubPayments(), now=lambda: NOW)
        worker = inline_worker(vela)
    return create_app(Settings(vela_upstream_mode="replay", vela_public_url=public_url),
                      vela=vela, worker=worker, catalog_loader=None)


def rpc(client, method, params=None, **headers):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=dict(HEADERS, **headers), follow_redirects=False)


class McpHttpTest(unittest.TestCase):
    def test_post_mcp_is_not_redirected(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "initialize", INIT)
        self.assertEqual(r.status_code, 200)

    def test_initialize_is_stateless_json(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "initialize", INIT)
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        self.assertNotIn("mcp-session-id", r.headers)
        result = r.json()["result"]
        self.assertEqual(result["serverInfo"]["name"], "vela")
        self.assertIn("exactly ONE", result["instructions"])

    def test_tools_list_over_http(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "tools/list", **{"MCP-Protocol-Version": "2025-06-18"})
        names = {t["name"] for t in r.json()["result"]["tools"]}
        self.assertEqual(names, {"create_intent", "get_proposal", "get_proposal_details",
                                 "reject_proposal", "accept_proposal", "get_order_status"})

    def test_tool_call_over_http(self):
        with TestClient(make_app()) as c:
            r = rpc(c, "tools/call", {"name": "create_intent", "arguments": {"text": INTENT}},
                    **{"MCP-Protocol-Version": "2025-06-18"})
        result = r.json()["result"]
        self.assertFalse(result.get("isError", False))
        self.assertIn("intent_id", result["structuredContent"])

    def test_without_domain_tools_say_unavailable(self):
        with TestClient(create_app(Settings())) as c:
            r = rpc(c, "tools/call", {"name": "get_order_status", "arguments": {"order_id": "x"}},
                    **{"MCP-Protocol-Version": "2025-06-18"})
        result = r.json()["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], say.say_unavailable())


class McpSecurityTest(unittest.TestCase):
    def test_unknown_host_is_421(self):
        with TestClient(make_app()) as c, self.assertLogs(level="WARNING") as logs:
            self.assertEqual(rpc(c, "initialize", INIT, Host="evil.example").status_code, 421)
        self.assertIn("Invalid Host header", "\n".join(logs.output))

    def test_public_url_host_is_accepted(self):
        with TestClient(make_app(public_url="https://vela-n506.onrender.com/")) as c:
            r = rpc(c, "initialize", INIT, Host="vela-n506.onrender.com")
        self.assertEqual(r.status_code, 200)

    def test_foreign_origin_is_403(self):
        with TestClient(make_app()) as c, self.assertLogs(level="WARNING") as logs:
            self.assertEqual(rpc(c, "initialize", INIT, Origin="https://evil.example").status_code, 403)
        self.assertIn("Invalid Origin header", "\n".join(logs.output))

    def test_claude_origin_is_accepted(self):
        with TestClient(make_app()) as c:
            self.assertEqual(rpc(c, "initialize", INIT, Origin="https://claude.ai").status_code, 200)


class OtherRoutesTest(unittest.TestCase):
    def test_other_routes_are_unchanged(self):
        with TestClient(make_app()) as c:
            self.assertEqual(c.post("/health").status_code, 405)
            self.assertEqual(c.get("/nope").status_code, 404)
            self.assertEqual(c.get("/replay/checkout/nope").status_code, 404)
            self.assertIn(c.get("/health").status_code, (200, 503))

    def test_mcp_route_is_present_in_every_mode(self):
        for settings in (Settings(), Settings(vela_upstream_mode="live")):
            paths = [getattr(r, "path", None) for r in create_app(settings).routes]
            self.assertIn("/mcp", paths)
