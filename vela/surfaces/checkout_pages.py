"""Pagine di ritorno dal Checkout di Stripe (deroga a spec §6, decisione M6).

Statiche: non leggono l'ordine, non riflettono parametri e non mostrano dati. Stripe manda a
``/checkout/success`` solo a pagamento riuscito e a ``/checkout/cancel`` quando il viaggiatore
torna indietro. La conferma vera arriva dal webhook; la pagina rimanda alla conversazione.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from vela.adapters.stripe_links import CANCEL_PATH, SUCCESS_PATH

router = APIRouter()

PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Vela · %(title)s</title>
<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;
line-height:1.5;color:#1a1a1a;background:#fff}h1{font-size:1.5rem}</style>
</head><body><h1>%(title)s</h1><p>%(text)s</p></body></html>
"""

SUCCESS = {"title": "Pagamento riuscito",
           "text": "Grazie! Torna nella conversazione con il tuo assistente: ti darà il codice "
                   "di prenotazione appena è pronto."}
CANCEL = {"title": "Pagamento non completato",
          "text": "Non ti è stato addebitato nulla. Il link di pagamento resta valido fino a "
                  "24 ore dalla sua creazione: puoi riaprirlo dalla conversazione."}


@router.get(SUCCESS_PATH, response_class=HTMLResponse, include_in_schema=False)
def checkout_success() -> HTMLResponse:
    return HTMLResponse(PAGE % SUCCESS)


@router.get(CANCEL_PATH, response_class=HTMLResponse, include_in_schema=False)
def checkout_cancel() -> HTMLResponse:
    return HTMLResponse(PAGE % CANCEL)
