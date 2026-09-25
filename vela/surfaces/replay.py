"""``GET /replay/checkout/{order_id}``: il "pagamento" della modalità replay (RNF-08).

Segna l'ordine come pagato e avvia la prenotazione in background. Montato solo con
``VELA_UPSTREAM_MODE=replay``. Risposta JSON, nessuna pagina: la sola pagina web del
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
        order = vela.orders.mark_paid(order_id, "pi_replay_" + order_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="ordine sconosciuto")
    if order.status == OrderStatus.PAID_PENDING_BOOKING:
        request.app.state.runner.submit(order_id)
        say = say_paid()
    else:
        say = say_status(order.status, order.booking_code, order.failure_reason)
    return JSONResponse({"order_id": order_id, "status": order.status.value, "say": say})
