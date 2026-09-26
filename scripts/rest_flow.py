"""Flusso REST cronometrato (M7): criteri 3 e 4 di spec §10 contro un server Vela, e latenza per M13.

Uso:
  VELA_API_TOKEN=... uv run python scripts/rest_flow.py https://vela-n506.onrender.com
  VELA_API_TOKEN=... uv run python scripts/rest_flow.py https://vela-n506.onrender.com --trap
  VELA_API_TOKEN=... uv run python scripts/rest_flow.py https://vela-n506.onrender.com --phone <numero>

Flusso (criterio 3): intento → proposta → rifiuto "troppo caro" (la seconda proposta deve costare
meno) → accept (202 in coda) → stato finché c'è il link → il link si paga a mano (4242 4242 4242
4242) → stato finché l'ordine è `confirmed` con il codice di prenotazione.
`--trap` (criterio 4): intento → proposta (il prodotto trappola della fixture di staging) →
accept → stato finché l'ordine è `replaced` con una proposta diversa e senza errori tecnici nel
`say`. Nessun link nasce, quindi non resta niente da pagare né da annullare.

`--phone` sostituisce il telefono finto del viaggiatore (test manuale degli SMS, docs/sms.md).
Ogni risposta deve contenere al massimo un prodotto (RF-10). Alla fine stampa i tempi di ogni
passo in una tabella Markdown per docs/acceptance.md. Il token si legge solo da VELA_API_TOKEN e
non viene mai stampato. Chiamate: quelle del flusso verso Vela; Vela chiama HofJ e Stripe.
Richiede Python 3.12 (`uv run`).
"""
import argparse
import os
import sys
import time
from decimal import Decimal
from typing import Callable, List, Optional, Tuple

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_smoke import count_products  # noqa: E402

# Frasi di prova sul catalogo di staging (fixtures/catalog-staging.json, verificate da
# tests/test_staging_fixture.py). Criteri 1 e 3: Barcellona (158, poi Tarragona 115); la frase di
# §10.1 sulla Spagna porta al 867, che su staging ha un errore di configurazione HofJ (M7).
# Criterio 4 (`--trap`): Firenze, dove la prima proposta è la trappola 900078 solo con una fixture
# con la trappola clonata dal 78 (`vela.fixtures.add_trap`); quella di staging non la contiene
# più (M7).
INTENT_FLOW = "un weekend di padel a Barcellona a ottobre, siamo in due, massimo 1500 euro"
INTENT_TRAP = "un weekend di padel a Firenze a ottobre, siamo in due"
REASON = "troppo caro"
PROFILE = {"first_name": "Prova", "last_name": "Flusso", "email": "prova.flusso@example.com",
           "phone": "+390000000000", "participants": [{"first_name": "Seconda", "last_name": "Prova"}]}
TERMINAL = {"failed", "booking_failed", "cancelled", "expired", "replaced", "confirmed"}
TECHNICAL = ("errore", "error", "502", "hofj", "upstream", "eccezione", "exception", "traceback")

Timings = List[Tuple[str, float]]


class FlowFailure(Exception):
    pass


def call(http, method: str, path: str, json: Optional[dict] = None) -> dict:
    response = http.request(method, path, json=json)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400:
        raise FlowFailure("%s %s: HTTP %d %s" % (method, path, response.status_code,
                                                 body.get("title") or body.get("detail") or ""))
    if count_products(body) > 1:
        raise FlowFailure("%s %s: più di un prodotto nella risposta (RF-10)" % (method, path))
    return body


def expect(body: dict, outcome: str, step: str) -> dict:
    if body.get("outcome") != outcome:
        raise FlowFailure("%s: atteso %s, ricevuto %s: %s" % (step, outcome, body.get("outcome"),
                                                              body.get("missing") or body.get("say")))
    return body


def wait_status(http, order_id: str, wanted: set, clock, sleep, tick, poll: float,
                timeout: float, stop: frozenset = frozenset(TERMINAL)) -> dict:
    """Interroga lo stato finché è in `wanted`; uno stato di `stop` diverso o il timeout falliscono."""
    start = clock()
    while True:
        tick()
        status = call(http, "GET", "/v1/orders/%s" % order_id)
        if status["status"] in wanted:
            return status
        if status["status"] in stop:
            raise FlowFailure("ordine %s in %s invece di %s: %s" % (
                order_id, status["status"], "/".join(sorted(wanted)),
                status.get("failure_reason") or status.get("say")))
        if clock() - start >= timeout:
            raise FlowFailure("ordine %s ancora in %s dopo %g s (timeout), atteso %s"
                              % (order_id, status["status"], timeout, "/".join(sorted(wanted))))
        sleep(poll)


