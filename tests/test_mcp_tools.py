"""Tool MCP in-process (RF-39, RF-41, RF-10): client dell'SDK collegato al server senza HTTP."""
import json
import unittest
from datetime import timedelta

from mcp import Client

from support import (NOW, FakeHofJ, StubPayments, assert_single_product, inline_worker,
                     make_product)
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain import say
from vela.domain.intent import QUESTION_PAX
from vela.domain.usecases import Vela
from vela.surfaces.mcp import (DESCRIPTIONS, DESCRIPTIONS_SMS, INSTRUCTIONS, INSTRUCTIONS_SMS,
                               TOOL_NAMES, build_mcp)

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
TRAVELER = {"first_name": "Anna", "last_name": "Rossi", "email": "anna@x.it", "phone": "+390000",
            "participants": [{"first_name": "Bo", "last_name": "Bi"}]}
PRODUCTS = [
    make_product(1, price=300, country="IT", destination="Riccione"),
    make_product(2, price=450, country="ES", destination="Madrid"),
    make_product(3, price=350, country="ES", destination="Valencia"),
    make_product(4, price=390, country="ES", destination="Lanzarote"),
]


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_vela(products=None, hofj=None, sms_enabled=False):
    repos = MemoryRepositories()
    repos.products.upsert_many(PRODUCTS if products is None else products)
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, hofj or FakeHofJ(), StubPayments(), now=Clock(), new_id=lambda: next(ids),
                sms_enabled=sms_enabled)


class McpCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.vela = make_vela()
        self.server = build_mcp(lambda: self.vela)

    async def call(self, name, **args):
        async with Client(self.server) as client:
            return await client.call_tool(name, args)

    async def ok(self, name, **args):
        r = await self.call(name, **args)
        self.assertFalse(r.is_error, r.content[0].text if r.content else r)
        assert_single_product(self, r.structured_content)
        return r.structured_content

    async def error_text(self, name, **args):
        r = await self.call(name, **args)
        self.assertTrue(r.is_error)
        self.assertIsNone(r.structured_content)
        return r.content[0].text


class ListToolsTest(McpCase):
    async def tools(self):
        async with Client(self.server) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    async def test_five_tools_named_as_rf39(self):
        self.assertEqual(set(await self.tools()), {"create_intent", "get_proposal", "reject_proposal",
                                                   "accept_proposal", "get_order_status"})
        self.assertEqual(set(TOOL_NAMES), set(await self.tools()))

    async def test_descriptions_are_written_for_voice(self):
        for name, tool in (await self.tools()).items():
            self.assertEqual(tool.description, DESCRIPTIONS[name])
            self.assertIn("Never list", tool.description, name)
            self.assertIn("`say`", tool.description, name)

    async def test_traveler_arguments_are_flat(self):
        tools = await self.tools()
        accept = tools["accept_proposal"].input_schema
        self.assertEqual(accept["required"], ["proposal_id"])
        for field in ("first_name", "last_name", "email", "phone", "participants"):
            self.assertIn(field, accept["properties"])
        self.assertEqual(accept["properties"]["participants"]["anyOf"][0]["type"], "array")
        intent = tools["create_intent"].input_schema
        self.assertEqual(intent["required"], ["text"])
        self.assertIn("pax", intent["properties"])


