"""Cache del prezzo con fanout (RF-84).

Due ordini con la stessa chiave hanno per HofJ lo stesso carrello, a meno di cliente e
passeggeri: il prezzo si scopre una volta (il leader) e vale per tutti fino al TTL. Qui le
regole che servono sia ai casi d'uso sia al job d'acquisto.
"""
import logging
from datetime import date, datetime
from typing import Callable

from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus, QuoteKey, QuoteStatus
from vela.ports.repositories import Repositories

log = logging.getLogger("vela.quotes")


def quote_key(order: Order, start_date: date) -> QuoteKey:
    """La data sta sulla proposta, il resto sull'ordine."""
    return QuoteKey(order.product_id, start_date, order.pax, order.rooms, order.currency)


def release_quote(repos: Repositories, order: Order, now: datetime, new_id: Callable[[], str]) -> int:
    """Ripiego: se `order` è il leader di un prezzo in volo, la riga sparisce e ogni agganciato
    torna un ordine normale con il suo job, al suo posto in coda. No-op negli altri casi.
    Da chiamare in ogni uscita del leader senza prezzo (failed, replaced, cancelled)."""
    proposal = repos.proposals.get(order.proposal_id)
    if proposal is None:
        return 0
    return _release(repos, quote_key(order, proposal.start_date), order.id, now, new_id)


def unstick(repos: Repositories, order: Order, now: datetime, new_id: Callable[[], str],
            fresh_after: datetime) -> None:
    """Rete di sicurezza: un agganciato il cui leader non è più `queued`, oppure è `queued` senza
    job d'acquisto da prima di `fresh_after` (crash tra `claim` e accodamento), fa il rilascio al
    posto suo. Il rilascio è atomico: tra più agganciati che ci provano insieme vince uno solo."""
    if not order.follows_quote or order.status != OrderStatus.QUEUED:
        return
    key = quote_key(order, repos.proposals.get(order.proposal_id).start_date)
    quote = repos.quotes.get(key)
    if quote is None or quote.status != QuoteStatus.PENDING:
        return
    leader = repos.orders.get(quote.leader_order_id)
    stalled = (leader is not None and leader.status == OrderStatus.QUEUED
               and repos.jobs.active_for_order(leader.id, JobKind.PURCHASE) is None
               and quote.updated_at < fresh_after)
    if leader is None or leader.status != OrderStatus.QUEUED or stalled:
        _release(repos, key, quote.leader_order_id, now, new_id)


def _release(repos: Repositories, key: QuoteKey, leader_order_id: str, now: datetime,
             new_id: Callable[[], str]) -> int:
    freed = repos.quotes.release(key, leader_order_id)
    for o in freed:
        repos.jobs.enqueue(Job(new_id(), JobKind.PURCHASE, o.id, JobStatus.PENDING,
                               o.enqueued_at or now, now))
    if freed:
        log.info("quote_released leader=%s followers=%d", leader_order_id, len(freed))
    return len(freed)
