"""Link di pagamento Stripe (RF-18, RF-21, RF-22): una Checkout Session per ordine.

Session ``mode=payment``, solo carta, un line item ``price_data`` in EUR per il totale reale,
``metadata`` con ordine e itinerario (anche sul PaymentIntent, che porta in più
``checkoutRefId`` = itinerario, l'etichetta con cui HofJ lega il pagamento al carrello).
La scadenza è calcolata dalla creazione dell'ordine (24 h meno un minuto: Stripe rifiuta oltre le 24 h), così i parametri
sono deterministici e ``idempotency_key`` = ordine restituisce sempre la stessa sessione.
Nessun dato di carta né personale passa da Vela (RNF-07). Il client è iniettabile: i test
non vanno in rete.
"""
from datetime import datetime, timedelta, timezone

import stripe

from vela.domain.models import Order
from vela.ports.payments import PaymentLink, PaymentsError, to_cents

LINK_TTL = timedelta(hours=24) - timedelta(minutes=1)   # RF-21
TIMEOUT_SECONDS = 15
SUCCESS_PATH = "/checkout/success"
CANCEL_PATH = "/checkout/cancel"


def build_stripe_client(secret_key: str) -> stripe.StripeClient:
    return stripe.StripeClient(secret_key, max_network_retries=2,
                               http_client=stripe.HTTPXClient(timeout=TIMEOUT_SECONDS,
                                                              allow_sync_methods=True))


class StripePayments:
    def __init__(self, client, public_url: str):
        self.client = client
        self.base = public_url.rstrip("/")

    def session_params(self, order: Order, description: str) -> dict:
        metadata = {"order_id": order.id, "itinerary_id": order.itinerary_id or ""}
        return {
            "mode": "payment",
            "payment_method_types": ["card"],
            "line_items": [{"quantity": 1, "price_data": {
                "currency": "eur", "unit_amount": to_cents(order.total),
                "product_data": {"name": description}}}],
            "metadata": metadata,
            # HofJ lega il PaymentIntent al carrello con checkoutRefId (verifica M5, §8).
            "payment_intent_data": {"metadata": {**metadata, "checkoutRefId": metadata["itinerary_id"]}},
            "client_reference_id": order.id,
            "expires_at": int((order.created_at + LINK_TTL).timestamp()),
            "success_url": self.base + SUCCESS_PATH,
            "cancel_url": self.base + CANCEL_PATH,
        }

    def create_payment_link(self, order: Order, description: str) -> PaymentLink:
        if order.currency.upper() != "EUR":   # RF-22
            raise PaymentsError("valuta non supportata: %s" % order.currency)
        params = self.session_params(order, description)
        try:
            session = self.client.v1.checkout.sessions.create(
                params=params, options={"idempotency_key": "vela-order-" + order.id})
        except stripe.StripeError as exc:
            raise PaymentsError("Stripe: %s" % type(exc).__name__) from exc
        return PaymentLink(session.url, datetime.fromtimestamp(params["expires_at"], timezone.utc),
                           session.id)
