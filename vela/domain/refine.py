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
prima si limitano a `pax`. Stessi ingressi danno sempre lo stesso risultato.

M21-F (RF-71..75): il rifiuto ha un tipo, dal campo `reject_kind`, altrimenti dalle regole it/en
sul motivo, altrimenti dai campi strutturati; con più tipi i criteri cambiano tutti e vale il
primo nell'ordine di `REJECT_KINDS`. Un luogo negato ("Estepona no") va in `excluded_areas` e non
diventa la nuova area; il tipo `place` senza luogo esclude quello del prodotto rifiutato.
`keep_product` (campo o "mi piace ma", "same trip"…) vale solo per il tipo `dates`. Senza tipo,
o con più di 2 persone nuove senza camere dette, `ask` chiede e i criteri restano quelli di prima.
"""
import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple

from vela.domain import geo
from vela.domain.intent import (MAX_NIGHTS, CheapestTotal, conflicts_between, parse_budget,
                                parse_budget_scope, parse_duration, parse_level, parse_pax,
                                parse_period, parse_rooms, parse_sport, parse_wants_coaching,
                                read_budget, validate_fields)
from vela.domain.intent import ROOMS_DEFAULT_MAX_PAX
from vela.domain.labels import LEVELS
from vela.domain.models import REJECT_KINDS, Area, Criteria, Proposal, StructuredFields

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


# M21-F (RF-71): parole dei tipi che non cambiano un criterio da sole
_HOTEL = re.compile(r"\b(?:hotel|albergh?[oi]|struttur[ae]|resort|accommodation|alloggio)\b")
_PLACE_WORDS = re.compile(r"\b(?:posto|posti|luogo|luoghi|località|zona|destinazione|lontan[oaie]|"
                          r"place|location|destination|too far|far away)\b")
_DATES_WORDS = re.compile(r"\b(?:date|periodo|dates|when else|quando altro)\b")
# RF-74: il viaggio piace, le date no; mai dopo una negazione ("non mi piace", "I don't like")
_KEEP = re.compile(r"(?<!non )(?<!n't )(?<!not )\b(?:mi piace|ci piace|tienimi|teniamo|tieni questo|"
                   r"stesso viaggio|quando altro|altre date|i like|we like|same trip|when else|"
                   r"other dates)\b")

# RF-71: il tipo che ogni campo strutturato valido dice da solo
_FIELD_KINDS = {"budget": "price", "budget_scope": "price", "area": "place", "period": "dates",
                "duration_min_nights": "duration", "duration_max_nights": "duration",
                "sport": "sport", "pax": "pax", "rooms": "pax", "level": "level",
                "wants_coaching": "level"}


@dataclass(frozen=True)
class Refinement:
    criteria: Criteria
    discarded: tuple = ()    # (campo, valore grezzo) dei campi invalidi, da dire nel `say`
    conflicts: tuple = ()    # (campo, valore dal testo, valore del campo), da loggare
    understood: bool = True  # False: né il motivo né i campi si traducono in un criterio (RF-54)
    kind: Optional[str] = None     # RF-71: il tipo registrato; None = motivo non classificato
    kinds: tuple = ()              # tutti i tipi riconosciuti, nell'ordine di `REJECT_KINDS`
    keep_product: bool = False     # RF-74, solo con `kind == "dates"`
    ask: Optional[str] = None      # "reason" (RF-75) o "rooms" (M21-D): domanda, criteri invariati


def is_price_reason(reason: Optional[str]) -> bool:
    """Il motivo parla di prezzo (parole di RF-08 o una cifra): dopo un rifiuto così le proposte
    successive devono costare meno di quella rifiutata (decisione M7, spec §10.1)."""
    low = (reason or "").lower()
    return bool(_PRICE.search(low)) or parse_budget(low) is not None


def is_hotel_rejection(kind: Optional[str], reason: Optional[str]) -> bool:
    """RF-72 (M21-F): il rifiuto esclude l'hotel se il tipo è `hotel` o se il motivo ne parla
    (motivo con più tipi, registrato col primo). Un rifiuto senza tipo (prima di M21-F, RF-17) no, e
    nemmeno `other`, che per RF-75 esclude solo il prodotto."""
    return kind == "hotel" or (kind not in (None, "other") and bool(_HOTEL.search((reason or "").lower())))


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


def _direction(low: str) -> Optional[str]:
    return "south" if _SOUTH.search(low) else "north" if _NORTH.search(low) else None


def _text_changes(criteria: Criteria, low: str, proposal: Proposal,
                  product_area: Optional[Area], today: date,
                  product_levels: frozenset = frozenset()) -> dict:
    changes = {}
    direction = _direction(low)
    if direction is not None:
        moved = geo.move(product_area, direction)
        if moved is not None:
            changes["area"] = moved
    else:
        area = geo.find_area_not_negated(low)   # RF-73: un luogo negato non è la nuova area
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


def _text_kinds(low: str, changes: dict, said: dict) -> set:
    """RF-71: i tipi che il motivo dice, anche senza cambiare un criterio ("l'hotel non mi piace")."""
    direction = _direction(low)
    kinds = set()
    if _PRICE.search(low) or said:
        kinds.add("price")
    if geo.negated_places(low) or (direction is None and ("area" in changes or _PLACE_WORDS.search(low))):
        kinds.add("place")
    if _HOTEL.search(low):
        kinds.add("hotel")
    if "period" in changes or _DATES_WORDS.search(low) or _KEEP.search(low):
        kinds.add("dates")
    if "duration_min_nights" in changes or _SHORTER.search(low) or _LONGER.search(low):
        kinds.add("duration")
    for name, kind in (("sport", "sport"), ("pax", "pax"), ("rooms", "pax"), ("level", "level"),
                       ("wants_coaching", "level")):
        if name in changes:
            kinds.add(kind)
    if _EASIER.search(low) or _HARDER.search(low):
        kinds.add("level")
    if direction is not None:
        kinds.add("direction")
    return kinds


def _kind_field(value, discarded: list) -> Optional[str]:
    """RF-53 per `reject_kind`: uno dei tipi di RF-71 (spazi e maiuscole tollerati)."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in REJECT_KINDS:
        return value.strip().lower()
    discarded.append(("reject_kind", value))
    return None


