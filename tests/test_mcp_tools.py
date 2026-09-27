"""Tool MCP in-process (RF-39, RF-41, RF-10): client dell'SDK collegato al server senza HTTP."""
import json
import unittest
from dataclasses import replace
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
        worker.drain()                                   # job d'acquisto: prezzo effettivo
        priced = await self.ok("get_order_status", order_id=accepted["order_id"])
        self.assertEqual((priced["status"], priced["payment_url"]), ("awaiting_confirmation", None))
        self.assertIn("Confermi?", priced["say"])
        confirmed = await self.ok("accept_proposal", proposal_id=second["proposal_id"])   # il sì
        self.assertEqual(confirmed["order_id"], accepted["order_id"])
        worker.drain()                                   # link
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
        self.assertIn("awaiting_confirmation", text)             # prima il prezzo effettivo
        self.assertIn("call accept_proposal again on the same proposal", text)
        self.assertIn("get_order_status", text)
        self.assertNotIn("show `payment_url`", text)

    def test_status_description_lists_new_states(self):
        text = DESCRIPTIONS["get_order_status"]
        for state in ("queued", "awaiting_payment", "paid_pending_booking", "confirmed", "replaced",
                      "cancelled", "failed", "booking_failed", "expired", "proposal_changed"):
            self.assertIn(state, text)
        self.assertIn("awaiting_confirmation", text)

    def test_instructions_mention_the_queue(self):
        self.assertIn("queue", INSTRUCTIONS)



# Testi senza SMS: quelli di prima degli SMS (e106b9c) con la conferma del prezzo (2026-09-26).
PRE_SMS_INSTRUCTIONS_END = (
    "Only after that confirmation the payment link comes in the answer, or later from "
    "get_order_status.")
PRE_SMS_ACCEPT_END = (
    "the answer is `queued` with `order_id`, `position` and `wait_seconds`. If the answer is "
    "`queued`, check with get_order_status after the stated wait, or whenever the user asks.")
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

    def test_sms_texts_forbid_polling_but_always_answer_the_user(self):
        # I1 (decisione dell'utente 2026-09-26): mai interrogare di propria iniziativa, sempre
        # quando l'utente chiede, e una volta se dice che l'SMS non è arrivato
        for name, text in (("instructions", INSTRUCTIONS_SMS),
                           ("accept_proposal", DESCRIPTIONS_SMS["accept_proposal"]),
                           ("get_order_status", DESCRIPTIONS_SMS["get_order_status"])):
            with self.subTest(name=name):
                self.assertIn("poll", text)
                self.assertIn("whenever the user asks how it is going", text)
                self.assertIn("once if the user says the text has not arrived", text)
                self.assertNotIn("only when", text)


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

    def test_proposal_description_says_how_vela_picks(self):
        """M21-B (RF-60): l'agente sa che la scelta non è "il più economico"."""
        text = DESCRIPTIONS["get_proposal"]
        for word in ("area", "budget", "length", "earliest departure", "featured", "then price"):
            self.assertIn(word, text, word)
        self.assertIn("do not present it as the cheapest option", text)

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
                          area="Atlantide", pax=3, rooms=2, budget=1000)
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


def trip(pid, nights, price, **kw):
    """Prodotto a finestra fissa di `nights` notti dal 1 ottobre."""
    end = "2026-10-%02d" % (1 + nights)
    return replace(make_product(pid, price=price, windows=(("2026-10-01", end),), **kw),
                   duration_days=nights + 1)


