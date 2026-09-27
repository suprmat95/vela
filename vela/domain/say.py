"""Frasi pronte da leggere in italiano e inglese (RF-42): nessun markdown, nessun URL.

Ogni funzione riceve la lingua dell'intento (`"it"` default, `"en"`), direttamente o tramite i
criteri. I luoghi dei criteri passano da `geo.where`; titoli, destinazioni e hotel del catalogo
restano come sono (catalogo in locale `it`). Le frasi di errore delle superfici (`say_not_found`,
`say_unavailable`, `say_error`) restano in italiano: non conoscono l'intento.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.models import Criteria, OrderStatus, Period, ProductSummary, Proposal

MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]


def fmt_date(d: date, lang: str = "it") -> str:
    months = MONTHS_EN if lang == "en" else MONTHS_IT
    return "%d %s %d" % (d.day, months[d.month - 1], d.year)


def on_date(d: date, lang: str = "it") -> str:
    """Data con l'articolo: "il 1 ottobre 2026", "l'8 ottobre 2026"; in inglese "on 1 October 2026"."""
    if lang == "en":
        return "on %s" % fmt_date(d, lang)
    return ("l'%s" if d.day in (8, 11) else "il %s") % fmt_date(d)


def fmt_span(start: date, end: date, lang: str = "it") -> str:
    """"dal 9 al 14 ottobre", "dall'8 all'11 ottobre", "from 9 to 14 October"; l'anno solo se
    le due date cadono in anni diversi."""
    months = MONTHS_EN if lang == "en" else MONTHS_IT
    if start.year != end.year:
        first, last = fmt_date(start, lang), fmt_date(end, lang)
    elif start.month != end.month:
        first = "%d %s" % (start.day, months[start.month - 1])
        last = "%d %s" % (end.day, months[end.month - 1])
    else:
        first, last = str(start.day), "%d %s" % (end.day, months[end.month - 1])
    if lang == "en":
        return "from %s to %s" % (first, last)
    return "%s%s %s%s" % ("dall'" if start.day in (8, 11) else "dal ", first,
                          "all'" if end.day in (8, 11) else "al ", last)


def fmt_nights(n: int, lang: str = "it") -> str:
    if lang == "en":
        return "1 night" if n == 1 else "%d nights" % n
    return "1 notte" if n == 1 else "%d notti" % n


def nights_range(low: Optional[int], high: Optional[int], lang: str = "it") -> str:
    """Durata chiesta (M21, RF-58): "3 notti", "da 1 a 3 notti", "almeno 3 notti"."""
    en = lang == "en"
    if low is not None and low == high:
        return fmt_nights(low, lang)
    if low is not None and high is not None:
        return ("%d to %s" if en else "da %d a %s") % (low, fmt_nights(high, lang))
    if low is not None:
        return ("at least %s" if en else "almeno %s") % fmt_nights(low, lang)
    return ("at most %s" if en else "al massimo %s") % fmt_nights(high, lang)


def fmt_money(value: Decimal, lang: str = "it") -> str:
    q = value.quantize(Decimal("0.01"))
    unit = "euros" if lang == "en" else "euro"
    if q == q.to_integral_value():
        return "%d %s" % (int(q), unit)
    number = format(q, "f")
    return "%s %s" % (number if lang == "en" else number.replace(".", ","), unit)


def _people(n: Optional[int], lang: str = "it") -> str:
    if n is None:
        return ""
    if lang == "en":
        return "1 person" if n == 1 else "%d people" % n
    return "1 persona" if n == 1 else "%d persone" % n


def fmt_rooms(n: int, lang: str = "it") -> str:
    if lang == "en":
        return "1 room" if n == 1 else "%d rooms" % n
    return "1 camera" if n == 1 else "%d camere" % n


def rooms_said(pax: Optional[int], rooms: Optional[int]) -> bool:
    """M21-D (decisione): le camere si dicono con più di 2 persone o con più di una camera; con
    1 o 2 persone in 1 camera è il default, non un criterio detto. None = intento pre-M21-D."""
    return rooms is not None and ((pax or 0) > 2 or rooms > 1)


def _join(parts: list, lang: str = "it") -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + (" and " if lang == "en" else " e ") + parts[-1]


def _when(period: Period, lang: str = "it") -> str:
    if period.start == period.end:
        return on_date(period.start, lang)
    if lang == "en":
        return "between %s and %s" % (fmt_date(period.start, lang), fmt_date(period.end, lang))
    return "tra %s e %s" % (on_date(period.start), on_date(period.end))


_ANY_SPORT = {"it": "padel o tennis", "en": "padel or tennis"}


def _comma(part: str) -> str:
    return part if part.endswith(",") else part + ","


