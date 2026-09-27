"""Cache del prezzo con fanout (RF-84).

Due ordini con la stessa chiave hanno per HofJ lo stesso carrello, a meno di cliente e
passeggeri: il prezzo si scopre una volta (il leader) e vale per tutti fino al TTL. Qui le
regole che servono sia ai casi d'uso sia al job d'acquisto.
"""
from datetime import date

from vela.domain.models import Order, QuoteKey


def quote_key(order: Order, start_date: date) -> QuoteKey:
    """La data sta sulla proposta, il resto sull'ordine."""
    return QuoteKey(order.product_id, start_date, order.pax, order.rooms, order.currency)
