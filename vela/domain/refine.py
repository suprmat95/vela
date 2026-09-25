"""Interpretazione del motivo di un rifiuto (RF-08): criteri aggiornati, funzione pura.

Regole it/en che si combinano: budget (una cifra nel motivo, altrimenti "troppo caro" porta il
budget all'80% del totale proposto, senza mai alzarlo), direzione ("più a sud"/"più a nord"
con le tabelle di `geo`), luogo esplicito, periodo, sport e persone con gli stessi parser
dell'intento. Un motivo non riconosciuto restituisce gli stessi criteri: il prodotto rifiutato
resta comunque escluso. Stesso motivo e stessa proposta danno sempre lo stesso risultato.
"""
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.intent import parse_budget, parse_pax, parse_period, parse_sport
from vela.domain.models import Area, Criteria, Proposal

PRICE_FACTOR = Decimal("0.8")

_PRICE = re.compile(r"\b(?:troppo car[oaie]|costa troppo|costano troppo|costos[oaie]|"
                    r"più economic[oaie]|meno car[oaie]|too expensive|too pricey|too much|"
                    r"cheaper|less expensive)\b")
_SOUTH = re.compile(r"\b(?:più a sud|più al sud|più giù|further south|farther south|more south|"
                    r"more to the south)\b")
_NORTH = re.compile(r"\b(?:più a nord|più al nord|più su|further north|farther north|more north|"
                    r"more to the north)\b")


def is_price_reason(reason: Optional[str]) -> bool:
    """Il motivo parla di prezzo (parole di RF-08 o una cifra): dopo un rifiuto così le proposte
    successive devono costare meno di quella rifiutata (decisione M7, spec §10.1)."""
    low = (reason or "").lower()
    return bool(_PRICE.search(low)) or parse_budget(low) is not None


def refine(criteria: Criteria, reason: Optional[str], proposal: Proposal,
           product_area: Optional[Area], today: date) -> Criteria:
    low = (reason or "").lower()
    changes = {}
    budget = parse_budget(low)
    if budget is not None:
        changes["budget"] = budget
    elif _PRICE.search(low):
        lowered = (proposal.price_from * proposal.pax * PRICE_FACTOR).quantize(Decimal("0.01"))
        changes["budget"] = lowered if criteria.budget is None else min(lowered, criteria.budget)
    direction = "south" if _SOUTH.search(low) else "north" if _NORTH.search(low) else None
    if direction is not None:
        moved = geo.move(product_area, direction)
        if moved is not None:
            changes["area"] = moved
    else:
        area = geo.find_area(low)
        if area is not None:
            changes["area"] = area
    for name, value in (("period", parse_period(low, today)), ("sport", parse_sport(low)),
                        ("pax", parse_pax(low))):
        if value is not None:
            changes[name] = value
    return replace(criteria, **changes) if changes else criteria