class FlowTest(McpCase):
    async def test_full_flow_section_10_1(self):
        intent = await self.ok("create_intent", text=INTENT)
        self.assertEqual(intent["intent_id"], "id1")
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        second = await self.ok("reject_proposal", proposal_id=first["proposal_id"], reason="troppo caro")
        self.assertNotEqual(second["product"]["product_id"], first["product"]["product_id"])

        partial = await self.ok("accept_proposal", proposal_id=second["proposal_id"], first_name="Anna")
        self.assertIn("last_name", partial["missing"])
        self.assertIsNone(self.vela.repos.orders.get_by_proposal(second["proposal_id"]))

        accepted = await self.ok("accept_proposal", proposal_id=second["proposal_id"], **TRAVELER)
        self.assertEqual((accepted["status"], accepted["position"]), ("queued", 1))
        self.assertNotIn("payment_url", accepted)
        again = await self.ok("accept_proposal", proposal_id=second["proposal_id"], **TRAVELER)
        self.assertEqual(again["order_id"], accepted["order_id"])

        worker = inline_worker(self.vela)
        worker.drain()                                   # job d'acquisto
        awaiting = await self.ok("get_order_status", order_id=accepted["order_id"])
        self.assertEqual(awaiting["status"], "awaiting_payment")
        self.assertTrue(awaiting["payment_url"].startswith("http://pay.test/"))
        self.vela.orders.mark_paid(accepted["order_id"], "pi_test")
        worker.drain()                                   # job di prenotazione
        status = await self.ok("get_order_status", order_id=accepted["order_id"])
        self.assertEqual(status["status"], "confirmed")
        self.assertEqual(status["booking_code"], "R-000001")
        self.assertIn("R-000001", status["say"])

    async def test_question_persists_nothing(self):
        d = await self.ok("create_intent", text="padel a ottobre")
        self.assertEqual(d, {"question": QUESTION_PAX, "say": QUESTION_PAX})
        self.assertIsNone(self.vela.repos.intents.get("id1"))

    async def test_profile_arguments_reach_the_intent(self):
        d = await self.ok("create_intent", text="padel a ottobre", first_name="Anna", pax=2)
        profile = self.vela.repos.intents.get(d["intent_id"]).profile
        self.assertEqual((profile.first_name, profile.pax), ("Anna", 2))

    async def test_empty_participants_are_missing(self):
        intent = await self.ok("create_intent", text=INTENT)
        proposal = await self.ok("get_proposal", intent_id=intent["intent_id"])
        args = dict(TRAVELER, participants=[])
        d = await self.ok("accept_proposal", proposal_id=proposal["proposal_id"], **args)
        self.assertEqual(d["missing"], ["participants[0].first_name", "participants[0].last_name"])

    async def test_no_match_names_the_criterion(self):
        self.vela = make_vela(products=[])
        intent = await self.ok("create_intent", text=INTENT)
        d = await self.ok("get_proposal", intent_id=intent["intent_id"])
        self.assertIn("failed_criterion", d)

    async def test_text_content_mirrors_structured_content(self):
        r = await self.call("create_intent", text=INTENT)
        self.assertEqual(json.loads(r.content[0].text), r.structured_content)


class DescriptionsM5Test(unittest.TestCase):
    """RF-41: l'accettazione è un'attesa, il link si legge con get_order_status."""

    def test_accept_description_says_wait_not_link(self):
        text = DESCRIPTIONS["accept_proposal"]
        self.assertIn("a wait, not a link", text)
        self.assertIn("get_order_status", text)
        self.assertNotIn("show `payment_url`", text)

    def test_status_description_lists_new_states(self):
        text = DESCRIPTIONS["get_order_status"]
        for state in ("queued", "awaiting_payment", "paid_pending_booking", "confirmed", "replaced",
                      "cancelled", "failed", "booking_failed", "expired", "proposal_changed"):
            self.assertIn(state, text)

    def test_instructions_mention_the_queue(self):
        self.assertIn("queue", INSTRUCTIONS)



# Testi di prima degli SMS (e106b9c): restano identici quando Twilio non è configurato.
PRE_SMS_INSTRUCTIONS_END = (
    "Accepting a proposal puts the order in a queue: the payment link comes later from "
    "get_order_status.")
PRE_SMS_ACCEPT_END = (
    "the order is `queued` with `order_id`, `position` and `wait_seconds`. Get the payment link "
    "with get_order_status after the stated wait, or whenever the user asks.")
PRE_SMS_STATUS_START = (
    "Check an order after the wait stated by accept_proposal, when the user says they paid or "
    "asks how it is going. Returns `status`: queued (with `position` and `wait_seconds`), ")


class SmsTextsTest(unittest.TestCase):
    """C1: gli SMS si annunciano solo se Twilio è configurato (`vela.sms_enabled`)."""

    def test_default_texts_are_the_pre_sms_ones(self):
        self.assertTrue(INSTRUCTIONS.endswith(PRE_SMS_INSTRUCTIONS_END))
        self.assertIn(PRE_SMS_ACCEPT_END, DESCRIPTIONS["accept_proposal"])
        self.assertTrue(DESCRIPTIONS["get_order_status"].startswith(PRE_SMS_STATUS_START))
        for text in (INSTRUCTIONS, DESCRIPTIONS["accept_proposal"], DESCRIPTIONS["get_order_status"]):
            self.assertNotIn("texts", text)

    def test_sms_texts_say_vela_texts_the_link(self):
        self.assertIn("texts the payment link", INSTRUCTIONS_SMS)
        self.assertNotIn("comes later from get_order_status", INSTRUCTIONS_SMS)
        self.assertIn("texts", DESCRIPTIONS_SMS["accept_proposal"])
        self.assertIn("texts", DESCRIPTIONS_SMS["get_order_status"])
        self.assertEqual(set(DESCRIPTIONS_SMS), set(DESCRIPTIONS))
        for name in ("create_intent", "get_proposal", "reject_proposal"):
            self.assertEqual(DESCRIPTIONS_SMS[name], DESCRIPTIONS[name])


