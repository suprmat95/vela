"""Smoke test della superficie MCP (M3): il flusso di spec §10.1 contro un server MCP.

Uso: uv run python scripts/mcp_smoke.py https://vela-n506.onrender.com/mcp

Solo per la modalità replay: il "pagamento" è la visita del link /replay/checkout/{order_id}.
Nessuna chiamata a HofJ né a Stripe; sul server restano un intento e un ordine di prova.
Richiede Python 3.12 (`uv run`), non il python3 di sistema. Il rifiuto "troppo caro" produce una
proposta diversa, non necessariamente più economica: l'interpretazione del motivo arriva con M9.
"""
import asyncio
import sys
from typing import Callable, Optional

import httpx
from mcp import Client

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
TRAVELER = {"first_name": "Prova", "last_name": "Smoke", "email": "smoke@example.com",
            "phone": "+390000000000",
            "participants": [{"first_name": "Seconda", "last_name": "Smoke"}]}
TOOL_NAMES = {"create_intent", "get_proposal", "reject_proposal", "accept_proposal",
              "get_order_status"}


class SmokeFailure(Exception):
    pass


def count_products(obj) -> int:
    """Dizionari con chiave `product_id` a qualunque profondità (RF-10)."""
    if isinstance(obj, dict):
        return (1 if "product_id" in obj else 0) + sum(count_products(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(count_products(v) for v in obj)
    return 0


async def call(client, name: str, args: dict, need: str) -> dict:
    r = await client.call_tool(name, args)
    if r.is_error:
        text = r.content[0].text if r.content else "?"
        raise SmokeFailure("%s ha risposto con un errore: %s" % (name, text))
    d = r.structured_content or {}
    if count_products(d) > 1:
        raise SmokeFailure("%s: più di un prodotto nella risposta (RF-10)" % name)
    if need not in d:
        raise SmokeFailure("%s: manca %r nella risposta: %s" % (name, need, d.get("say", d)))
    return d


async def run_flow(client, open_url: Callable[[str], None], expected_base: Optional[str] = None,
                   attempts: int = 10, delay: float = 1.0) -> dict:
    names = {t.name for t in (await client.list_tools()).tools}
    if names != TOOL_NAMES:
        raise SmokeFailure("tool attesi %s, trovati %s" % (sorted(TOOL_NAMES), sorted(names)))
    intent = await call(client, "create_intent", {"text": INTENT}, "intent_id")
    first = await call(client, "get_proposal", {"intent_id": intent["intent_id"]}, "proposal_id")
    second = await call(client, "reject_proposal",
                        {"proposal_id": first["proposal_id"], "reason": "troppo caro"}, "proposal_id")
    if second["product"]["product_id"] == first["product"]["product_id"]:
        raise SmokeFailure("reject_proposal ha riproposto lo stesso prodotto")
    accepted = await call(client, "accept_proposal",
                          dict(TRAVELER, proposal_id=second["proposal_id"]), "payment_url")
    url = accepted["payment_url"]
    if expected_base and not url.startswith(expected_base.rstrip("/") + "/"):
        raise SmokeFailure("il link di pagamento %s non punta a %s: VELA_PUBLIC_URL è impostata?"
                           % (url, expected_base))
    open_url(url)
    status = {}
    for _ in range(attempts):
        status = await call(client, "get_order_status", {"order_id": accepted["order_id"]}, "status")
        if status["status"] == "confirmed":
            return {"first": first["product"]["title"], "second": second["product"]["title"],
                    "order_id": accepted["order_id"], "total": accepted["total"],
                    "booking_code": status["booking_code"]}
        await asyncio.sleep(delay)
    raise SmokeFailure("ordine %s non confermato: stato %s"
                       % (accepted["order_id"], status.get("status")))


def open_with_httpx(url: str) -> None:
    httpx.get(url, timeout=30).raise_for_status()


def base_of(mcp_url: str) -> str:
    return mcp_url.rstrip("/").rsplit("/mcp", 1)[0]


async def main_async(url: str) -> dict:
    async with Client(url) as client:
        return await run_flow(client, open_with_httpx, expected_base=base_of(url))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: uv run python scripts/mcp_smoke.py <url>/mcp", file=sys.stderr)
        return 2
    try:
        summary = asyncio.run(main_async(argv[0]))
    except SmokeFailure as exc:
        print("FALLITO: %s" % exc, file=sys.stderr)
        return 1
    for key, value in summary.items():
        print("%s: %s" % (key, value))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