def _describe(c: Criteria) -> str:
    """I criteri capiti come frase: "un viaggio di padel in Spagna … per 2 persone …"."""
    lang = c.language
    en = lang == "en"
    sport = _ANY_SPORT["en" if en else "it"] if c.sport == "any" else c.sport
    if en:
        parts = ["a %s trip" % sport if sport else "a trip"]
    else:
        parts = ["un viaggio di %s" % sport if sport else "un viaggio"]
    if c.area:
        parts.append(geo.where(c.area, lang))
    if c.excluded_areas:
        # tra virgole come la durata: "…in Spagna, esclusi i viaggi a Estepona, a ottobre…" (RF-73)
        parts[-1] = _comma(parts[-1])
        places = [geo.display_name(a, lang) if en else geo.where(a, lang) for a in c.excluded_areas]
        more = (c.period or c.duration_min_nights is not None or c.duration_max_nights is not None
                or c.pax or rooms_said(c.pax, c.rooms) or _level_and_coaching(c) or c.budget is not None)
        parts.append(("excluding %s" if en else "esclusi i viaggi %s") % _join(places, lang)
                     + ("," if more else ""))
    if c.period:
        parts.append(_when(c.period, lang))
    if c.duration_min_nights is not None or c.duration_max_nights is not None:
        # tra virgole: "…a ottobre, da 1 a 3 notti, per 2 persone" (M21, RF-58)
        parts[-1] = _comma(parts[-1])
        parts.append(nights_range(c.duration_min_nights, c.duration_max_nights, lang)
                     + ("," if c.pax or c.budget is not None else ""))
    if c.pax:
        parts.append(("for %s" if en else "per %s") % _people(c.pax, lang))
    if rooms_said(c.pax, c.rooms):
        parts.append("in " + fmt_rooms(c.rooms, lang))
    play = _level_and_coaching(c)
    if play:
        # tra virgole come la durata: "…per 2 persone, livello principiante, con lezioni, con un budget…"
        parts[-1] = _comma(parts[-1])
        parts.append(", ".join(play) + ("," if c.budget is not None else ""))
    if c.budget is not None:
        parts.append(_budget_reading(c))
    return " ".join(parts)


_LEVEL_NAMES = {"it": {"beginner": "principiante", "intermediate": "intermedio", "advanced": "avanzato"},
                "en": {"beginner": "beginner", "intermediate": "intermediate", "advanced": "advanced"}}


def _level_and_coaching(c: Criteria) -> list:
    """M21-C (RF-54, RF-62): "livello principiante", "con lezioni" / "senza lezioni"."""
    en = c.language == "en"
    words = []
    if c.level in _LEVEL_NAMES["it"]:
        name = _LEVEL_NAMES["en" if en else "it"][c.level]
        words.append(("%s level" if en else "livello %s") % name)
    if c.wants_coaching is True:
        words.append("with lessons" if en else "con lezioni")
    elif c.wants_coaching is False:
        words.append("without lessons" if en else "senza lezioni")
    return words


def _budget_reading(c: Criteria) -> str:
    """RF-70: "con un budget di 600 euro a persona, 1800 in tutto", "… di 600 euro in tutto";
    un budget salvato prima di M21-E è un totale."""
    lang = c.language
    en = lang == "en"
    if c.budget_scope == "per_person" and c.pax:
        each = fmt_money(c.budget / c.pax, lang)
        total = fmt_money(c.budget, lang).rsplit(" ", 1)[0]
        return ("with a budget of %s per person, %s in total" if en
                else "con un budget di %s a persona, %s in tutto") % (each, total)
    return ("with a budget of %s in total" if en else "con un budget di %s in tutto") % fmt_money(c.budget, lang)


def say_understood(c: Criteria) -> str:
    """RF-54: i criteri capiti, ripetuti così che il viaggiatore possa correggerli."""
    return ("Got it: %s." if c.language == "en" else "Ho capito: %s.") % _describe(c)


def say_intent_created(c: Criteria, discarded: tuple = ()) -> str:
    looking = ("I'm looking for the right proposal." if c.language == "en"
               else "Cerco la proposta giusta.")
    return prefixed(say_discarded(discarded, c.language), "%s %s" % (say_understood(c), looking))


def prefixed(prefix: str, sentence: str) -> str:
    return "%s %s" % (prefix, sentence) if prefix else sentence


