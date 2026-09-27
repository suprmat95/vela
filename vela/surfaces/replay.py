"""``GET /replay/checkout/{order_id}``: il "pagamento" della modalità replay (RNF-08).

Paga il link finto e applica subito l'esito come farebbe la verifica del pagamento (RF-20):
l'ordine diventa pagato e il job di prenotazione entra in coda (RF-51). Montato solo con
``VELA_UPSTREAM_MODE=replay`` o ``loadtest`` (M13a). Risposta JSON, nessuna pagina: la sola pagina web del
progetto è il Checkout di Stripe (spec §6).
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from vela.domain.models import OrderStatus
from vela.domain.orders import NotFound
from vela.domain.say import say_paid, say_status

router = APIRouter()


@router.get("/replay/checkout/{order_id}")
def replay_checkout(order_id: str, request: Request) -> JSONResponse:
    vela = request.app.state.vela
    if vela is None:
        raise HTTPException(status_code=503, detail="dominio non disponibile: DATABASE_URL mancante")
    try:
        order = vela.orders.get(order_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="ordine sconosciuto")
    if order.status == OrderStatus.AWAITING_PAYMENT:
        if hasattr(vela.payments, "pay"):
            order = vela.orders.settle_payment(order_id, vela.payments.pay(order))
        else:   # pagamento Stripe reale con HofJ in replay: il checkout finto segna comunque pagato
            order = vela.orders.mark_paid(order_id, "pi_replay_" + order_id)
    if order.status == OrderStatus.PAID_PENDING_BOOKING:
        say = say_paid()
    else:
        say = say_status(order.status, order.booking_code, order.failure_reason)
    return JSONResponse({"order_id": order_id, "status": order.status.value, "say": say})
