"""Superficie MCP (RF-41): i casi d'uso di RF-39 e RF-83 come tool Streamable HTTP su ``/mcp``.

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
TOOL_NAMES = ("create_intent", "get_proposal", "get_proposal_details", "reject_proposal",
              "accept_proposal", "get_order_status")
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
    "proposal, never through a new create_intent. Accepting a proposal puts the order in a queue "
    "and Vela gets the actual price from the supplier: the answer is `awaiting_confirmation` with the real "
    "`total`. Speak it and ask the user to confirm; if they say yes call accept_proposal again "
    "on the same proposal, if they say no or it is too expensive call reject_proposal. Only "
    "after that confirmation "
)
# Senza Twilio configurato nessun SMS parte: restano i testi di prima degli SMS (C1).
INSTRUCTIONS = _INSTRUCTIONS_BASE + (
    "the payment link comes in the answer, or later from get_order_status.")
INSTRUCTIONS_SMS = _INSTRUCTIONS_BASE + (
    "Vela texts the payment link and later the booking confirmation to the traveler's phone, "
    "so do not poll get_order_status on your own: call it whenever the user asks how it "
    "is going or says they paid, and once if the user says the text has not arrived.")

_VOICE = (" Speak the `say` field verbatim. Never list alternatives, never compare options, "
          "never mention other trips.")

_ACCEPT = (
    "Call only after the user explicitly says yes to the current proposal. Pass the details "
    "the user gave you: first_name, last_name, email and phone of the main traveler, plus "
    "first and last name of every other participant. If the result has `missing`, ask the "
    "user only for those details and call accept_proposal again with everything you have: "
    "calling it again never creates a second order. Pass `rooms` only if the user corrects the "
    "number of hotel rooms at the last moment; if the answer is `question`, the rooms are too "
    "few for this trip: ask the user and call accept_proposal again with `rooms`. The call can take up to about a minute and "
    "a half: Vela waits for the supplier. The answer is usually `awaiting_confirmation` with "
    "the actual `total`: speak `say` and wait for the user. If the user confirms the price, call "
    "accept_proposal again on the same proposal: that is the confirmation, and the answer is "
    "`awaiting_payment` with `payment_url`. If the user does not accept the price, call "
    "reject_proposal with their reason. If the supplier is slow the answer is `queued` with "
    "`order_id`, `position` and `wait_seconds`.")
_STATES = (
    " Returns `status`: queued (with `position` and `wait_seconds`), awaiting_confirmation "
    "(with the actual `total`: speak `say`, then call accept_proposal again on the same proposal "
    "if the user confirms, reject_proposal if not), awaiting_payment (with `payment_url` and "
    "the real `total`: show the link in the chat, never read it aloud), paid_pending_booking, confirmed (with `booking_code`), replaced "
    "(`proposal_changed` is true and `proposal` is the new single trip: speak it and ask if "
    "the user likes it), cancelled, failed or booking_failed (with `failure_reason`), expired "
    "(the payment link expired, or the order was closed in the queue after a long silence with "
    "nothing to pay: speak `say`)."
    + _VOICE)

DESCRIPTIONS = {
    "create_intent": (
        "Start a trip request from the user's own words. If the user has not said padel, tennis "
        "or that either is fine, first ask \"Padel or tennis?\" and wait for the answer. Pass "
        "the user's sentence verbatim in `text`, plus every criterion you already understood as "
        "a field: `sport` (padel, tennis, or any when either is fine), `area`, `period_start` and "
        "`period_end`, `pax`, `budget` (the figure as the user said it, never multiplied or "
        "divided by the people) with `budget_scope` (per_person or total) only if the user said "
        "it explicitly, and the trip length in nights as `duration_min_nights` and "
        "`duration_max_nights` (a weekend is 1 to 3, a long weekend 2 to 4, a week 6 to 8, N days "
        "is N-1 nights), the playing level as `level` (beginner, intermediate or advanced) and "
        "`wants_coaching` (true if the user wants lessons or a coach, false if they said no "
        "lessons), and the hotel rooms as `rooms`. With more than 2 people, if the user "
        "has not said how many rooms, first ask \"In quante camere?\" / \"How many rooms?\" and "
        "wait for the answer; with 1 or 2 people leave `rooms` out unless the user said it, Vela "
        "assumes one room. Leave out what the user did not say: never guess. Add "
        "traveler details only if the user already gave them. Returns either `intent_id` (then "
        "call get_proposal immediately) or `question` (ask the user exactly that question, then "
        "call create_intent again with the original sentence plus the answer). Use it only "
        "before a proposal exists: after a proposal never call it again, every change goes "
        "through reject_proposal." + _VOICE),
    "get_proposal": (
        "Get the single trip Vela proposes for an intent. Vela picks it by area, budget, trip "
        "length, level and lessons, earliest departure in the period, featured trips, then price, "
        "so do not present "
        "it as the cheapest option: the `say` explains the choice. Returns one proposal (`proposal_id`, "
        "`product`, dates, price from) or, when nothing fits, `failed_criterion`: then no "
        "proposal exists yet, so ask the user which criterion to change and call create_intent "
        "with the changed criteria. After speaking the proposal, ask if the user likes it; from "
        "then on every change goes through reject_proposal, never a new create_intent." + _VOICE),
    "get_proposal_details": (
        "Call only when the user asks about the current proposal: the day-by-day program, what "
        "is included, the hotel, the club, how many hours of play, the level or who the trip is "
        "for. Returns `program` (sections of days with events, or null when the supplier has no "
        "day-by-day program), `description`, `why_this_trip`, `hotel`, `venue`, `playing_hours`, "
        "`style`, `goal`, `best_for_level` and `accepts_companions`, in the catalogue language. "
        "Speak `say`, then answer the user's question in a few sentences from these fields, in "
        "the user's language: never read everything, never read markdown symbols. Say nothing "
        "the fields do not contain. It changes nothing: the proposal stays the same, and any "
        "change still goes through reject_proposal." + _VOICE),
    "reject_proposal": (
        "The user said no to the current proposal or wants to change something about it (place, "
        "dates, length, sport, budget, people, rooms, level, lessons). Always use this tool for "
        "changes after a proposal, never "
        "a new create_intent: the intent keeps what the user already turned down. Pass the "
        "user's reason in their own words in `reason`, plus only the criteria that changed as "
        "fields (`sport`, `area`, `period_start`, `period_end`, `pax`, `budget` as the user said "
        "it, `budget_scope` when the user says the budget was per person or in total, "
        "`duration_min_nights`, `duration_max_nights`, `rooms`, `level`, `wants_coaching`; when "
        "the user only says the trip is too hard or too easy, pass the reason and Vela moves the "
        "level by one), and "
        "`direction`: north when the user wants somewhere cooler, south when they want somewhere "
        "warmer. Returns the next single proposal, or `failed_criterion` with "
        "`rejected_proposal_id` when nothing else fits: ask what to change, then call "
        "reject_proposal again on `rejected_proposal_id` with the updated fields." + _VOICE),
    "accept_proposal": _ACCEPT + (
        " If the answer is `queued`, check with get_order_status after the stated wait, or "
        "whenever the user asks." + _VOICE),
    "get_order_status": (
        "Check an order after the wait stated by accept_proposal, when the user says they paid or "
        "asks how it is going." + _STATES),
}

DESCRIPTIONS_SMS = dict(DESCRIPTIONS, **{
    "accept_proposal": _ACCEPT + (
        " After the price confirmation Vela texts the payment link to the traveler's phone and "
        "texts again when the booking is confirmed. Do not poll get_order_status on your own: call it "
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
    description="Maximum budget in euros, the figure exactly as the user said it: never multiply "
                "or divide it by the number of people. Only if the user said it.")]
BudgetScope = Annotated[Optional[str], Field(
    description="per_person when the user explicitly said the budget is per person (each, a "
                "testa), total when they explicitly said it is for everyone (in total, in tutto). "
                "Leave it out otherwise: Vela reads the figure and says how it read it.")]
DurationMin = Annotated[Optional[int], Field(
    description="Shortest trip the user wants, in nights, only if they said a length: weekend 1, "
                "long weekend 2, a week 6, N days N-1, N nights N.")]
DurationMax = Annotated[Optional[int], Field(
    description="Longest trip the user wants, in nights, only if they said a length: weekend 3, "
                "long weekend 4, a week 8, N days N-1, N nights N. Leave out for 'at least N "
                "nights'.")]
Level = Annotated[Optional[str], Field(
    description="Playing level the user said: beginner (never played, first steps), intermediate "
                "or advanced (competitive players). Only if the user said it.")]
WantsCoaching = Annotated[Optional[bool], Field(
    description="true if the user wants lessons, a coach or a clinic; false if they said they "
                "want no lessons. Leave it out otherwise.")]
Direction = Annotated[Optional[str], Field(
    description="north when the user wants somewhere cooler, south when somewhere warmer.")]
Rooms = Annotated[Optional[int], Field(
    description="Number of hotel rooms, 1 to the number of people, only if the user said it. "
                "With more than 2 people ask \"In quante camere?\" / \"How many rooms?\" before "
                "calling if they have not said it; with 1 or 2 people leave it out, Vela assumes "
                "one room.")]
RoomsCorrection = Annotated[Optional[int], Field(
    description="Only if the user corrects the number of hotel rooms at the last moment: 1 to "
                "the number of people. Leave it out otherwise, the rooms come from the intent.")]
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
    """Server MCP con i sei tool. ``get_vela`` è letto a ogni chiamata; alla costruzione
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
                      pax: Pax = None, budget: Budget = None,
                      duration_min_nights: DurationMin = None,
                      duration_max_nights: DurationMax = None,
                      budget_scope: BudgetScope = None, rooms: Rooms = None,
                      level: Level = None, wants_coaching: WantsCoaching = None,
                      first_name: FirstName = None, last_name: LastName = None,
                      email: Email = None, phone: Phone = None,
                      participants: Participants = None) -> CallToolResult:
        profile = traveler_profile(first_name, last_name, email, phone, pax, participants)
        fields = StructuredFields(sport, area, period_start, period_end, pax, budget,
                                  duration_min_nights=duration_min_nights,
                                  duration_max_nights=duration_max_nights,
                                  budget_scope=budget_scope, rooms=rooms, level=level,
                                  wants_coaching=wants_coaching)
        return run("create_intent", lambda v: v.create_intent(text, profile, fields))

    @server.tool(description=descriptions["get_proposal"])
    def get_proposal(intent_id: IntentId) -> CallToolResult:
        return run("get_proposal", lambda v: v.get_proposal(intent_id))

    @server.tool(description=descriptions["get_proposal_details"])
    def get_proposal_details(proposal_id: ProposalId) -> CallToolResult:
        return run("get_proposal_details", lambda v: v.get_proposal_details(proposal_id))

    @server.tool(description=descriptions["reject_proposal"])
    def reject_proposal(proposal_id: ProposalId, reason: Reason = "", sport: Sport = None,
                        area: Area = None, period_start: PeriodStart = None,
                        period_end: PeriodEnd = None, pax: Pax = None, budget: Budget = None,
                        direction: Direction = None, duration_min_nights: DurationMin = None,
                        duration_max_nights: DurationMax = None,
                        budget_scope: BudgetScope = None, rooms: Rooms = None,
                        level: Level = None, wants_coaching: WantsCoaching = None) -> CallToolResult:
        fields = StructuredFields(sport, area, period_start, period_end, pax, budget, direction,
                                  duration_min_nights, duration_max_nights, budget_scope, rooms,
                                  level, wants_coaching)
        return run("reject_proposal", lambda v: v.reject_proposal(proposal_id, reason, fields))

    @server.tool(description=descriptions["accept_proposal"])
    def accept_proposal(proposal_id: ProposalId, first_name: FirstName = None,
                        last_name: LastName = None, email: Email = None, phone: Phone = None,
                        participants: Participants = None,
                        rooms: RoomsCorrection = None) -> CallToolResult:
        profile = traveler_profile(first_name, last_name, email, phone, None, participants)
        return run("accept_proposal", lambda v: v.accept_proposal(proposal_id, profile, rooms))

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