_DISCARDED = {
    "it": {"sport": "Lo sport %s non lo tratto: solo padel o tennis.",
           "area": "Non conosco il luogo %s.",
           "period": "Non ho potuto usare le date %s.",
           "pax": "Non ho potuto usare %s come numero di persone.",
           "budget": "Non ho potuto usare %s come budget.",
           "direction": "Non so spostare la ricerca verso %s.",
           "duration": "Non ho potuto usare %s come durata in notti.",
           "budget_scope": "Non ho potuto usare %s come lettura del budget, a persona o in tutto.",
           "rooms": "Non ho potuto usare %s come numero di camere.",
           "level": "Non ho potuto usare %s come livello di gioco: principiante, intermedio o avanzato.",
           "wants_coaching": "Non ho potuto usare %s per sapere se vuoi lezioni: sì o no.",
           "reject_kind": "Non ho potuto usare %s come tipo di rifiuto.",
           "keep_product": "Non ho potuto usare %s per sapere se tenere questo viaggio: sì o no."},
    "en": {"sport": "I don't handle %s: only padel or tennis.",
           "area": "I don't know the place %s.",
           "period": "I couldn't use the dates %s.",
           "pax": "I couldn't use %s as the number of people.",
           "budget": "I couldn't use %s as the budget.",
           "direction": "I can't move the search %s.",
           "duration": "I couldn't use %s as the length in nights.",
           "budget_scope": "I couldn't use %s as the budget reading, per person or in total.",
           "rooms": "I couldn't use %s as the number of rooms.",
           "level": "I couldn't use %s as the playing level: beginner, intermediate or advanced.",
           "wants_coaching": "I couldn't use %s to know whether you want lessons: yes or no.",
           "reject_kind": "I couldn't use %s as the kind of rejection.",
           "keep_product": "I couldn't use %s to know whether to keep this trip: yes or no."},
}
_DIRECTION_WORDS = {"it": {"north": "nord", "south": "sud"}, "en": {"north": "north", "south": "south"}}


def _discarded_value(field: str, value, lang: str) -> str:
    if field in ("period", "duration"):
        start, end = value
        return "%s - %s" % tuple("?" if v is None else v for v in (start, end))
    if field == "direction":
        return _DIRECTION_WORDS.get(lang, _DIRECTION_WORDS["it"]).get(value, str(value))
    return str(value)


def say_discarded(items: tuple, lang: str = "it") -> str:
    """RF-53, RF-54: una frase per ogni campo strutturato scartato perché invalido."""
    texts = _DISCARDED.get(lang, _DISCARDED["it"])
    return " ".join(texts[field] % _discarded_value(field, value, lang) for field, value in items)


def say_untranslatable(lang: str = "it") -> str:
    """RF-54: un motivo di rifiuto che non diventa nessun criterio."""
    if lang == "en":
        return "I can't choose based on that: I've only excluded the previous proposal."
    return "Non so scegliere in base a questo: ho escluso solo la proposta di prima."


# M21-F (RF-75): la domanda chiusa per un motivo di rifiuto che non si classifica
QUESTION_REASON = {"it": "Cosa non ti convince: il posto, l'hotel, le date o il prezzo?",
                   "en": "What doesn't convince you: the place, the hotel, the dates or the price?"}


def question_reason(lang: str = "it") -> str:
    return QUESTION_REASON.get(lang, QUESTION_REASON["it"])


def say_hotel_excluded(hotel: Optional[str], lang: str = "it") -> str:
    """RF-72: "Ho escluso i viaggi con l'hotel X."; senza hotel si esclude lo stesso viaggio."""
    if lang == "en":
        return ("I've left out the trips at %s." % hotel if hotel
                else "This trip doesn't name its hotel: I've left out this trip.")
    return ("Ho escluso i viaggi con l'hotel %s." % hotel if hotel
            else "Questo viaggio non indica l'hotel: ho escluso questo viaggio.")


def say_same_trip(lang: str = "it") -> str:
    """RF-74: la proposta successiva è lo stesso prodotto con un'altra partenza."""
    return "Same trip, with another departure." if lang == "en" else "Stesso viaggio, con un'altra partenza."


def say_proposal(product: ProductSummary, p: Proposal, lang: str = "it",
                 rooms: Optional[int] = None) -> str:
    """`rooms` (M21-D, RF-06): "per 5 persone in 3 camere", con la regola di `rooms_said`."""
    hotel = ", hotel %s" % product.hotel if product.hotel else ""
    people = _people(p.pax, lang)
    if rooms_said(p.pax, rooms):
        people += " in " + fmt_rooms(rooms, lang)
    if lang == "en":
        where = " in %s" % product.destination if product.destination else ""
        if p.start_date == p.end_date:
            when = on_date(p.start_date, lang)
        else:
            when = "from %s to %s" % (fmt_date(p.start_date, lang), fmt_date(p.end_date, lang))
        return ("I suggest %s%s%s, %s for %s, starting at %s per person: that's the minimum "
                "price, the actual total depends on dates and availability and I'll tell you "
                "before the payment link. %s Shall I go ahead?"
                % (product.title, where, hotel, when, people, fmt_money(p.price_from, lang), p.reason))
    where = " a %s" % product.destination if product.destination else ""
    if p.start_date == p.end_date:
        when = on_date(p.start_date)
    else:
        when = "dal %s al %s" % (fmt_date(p.start_date), fmt_date(p.end_date))
    return ("Ti propongo %s%s%s, %s per %s, a partire da %s a persona: è il prezzo minimo, il "
            "totale effettivo dipende da date e disponibilità e te lo dico prima del link di "
            "pagamento. %s Ti va?"
            % (product.title, where, hotel, when, people, fmt_money(p.price_from), p.reason))


# M21-C (RF-64): livelli del catalogo detti ai giocatori
_PLAYERS = {"it": {"beginner": "principianti", "intermediate": "intermedi", "advanced": "avanzati"},
            "en": {"beginner": "beginner", "intermediate": "intermediate", "advanced": "advanced"}}
