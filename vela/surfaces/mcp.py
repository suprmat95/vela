"""Superficie MCP (RF-41): i cinque casi d'uso di RF-39 come tool Streamable HTTP su ``/mcp``.

Adapter sottile: argomenti piatti → ``TravelerProfile`` → caso d'uso → ``to_dict()``, restituito
come ``structuredContent`` e come testo JSON. Gli errori diventano un risultato ``isError`` con
una frase italiana pronta da leggere, mai un messaggio interno. Trasporto stateless con risposte
JSON; nessuna autenticazione fino a M8 (RF-43). Le istruzioni sono in inglese, ``say`` in italiano.
"""
import json
import logging
from typing import Annotated, Callable, List, Optional
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from vela.domain import say
from vela.domain.models import Participant, StructuredFields, TravelerProfile
from vela.domain.usecases import NotFound, Vela
from vela.ports.payments import PaymentsError

log = logging.getLogger("vela.mcp")

MCP_PATH = "/mcp"
TOOL_NAMES = ("create_intent", "get_proposal", "reject_proposal", "accept_proposal", "get_order_status")
LOCAL_HOSTS = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "testserver"]
LOCAL_ORIGINS = ["http://localhost:*", "http://127.0.0.1:*"]
CLAUDE_ORIGIN = "https://claude.ai"

_INSTRUCTIONS_BASE = (
    "Vela books a padel or tennis trip with hotel from one sentence of the user. "
    "Always propose exactly ONE option at a time: never list, compare or invent alternatives, "
    "and never search or suggest trips yourself. After every tool call, speak the `say` field "
    "to the user verbatim, in the user's language. Never read URLs aloud: when there is a "
    "payment link, tell the user it is in the chat. Call get_proposal right after create_intent "
    "returns an intent_id. Once a proposal exists, every change the user asks for (place, dates, "
    "sport, budget, people, somewhere cooler or warmer) goes through reject_proposal on that "
    "proposal, never through a new create_intent. Accepting a proposal puts the order in a "
    "queue: "
)
# Senza Twilio configurato nessun SMS parte: restano i testi di prima degli SMS (C1).
INSTRUCTIONS = _INSTRUCTIONS_BASE + "the payment link comes later from get_order_status."
INSTRUCTIONS_SMS = _INSTRUCTIONS_BASE + (
    "Vela texts the payment link and later the booking confirmation to the traveler's "
    "phone, so do not poll get_order_status on your own: call it whenever the user asks how it "
    "is going or says they paid, and once if the user says the text has not arrived.")

_VOICE = (" Speak the `say` field verbatim. Never list alternatives, never compare options, "
          "never mention other trips.")

_ACCEPT = (
    "Call only after the user explicitly says yes to the current proposal. Pass the details "
    "the user gave you: first_name, last_name, email and phone of the main traveler, plus "
    "first and last name of every other participant. If the result has `missing`, ask the "
    "user only for those details and call accept_proposal again with everything you have: "
    "calling it again never creates a second order. On success the answer is a wait, not a "
    "link: the order is `queued` with `order_id`, `position` and `wait_seconds`.")
_STATES = (
    " Returns `status`: queued (with `position` and `wait_seconds`), "
    "awaiting_payment (with `payment_url` and the real `total`: show the link in the chat, "
    "never read it aloud), paid_pending_booking, confirmed (with `booking_code`), replaced "
    "(`proposal_changed` is true and `proposal` is the new single trip: speak it and ask if "
    "the user likes it), cancelled, failed or booking_failed (with `failure_reason`), expired."
    + _VOICE)