def run_flow(http, open_url: Callable[[str], None], intent: Optional[str] = None,
             profile: Optional[dict] = None, trap: bool = False, tick: Callable[[], None] = lambda: None,
             clock: Callable[[], float] = None, sleep: Callable[[float], None] = None,
             poll: float = 5.0, timeout: float = 900.0) -> dict:
    """`tick` fa avanzare la coda nei test (worker.drain); contro un server vero il worker gira da sé."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    timings: Timings = []
    started = mark = clock()

    def lap(name: str) -> None:
        nonlocal mark
        now = clock()
        timings.append((name, now - mark))
        mark = now

    text = intent or (INTENT_TRAP if trap else INTENT_FLOW)
    created = expect(call(http, "POST", "/v1/intents", {"text": text, "profile": profile or PROFILE}),
                     "intent_created", "intento")
    lap("intento")
    first = expect(call(http, "GET", "/v1/intents/%s/proposal" % created["intent_id"]),
                   "proposal", "proposta")
    lap("proposta")
    chosen = first
    if not trap:
        chosen = expect(call(http, "POST", "/v1/proposals/%s/reject" % first["proposal_id"],
                             {"reason": REASON}), "proposal", "rifiuto")
        if Decimal(chosen["total_from"]) >= Decimal(first["total_from"]):
            raise FlowFailure("dopo \"%s\" la proposta non è più economica: %s → %s"
                              % (REASON, first["total_from"], chosen["total_from"]))
        lap("rifiuto")
    queued = expect(call(http, "POST", "/v1/proposals/%s/accept" % chosen["proposal_id"]),
                    "order_queued", "accept")
    order_id = queued["order_id"]
    lap("accept")

    if trap:
        # il link nasce solo se il carrello è riuscito: allora la trappola non è fallita
        replaced = wait_status(http, order_id, {"replaced"}, clock, sleep, tick, poll, timeout,
                               stop=frozenset(TERMINAL | {"awaiting_payment"}))
        lap("accept → sostituzione")
        new = replaced.get("proposal") or {}
        trap_product = chosen["product"]["product_id"]
        new_product = (new.get("product") or {}).get("product_id")
        if not new_product or new_product == trap_product:
            raise FlowFailure("la sostituzione ripropone lo stesso prodotto %s" % trap_product)
        said = " ".join(s for s in (replaced.get("say"), new.get("say")) if s)
        if any(word in said.lower() for word in TECHNICAL):
            raise FlowFailure("la sostituzione mostra un errore tecnico al viaggiatore: %s" % said)
        timings.append(("totale", clock() - started))
        return {"status": "replaced", "order_id": order_id, "trap_product": trap_product,
                "replacement_product": new_product, "say": said, "timings": timings}

    ready = wait_status(http, order_id, {"awaiting_payment"}, clock, sleep, tick, poll, timeout)
    lap("accept → link")
    open_url(ready["payment_url"])
    done = wait_status(http, order_id, {"confirmed"}, clock, sleep, tick, poll, timeout)
    lap("link → confirmed")
    timings.append(("totale", clock() - started))
    return {"status": "confirmed", "order_id": order_id, "booking_code": done["booking_code"],
            "first_product": first["product"]["product_id"], "first_total": first["total_from"],
            "second_product": chosen["product"]["product_id"], "second_total": chosen["total_from"],
            "total": ready.get("total"), "timings": timings}


def format_table(timings: Timings) -> str:
    rows = ["| Passo | Secondi |", "|---|---|"]
    rows += ["| %s | %.2f |" % (name, seconds) for name, seconds in timings]
    return "\n".join(rows)


def print_link(url: str) -> None:
    print("Link di pagamento: %s\nPaga con 4242 4242 4242 4242, poi aspetto la conferma." % url,
          flush=True)


def http_client(url: str, token: str) -> httpx.Client:
    return httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": "Bearer " + token},
                        timeout=30)


def main(argv=None, env=None, client_factory=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url", help="base del server Vela, es. https://vela-n506.onrender.com")
    ap.add_argument("--trap", action="store_true", help="criterio 4: prodotto che fallisce al carrello")
    ap.add_argument("--intent", help="frase dell'intento (default: INTENT_FLOW o INTENT_TRAP)")
    ap.add_argument("--poll", type=float, default=5.0, help="secondi tra due richieste di stato")
    ap.add_argument("--timeout", type=float, default=900.0, help="attesa massima per stato, in secondi")
    ap.add_argument("--phone", default=PROFILE["phone"],
                    help="telefono del viaggiatore, es. il proprio per il test degli SMS "
                         "(docs/sms.md); mai nei commit")
    args = ap.parse_args(argv)
    env = os.environ if env is None else env
    token = env.get("VELA_API_TOKEN")
    if not token:
        print("variabile d'ambiente VELA_API_TOKEN assente", file=sys.stderr)
        return 2
    factory = client_factory or http_client
    try:
        with factory(args.url, token) as client:
            summary = run_flow(client, print_link, intent=args.intent,
                               profile=dict(PROFILE, phone=args.phone), trap=args.trap,
                               poll=args.poll, timeout=args.timeout)
    except (FlowFailure, httpx.HTTPError) as exc:
        print("FALLITO: %s" % exc, file=sys.stderr)
        return 1
    for key, value in summary.items():
        if key != "timings":
            print("%s: %s" % (key, value))
    print()
    print(format_table(summary["timings"]))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