_LEVEL_ORDER = ("beginner", "intermediate", "advanced")


def _players(levels, lang: str = "it") -> str:
    """"principianti", "giocatori intermedi e avanzati"; "beginners", "intermediate and advanced
    players"."""
    known = [lv for lv in _LEVEL_ORDER if lv in levels]
    if lang == "en":
        return "beginners" if known == ["beginner"] else "%s players" % _join(
            [_PLAYERS["en"][lv] for lv in known], "en")
    return "principianti" if known == ["beginner"] else "giocatori " + _join(
        [_PLAYERS["it"][lv] for lv in known])


def level_sentence(levels: frozenset, coaching: bool, c: Criteria) -> Optional[str]:
    """RF-64 (UC-C): se il prodotto proposto rispetta livello e lezioni chiesti. Rispettati: "Il
    programma è pensato anche per principianti e include lezioni o allenamenti." Non rispettati:
    "Non ho trovato viaggi per principianti con lezioni: questo è pensato per giocatori intermedi
    e avanzati e include lezioni o allenamenti." Niente se il viaggiatore non ha chiesto né
    livello né lezioni; `wants_coaching=false` non si dichiara (non penalizza)."""
    level, lessons = c.level, c.wants_coaching is True
    if level not in _LEVEL_ORDER and not lessons:
        return None
    en = c.language == "en"
    lang = "en" if en else "it"
    facts, ok = [], True
    if level in _LEVEL_ORDER:
        known = {lv for lv in levels if lv in _LEVEL_ORDER}
        if "all" in levels:
            facts.append("is designed for players of every level" if en
                         else "è pensato per giocatori di ogni livello")
        elif not known:
            facts.append("doesn't state a playing level" if en else "non indica un livello di gioco")
        elif level in known:
            only = known == {level}
            facts.append(("is designed for %s" + ("" if only else " too")) % _players({level}, lang) if en
                         else ("è pensato %sper %s" % ("" if only else "anche ", _players({level}, lang))))
        else:
            ok = False
            facts.append(("is designed for %s" if en else "è pensato per %s") % _players(known, lang))
    if lessons:
        ok = ok and coaching
        facts.append(("includes lessons or training" if en else "include lezioni o allenamenti") if coaching
                     else ("doesn't include lessons" if en else "non prevede lezioni"))
    joined = (" and " if en else " e ").join(facts)
    if ok:
        return ("The programme %s." if en else "Il programma %s.") % joined
    wanted = []
    if level in _LEVEL_ORDER:
        wanted.append("for %s" % _players({level}, lang) if en else "per %s" % _players({level}, lang))
    if lessons:
        wanted.append("with lessons" if en else "con lezioni")
    return (("I have no trips %s: this one %s." if en else "Non ho trovato viaggi %s: questo %s.")
            % (" ".join(wanted), joined))


def say_rooms_below_minimum(max_pax_per_room: int, pax: int, needed: int, lang: str = "it") -> str:
    """RF-65 su `accept_proposal`: la correzione delle camere è sotto il minimo del prodotto
    (RF-66); nessun ordine, la domanda di RF-04."""
    from vela.domain.intent import question_rooms   # evita l'import circolare (intent importa say? no: models)
    if lang == "en":
        head = ("The rooms of this trip hold at most %s: %s need at least %s."
                % (_people(max_pax_per_room, lang), _people(pax, lang), fmt_rooms(needed, lang)))
    else:
        head = ("Le camere di questo viaggio ospitano al massimo %s: per %d servono almeno %s."
                % (_people(max_pax_per_room), pax, fmt_rooms(needed)))
    return head + " " + question_rooms(lang)


def say_details(product: ProductSummary, has_program: bool, lang: str = "it") -> str:
    """RF-83: frase breve; i contenuti sono nei campi, da riassumere a chi li chiede."""
    if lang == "en":
        what = ("the day-by-day program, the hotel and the club" if has_program else
                "the description, the hotel and the club; there is no day-by-day program")
        return "Here are the details of %s: %s. What would you like to know?" % (product.title, what)
    what = ("il programma giorno per giorno, l'hotel e il club" if has_program else
            "la descrizione, l'hotel e il club; il programma giorno per giorno non c'è")
    return "Ecco i dettagli di %s: %s. Cosa vuoi sapere?" % (product.title, what)


