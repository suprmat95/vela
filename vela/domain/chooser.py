"""Chooser v3 (RF-06, RF-07, RF-09, RF-60, RF-61): una sola scelta deterministica.

Filtri duri in sequenza: archiviati, non prenotabili, non-viaggi, sport, date, pax, camere
(RF-66, M21-D: un prodotto con `max_pax_per_room` vuole almeno ceil(pax / limite) camere), livello
(RF-64, M21-C: solo un prodotto riservato esplicitamente ad altri livelli), prezzo
(dopo un rifiuto per prezzo solo totali minori del rifiutato, decisione M7), rifiutati (ultimi, così `NoChoice("rejected")` significa "i compatibili li hai scartati tutti"). Dei
prodotti equivalenti (RF-61, M21-B) resta un solo candidato, quello con l'id più basso. Tra i
restanti ordina come RF-60 (M21-B): aderenza all'area (dentro l'area 3, stessa regione 2,
stesso paese 1), totale entro budget, durata compatibile (RF-58), livello e lezioni compatibili
(RF-62..64, M21-C: prima il livello, poi le lezioni), partenza più vicina all'inizio del periodo
(o a oggi senza periodo), `featured` o offerta speciale, prezzo crescente, id numerico. Area,
budget, durata, livello e lezioni non escludono mai (tranne la riserva esplicita di RF-64): se
non sono rispettati la motivazione lo dichiara (RF-59, RF-64); la motivazione dice anche il livello
che ha deciso quando un prodotto più economico ha perso sulla partenza o su `featured`. Se un
filtro azzera i candidati, `NoChoice` porta il nome di quel filtro (RF-09); per le camere anche
le camere minime che avrebbero salvato un prodotto e il relativo massimo per camera, per il
livello i livelli a cui sono riservati i prodotti esclusi.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional, Set, Tuple, Union

from vela.domain import geo
from vela.domain.catalog import is_trip
from vela.domain.labels import ALL, ordered
from vela.domain.models import Area, Criteria, Period, Product
from vela.domain.say import (_people, fmt_money, fmt_nights, fmt_rooms, fmt_span, level_sentence,
                             nights_range, on_date)

FILTERS = ("archived", "bookable", "trip", "sport", "dates", "pax", "rooms", "level", "price",
           "rejected")

INSIDE, SAME_REGION, SAME_COUNTRY, ELSEWHERE = 3, 2, 1, 0

EQUIVALENT_PRICE_TOLERANCE = Decimal("0.05")   # RF-61: prezzo entro il 5% dell'id più basso


@dataclass(frozen=True)
class Choice:
    product: Product
    start_date: date
    end_date: date
    reason: str
    area_score: int
    within_budget: bool
    nights: int = 0
    duration_ok: bool = True


@dataclass(frozen=True)
class NoChoice:
    failed_criterion: str
    rooms_needed: Optional[int] = None        # solo "rooms" (RF-66): camere minime per un candidato
    max_pax_per_room: Optional[int] = None    # solo "rooms": il limite per camera di quel candidato
    levels: Optional[tuple] = None            # solo "level" (RF-64): i livelli dei prodotti esclusi


@dataclass(frozen=True)
class Why:
    """Cosa la motivazione può dire del prodotto scelto rispetto ai suoi pari (stessa area e
    stesso stato di budget), calcolato in `choose` così che ogni frase sia vera (RF-06)."""
    cheapest: bool = True            # nessun pari più economico che non abbia perso sulla durata
    cheaper_skipped: bool = False    # un pari più economico ha perso solo sulla durata (M21-A)
    departure_won: bool = False      # un pari più economico parte dopo (RF-60, livello 5)
    featured_won: bool = False       # un pari più economico parte lo stesso giorno senza `featured`


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


def rooms_needed(product: Product, pax: int) -> int:
    """RF-66: ceil(pax / `max_pax_per_room`); senza limite (None o 0) una camera basta."""
    limit = product.max_pax_per_room
    return -(-pax // limit) if limit else 1


def _rooms_ok(product: Product, pax: Optional[int], rooms: Optional[int]) -> bool:
    """Senza persone o senza camere (intenti salvati prima di M21-D) nessun filtro."""
    if pax is None or rooms is None:
        return True
    return rooms >= rooms_needed(product, pax)


def level_allowed(product: Product, level: Optional[str]) -> bool:
    """RF-64: escluso solo un prodotto `levels_exclusive` che non ammette il livello chiesto."""
    if level is None or not product.levels_exclusive:
        return True
    return ALL in product.levels or level in product.levels


def level_ok(product: Product, level: Optional[str]) -> bool:
    """RF-60 livello 4 (UC-C): compatibile = livello non chiesto, sconosciuto (`levels` vuoto),
    `all` o il livello chiesto."""
    return level is None or not product.levels or ALL in product.levels or level in product.levels


def coaching_ok(product: Product, wants_coaching: Optional[bool]) -> bool:
    """Con `wants_coaching=true` servono le lezioni; `false` non penalizza nessuno (decisione
    "Scelta v3": la descrizione non dice quando le lezioni sono obbligatorie)."""
    return wants_coaching is not True or product.coaching


def _no_choice(name: str, candidates: list, criteria: Criteria) -> NoChoice:
    """Il filtro `name` ha azzerato `candidates`. Per le camere: il candidato che ne chiede meno;
    per il livello: i livelli a cui sono riservati i candidati esclusi."""
    if name == "level" and candidates:
        return NoChoice(name, levels=tuple(ordered(frozenset().union(*(p.levels for p in candidates)))))
    if name != "rooms" or not candidates or criteria.pax is None:
        return NoChoice(name)
    best = min(candidates, key=lambda p: (rooms_needed(p, criteria.pax), id_key(p)))
    return NoChoice(name, rooms_needed(best, criteria.pax), best.max_pax_per_room)


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


def nights_between(start: date, end: date) -> int:
    """Notti del viaggio scelto da `departure`: `duration_days` − 1 o la finestra fissa."""
    return (end - start).days


def _duration_ok(nights: int, criteria: Criteria) -> bool:
    low, high = criteria.duration_min_nights, criteria.duration_max_nights
    return (low is None or nights >= low) and (high is None or nights <= high)


# durate della tabella di UC-A che hanno un nome proprio nella motivazione
_DURATION_NAMES = {(1, 3): ("weekend", "weekend trips"),
                   (2, 4): ("ponti o weekend lunghi", "long-weekend trips"),
                   (6, 8): ("viaggi di una settimana", "week-long trips"),
                   (13, 15): ("viaggi di due settimane", "two-week trips")}


def _duration_sentence(criteria: Criteria, start: date, end: date) -> str:
    """RF-59: "Non ho weekend compatibili: questo dura 5 notti, dal 9 al 14 ottobre." """
    lang = criteria.language
    en = lang == "en"
    low, high = criteria.duration_min_nights, criteria.duration_max_nights
    named = _DURATION_NAMES.get((low, high))
    if named is not None:
        wanted = named[1] if en else named[0]
    else:
        asked = nights_range(low, high, lang)
        if en:
            wanted = "trips of " + asked
        else:
            wanted = "viaggi " + (asked if asked.startswith("da ") else "di " + asked)
    nights = fmt_nights(nights_between(start, end), lang)
    return (("I have no %s: this one is %s, %s." if en else "Non ho %s compatibili: questo dura %s, %s.")
            % (wanted, nights, fmt_span(start, end, lang)))


def _dates_budget_sentence(product: Product, criteria: Criteria, start: date, score: int,
                           within: bool, why: Why) -> str:
    """"Parte il 5 ottobre 2026, la prima partenza nel periodo che hai chiesto, con un totale a
    partire da 1000 euro, dentro il tuo budget di 1500 euro, ed è tra i viaggi in evidenza del
    catalogo." Ogni pezzo compare solo se è vero (`why`): "la più economica" resta la frase di
    prima quando nessun pari costa meno, con "tra quelle della durata che hai chiesto" se un più
    economico ha perso solo sulla durata."""
    lang = criteria.language
    en = lang == "en"
    text = ("It leaves %s" if en else "Parte %s") % on_date(start, lang)
    if why.departure_won:
        if criteria.period is not None:
            text += (", the first departure in the period you asked for," if en
                     else ", la prima partenza nel periodo che hai chiesto,")
        else:
            text += ", the earliest departure available," if en else ", la prima partenza disponibile,"
    elif criteria.period is not None:
        text += ", in the period you asked for," if en else ", nel periodo che hai chiesto,"
    total = fmt_money(_total(product, criteria), lang)
    cheapest = "it's the cheapest compatible option" if en else "è la più economica compatibile"
    featured = ("it's one of the catalogue's featured trips" if en
                else "è tra i viaggi in evidenza del catalogo")
    length = ""
    if why.cheaper_skipped:
        length = " of the length you asked for" if en else " tra quelle della durata che hai chiesto"
        cheapest += length
    if criteria.budget is None:
        if criteria.area is None and why.cheapest:
            return text + (" and %s." if en else " ed %s.") % cheapest
        text += (" with a total starting at %s" if en else " con un totale a partire da %s") % total
        if why.featured_won:
            text += (", and %s" if en else ", ed %s") % featured
        return text + "."
    budget = fmt_money(criteria.budget, lang)
    if within:
        text += ((" with a total starting at %s, within your budget of %s" if en
                  else " con un totale a partire da %s, dentro il tuo budget di %s") % (total, budget))
        if why.featured_won:
            text += (", and %s" if en else ", ed %s") % featured
        return text + "."
    text += ((" with a total starting at %s, over your budget of %s" if en
              else " con un totale a partire da %s, oltre il tuo budget di %s") % (total, budget))
    if why.featured_won:
        return text + (", but %s." if en else ", ma %s.") % featured
    if not why.cheapest:
        return text + "."
    if criteria.area is None:
        return text + (", but %s." if en else ", ma %s.") % cheapest
    if score == INSIDE:
        return text + ((", but it's the cheapest %s%s." if en else ", ma è la più economica %s%s.")
                       % (geo.where(criteria.area, lang), length))
    return text + "."


def _rooms_sentence(product: Product, criteria: Criteria) -> Optional[str]:
    """RF-66: "Le camere di questo viaggio ospitano al massimo 2 persone: per 5 servono almeno 3
    camere, come hai chiesto." Solo quando il limite obbliga a più di una camera."""
    if criteria.pax is None or criteria.rooms is None or not product.max_pax_per_room:
        return None
    needed = rooms_needed(product, criteria.pax)
    if needed < 2:
        return None
    limit, pax, rooms = product.max_pax_per_room, criteria.pax, criteria.rooms
    if criteria.language == "en":
        tail = "as you asked" if rooms == needed else "you asked for %d" % rooms
        return ("The rooms of this trip hold at most %s: %s need at least %s, %s."
                % (_people(limit, "en"), _people(pax, "en"), fmt_rooms(needed, "en"), tail))
    tail = "come hai chiesto" if rooms == needed else "tu ne hai chieste %d" % rooms
    return ("Le camere di questo viaggio ospitano al massimo %s: per %d servono almeno %s, %s."
            % (_people(limit), pax, fmt_rooms(needed), tail))


