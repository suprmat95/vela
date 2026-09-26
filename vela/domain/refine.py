"""Interpretazione di un rifiuto (RF-08, RF-53): criteri aggiornati, funzione pura.

Prima il motivo in testo libero, con regole it/en che si combinano: budget (una cifra nel motivo,
altrimenti "troppo caro" porta il budget all'80% del totale proposto, senza mai alzarlo),
direzione ("più a sud"/"più a nord", "più fresco"/"più caldo" con le tabelle di `geo`), luogo
esplicito, periodo, sport e persone con gli stessi parser dell'intento. Poi i campi strutturati
dell'agente (RF-52), che vincono sul testo: `direction` sostituisce la direzione del testo,
`area` vince su ogni direzione. Un motivo non riconosciuto restituisce gli stessi criteri: il
prodotto rifiutato resta comunque escluso. Stessi ingressi danno sempre lo stesso risultato.
"""
import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.intent import (conflicts_between, parse_budget, parse_pax, parse_period,
                                parse_sport, validate_fields)
from vela.domain.models import Area, Criteria, Proposal, StructuredFields

PRICE_FACTOR = Decimal("0.8")
DIRECTIONS = ("north", "south")

_PRICE = re.compile(r"\b(?:troppo car[oaie]|costa troppo|costano troppo|costos[oaie]|"
                    r"più economic[oaie]|meno car[oaie]|too expensive|too pricey|too much|"
                    r"cheaper|less expensive)\b")
# "più fresco" = più a nord, "più caldo" = più a sud: il catalogo non ha dati climatici (RF-55)
_SOUTH = re.compile(r"\b(?:più a sud|più al sud|più giù|further south|farther south|more south|"
                    r"more to the south|più cald[oaie]|troppo fredd[oaie]|warmer|hotter|"
                    r"too cold)\b")
_NORTH = re.compile(r"\b(?:più a nord|più al nord|più su|further north|farther north|more north|"
                    r"more to the north|più fresc[oaie]|più fresch[ie]|più fredd[oaie]|"
                    r"troppo cald[oaie]|cooler|colder|too hot)\b")


@dataclass(frozen=True)
class Refinement:
    criteria: Criteria
    discarded: tuple = ()    # (campo, valore grezzo) dei campi invalidi, da dire nel `say`
    conflicts: tuple = ()    # (campo, valore dal testo, valore del campo), da loggare
    understood: bool = True  # False: né il motivo né i campi si traducono in un criterio (RF-54)


def is_price_reason(reason: Optional[str]) -> bool:
    """Il motivo parla di prezzo (parole di RF-08 o una cifra): dopo un rifiuto così le proposte
    successive devono costare meno di quella rifiutata (decisione M7, spec §10.1)."""
    low = (reason or "").lower()
    return bool(_PRICE.search(low)) or parse_budget(low) is not None


def _text_changes(criteria: Criteria, low: str, proposal: Proposal,
                  product_area: Optional[Area], today: date) -> dict:
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
    return changes


def refine(criteria: Criteria, reason: Optional[str], proposal: Proposal,
           product_area: Optional[Area], today: date,
           fields: Optional[StructuredFields] = None) -> Refinement:
    fields = fields or StructuredFields()
    changes = _text_changes(criteria, (reason or "").lower(), proposal, product_area, today)
    given, discarded = validate_fields(fields.as_dict(), today)
    discarded = list(discarded)
    if fields.direction is not None:
        moved = None
        if fields.direction in DIRECTIONS:
            moved = geo.move(product_area, fields.direction)
        if moved is None:
            discarded.append(("direction", fields.direction))
        elif "area" not in given:
            changes["area"] = moved
        else:
            changes.setdefault("area", moved)   # vince `area`: la direzione resta nei conflitti
    conflicts = conflicts_between(changes, given)
    changes.update(given)
    refined = replace(criteria, **changes) if changes else criteria
    return Refinement(refined, tuple(discarded), conflicts, understood=bool(changes))
