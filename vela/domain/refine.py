"""Interpretazione di un rifiuto (RF-08, RF-53): criteri aggiornati, funzione pura.

Prima il motivo in testo libero, con regole it/en che si combinano: budget (una cifra nel motivo,
letta a persona o in totale come in `create_intent`, M21-E; altrimenti "troppo caro" porta il
budget all'80% del totale proposto, senza mai alzarlo, e lo legge in totale),
direzione ("più a sud"/"più a nord", "più fresco"/"più caldo" con le tabelle di `geo`), luogo
esplicito, periodo, sport, persone, camere e durata con gli stessi parser dell'intento, "troppo
lungo"/"troppo corto" che spostano la durata rispetto alla proposta (M21-A), livello e lezioni
(M21-C) con "troppo difficile"/"troppo facile" che spostano il livello di uno rispetto a quello
dell'intento o, senza, ai livelli del prodotto rifiutato. Poi i campi strutturati
dell'agente (RF-52), che vincono sul testo: `direction` sostituisce la direzione del testo,
`area` vince su ogni direzione. Le camere restano entro le persone aggiornate (M21-D): un campo
oltre è scartato e detto, un testo oltre è ignorato, e se cambiano solo le persone le camere di
prima si limitano a `pax`. Un motivo non riconosciuto restituisce gli stessi criteri: il
prodotto rifiutato resta comunque escluso. Stessi ingressi danno sempre lo stesso risultato.
"""
import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.intent import (MAX_NIGHTS, CheapestTotal, conflicts_between, parse_budget,
                                parse_budget_scope, parse_duration, parse_level, parse_pax,
                                parse_period, parse_rooms, parse_sport, parse_wants_coaching,
                                read_budget, validate_fields)
from vela.domain.labels import LEVELS
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

_SHORTER = re.compile(r"\b(?:troppo lung[oaie]|dura troppo|durano troppo|più brev[ei]|"
                      r"più cort[oaie]|meno notti|too long|shorter|fewer nights)\b")
_LONGER = re.compile(r"\b(?:troppo cort[oaie]|troppo brev[ei]|più lung[oaie]|più notti|"
                     r"too short|longer|more nights)\b")

# M21-C: il livello della proposta era sbagliato di uno (le parole di livello qui non contano come
# livello detto: "troppo avanzato" non vuol dire "siamo avanzati")
_EASIER = re.compile(r"\b(?:troppo (?:difficil[ei]|impegnativ[oaie]|avanzat[oaie]|tecnic[oaie]|dur[oaie])|"
                     r"più (?:facil[ei]|semplic[ei])|meno (?:impegnativ[oaie]|difficil[ei])|"
                     r"too (?:hard|difficult|advanced|demanding|technical)|easier|less demanding)\b")
_HARDER = re.compile(r"\b(?:troppo (?:facil[ei]|semplic[ei]|base)|"
                     r"più (?:difficil[ei]|impegnativ[oaie]|avanzat[oaie]|tecnic[oaie])|"
                     r"too (?:easy|basic|simple)|harder|more (?:challenging|advanced|demanding))\b")


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


def _level_changes(criteria: Criteria, low: str, product_levels: frozenset) -> dict:
    """Livello detto nel motivo; altrimenti "troppo difficile" = un livello sotto quello
    dell'intento (senza livello: sotto il più basso del prodotto rifiutato), "troppo facile" = uno
    sopra (sopra il più alto). Oltre gli estremi, o senza un livello da cui partire, niente."""
    step = -1 if _EASIER.search(low) else 1 if _HARDER.search(low) else 0
    said = parse_level(_HARDER.sub(" ", _EASIER.sub(" ", low)))
    if said is not None:
        return {"level": said}
    if step == 0:
        return {}
    known = [LEVELS.index(lv) for lv in product_levels if lv in LEVELS]
    if criteria.level in LEVELS:
        start = LEVELS.index(criteria.level)
    elif known:
        start = min(known) if step < 0 else max(known)
    else:
        return {}
    moved = start + step
    return {"level": LEVELS[moved]} if 0 <= moved < len(LEVELS) else {}


def _text_changes(criteria: Criteria, low: str, proposal: Proposal,
                  product_area: Optional[Area], today: date,
                  product_levels: frozenset = frozenset()) -> dict:
    changes = {}
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
                        ("pax", parse_pax(low)), ("rooms", parse_rooms(low))):
        if value is not None:
            changes[name] = value
    changes.update(_duration_changes(criteria, low, proposal))
    changes.update(_level_changes(criteria, low, product_levels))
    coaching = parse_wants_coaching(low)
    if coaching is not None:
        changes["wants_coaching"] = coaching
    return changes