def _reason(product: Product, criteria: Criteria, start: date, end: date, score: int,
            within: bool, duration_ok: bool, why: Why) -> str:
    sentences = [_area_sentence(product, criteria.area, score, criteria.language)]
    if not duration_ok:
        sentences.append(_duration_sentence(criteria, start, end))
    sentences.append(level_sentence(product.levels, product.coaching, criteria))   # RF-64
    sentences.append(_dates_budget_sentence(product, criteria, start, score, within, why))
    sentences.append(_rooms_sentence(product, criteria))
    return " ".join(s for s in sentences if s is not None)


def id_key(product: Product) -> tuple:
    """Ordine degli id (RF-60, RF-61): numerici prima, in ordine numerico ("78" < "100"); un id
    non numerico dopo, come stringa (decisione M10 sui possibili prefissi). Mai un'eccezione."""
    pid = product.id
    return (0, int(pid)) if pid.isdecimal() else (1, pid)


def _equivalence_key(product: Product) -> tuple:
    """RF-61: stesso hotel (nessun hotel = nessun hotel), stesso titolo minuscolo senza spazi doppi,
    stessa destinazione."""
    return (product.hotel or "", " ".join(product.title.lower().split()), product.destination or "")


def one_per_equivalence_group(products: Iterable[Product]) -> list:
    """RF-61: un solo candidato per gruppo di prodotti equivalenti, quello con l'id più basso
    (`id_key`). Scorrendo in ordine di id, un prodotto con la stessa chiave e il prezzo entro
    `EQUIVALENT_PRICE_TOLERANCE` di un capogruppo già tenuto esce; altrimenti è un capogruppo
    nuovo. Il confronto è sempre col capogruppo, mai a catena: 100, 104 e 108 danno due gruppi."""
    anchors = {}
    kept = []
    for product in sorted(products, key=id_key):
        group = anchors.setdefault(_equivalence_key(product), [])
        if any(abs(product.price - a.price) <= a.price * EQUIVALENT_PRICE_TOLERANCE for a in group):
            continue
        group.append(product)
        kept.append(product)
    return kept