_NO_MATCH = {
    "it": {
        "archived": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
        "bookable": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
        "trip": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
        "rejected": "Hai già scartato tutte le proposte compatibili con la tua richiesta: dimmi cosa vuoi cambiare.",
        "sport": "Non trovo nessun viaggio per lo sport che hai chiesto: prova con l'altro sport o dimmi cosa vuoi cambiare.",
        "dates": "Non trovo partenze nel periodo che hai chiesto: prova con un altro periodo.",
        "pax": "Non trovo viaggi per il numero di persone indicato: prova a cambiare il numero di persone.",
        "price": "Non ho niente di più economico per la tua richiesta: prova a cambiare periodo o destinazione.",
        "rooms": "Non trovo viaggi per il numero di camere indicato: prova a cambiare il numero di camere.",
        None: "Non trovo nessun viaggio compatibile: dimmi cosa vuoi cambiare.",
        "sport_value": "Non trovo nessun viaggio di %s: prova con l'altro sport o dimmi cosa vuoi cambiare.",
        "dates_value": "Non trovo partenze %s: prova con un altro periodo.",
        "pax_value": "Non trovo viaggi per %s: prova a cambiare il numero di persone.",
        # M21-D (RF-68): da solo restano solo viaggi da 2 persone in su
        "pax_alone": "I viaggi%s compatibili partono da 2 persone: da solo non posso prenotarli. Vuoi cambiare qualcosa?",
        "pax_alone_sport": " di %s",
        # M21-D (RF-66): le camere minime che avrebbero salvato un prodotto
        "rooms_value": ("I viaggi compatibili hanno camere da massimo %s: per %s servono almeno %s. "
                        "Vuoi cambiare il numero di camere?"),
        # M21-C (RF-64): i compatibili sono riservati ad altri livelli
        "level": "I viaggi compatibili sono riservati a un altro livello di gioco. Vuoi cambiare qualcosa?",
        "level_value": "I viaggi compatibili sono riservati a %s. Vuoi cambiare qualcosa?",
        # M21-F (RF-72..74)
        "place": "Senza i luoghi che hai escluso non trovo altri viaggi compatibili. Vuoi cambiare qualcosa?",
        "place_value": "Esclusi i viaggi %s non trovo altri viaggi compatibili. Vuoi cambiare qualcosa?",
        "hotel": "Gli altri viaggi compatibili sono negli hotel che hai scartato. Vuoi cambiare qualcosa?",
        "same_trip": "Questo viaggio non ha altre partenze disponibili. Vuoi che cerchi un altro viaggio?",
        "same_trip_value": "Questo viaggio non ha altre partenze %s. Vuoi che cerchi un altro viaggio?",
    },
    "en": {
        "archived": "Right now I have no bookable trips: please try again later.",
        "bookable": "Right now I have no bookable trips: please try again later.",
        "trip": "Right now I have no bookable trips: please try again later.",
        "rejected": "You have already turned down every proposal that matches your request: tell me what you want to change.",
        "sport": "I can't find any trip for the sport you asked for: try the other sport or tell me what you want to change.",
        "dates": "I can't find departures in the period you asked for: try another period.",
        "pax": "I can't find trips for that number of people: try changing the number of people.",
        "price": "I have nothing cheaper for your request: try another period or destination.",
        "rooms": "I can't find trips for that number of rooms: try changing the number of rooms.",
        None: "I can't find any matching trip: tell me what you want to change.",
        "sport_value": "I can't find any %s trip: try the other sport or tell me what you want to change.",
        "dates_value": "I can't find departures %s: try another period.",
        "pax_value": "I can't find trips for %s: try changing the number of people.",
        "pax_alone": "The compatible%s trips start from 2 people: I can't book them for you alone. Do you want to change something?",
        "pax_alone_sport": " %s",
        "rooms_value": ("The compatible trips have rooms for at most %s: %s need at least %s. "
                        "Do you want to change the number of rooms?"),
        "level": "The compatible trips are reserved for another playing level. Do you want to change something?",
        "level_value": "The compatible trips are reserved for %s. Do you want to change something?",
        "place": "Without the places you excluded I can't find other matching trips. Do you want to change something?",
        "place_value": "Excluding %s, I can't find other matching trips. Do you want to change something?",
        "hotel": "The other matching trips are in the hotels you turned down. Do you want to change something?",
        "same_trip": "This trip has no other departures. Shall I look for another trip?",
        "same_trip_value": "This trip has no other departures %s. Shall I look for another trip?",
    },
}


def say_no_match(criterion: str, criteria: Optional[Criteria] = None,
                 rooms_needed: Optional[int] = None, max_pax_per_room: Optional[int] = None,
                 levels: Optional[tuple] = None, same_trip: bool = False) -> str:
    """Frase di RF-09: dice quale criterio non si riesce a soddisfare e, se noto, con che valore,
    nella lingua dei criteri. Con una persona sola il filtro `pax` cade solo per `minPax` ≥ 2
    (RF-68); per `rooms` i due numeri arrivano dal chooser (RF-66), per `level` i livelli a cui
    sono riservati i prodotti esclusi (RF-64). `same_trip` (RF-74): lo stesso prodotto chiesto
    con `keep_product` non ha altre partenze."""
    c = criteria or Criteria()
    lang = c.language
    texts = _NO_MATCH.get(lang, _NO_MATCH["it"])
    if criterion == "dates" and same_trip:
        return (texts["same_trip_value"] % _when(c.period, lang) if c.period
                else texts["same_trip"])
    if criterion == "place" and c.excluded_areas:
        en = lang == "en"
        places = [geo.display_name(a, lang) if en else geo.where(a, lang) for a in c.excluded_areas]
        return texts["place_value"] % _join(places, lang)
    if criterion == "sport" and c.sport:
        return texts["sport_value"] % c.sport
    if criterion == "dates" and c.period:
        return texts["dates_value"] % _when(c.period, lang)
    if criterion == "pax" and c.pax == 1:
        sport = texts["pax_alone_sport"] % c.sport if c.sport in ("padel", "tennis") else ""
        return texts["pax_alone"] % sport
    if criterion == "pax" and c.pax:
        return texts["pax_value"] % _people(c.pax, lang)
    if criterion == "rooms" and c.pax and rooms_needed and max_pax_per_room:
        return texts["rooms_value"] % (_people(max_pax_per_room, lang), _people(c.pax, lang),
                                       fmt_rooms(rooms_needed, lang))
    if criterion == "level" and levels and any(lv in _LEVEL_ORDER for lv in levels):
        return texts["level_value"] % _players(levels, "en" if lang == "en" else "it")
    return texts.get(criterion, texts[None])


