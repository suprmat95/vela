"""Chooser v2 (RF-06, RF-07, RF-09): una sola scelta deterministica.

Filtri duri in sequenza: archiviati, non prenotabili, non-viaggi, sport, date, pax, rifiutati
(ultimi, così `NoChoice("rejected")` significa "i compatibili li hai scartati tutti"). Tra i
restanti ordina per aderenza all'area (dentro l'area 3, stessa regione 2, stesso paese 1),
totale entro budget, prezzo crescente, id. Area e budget non escludono mai: se non sono
rispettati la motivazione lo dichiara. Se un filtro azzera i candidati, `NoChoice` porta il
nome di quel filtro (RF-09).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Set, Tuple, Union

from vela.domain import geo
from vela.domain.catalog import is_trip
from vela.domain.models import Area, Criteria, Period, Product
from vela.domain.say import fmt_money, on_date

FILTERS = ("archived", "bookable", "trip", "sport", "dates", "pax", "rejected")

INSIDE, SAME_REGION, SAME_COUNTRY, ELSEWHERE = 3, 2, 1, 0


@dataclass(frozen=True)
class Choice:
    product: Product
    start_date: date
    end_date: date
    reason: str
    area_score: int
    within_budget: bool


@dataclass(frozen=True)
class NoChoice:
    failed_criterion: str


def departure(product: Product, period: Optional[Period], today: date) -> Optional[Tuple[date, date]]:
    """Prima partenza valida (inizio, fine). Finestra fissa (lunga al più `duration_days`): il
    viaggio è la finestra. Finestra aperta: inizio = max(inizio finestra, oggi, minDate, inizio
    periodo), fine = inizio + durata - 1 dentro la finestra. L'inizio cade nel periodo e non nel
    passato; il viaggio sta in [minDate, maxDate]."""
    duration = product.duration_days
    for window in product.availabilities:
        if duration and (window.end - window.start).days + 1 > duration:
            start = max(d for d in (window.start, today, product.min_date,
                                    period.start if period else None) if d is not None)
            end = start + timedelta(days=duration - 1)
            if end > window.end:
                continue
        else:
            start, end = window.start, window.end
        if start < today:
            continue
        if period is not None and not (period.start <= start <= period.end):
            continue
        if product.min_date and start < product.min_date:
            continue
        if product.max_date and end > product.max_date:
            continue
        return start, end
    return None


def _pax_ok(product: Product, pax: Optional[int]) -> bool:
    if pax is None:
        return True
    if product.min_pax and pax < product.min_pax:
        return False
    if product.max_pax and pax > product.max_pax:
        return False
    return True


def place_of(product: Product) -> Optional[Area]:
    """Area del prodotto: dalla destinazione, altrimenti dal titolo, altrimenti dal paese."""
    if product.destination:
        return geo.area_of_destination(product.destination, product.country)
    return geo.area_of_destination(product.title, product.country)


def area_score(product: Product, area: Optional[Area]) -> int:
    if area is None:
        return ELSEWHERE
    place = place_of(product)
    if place is not None:
        if area in geo.ancestors(place):
            return INSIDE
        if geo.common_region(place, area) is not None:
            return SAME_REGION
    country = product.country or (place.country_code if place else None)
    return SAME_COUNTRY if country == area.country_code else ELSEWHERE


def _total(product: Product, criteria: Criteria):
    return product.price * (criteria.pax or 1)


def _within_budget(product: Product, criteria: Criteria) -> bool:
    return criteria.budget is None or _total(product, criteria) <= criteria.budget


def _area_sentence(product: Product, area: Optional[Area], score: int, lang: str) -> Optional[str]:
    en = lang == "en"

    def where(a: Area) -> str:
        return geo.where(a, lang)

    place = place_of(product)
    if area is None:
        return ("It's %s." if en else "È %s.") % where(place) if place else None
    if score == INSIDE:
        if place is None or place == area:
            return ("It's %s, as you asked." if en else "È %s, come hai chiesto.") % where(area)
        return (("It's %s, %s as you asked." if en else "È %s, %s come hai chiesto.")
                % (where(place), where(area)))
    head = ("I have no compatible departures %s" if en
            else "Non ho partenze compatibili %s") % where(area)
    if place is None:
        return head + (": I'm suggesting this trip anyway." if en
                       else ": ti propongo comunque questo viaggio.")
    here = where(place)
    if score == SAME_REGION:
        region = geo.common_region(place, area)
        if region != place:
            here += ", " + where(region)
    elif place.kind != "country":
        country = geo.country_area(place.country_code)
        if country is not None:
            still = (", still " if en else ", sempre ") if score == SAME_COUNTRY else ", "
            here += still + where(country)
    return ("%s: this one is %s." if en else "%s: questa è %s.") % (head, here)


def _dates_budget_sentence(product: Product, criteria: Criteria, start: date, score: int,
                           within: bool) -> str:
    lang = criteria.language
    en = lang == "en"
    text = ("It leaves %s" if en else "Parte %s") % on_date(start, lang)
    if criteria.period is not None:
        text += ", in the period you asked for," if en else ", nel periodo che hai chiesto,"
    total = fmt_money(_total(product, criteria), lang)
    cheapest = "it's the cheapest compatible option" if en else "è la più economica compatibile"
    if criteria.budget is None:
        if criteria.area is None:
            return text + (" and %s." if en else " ed %s.") % cheapest
        return text + (" and costs %s in total." if en else " e costa %s in totale.") % total
    budget = fmt_money(criteria.budget, lang)
    if within:
        return text + ((" and costs %s in total, within your budget of %s." if en
                        else " e costa %s in totale, dentro il tuo budget di %s.") % (total, budget))
    text += ((" and costs %s in total, over your budget of %s" if en
              else " e costa %s in totale, oltre il tuo budget di %s") % (total, budget))
    if criteria.area is None:
        return text + (", but %s." if en else ", ma %s.") % cheapest
    if score == INSIDE:
        return text + ((", but it's the cheapest %s." if en else ", ma è la più economica %s.")
                       % geo.where(criteria.area, lang))
    return text + "."


def _reason(product: Product, criteria: Criteria, start: date, score: int, within: bool) -> str:
    first = _area_sentence(product, criteria.area, score, criteria.language)
    second = _dates_budget_sentence(product, criteria, start, score, within)
    return second if first is None else first + " " + second


def choose(products: Iterable[Product], criteria: Criteria, rejected_ids: Set[str],
           today: date) -> Union[Choice, NoChoice]:
    candidates = list(products)
    steps = (
        ("archived", lambda p: not p.archived),
        ("bookable", lambda p: p.bookable),
        ("trip", is_trip),
        ("sport", lambda p: criteria.sport is None or p.sport == criteria.sport),
        ("dates", lambda p: departure(p, criteria.period, today) is not None),
        ("pax", lambda p: _pax_ok(p, criteria.pax)),
        ("rejected", lambda p: p.id not in rejected_ids),
    )
    for name, keep in steps:
        candidates = [p for p in candidates if keep(p)]
        if not candidates:
            return NoChoice(name)
    candidates.sort(key=lambda p: (-area_score(p, criteria.area), not _within_budget(p, criteria),
                                   p.price, p.id))
    best = candidates[0]
    start, end = departure(best, criteria.period, today)
    score = area_score(best, criteria.area)
    within = _within_budget(best, criteria)
    return Choice(best, start, end, _reason(best, criteria, start, score, within), score, within)