RECHECK_AFTER = timedelta(hours=24)   # RF-34


def bookable(product: Product, now: Optional[datetime]) -> bool:
    """RF-33, RF-34: un prodotto marcato non prenotabile torna candidato 24 h dopo il controllo;
    il primo tentativo lo riconferma o lo riabilita. Senza `now` resta escluso."""
    if product.bookable:
        return True
    checked = product.bookable_checked_at
    return now is not None and checked is not None and now - checked >= RECHECK_AFTER


def _hard_filters(criteria: Criteria, today: date, now: Optional[datetime]) -> tuple:
    """I filtri duri che dipendono solo dal catalogo e dai criteri, in ordine (RF-07)."""
    return (
        ("archived", lambda p: not p.archived),
        ("bookable", lambda p: bookable(p, now)),
        ("trip", is_trip),
        ("sport", lambda p: criteria.sport in (None, "any") or p.sport == criteria.sport),
        ("dates", lambda p: departure(p, criteria.period, today) is not None),
        ("pax", lambda p: _pax_ok(p, criteria.pax)),
        ("rooms", lambda p: _rooms_ok(p, criteria.pax, criteria.rooms)),
        ("level", lambda p: level_allowed(p, criteria.level)),
    )


def cheapest_total(products: Iterable[Product], criteria: Criteria, today: date,
                   now: Optional[datetime] = None) -> Optional[Decimal]:
    """RF-69, regola 4: totale del prodotto compatibile più economico, con gli stessi filtri
    duri di `choose` e senza budget, rifiuti né tetto di prezzo; None se nessuno è compatibile."""
    filters = _hard_filters(criteria, today, now)
    totals = [_total(p, criteria) for p in products if all(keep(p) for _, keep in filters)]
    return min(totals) if totals else None