DESCRIPTIONS = {
    "create_intent": (
        "Start a trip request from the user's own words. If the user has not said padel, tennis "
        "or that either is fine, first ask \"Padel or tennis?\" and wait for the answer. Pass "
        "the user's sentence verbatim in `text`, plus every criterion you already understood as "
        "a field: `sport` (padel, tennis, or any when either is fine), `area`, `period_start` and "
        "`period_end`, `pax`, `budget`. Leave out what the user did not say: never guess. Add "
        "traveler details only if the user already gave them. Returns either `intent_id` (then "
        "call get_proposal immediately) or `question` (ask the user exactly that question, then "
        "call create_intent again with the original sentence plus the answer). Use it only "
        "before a proposal exists: after a proposal never call it again, every change goes "
        "through reject_proposal." + _VOICE),
    "get_proposal": (
        "Get the single trip Vela proposes for an intent. Returns one proposal (`proposal_id`, "
        "`product`, dates, price from) or, when nothing fits, `failed_criterion`: then no "
        "proposal exists yet, so ask the user which criterion to change and call create_intent "
        "with the changed criteria. After speaking the proposal, ask if the user likes it; from "
        "then on every change goes through reject_proposal, never a new create_intent." + _VOICE),
    "reject_proposal": (
        "The user said no to the current proposal or wants to change something about it (place, "
        "dates, sport, budget, people). Always use this tool for changes after a proposal, never "
        "a new create_intent: the intent keeps what the user already turned down. Pass the "
        "user's reason in their own words in `reason`, plus only the criteria that changed as "
        "fields (`sport`, `area`, `period_start`, `period_end`, `pax`, `budget`), and "
        "`direction`: north when the user wants somewhere cooler, south when they want somewhere "
        "warmer. Returns the next single proposal, or `failed_criterion` with "
        "`rejected_proposal_id` when nothing else fits: ask what to change, then call "
        "reject_proposal again on `rejected_proposal_id` with the updated fields." + _VOICE),
    "accept_proposal": _ACCEPT + (
        " Get the payment link with get_order_status after the stated wait, or whenever the user "
        "asks." + _VOICE),
    "get_order_status": (
        "Check an order after the wait stated by accept_proposal, when the user says they paid or "
        "asks how it is going." + _STATES),
}

DESCRIPTIONS_SMS = dict(DESCRIPTIONS, **{
    "accept_proposal": _ACCEPT + (
        " Vela texts the payment link to the traveler's phone when it is ready and texts again "
        "when the booking is confirmed. Do not poll get_order_status on your own: call it "
        "whenever the user asks how it is going, and once if the user says the text has not "
        "arrived." + _VOICE),
    "get_order_status": (
        "Vela already texts the payment link and the confirmation, so do not poll: check an "
        "order whenever the user asks how it is going or says they paid, and once if the user "
        "says the text has not arrived." + _STATES),
})


def texts(sms_enabled: bool):
    """Istruzioni e descrizioni: con gli SMS solo se partono davvero (Twilio configurato)."""
    return (INSTRUCTIONS_SMS, DESCRIPTIONS_SMS) if sms_enabled else (INSTRUCTIONS, DESCRIPTIONS)


class ParticipantArg(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


Text = Annotated[str, Field(description="The user's request, verbatim, in their own words.")]
FirstName = Annotated[Optional[str], Field(description="Main traveler's first name, only if the user said it.")]
LastName = Annotated[Optional[str], Field(description="Main traveler's last name, only if the user said it.")]
Email = Annotated[Optional[str], Field(description="Main traveler's email, only if the user said it.")]
Phone = Annotated[Optional[str], Field(description="Main traveler's phone number, only if the user said it.")]
Pax = Annotated[Optional[int], Field(description="Number of travelers, only if the user said it.")]
Sport = Annotated[Optional[str], Field(
    description="padel, tennis, or any when the user said either is fine. Only if the user said it.")]
Area = Annotated[Optional[str], Field(
    description="Place the user named: country, region or city, e.g. Spagna, Maiorca, Madrid.")]
PeriodStart = Annotated[Optional[str], Field(description="First day of the period, YYYY-MM-DD.")]
PeriodEnd = Annotated[Optional[str], Field(description="Last day of the period, YYYY-MM-DD.")]
Budget = Annotated[Optional[float], Field(
    description="Maximum total budget in euros for the whole group, only if the user said it.")]
Direction = Annotated[Optional[str], Field(
    description="north when the user wants somewhere cooler, south when somewhere warmer.")]
Participants = Annotated[Optional[List[ParticipantArg]],
                         Field(description="First and last name of each traveler other than the main one.")]
IntentId = Annotated[str, Field(description="The intent_id returned by create_intent.")]
ProposalId = Annotated[str, Field(description="The proposal_id of the current proposal.")]
Reason = Annotated[str, Field(description="Why the user said no, in their own words.")]
OrderId = Annotated[str, Field(description="The order_id returned by accept_proposal.")]


def traveler_profile(first_name=None, last_name=None, email=None, phone=None, pax=None,
                     participants=None) -> TravelerProfile:
    return TravelerProfile(first_name=first_name, last_name=last_name, email=email, phone=phone,
                           pax=pax, participants=tuple(Participant(p.first_name, p.last_name)
                                                       for p in participants or ()))


def ok(response) -> CallToolResult:
    d = response.to_dict()
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(d, ensure_ascii=False))],
                          structured_content=d)


def fail(sentence: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=sentence)], is_error=True)