_ORDINALS = {
    "it": ["secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo"],
    "en": ["second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"],
}
_FIELD_LABELS = {
    "it": {"first_name": "il nome", "last_name": "il cognome", "email": "l'email",
           "phone": "il telefono"},
    "en": {"first_name": "the first name", "last_name": "the last name", "email": "the email",
           "phone": "the phone number"},
}


def _label(field: str, lang: str = "it") -> str:
    labels = _FIELD_LABELS.get(lang, _FIELD_LABELS["it"])
    if field.startswith("participants["):
        index = int(field[len("participants["):field.index("]")])
        leaf = field.split(".")[-1]
        ordinals = _ORDINALS.get(lang, _ORDINALS["it"])
        if lang == "en":
            ordinal = ordinals[index] if index < len(ordinals) else "number %d" % (index + 2)
            return "%s of the %s participant" % (labels[leaf], ordinal)
        ordinal = ordinals[index] if index < len(ordinals) else "numero %d" % (index + 2)
        return "%s del %s partecipante" % (labels[leaf], ordinal)
    return labels.get(field, field)


def say_missing(missing: list, lang: str = "it") -> str:
    head = "To book I still need: %s." if lang == "en" else "Per prenotare mi servono ancora: %s."
    return head % _join([_label(f, lang) for f in missing], lang)


_STATUS = {
    "it": {
        OrderStatus.CONFIRMED: "La tua prenotazione è confermata, codice %s.",
        OrderStatus.AWAITING_PAYMENT: "L'ordine è in attesa del pagamento: usa il link che ti ho mandato.",
        OrderStatus.PAID_PENDING_BOOKING: ("Pagamento ricevuto, sto completando la prenotazione: "
                                           "richiedi lo stato tra qualche secondo."),
        OrderStatus.BOOKING_FAILED: ("Il pagamento è arrivato ma la prenotazione non è riuscita: "
                                     "riprovo io, e se non ci riesco ti avviso."),
        OrderStatus.QUEUED: "Sto preparando il pagamento con il fornitore: chiedimi di nuovo tra poco.",
        OrderStatus.AWAITING_CONFIRMATION: ("Ho il prezzo effettivo: dimmi se confermi e preparo il "
                                            "link di pagamento."),
        OrderStatus.REPLACED: "Quel viaggio non è più prenotabile: ti ho proposto un'alternativa.",
        OrderStatus.CANCELLED: "Ho annullato l'ordine.",
        OrderStatus.FAILED: ("Non sono riuscito a preparare il pagamento: %s. Se vuoi, riproviamo "
                             "con una nuova proposta."),
        None: "Il link di pagamento è scaduto: dimmi se vuoi che prepari una nuova proposta.",
    },
    "en": {
        OrderStatus.CONFIRMED: "Your booking is confirmed, code %s.",
        OrderStatus.AWAITING_PAYMENT: "The order is waiting for payment: use the link I sent you.",
        OrderStatus.PAID_PENDING_BOOKING: ("Payment received, I'm completing the booking: ask for "
                                           "the status again in a few seconds."),
        OrderStatus.BOOKING_FAILED: ("The payment arrived but the booking did not go through: "
                                     "I'll try again, and if I can't I'll let you know."),
        OrderStatus.QUEUED: "I'm preparing the payment with the supplier: ask me again in a moment.",
        OrderStatus.AWAITING_CONFIRMATION: ("I have the actual price: tell me if you confirm and I'll "
                                            "prepare the payment link."),
        OrderStatus.REPLACED: "That trip can no longer be booked: I've suggested an alternative.",
        OrderStatus.CANCELLED: "I've cancelled the order.",
        OrderStatus.FAILED: ("I couldn't prepare the payment: %s. If you like, we can try again "
                             "with a new proposal."),
        None: "The payment link has expired: tell me if you want me to prepare a new proposal.",
    },
}