def choose(products: Iterable[Product], criteria: Criteria, rejected_ids: Set[str],
           today: date, now: Optional[datetime] = None,
           max_total: Optional[Decimal] = None) -> Union[Choice, NoChoice]:
    """`max_total`: tetto dopo un rifiuto per prezzo (decisione M7), totale strettamente minore."""
    candidates = list(products)
    steps = _hard_filters(criteria, today, now) + (
        ("price", lambda p: max_total is None or _total(p, criteria) < max_total),
        ("rejected", lambda p: p.id not in rejected_ids),
    )
    for name, keep in steps:
        before, candidates = candidates, [p for p in candidates if keep(p)]
        if not candidates:
            return _no_choice(name, before, criteria)
    candidates = one_per_equivalence_group(candidates)   # RF-61: mai vuoto
    trips = {p.id: departure(p, criteria.period, today) for p in candidates}   # mai None: filtro "dates"
    score_of = {p.id: area_score(p, criteria.area) for p in candidates}
    within_of = {p.id: _within_budget(p, criteria) for p in candidates}
    fits_of = {p.id: _duration_ok(nights_between(*trips[p.id]), criteria) for p in candidates}
    # livello 4 (M21-C): prima il livello, poi le lezioni; tutto vero se nessuno dei due è chiesto
    play_of = {p.id: (not level_ok(p, criteria.level), not coaching_ok(p, criteria.wants_coaching))
               for p in candidates}

    def rank(p: Product) -> tuple:
        # RF-60. La partenza si ordina per data: ogni partenza valida è già all'inizio del periodo
        # o dopo (o a oggi o dopo), quindi la distanza dall'inizio cresce con la data.
        return (-score_of[p.id], not within_of[p.id], not fits_of[p.id], play_of[p.id],
                trips[p.id][0], not _promoted(p), p.price, id_key(p))

    candidates.sort(key=rank)
    best = candidates[0]
    start, end = trips[best.id]
    score, within, fits = score_of[best.id], within_of[best.id], fits_of[best.id]
    peers = [p for p in candidates[1:] if score_of[p.id] == score and within_of[p.id] == within]
    cheaper = [p for p in peers if p.price < best.price]
    same_length = [p for p in cheaper if fits_of[p.id] == fits]
    # pari anche su livello e lezioni: solo tra questi partenza e `featured` hanno deciso
    same_rank = [p for p in same_length if play_of[p.id] == play_of[best.id]]
    why = Why(cheapest=not same_length, cheaper_skipped=bool(cheaper) and not same_length,
              departure_won=any(trips[p.id][0] > start for p in same_rank),
              featured_won=_promoted(best) and any(trips[p.id][0] == start and not _promoted(p)
                                                   for p in same_rank))
    reason = _reason(best, criteria, start, end, score, within, fits, why)
    return Choice(best, start, end, reason, score, within, nights_between(start, end), fits)


def _promoted(product: Product) -> bool:
    """RF-60, livello 6: `featured` o offerta speciale di HofJ, letti dal sync (M21-B)."""
    return product.featured or product.special_offer