def _duration_changes(criteria: Criteria, low: str, proposal: Proposal) -> dict:
    """Durata esplicita nel motivo, altrimenti "troppo lungo" = al massimo una notte in meno
    della proposta, "troppo corto" = almeno una in più; l'altro estremo si adegua se serve."""
    nights = parse_duration(low)
    if nights is not None:
        return {"duration_min_nights": nights[0], "duration_max_nights": nights[1]}
    shortest, longest = criteria.duration_min_nights, criteria.duration_max_nights
    if _SHORTER.search(low) and proposal.nights > 1:
        longest = proposal.nights - 1
        shortest = None if shortest is None else min(shortest, longest)
    elif _LONGER.search(low) and proposal.nights < MAX_NIGHTS:
        shortest = proposal.nights + 1
        longest = None if longest is None else max(longest, shortest)
    else:
        return {}
    return {"duration_min_nights": shortest, "duration_max_nights": longest}


def _rooms(before: Criteria, pax: Optional[int], from_field: Optional[int],
           from_text: Optional[int], discarded: list) -> Optional[int]:
    """RF-65 sul rifiuto: campo, poi testo, entrambi solo entro `pax`; altrimenti le camere di
    prima limitate a `pax` (None resta None: intento salvato prima di M21-D)."""
    if from_field is not None:
        if pax is None or from_field <= pax:
            return from_field
        discarded.append(("rooms", from_field))
    if from_text is not None and (pax is None or from_text <= pax):
        return from_text
    if before.rooms is not None and pax is not None:
        return min(before.rooms, pax)
    return before.rooms


def _lowered(criteria: Criteria, low: str, proposal: Proposal) -> Optional[Decimal]:
    """"Troppo caro" senza cifra: l'80% del totale proposto, senza mai alzare il budget."""
    if not _PRICE.search(low):
        return None
    lowered = (proposal.price_from * proposal.pax * PRICE_FACTOR).quantize(Decimal("0.01"))
    return lowered if criteria.budget is None else min(lowered, criteria.budget)


def _said_figure(criteria: Criteria) -> Decimal:
    """La cifra detta dal viaggiatore, dal tetto sul totale e dalla lettura (RF-69)."""
    if criteria.budget_scope == "per_person" and criteria.pax:
        return criteria.budget / criteria.pax
    return criteria.budget


def _budget_changes(before: Criteria, after: Criteria, figure: Optional[Decimal],
                    stated: Optional[str], lowered: Optional[Decimal],
                    cheapest_total: Optional[CheapestTotal]) -> dict:
    """RF-69 sul rifiuto (decisioni M21-E): una cifra nuova passa dalle regole 1-5 con i criteri
    già aggiornati; "troppo caro" dà un totale; altrimenti la cifra già detta si rilegge con la
    lettura nuova (campo o parole) o con quella di prima, per il numero di persone aggiornato."""
    if figure is not None:
        read = read_budget(replace(after, budget=figure, budget_scope=stated), cheapest_total)
    elif lowered is not None:
        return {"budget": lowered, "budget_scope": "total"}
    elif before.budget is not None and (stated is not None or after.pax != before.pax):
        read = read_budget(replace(after, budget=_said_figure(before),
                                   budget_scope=stated or before.budget_scope or "total"))
    else:
        return {}
    return {"budget": read.budget, "budget_scope": read.budget_scope}


def refine(criteria: Criteria, reason: Optional[str], proposal: Proposal,
           product_area: Optional[Area], today: date,
           fields: Optional[StructuredFields] = None,
           cheapest_total: Optional[CheapestTotal] = None,
           product_levels: frozenset = frozenset()) -> Refinement:
    """`cheapest_total`: la regola 4 di RF-69 per una cifra nuova senza lettura detta.
    `product_levels`: le etichette di livello del prodotto rifiutato (M21-C)."""
    fields = fields or StructuredFields()
    low = (reason or "").lower()
    changes = _text_changes(criteria, low, proposal, product_area, today, product_levels)
    said = {k: v for k, v in (("budget", parse_budget(low)), ("budget_scope", parse_budget_scope(low)))
            if v is not None}
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
    rooms_text, rooms_field = changes.pop("rooms", None), given.get("rooms")
    pax = given.get("pax", changes.get("pax", criteria.pax))
    rooms = _rooms(criteria, pax, rooms_field, rooms_text, discarded)
    if rooms_field is not None and rooms != rooms_field:
        given.pop("rooms")   # scartato: non è un conflitto
    conflicts = conflicts_between({**changes, **said, "rooms": rooms_text}, given)
    figure = given.pop("budget", said.get("budget"))
    stated = given.pop("budget_scope", said.get("budget_scope"))
    lowered = _lowered(criteria, low, proposal)
    changes.update(given)
    if rooms != criteria.rooms:
        changes["rooms"] = rooms
    if rooms_text is not None:
        changes.setdefault("rooms", rooms)   # le camere dette contano come capite
    refined = replace(criteria, **changes) if changes else criteria
    budget = _budget_changes(criteria, refined, figure, stated, lowered, cheapest_total)
    # la lettura conta come capita solo se c'è un budget da leggere (decisione M21-E 3)
    touched = figure is not None or lowered is not None or (
        criteria.budget is not None and stated is not None)
    if budget:
        refined = replace(refined, **budget)
    return Refinement(refined, tuple(discarded), conflicts, understood=bool(changes) or touched)