_AWAITING_AMOUNT = {
    "it": "L'ordine è in attesa del pagamento di %s: usa il link che ti ho mandato.",
    "en": "The order is waiting for payment of %s: use the link I sent you.",
}
_AWAITING_AMOUNT_SMS = {
    "it": ("L'ordine è in attesa del pagamento di %s: usa il link che ti ho mandato, anche per SMS "
           "al numero che finisce con %s."),
    "en": "The order is waiting for payment of %s: use the link I sent you, also by text to the number ending in %s.",
}


def say_status(status: OrderStatus, booking_code: Optional[str], failure_reason: Optional[str],
               lang: str = "it", total: Optional[Decimal] = None, minutes: Optional[int] = None,
               price_from_total: Optional[Decimal] = None, phone_tail: Optional[str] = None,
               pax: Optional[int] = None) -> str:
    if status == OrderStatus.QUEUED and minutes is not None:
        if total is None:   # prima del prezzo effettivo
            return say_queued_for_price(minutes, lang)
        return say_queued(minutes, lang, phone_tail)
    if status == OrderStatus.AWAITING_CONFIRMATION and total is not None:
        return say_confirm_price(total, price_from_total, pax, lang)
    if status == OrderStatus.AWAITING_PAYMENT and total is not None:
        if phone_tail:
            text = _AWAITING_AMOUNT_SMS.get(lang, _AWAITING_AMOUNT_SMS["it"]) % (fmt_money(total, lang), phone_tail)
        else:
            text = _AWAITING_AMOUNT.get(lang, _AWAITING_AMOUNT["it"]) % fmt_money(total, lang)
        if price_from_total is not None and total != price_from_total:
            text = _price_changed(total, price_from_total, lang) + " " + text   # RF-16: prima del link
        return text
    texts = _STATUS.get(lang, _STATUS["it"])
    text = texts.get(status, texts[None])
    if status == OrderStatus.CONFIRMED:
        return text % booking_code
    if status == OrderStatus.FAILED:
        return text % (failure_reason or failure_reason_default(lang))
    return text


def _price_changed(total: Decimal, price_from_total: Decimal, lang: str = "it") -> str:
    if lang == "en":
        return "The real total is %s, not the estimated %s." % (
            fmt_money(total, lang), fmt_money(price_from_total, lang).replace(" euros", ""))
    return "Il totale reale è %s, non i %s stimati." % (
        fmt_money(total), fmt_money(price_from_total).replace(" euro", ""))


def say_confirm_price(total: Decimal, price_from_total: Optional[Decimal], pax: Optional[int],
                      lang: str = "it") -> str:
    """Decisione 2026-09-26: il prezzo effettivo del carrello, confrontato con la stima della
    proposta, e la domanda di conferma. Il link nasce solo dopo il sì."""
    people = _people(pax, lang)
    if lang == "en":
        text = "The actual price is %s in total" % fmt_money(total, lang)
        text += " for %s" % people if people else ""
        if price_from_total is None or total == price_from_total:
            text += ", as estimated." if price_from_total is not None else "."
        else:
            more = "more" if total > price_from_total else "less"
            text += ", %s than the estimated %s." % (more, fmt_money(price_from_total, lang))
        return text + " Do you confirm? If you say yes, I'll prepare the payment link."
    text = "Il prezzo effettivo è %s in totale" % fmt_money(total)
    text += " per %s" % people if people else ""
    if price_from_total is None or total == price_from_total:
        text += ", come stimato." if price_from_total is not None else "."
    else:
        more = "più" if total > price_from_total else "meno"
        text += ", %s dei %s stimati." % (more, fmt_money(price_from_total).replace(" euro", ""))
    return text + " Confermi? Se mi dici di sì preparo il link di pagamento."


def say_price_changed_since(total: Decimal, confirmed: Decimal, lang: str = "it") -> str:
    """RF-84: il carrello, creato dopo il sì a un prezzo in cache, costa un'altra cifra. Il link
    nasce solo con un nuovo sì."""
    if lang == "en":
        return ("In the meantime the price has changed: it is now %s in total instead of the %s you "
                "confirmed. Do you confirm? If you say yes, I'll prepare the payment link." % (
                    fmt_money(total, lang), fmt_money(confirmed, lang).replace(" euros", "")))
    return ("Nel frattempo il prezzo è cambiato: ora è %s in totale invece dei %s che avevi "
            "confermato. Confermi? Se mi dici di sì preparo il link di pagamento." % (
                fmt_money(total), fmt_money(confirmed).replace(" euro", "")))


def say_queued_for_price(minutes: int, lang: str = "it") -> str:
    """L'attesa per il prezzo effettivo, quando il caso d'uso smette di aspettare prima che il
    carrello sia pronto: nessun SMS, il prezzo si chiede all'agente."""
    if lang == "en":
        wait = "a minute" if minutes == 1 else "%d minutes" % minutes
        return ("I'm getting the actual price from the supplier: it will be ready in about %s. "
                "Ask me for it and I'll tell you before sending the payment link." % wait)
    wait = "un minuto" if minutes == 1 else "%d minuti" % minutes
    return ("Sto chiedendo il prezzo effettivo al fornitore: sarà pronto tra circa %s. Chiedimelo "
            "e te lo dico prima di mandarti il link di pagamento." % wait)