def build_mcp(get_vela: Callable[[], Optional[Vela]]) -> MCPServer:
    """Server MCP con i cinque tool. ``get_vela`` è letto a ogni chiamata; alla costruzione
    sceglie i testi con o senza SMS da ``vela.sms_enabled`` (senza Vela: senza SMS)."""
    vela = get_vela()
    instructions, descriptions = texts(bool(vela is not None and vela.sms_enabled))
    # MCPServer() chiama logging.basicConfig: WARNING evita di portare a INFO il root dell'app.
    server = MCPServer("vela", title="Vela", instructions=instructions, version="0.1.0",
                       log_level="WARNING")

    def run(name: str, use_case: Callable[[Vela], object]) -> CallToolResult:
        vela = get_vela()
        if vela is None:
            return fail(say.say_unavailable())
        try:
            return ok(use_case(vela))
        except NotFound as exc:
            return fail(say.say_not_found(exc.kind))
        except PaymentsError:
            log.warning("tool MCP %s: link di pagamento non creato", name)
            return fail(say.say_payments_unavailable())
        except Exception:   # noqa: BLE001 - nessun dettaglio interno verso il modello
            log.exception("tool MCP %s fallito", name)
            return fail(say.say_error())

    @server.tool(description=descriptions["create_intent"])
    def create_intent(text: Text, sport: Sport = None, area: Area = None,
                      period_start: PeriodStart = None, period_end: PeriodEnd = None,
                      pax: Pax = None, budget: Budget = None, first_name: FirstName = None,
                      last_name: LastName = None, email: Email = None, phone: Phone = None,
                      participants: Participants = None) -> CallToolResult:
        profile = traveler_profile(first_name, last_name, email, phone, pax, participants)
        fields = StructuredFields(sport, area, period_start, period_end, pax, budget)
        return run("create_intent", lambda v: v.create_intent(text, profile, fields))

    @server.tool(description=descriptions["get_proposal"])
    def get_proposal(intent_id: IntentId) -> CallToolResult:
        return run("get_proposal", lambda v: v.get_proposal(intent_id))

    @server.tool(description=descriptions["reject_proposal"])
    def reject_proposal(proposal_id: ProposalId, reason: Reason = "", sport: Sport = None,
                        area: Area = None, period_start: PeriodStart = None,
                        period_end: PeriodEnd = None, pax: Pax = None, budget: Budget = None,
                        direction: Direction = None) -> CallToolResult:
        fields = StructuredFields(sport, area, period_start, period_end, pax, budget, direction)
        return run("reject_proposal", lambda v: v.reject_proposal(proposal_id, reason, fields))

    @server.tool(description=descriptions["accept_proposal"])
    def accept_proposal(proposal_id: ProposalId, first_name: FirstName = None,
                        last_name: LastName = None, email: Email = None, phone: Phone = None,
                        participants: Participants = None) -> CallToolResult:
        profile = traveler_profile(first_name, last_name, email, phone, None, participants)
        return run("accept_proposal", lambda v: v.accept_proposal(proposal_id, profile))

    @server.tool(description=descriptions["get_order_status"])
    def get_order_status(order_id: OrderId) -> CallToolResult:
        return run("get_order_status", lambda v: v.get_order_status(order_id))

    return server


def allowed_hosts(public_url: Optional[str]) -> List[str]:
    hosts = list(LOCAL_HOSTS)
    netloc = urlparse(public_url).netloc if public_url else ""
    if netloc and netloc not in hosts:
        hosts.append(netloc)
    return hosts


def allowed_origins(public_url: Optional[str]) -> List[str]:
    origins = [CLAUDE_ORIGIN] + LOCAL_ORIGINS
    parsed = urlparse(public_url) if public_url else None
    if parsed is not None and parsed.scheme and parsed.netloc:
        origins.append("%s://%s" % (parsed.scheme, parsed.netloc))
    return origins


def mcp_routes(server: MCPServer, public_url: Optional[str]) -> list:
    """Route Streamable HTTP su ``/mcp`` da innestare nel router FastAPI.

    Innestate e non montate: ``Mount("/mcp")`` risponde 307 a ``POST /mcp`` e ``Mount("/")``
    trasformerebbe i 405 dell'app in 404. ``server.session_manager.run()`` va aperto nel
    lifespan dell'app, perché le route innestate non eseguono il lifespan della sottoapp.
    """
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                         allowed_hosts=allowed_hosts(public_url),
                                         allowed_origins=allowed_origins(public_url))
    http = server.streamable_http_app(streamable_http_path=MCP_PATH, json_response=True,
                                      stateless_http=True, transport_security=security)
    return list(http.routes)
