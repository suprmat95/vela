"""Chooser v1 (RF-06, RF-07 semplificato, RF-09): una sola scelta deterministica.

Esclusioni in sequenza (archiviati, non prenotabili, rifiutati, sport, date, pax); tra i
restanti ordina per area coincidente (città > paese), totale entro budget, prezzo crescente,
id. Se un filtro azzera i candidati, `NoChoice` porta il nome di quel filtro (RF-09). M11
aggiunge geohierarchy, durata e intersezioni parziali.
"""
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Set, Union

from vela.domain import geo
from vela.domain.models import Area, Availability, Criteria, Period, Product
from vela.domain.say import fmt_date, fmt_money

FILTERS = ("archived", "bookable", "rejected", "sport", "dates", "pax")


@dataclass(frozen=True)
class Choice:
    product: Product
    start_date: date
    end_date: date
    reason: str


@dataclass(frozen=True)
class NoChoice:
    failed_criterion: str


def window_for(product: Product, period: Optional[Period], today: date) -> Optional[Availability]:
    for window in product.availabilities:
        if window.start < today:
            continue
        if period is None or period.start <= window.start <= period.end:
            return window
    return None


def _dates_ok(product: Product, period: Optional[Period], today: date) -> bool:
    if period is not None:
        if product.min_date and period.end < product.min_date:
            return False
        if product.max_date and period.start > product.max_date:
            return False
    return window_for(product, period, today) is not None


def _pax_ok(product: Product, pax: Optional[int]) -> bool:
    if pax is None:
        return True
    if product.min_pax and pax < product.min_pax:
        return False
    if product.max_pax and pax > product.max_pax:
        return False
    return True


def area_score(product: Product, area: Optional[Area]) -> int:
    if area is None:
        return 0
    if area.kind != "country":
        found = geo.find_area(product.destination)
        if found is not None and found.name == area.name:
            return 2
    return 1 if product.country == area.country_code else 0


def _within_budget(product: Product, criteria: Criteria) -> bool:
    if criteria.budget is None:
        return True
    return product.price * (criteria.pax or 1) <= criteria.budget


def _reason(product: Product, criteria: Criteria, window: Availability) -> str:
    parts = []
    if area_score(product, criteria.area) > 0:
        where = criteria.area.name if area_score(product, criteria.area) == 1 else product.destination
        parts.append("è in %s" % where if criteria.area.kind == "country" else "è a %s" % where)
    elif product.destination:
        parts.append("è a %s" % product.destination)
    parts.append("parte il %s" % fmt_date(window.start))
    if criteria.budget is not None and _within_budget(product, criteria):
        parts.append("resta nel tuo budget di %s" % fmt_money(criteria.budget))
    else:
        parts.append("è la proposta più economica tra quelle compatibili")
    sentence = ", ".join(parts[:-1]) + " e " + parts[-1] if len(parts) > 1 else parts[0]
    return sentence[0].upper() + sentence[1:] + "."


def choose(products: Iterable[Product], criteria: Criteria, rejected_ids: Set[str],
           today: date) -> Union[Choice, NoChoice]:
    candidates = list(products)
    steps = (
        ("archived", lambda p: not p.archived),
        ("bookable", lambda p: p.bookable),
        ("rejected", lambda p: p.id not in rejected_ids),
        ("sport", lambda p: criteria.sport is None or p.sport == criteria.sport),
        ("dates", lambda p: _dates_ok(p, criteria.period, today)),
        ("pax", lambda p: _pax_ok(p, criteria.pax)),
    )
    for name, keep in steps:
        candidates = [p for p in candidates if keep(p)]
        if not candidates:
            return NoChoice(name)
    candidates.sort(key=lambda p: (-area_score(p, criteria.area), not _within_budget(p, criteria),
                                   p.price, p.id))
    best = candidates[0]
    window = window_for(best, criteria.period, today)
    return Choice(best, window.start, window.end, _reason(best, criteria, window))