class DurationContractTest(McpCase):
    """M21-A (UC-A): durata come campi opzionali, criterio morbido, `nights` nella proposta."""

    WEEK_CHEAP, WEEKEND = trip(1, 7, 300), trip(2, 3, 400)

    async def test_duration_fields_are_optional_integer_arguments(self):
        async with Client(self.server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("create_intent", "reject_proposal"):
            props = tools[name].input_schema["properties"]
            for field in ("duration_min_nights", "duration_max_nights"):
                with self.subTest(tool=name, field=field):
                    self.assertIn("integer", json.dumps(props[field]))
                    self.assertIn("nights", props[field]["description"])
                    self.assertNotIn(field, tools[name].input_schema["required"])
            self.assertIn("duration_min_nights", DESCRIPTIONS[name])

    async def test_fields_reach_the_intent_and_the_say(self):
        d = await self.ok("create_intent", text=INTENT, duration_min_nights=6, duration_max_nights=8)
        c = d["criteria"]
        self.assertEqual((c["duration_min_nights"], c["duration_max_nights"]), (6, 8))
        self.assertIn("da 6 a 8 notti", d["say"])

    async def test_invalid_duration_is_declared_not_an_error(self):
        d = await self.ok("create_intent", text="padel a ottobre, siamo in due",
                          duration_min_nights=0)
        self.assertIsNone(d["criteria"]["duration_min_nights"])
        self.assertTrue(d["say"].startswith("Non ho potuto usare 0 - ? come durata in notti."))

    async def test_weekend_is_preferred_then_too_short_moves_to_the_week(self):
        self.vela = make_vela(products=[self.WEEK_CHEAP, self.WEEKEND])
        intent = await self.ok("create_intent", text=INTENT)
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        self.assertEqual((first["product"]["product_id"], first["nights"]), ("2", 3))
        d = await self.ok("reject_proposal", proposal_id=first["proposal_id"], reason="troppo corto")
        self.assertEqual((d["product"]["product_id"], d["nights"]), ("1", 7))

    async def test_reject_with_duration_fields(self):
        # senza i campi la proposta successiva sarebbe l'altro weekend (id 3)
        self.vela = make_vela(products=[self.WEEK_CHEAP, self.WEEKEND, trip(3, 2, 450)])
        intent = await self.ok("create_intent", text="un weekend di padel in Spagna a ottobre, "
                                                     "siamo in due")
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        d = await self.ok("reject_proposal", proposal_id=first["proposal_id"],
                          reason="no grazie", duration_min_nights=6, duration_max_nights=8)
        self.assertEqual((d["product"]["product_id"], d["nights"]), ("1", 7))

    async def test_no_weekend_is_declared(self):
        self.vela = make_vela(products=[self.WEEK_CHEAP])
        intent = await self.ok("create_intent", text=INTENT)
        d = await self.ok("get_proposal", intent_id=intent["intent_id"])
        self.assertIn("Non ho weekend compatibili: questo dura 7 notti, dal 1 all'8 ottobre.",
                      d["say"])


class BudgetScopeContractTest(McpCase):
    """M21-E (UC-E): `budget_scope` opzionale, cifra passata come detta, lettura nel `say`."""

    THREE = "tennis in Spagna a ottobre, siamo in tre, due camere"

    def setUp(self):
        super().setUp()
        self.vela = make_vela(products=[make_product(1, price=400, sport="tennis"),
                                        make_product(2, price=500, sport="tennis")])

    async def test_budget_scope_is_an_optional_argument(self):
        async with Client(self.server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("create_intent", "reject_proposal"):
            with self.subTest(tool=name):
                schema = tools[name].input_schema
                self.assertIn("per_person", schema["properties"]["budget_scope"]["description"])
                self.assertNotIn("budget_scope", schema["required"])
                self.assertIn("never multiply or divide",
                              schema["properties"]["budget"]["description"])
                self.assertIn("budget_scope", DESCRIPTIONS[name])
                self.assertIn("budget_scope", DESCRIPTIONS_SMS[name])

    async def test_field_reaches_the_criteria_and_the_say(self):
        # senza il campo la regola 4 leggerebbe 600 a persona (il più economico costa 1200)
        d = await self.ok("create_intent", text=self.THREE + ", massimo 600 euro", budget=600,
                          budget_scope="total")
        c = d["criteria"]
        self.assertEqual((c["budget"], c["budget_scope"]), ("600.00", "total"))
        self.assertIn("con un budget di 600 euro in tutto", d["say"])

    async def test_bare_figure_is_read_by_the_server(self):
        d = await self.ok("create_intent", text=self.THREE + ", massimo 600 euro", budget=600)
        self.assertEqual(d["criteria"]["budget_scope"], "per_person")

    async def test_invalid_scope_is_declared_not_an_error(self):
        d = await self.ok("create_intent", text=self.THREE + ", 1800 euro", budget_scope="each")
        self.assertEqual(d["criteria"]["budget_scope"], "total")   # 1800 copre 400 × 3
        self.assertTrue(d["say"].startswith("Non ho potuto usare each come lettura del budget"))

    async def test_reject_with_budget_scope(self):
        intent = await self.ok("create_intent", text=self.THREE + ", 1800 euro in tutto")
        first = await self.ok("get_proposal", intent_id=intent["intent_id"])
        d = await self.ok("reject_proposal", proposal_id=first["proposal_id"],
                          reason="no", budget_scope="per_person")
        self.assertIn("con un budget di 1800 euro a persona, 5400 in tutto", d["say"])


class RoomsContractTest(McpCase):
    """M21-D (UC-D, RF-65): `rooms` sui tool; con più di 2 persone senza camere `question`."""

    FIVE = "padel in Portogallo a novembre, siamo in cinque"

    async def test_rooms_is_an_optional_argument_of_intent_and_reject(self):
        async with Client(self.server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("create_intent", "reject_proposal"):
            with self.subTest(tool=name):
                schema = tools[name].input_schema
                self.assertIn("rooms", schema["properties"])
                self.assertNotIn("rooms", schema["required"])

    async def test_five_without_rooms_is_a_question(self):
        d = await self.ok("create_intent", text=self.FIVE, sport="padel", pax=5)
        self.assertEqual(d["question"], "In quante camere?")
        self.assertNotIn("intent_id", d)

    async def test_five_with_rooms_is_created(self):
        d = await self.ok("create_intent", text=self.FIVE, sport="padel", pax=5, rooms=3)
        self.assertEqual((d["criteria"]["pax"], d["criteria"]["rooms"]), (5, 3))
        self.assertIn("per 5 persone in 3 camere", d["say"])