class SmsServerTest(unittest.IsolatedAsyncioTestCase):
    async def served(self, get_vela):
        server = build_mcp(get_vela)
        async with Client(server) as client:
            tools = {t.name: t.description for t in (await client.list_tools()).tools}
        return server.instructions, tools

    async def test_sms_disabled_serves_the_pre_sms_texts(self):
        vela = make_vela()
        self.assertFalse(vela.sms_enabled)
        for get_vela in (lambda: vela, lambda: None):
            instructions, tools = await self.served(get_vela)
            self.assertEqual(instructions, INSTRUCTIONS)
            self.assertEqual(tools, DESCRIPTIONS)

    async def test_sms_enabled_serves_the_sms_texts(self):
        vela = make_vela(sms_enabled=True)
        instructions, tools = await self.served(lambda: vela)
        self.assertEqual(instructions, INSTRUCTIONS_SMS)
        self.assertEqual(tools, DESCRIPTIONS_SMS)


class ErrorsTest(McpCase):
    async def test_unknown_ids_read_a_sentence(self):
        cases = [("get_proposal", {"intent_id": "nope"}, "intent"),
                 ("reject_proposal", {"proposal_id": "nope", "reason": "no"}, "proposal"),
                 ("accept_proposal", {"proposal_id": "nope"}, "proposal"),
                 ("get_order_status", {"order_id": "nope"}, "order")]
        for name, args, kind in cases:
            with self.subTest(name):
                self.assertEqual(await self.error_text(name, **args), say.say_not_found(kind))

    async def test_unexpected_error_is_generic_and_logged(self):
        intent = await self.ok("create_intent", text=INTENT)
        proposal = await self.ok("get_proposal", intent_id=intent["intent_id"])

        def boom(*args, **kwargs):
            raise RuntimeError("segreto interno")
        self.vela.accept_proposal = boom
        with self.assertLogs("vela.mcp", "ERROR") as logs:
            text = await self.error_text("accept_proposal", proposal_id=proposal["proposal_id"], **TRAVELER)
        self.assertEqual(text, say.say_error())
        self.assertNotIn("segreto", text)
        self.assertIn("accept_proposal", logs.output[0])

    async def test_accept_returns_queued_shape(self):
        intent = await self.ok("create_intent", text=INTENT)
        proposal = await self.ok("get_proposal", intent_id=intent["intent_id"])
        d = await self.ok("accept_proposal", proposal_id=proposal["proposal_id"], **TRAVELER)
        self.assertEqual(set(d), {"order_id", "status", "position", "wait_seconds", "say"})
        self.assertEqual(self.vela.hofj.calls, [])

    async def test_domain_unavailable(self):
        self.server = build_mcp(lambda: None)
        self.assertEqual(await self.error_text("get_order_status", order_id="x"), say.say_unavailable())

    async def test_invalid_arguments_are_a_tool_error(self):
        with self.assertLogs(level="INFO") as logs:
            r = await self.call("create_intent")
        self.assertTrue(r.is_error)
        self.assertIn("rejected arguments", "\n".join(logs.output))


class AllowedHostsTest(unittest.TestCase):
    def test_allowed_hosts_from_public_url(self):
        from vela.surfaces.mcp import allowed_hosts
        self.assertIn("vela-n506.onrender.com", allowed_hosts("https://vela-n506.onrender.com/"))
        self.assertIn("vela-n506.onrender.com", allowed_hosts("https://vela-n506.onrender.com/x/y"))
        self.assertIn("localhost:8000", allowed_hosts("http://localhost:8000"))
        self.assertEqual(allowed_hosts(None), ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*",
                                               "testserver"])

    def test_allowed_origins_from_public_url(self):
        from vela.surfaces.mcp import allowed_origins
        origins = allowed_origins("https://vela-n506.onrender.com/")
        self.assertIn("https://claude.ai", origins)
        self.assertIn("https://vela-n506.onrender.com", origins)
        self.assertEqual(allowed_origins(None), ["https://claude.ai", "http://localhost:*",
                                                 "http://127.0.0.1:*"])