def _keep_field(value, discarded: list) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    discarded.append(("keep_product", value))
    return None


def _inside(area: Area, excluded: tuple) -> bool:
    return any(x in geo.ancestors(area) for x in excluded)


def _excluded_areas(criteria: Criteria, area: Optional[Area], low: str, place_kind: bool,
                    area_changed: bool, product_area: Optional[Area]) -> Tuple[tuple, Optional[Area]]:
    """RF-73: i luoghi negati si aggiungono alle esclusioni; il tipo `place` senza luogo nuovo né
    negato esclude quello del prodotto. Un'area dell'intento dentro un'esclusione sale al primo
    antenato non escluso (nessuno: nessuna area)."""
    new = geo.negated_places(low)
    if not new and place_kind and not area_changed and product_area is not None:
        new = [product_area]
    excluded = tuple(criteria.excluded_areas) + tuple(a for a in new if a not in criteria.excluded_areas)
    excluded = tuple(dict.fromkeys(excluded))
    if area is not None and _inside(area, excluded):
        area = next((a for a in geo.ancestors(area) if not _inside(a, excluded)), None)
    return excluded, area


def refine(criteria: Criteria, reason: Optional[str], proposal: Proposal,
           product_area: Optional[Area], today: date,
           fields: Optional[StructuredFields] = None,
           cheapest_total: Optional[CheapestTotal] = None,
           product_levels: frozenset = frozenset()) -> Refinement:
    """`cheapest_total`: la regola 4 di RF-69 per una cifra nuova senza lettura detta.
    `product_levels`: le etichette di livello del prodotto rifiutato (M21-C). `product_area`:
    il luogo del prodotto rifiutato, per le direzioni e per il tipo `place` senza luogo (RF-73)."""
    fields = fields or StructuredFields()
    low = (reason or "").lower()
    changes = _text_changes(criteria, low, proposal, product_area, today, product_levels)
    said = {k: v for k, v in (("budget", parse_budget(low)), ("budget_scope", parse_budget_scope(low)))
            if v is not None}
    text_kinds = _text_kinds(low, changes, said)
    given, discarded = validate_fields(fields.as_dict(), today)
    discarded = list(discarded)
    kind_field = _kind_field(fields.reject_kind, discarded)
    keep_field = _keep_field(fields.keep_product, discarded)
    field_kinds = {_FIELD_KINDS[name] for name in given}
    if fields.direction is not None:
        moved = None
        if fields.direction in DIRECTIONS:
            moved = geo.move(product_area, fields.direction)
        if moved is None:
            discarded.append(("direction", fields.direction))
        elif "area" not in given:
            changes["area"] = moved
            field_kinds.add("direction")
        else:
            changes.setdefault("area", moved)   # vince `area`: la direzione resta nei conflitti
            field_kinds.add("direction")
    rooms_text, rooms_field = changes.pop("rooms", None), given.get("rooms")
    pax = given.get("pax", changes.get("pax", criteria.pax))
    keep = keep_field if keep_field is not None else bool(_KEEP.search(low))
    kinds = tuple(k for k in REJECT_KINDS if k in text_kinds | field_kinds)
    if keep and not kinds:
        kinds = ("dates",)
    kind = kind_field or (kinds[0] if kinds else None)
    keep = keep and kind == "dates"
    if kind is None:   # RF-75: nessun effetto finché il viaggiatore non dice cosa non va
        return Refinement(criteria, tuple(discarded), (), understood=False, ask="reason")
    rooms_said = rooms_text is not None or rooms_field is not None
    if (criteria.rooms is not None and pax is not None and pax != criteria.pax
            and pax > ROOMS_DEFAULT_MAX_PAX and not rooms_said):
        # da M21-D: più persone senza camere dette → "In quante camere?", niente registrato; un
        # intento salvato prima di M21-D resta senza camere finché non le dice (decisione M21-D)
        return Refinement(criteria, tuple(discarded), (), kind=kind, kinds=kinds, ask="rooms")
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
    area_changed = "area" in changes
    excluded, area = _excluded_areas(criteria, changes.get("area", criteria.area), low,
                                     "place" in kinds or kind == "place", area_changed, product_area)
    if excluded != criteria.excluded_areas:
        changes["excluded_areas"] = excluded
    if area != changes.get("area", criteria.area):
        changes["area"] = area
    refined = replace(criteria, **changes) if changes else criteria
    budget = _budget_changes(criteria, refined, figure, stated, lowered, cheapest_total)
    # la lettura conta come capita solo se c'è un budget da leggere (decisione M21-E 3)
    touched = figure is not None or lowered is not None or (
        criteria.budget is not None and stated is not None)
    if budget:
        refined = replace(refined, **budget)
    return Refinement(refined, tuple(discarded), conflicts, understood=bool(changes) or touched,
                      kind=kind, kinds=kinds, keep_product=keep)
