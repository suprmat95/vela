"""Il percorso di un viaggiatore contro la REST di Vela (M13a), senza Locust: `call`, `clock` e
`sleep` arrivano dal chiamante, così il percorso si prova nei test e gira nei greenlet di Locust.

`record` si aggiorna mentre il viaggiatore avanza: se il giro finisce a metà, quello che c'è è già
scritto. Tempi in secondi dall'inizio dello scenario.
"""
import random
import time
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

from loadtest.scenario import PROFILE, REASON, Traveler

Call = Callable[..., Tuple[int, dict]]   # call(method, path, name, json=None) → (status, corpo)
TERMINAL = {"failed", "booking_failed", "cancelled", "expired", "replaced", "confirmed"}


def run_journey(tr: Traveler, call: Call, clock: Callable[[], float],
                sleep: Callable[[float], None], deadline: float, record: dict,
                rng: Optional[random.Random] = None) -> dict:
    _journey(tr, call, clock, sleep, deadline, record, rng or random.Random(tr.index))
    record["t_end"] = round(clock(), 3)
    return record


def _journey(tr: Traveler, call: Call, clock, sleep, deadline: float, record: dict,
             rng: random.Random) -> dict:
    record.update(index=tr.index, role=tr.role, arrival=round(clock(), 3), sport=tr.sport,
                  rejects=tr.rejects, accepts=tr.accepts, pays=tr.pays, final=None)

    status, body = call("POST", "/v1/intents", "create_intent",
                        {"text": tr.text, "sport": tr.sport, "profile": PROFILE})
    if status != 201:
        return _end(record, "intent_%s" % (body.get("outcome") or status))
    started = clock()
    status, proposal = call("GET", "/v1/intents/%s/proposal" % body["intent_id"], "get_proposal")
    record["proposal_ms"] = round((clock() - started) * 1000, 1)
    if proposal.get("outcome") != "proposal":
        return _end(record, "no_proposal")
    proposal_id = proposal["proposal_id"]

    if tr.rejects:
        status, second = call("POST", "/v1/proposals/%s/reject" % proposal_id, "reject_proposal",
                              {"reason": REASON})
        if second.get("outcome") != "proposal":
            return _end(record, "no_match_after_reject")
        proposal_id = second["proposal_id"]
    if not tr.accepts:
        return _end(record, "browsed")

    if tr.accept_at is not None and clock() < tr.accept_at:
        sleep(tr.accept_at - clock())
    status, queued = call("POST", "/v1/proposals/%s/accept" % proposal_id, "accept_proposal")
    if status != 202:
        return _end(record, "accept_%s" % (queued.get("outcome") or status))
    record.update(t_accept=round(clock(), 3), order_id=queued["order_id"],
                  position=queued.get("position"), wait_seconds=queued.get("wait_seconds"))

    low, high = tr.poll or (30.0, 60.0)
    last = queued.get("status")
    while clock() < deadline:
        sleep(max(0.0, min(rng.uniform(low, high), deadline - clock())))
        if clock() >= deadline:
            break
        status, order = call("GET", "/v1/orders/%s" % record["order_id"], "get_order_status")
        if status != 200:
            continue
        last = order.get("status")
        record["last_status"] = last
        if last == "awaiting_payment" and "t_link" not in record:
            record["t_link"] = round(clock(), 3)
            if not tr.pays:
                return _end(record, "link_unpaid")
            call("GET", urlparse(order["payment_url"]).path, "replay_checkout")
            record["t_paid"] = round(clock(), 3)
        elif last == "confirmed":
            record["t_confirmed"] = round(clock(), 3)
            return _end(record, "confirmed")
        elif last in TERMINAL:
            return _end(record, last)
    return _end(record, "open_%s" % last)


def _end(record: dict, final: str) -> dict:
    record["final"] = final
    return record


class ScenarioClock:
    """Secondi dall'inizio dello scenario (monotono) e istante epoch dell'inizio, per allineare
    gli eventi al registro del finto."""

    def __init__(self):
        self.epoch_start = time.time()
        self._start = time.monotonic()

    def __call__(self) -> float:
        return time.monotonic() - self._start