def say_queued(minutes: int, lang: str = "it", phone_tail: Optional[str] = None) -> str:
    """RF-45: l'attesa dichiarata in minuti (già arrotondati per eccesso, almeno 1). Con le
    ultime cifre di un numero valido annuncia i due SMS (RF-19, RF-57) e ricorda che si può
    sempre chiedere lo stato, anche se l'SMS non arriva (decisione 2026-09-26)."""
    if lang == "en":
        wait = "a minute" if minutes == 1 else "%d minutes" % minutes
        if phone_tail:
            return ("You're in the queue: the payment link will be ready in about %s and I'll text "
                    "it to the number ending in %s. I'll text you again when the booking is "
                    "confirmed. If you want to know how it's going, or the text hasn't arrived in "
                    "a few minutes, just ask me." % (wait, phone_tail))
        return ("You're in the queue: the payment link will be ready in about %s. Ask me how it's "
                "going whenever you like." % wait)
    wait = "un minuto" if minutes == 1 else "%d minuti" % minutes
    if phone_tail:
        return ("Ti ho messo in coda: tra circa %s il link di pagamento sarà pronto e te lo mando "
                "per SMS al numero che finisce con %s. Ti scrivo di nuovo quando la prenotazione "
                "è confermata. Se vuoi sapere a che punto è, o se l'SMS non arriva entro qualche "
                "minuto, chiedimi pure." % (wait, phone_tail))
    return ("Ti ho messo in coda: tra circa %s il link di pagamento sarà pronto. Chiedimi a che "
            "punto è quando vuoi." % wait)


_REPLACED_INTRO = {
    "it": "Quel viaggio non è più prenotabile, ti propongo un'alternativa. ",
    "en": "That trip can no longer be booked, here is an alternative. ",
}


def say_replaced(product: ProductSummary, p: Proposal, lang: str = "it",
                 rooms: Optional[int] = None) -> str:
    """RF-17: la proposta sostitutiva, senza nominare l'errore del fornitore."""
    return _REPLACED_INTRO.get(lang, _REPLACED_INTRO["it"]) + say_proposal(product, p, lang, rooms)


def say_cancelled_then(next_sentence: str, lang: str = "it") -> str:
    """RF-49: rinuncia a un ordine in coda, poi la proposta (o il nessun risultato) successiva."""
    return _STATUS.get(lang, _STATUS["it"])[OrderStatus.CANCELLED] + " " + next_sentence


_FAILURE_REASONS = {
    "it": {
        "upstream": "il fornitore non ha risposto dopo tre tentativi",
        "config": "il collegamento con il fornitore non è configurato correttamente",
        "no_alternative": "il viaggio non è più prenotabile e non ho trovato alternative",
        "payments": "il servizio di pagamento non ha risposto dopo tre tentativi",
        "booking_upstream": "il fornitore non ha confermato la prenotazione dopo cinque tentativi",
        "booking_rejected": "il fornitore ha rifiutato la prenotazione",
    },
    "en": {
        "upstream": "the supplier did not answer after three attempts",
        "config": "the connection to the supplier is not configured correctly",
        "no_alternative": "the trip can no longer be booked and I found no alternative",
        "payments": "the payment service did not answer after three attempts",
        "booking_upstream": "the supplier did not confirm the booking after five attempts",
        "booking_rejected": "the supplier rejected the booking",
    },
}


def failure_reason(code: str, lang: str = "it") -> str:
    """Motivo leggibile di un ordine `failed` (RF-25, RF-46), salvato sull'ordine."""
    reasons = _FAILURE_REASONS.get(lang, _FAILURE_REASONS["it"])
    return reasons.get(code, reasons["upstream"])


def failure_reason_default(lang: str = "it") -> str:
    return failure_reason("upstream", lang)


def say_paid() -> str:
    return "Pagamento simulato registrato: la prenotazione è in corso."


_NOT_FOUND = {
    "intent": "Non ritrovo questa richiesta di viaggio: dimmi di nuovo che viaggio hai in mente e riparto da lì.",
    "proposal": "Non ritrovo questa proposta: dimmi di nuovo che viaggio hai in mente e te ne preparo una.",
    "order": ("Non ritrovo questo ordine: controlla il link di pagamento che ti ho mandato, "
              "oppure ripartiamo dal viaggio che hai in mente."),
}


def say_not_found(kind: str) -> str:
    return _NOT_FOUND.get(kind, "Non ritrovo quello che mi chiedi: ripartiamo dal viaggio che hai in mente.")


def say_unavailable() -> str:
    return "Vela non è disponibile in questo momento: riprova tra qualche minuto."


def say_error() -> str:
    return "Qualcosa non ha funzionato dalla mia parte: riprova tra poco."


def say_payments_unavailable() -> str:
    return ("Non riesco a preparare il link di pagamento in questo momento: riprova tra poco, "
            "la proposta resta valida.")