class RootLoggingTest(unittest.TestCase):
    """`MCPServer()` chiama `logging.basicConfig`: non deve portare il root logger a INFO."""

    def test_build_mcp_keeps_root_logger_at_warning(self):
        import logging
        root = logging.getLogger()
        saved_level, saved_handlers = root.level, root.handlers[:]
        root.handlers[:] = []
        root.setLevel(logging.WARNING)
        try:
            build_mcp(lambda: None)
            self.assertGreaterEqual(root.level, logging.WARNING)
        finally:
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)


class AgentToolContractTest(McpCase):
    """M17: campi strutturati (RF-52), descrizioni (RF-41), UC1, UC4, UC7, UC8."""

    FIELDS = {"sport", "area", "period_start", "period_end", "pax", "budget"}

    async def tools(self):
        async with Client(self.server) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    async def test_structured_fields_are_optional_arguments(self):
        tools = await self.tools()
        intent = tools["create_intent"].input_schema
        reject = tools["reject_proposal"].input_schema
        self.assertLessEqual(self.FIELDS, set(intent["properties"]))
        self.assertLessEqual(self.FIELDS | {"direction"}, set(reject["properties"]))
        self.assertNotIn("direction", intent["properties"])
        self.assertEqual(intent["required"], ["text"])
        self.assertEqual(reject["required"], ["proposal_id"])

    def test_descriptions_route_changes_through_reject_proposal(self):
        texts = dict(DESCRIPTIONS, instructions=INSTRUCTIONS)
        for name, text in texts.items():
            with self.subTest(name=name):
                self.assertNotIn("rephrase", text.lower())
                self.assertNotIn("reformulat", text.lower())
        self.assertIn("Padel or tennis", DESCRIPTIONS["create_intent"])
        for name in ("create_intent", "get_proposal", "reject_proposal"):
            with self.subTest(name=name):
                self.assertIn("reject_proposal", DESCRIPTIONS[name])
                self.assertIn("never", DESCRIPTIONS[name].lower())
        for piece in ("north", "south", "rejected_proposal_id", "cooler", "warmer"):
            self.assertIn(piece, DESCRIPTIONS["reject_proposal"])
        self.assertIn("reject_proposal", INSTRUCTIONS)

    async def test_uc1_fields_reach_the_intent(self):
        d = await self.ok("create_intent", text=INTENT, sport="padel", area="Spagna",
                          period_start="2026-10-01", period_end="2026-10-31", pax=2, budget=800)
        c = d["criteria"]
        self.assertEqual((c["sport"], c["area"]["name"], c["pax"], c["budget"]),
                         ("padel", "Spagna", 2, "800.00"))
        self.assertTrue(d["say"].startswith("Ho capito: un viaggio di padel in Spagna"))

    async def test_uc4_reject_with_direction_keeps_the_intent(self):
        self.vela = make_vela(products=[make_product(1, price=300, destination="Siviglia"),
                                        make_product(2, price=450, destination="Madrid")])
        intent = await self.ok("create_intent", text=INTENT)
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        self.assertEqual(first["product"]["destination"], "Siviglia")
        d = await self.ok("reject_proposal", proposal_id=first["proposal_id"],
                          reason="Troppo caldo, vorrei un posto più fresco", direction="north")
        self.assertEqual(d["intent_id"], intent["intent_id"])
        self.assertEqual(d["product"]["destination"], "Madrid")

    async def test_uc7_invalid_field_is_declared_not_an_error(self):
        d = await self.ok("create_intent", text="Padel a Atlantide, siamo in tre.", sport="padel",
                          area="Atlantide", pax=3, budget=1000)
        self.assertIsNone(d["criteria"]["area"])
        self.assertTrue(d["say"].startswith("Non conosco il luogo Atlantide."))

    async def test_uc7_sport_outside_the_values_is_declared(self):
        d = await self.ok("create_intent", text="una vacanza per due", sport="golf")
        self.assertEqual(d["question"], "Padel o tennis?")
        self.assertIn("golf", d["say"])

    async def test_uc8_field_wins_over_text(self):
        with self.assertLogs("vela.domain.usecases", "INFO"):
            d = await self.ok("create_intent", text="Tennis a Roma a maggio, siamo in due",
                              sport="padel")
        self.assertEqual(d["criteria"]["sport"], "padel")

    async def test_no_match_after_reject_carries_the_proposal_to_restart_from(self):
        self.vela = make_vela(products=[make_product(1, price=300, destination="Siviglia")])
        intent = await self.ok("create_intent", text=INTENT)
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        d = await self.ok("reject_proposal", proposal_id=first["proposal_id"], reason="no")
        self.assertEqual(d["rejected_proposal_id"], first["proposal_id"])
