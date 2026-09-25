"""``POST /webhooks/stripe``: conferma e scadenza del pagamento (RF-20, RF-21, RNF-03).

La firma ``Stripe-Signature`` è verificata sul corpo grezzo con ``STRIPE_WEBHOOK_SECRET`` e una
tolleranza di 300 s prima di ogni altra lettura: firma assente, errata o vecchia → 400. Ogni
evento gestito viene preso in carico una sola volta nella tabella ``stripe_events`` (claim):
un duplicato risponde 200 senza effetti; se l'elaborazione fallisce il claim viene rilasciato e
la risposta è 500, così Stripe ripete. Un evento non applicabile (ordine sconosciuto, importo o
valuta diversi, non pagato) resta registrato e risponde 200. Nei log solo id di evento e di
ordine, mai payload né firma (RNF-07). Nessun bearer: l'autenticazione è la firma.

Punto di aggancio per M5: ``runner.submit`` diventa l'accodamento del job ``booking`` (RF-51).
"""
import json
import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from vela.domain.models import Order, OrderStatus
from vela.domain.orders import NotFound
from vela.ports.payments import to_cents

log = logging.getLogger("vela.webhooks")

router = APIRouter()

WEBHOOK_PATH = "/webhooks/stripe"
TOLERANCE_SECONDS = 300
COMPLETED = "checkout.session.completed"
EXPIRED = "checkout.session.expired"
HANDLED = (COMPLETED, EXPIRED)


class InvalidSignature(Exception):
    pass


def verify(payload: bytes, header: Optional[str], secret: str) -> dict:
    """Evento come dict semplice, solo se la firma è valida e recente."""
    if not header:
        raise InvalidSignature("Stripe-Signature mancante")
    try:
        stripe.WebhookSignature.verify_header(payload, header, secret, TOLERANCE_SECONDS)
        event = json.loads(payload)
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise InvalidSignature(type(exc).__name__) from exc
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise InvalidSignature("evento senza id o tipo")
    return event


def process(vela, runner, event: dict) -> str:
    if event["type"] not in HANDLED:
        return "ignored"
    if not vela.repos.webhook_events.claim(event["id"], event["type"], vela.now()):
        return "duplicate"
    try:
        return _apply(vela, runner, event)
    except Exception:
        vela.repos.webhook_events.release(event["id"])
        raise


def _apply(vela, runner, event: dict) -> str:
    session = (event.get("data") or {}).get("object") or {}
    order_id = (session.get("metadata") or {}).get("order_id")
    try:
        order = vela.orders.get(order_id) if order_id else None
    except NotFound:
        order = None
    if order is None:
        log.warning("evento %s: ordine sconosciuto %s", event["id"], order_id)
        return "rejected"
    was_awaiting = order.status == OrderStatus.AWAITING_PAYMENT
    if event["type"] == EXPIRED:
        vela.orders.expire(order.id)
        return "expired" if was_awaiting else "noop"
    problem = _mismatch(session, order)
    if problem:
        log.warning("evento %s sull'ordine %s non applicato: %s", event["id"], order.id, problem)
        return "rejected"
    paid = vela.orders.mark_paid(order.id, session.get("payment_intent") or session.get("id") or "")
    if was_awaiting and paid.status == OrderStatus.PAID_PENDING_BOOKING:
        runner.submit(order.id)
        return "paid"
    return "noop"


def _mismatch(session: dict, order: Order) -> Optional[str]:
    if session.get("payment_status") != "paid":
        return "payment_status=%s" % session.get("payment_status")
    if str(session.get("currency") or "").upper() != order.currency.upper():
        return "valuta %s" % session.get("currency")
    if session.get("amount_total") != to_cents(order.total):
        return "importo %s invece di %s" % (session.get("amount_total"), to_cents(order.total))
    return None


@router.post(WEBHOOK_PATH, include_in_schema=False)
async def stripe_webhook(request: Request) -> JSONResponse:
    secret = request.app.state.settings.stripe_webhook_secret
    vela = request.app.state.vela
    if not secret or vela is None:
        return JSONResponse({"error": "webhook non configurato"}, status_code=503)
    payload = await request.body()
    try:
        event = verify(payload, request.headers.get("stripe-signature"), secret)
    except InvalidSignature:
        return JSONResponse({"error": "firma non valida"}, status_code=400)
    try:
        outcome = await run_in_threadpool(process, vela, request.app.state.runner, event)
    except Exception:   # noqa: BLE001 - Stripe ripete; il dettaglio resta nei log
        log.exception("evento %s non elaborato", event["id"])
        return JSONResponse({"error": "elaborazione non riuscita"}, status_code=500)
    return JSONResponse({"received": True, "outcome": outcome})
