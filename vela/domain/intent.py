"""Parser deterministico degli intenti, italiano e inglese (RF-02, RF-04), con fallback LLM
opzionale (RF-03).

Estrae sport, area (dizionario `geo`), periodo, durata in notti (M21, RF-58), numero di
persone, numero di camere (M21-D, RF-65), budget con la sua lettura a persona o totale (M21-E,
RF-69) e lingua. I campi strutturati passati dall'agente (RF-52) vincono sul parser, che vince
sul fallback (RF-53). Se manca lo sport, oppure il numero di persone (e il profilo non lo dà),
oppure le camere con più di `ROOMS_DEFAULT_MAX_PAX` persone, produce una sola domanda per
l'agente, in quest'ordine (RF-04); con 1 o 2 persone la camera è una. `today` è iniettato per
rendere i periodi deterministici.
"""
import calendar
import logging
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Optional, Tuple

from vela.domain import geo
from vela.domain.models import Criteria, Period, StructuredFields, TravelerProfile
from vela.ports.llm import IntentExtractor

log = logging.getLogger(__name__)

QUESTION_SPORT = "Padel o tennis?"
QUESTION_PAX = "In quante persone siete?"
QUESTION_ROOMS = "In quante camere?"
QUESTION_SPORT_EN = "Padel or tennis?"
QUESTION_PAX_EN = "How many people are travelling?"
QUESTION_ROOMS_EN = "How many rooms?"
_QUESTIONS = {"it": (QUESTION_SPORT, QUESTION_PAX, QUESTION_ROOMS),
              "en": (QUESTION_SPORT_EN, QUESTION_PAX_EN, QUESTION_ROOMS_EN)}
ROOMS_DEFAULT_MAX_PAX = 2   # RF-65: fino a 2 persone una camera senza chiedere

MONTHS = {
    "gennaio": 1, "january": 1, "febbraio": 2, "february": 2, "marzo": 3, "march": 3,
    "aprile": 4, "april": 4, "maggio": 5, "may": 5, "giugno": 6, "june": 6, "luglio": 7,
    "july": 7, "agosto": 8, "august": 8, "settembre": 9, "september": 9, "ottobre": 10,
    "october": 10, "novembre": 11, "november": 11, "dicembre": 12, "december": 12,
}
SEASONS = {
    "primavera": (3, 5), "spring": (3, 5), "estate": (6, 8), "summer": (6, 8),
    "autunno": (9, 11), "autumn": (9, 11), "fall": (9, 11), "inverno": (12, 2), "winter": (12, 2),
}
# abbreviazioni valide solo accanto a un giorno ("12 ott", "Oct 3"): "mar" da solo è Lloret de Mar
MONTH_ABBR = {
    "gen": 1, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "jun": 6, "lug": 7,
    "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "sept": 9, "ott": 10, "oct": 10, "nov": 11,
    "dic": 12, "dec": 12,
}
ALL_MONTHS = {**MONTHS, **MONTH_ABBR}
MONTH_PARTS = {"inizio": (1, 10), "early": (1, 10), "metà": (11, 20), "meta": (11, 20),
               "mid": (11, 20), "fine": (21, None), "late": (21, None)}
NUMBER_WORDS = {
    "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
    "otto": 8, "nove": 9, "dieci": 10, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
MAX_PAX = 20
MAX_NIGHTS = 30
SPORTS = ("padel", "tennis", "any")
BUDGET_SCOPES = ("per_person", "total")
LLM_PERIOD_LABEL = "llm"
FIELD_PERIOD_LABEL = "agent"

IT_MARKERS = {"un", "una", "di", "del", "della", "per", "siamo", "con", "massimo", "vorrei",
              "voglio", "noi", "persone", "giorni", "il", "la", "viaggio", "vacanza", "due",
              "tre", "quattro", "fine", "settimana", "euro", "e", "dal", "al", "tra", "fra",
              "coppia", "coppie", "io", "mia", "mio", "moglie", "marito", "prossimo", "mese",
              "sotto", "testa", "solo", "sola", "famiglia", "gruppo", "metà", "inizio",
              "vorremmo", "giocare"}
EN_MARKERS = {"the", "of", "for", "we", "are", "with", "max", "want", "would", "like", "people",
              "under", "and", "two", "three", "four", "our", "my", "trip", "holiday", "us",
              "euros", "next", "camp", "from", "to", "between", "month", "couple", "couples",
              "each", "just", "early", "late", "mid", "family", "group", "alone", "players",
              "adults", "wife", "husband", "friends", "below"}

# "per 4 notti", "in 5 giorni": una durata (M21-A); "in 2 camere": camere (M21-D), non persone
_ROOM_WORDS = r"(?:camere|camera|stanze|stanza|rooms?|bedrooms?)"
_NOT_PEOPLE_AFTER = (r"(?!\s*(?:notti|notte|nights?|giorni|giorno|days?|settimane|weeks?|%s)\b)"
                     % _ROOM_WORDS)

# (pattern, moltiplicatore): il numero catturato × moltiplicatore; i numeri espliciti vincono
_PAX_PATTERNS = [
    (re.compile(r"\b(\w+)\s+(?:coppie|couples)\b"), 2),
    (re.compile(r"\bsiamo in (\w+)"), 1),
    (re.compile(r"\bwe are (\w+)"), 1),
    (re.compile(r"\bwe're (\w+)"), 1),
    (re.compile(r"\b(\w+)\s+(?:persone|adulti|giocatori|amici|people|adults|players|friends|pax)\b"), 1),
    (re.compile(r"\b(\w+)\s+of us\b"), 1),
    (re.compile(r"\b(?:famiglia|gruppo|family|group)\s+(?:di|of)\s+(\w+)"), 1),
    (re.compile(r"\b(?:per|for)\s+(\w+)\b" + _NOT_PEOPLE_AFTER), 1),
    (re.compile(r"\bx\s?(\d+)\b"), 1),
    (re.compile(r"\bin\s+(\d+)\b" + _NOT_PEOPLE_AFTER), 1),
]
_PAX_PHRASES = [
    (re.compile(r"\b(?:in coppia|una coppia|as a couple|a couple\b(?! of)|"
                r"io e (?:mia|mio|il mio|la mia|un|una)\b|me and my\b|"
                r"my (?:wife|husband|partner|girlfriend|boyfriend|friend) and i\b)"), 2),
    (re.compile(r"\b(?:da sol[oa]|solo io|io solo|just me|only me|on my own|by myself|alone)\b"), 1),
]
_NOT_MONEY_AFTER = (r"(?!\s*(?:persone|persona|adulti|giocatori|amici|people|persons|adults|"
                    r"players|friends|pax|notti|nights|giorni|days|stelle|stars|"
                    r"camere|camera|stanze|stanza|rooms?|bedrooms?))")
_PER_PERSON_WORDS = r"(?:a testa|a persona|per persona|each|per person|per head|pp)"
_TOTAL_WORDS = r"(?:in tutto|in totale|totale|complessiv[oaie]|in total|total|altogether)"
_BUDGET_PATTERNS = [
    re.compile(r"(?:al massimo|massimo|max|budget(?: totale| complessivo)?|in totale|in tutto|"
               r"in total|under|up to|fino a|entro|non più di|non oltre|"
               r"no more than|not more than|less than|meno di|sotto(?: i| ai| a)?|below|at most|"
               r"tetto(?: di)?)\s*(?:di\s+)?(?:€|eur|euro|euros)?\s*(\d[\d.,]*+)" + _NOT_MONEY_AFTER),
    re.compile(r"(\d[\d.,]*+)\s*(?:€|euros?\b|eur\b)"),
    re.compile(r"€\s*(\d[\d.,]*+)"),
    # cifra senza valuta seguita dalla lettura ("1,800 in total", "600 each", M21-E): sopra
    # MAX_PAX, perché "siamo 4 in tutto" parla delle persone
    re.compile(r"(\d[\d.,]*+)\s+(?:%s|%s)\b" % (_PER_PERSON_WORDS, _TOTAL_WORDS)),
]
_THOUSANDS_K = re.compile(r"(\d+(?:[.,]\d+)?)\s*k\b")
_PER_PERSON = re.compile(r"\b%s\b" % _PER_PERSON_WORDS)
_TOTAL = re.compile(r"\b%s\b" % _TOTAL_WORDS)
# "siamo 4 in tutto", "three of us in total", "3 persone in tutto": persone, non budget
_PEOPLE_BEFORE = re.compile(r"\b(\w+)\s+(?:persone\s+|people\s+|of us\s+)?$")


@dataclass(frozen=True)
class ParseResult:
    criteria: Criteria
    question: Optional[str] = None
    discarded: tuple = ()   # (campo, valore grezzo) dei campi strutturati invalidi (RF-53)
    conflicts: tuple = ()   # (campo, valore del parser, valore del campo) da loggare (RF-53)


def _words(text: str) -> list:
    return re.findall(r"[a-zà-ÿ']+", text.lower())


def detect_language(text: str) -> str:
    words = _words(text)
    it = sum(w in IT_MARKERS for w in words)
    en = sum(w in EN_MARKERS for w in words)
    return "en" if en > it else "it"


# Decisioni M17: sport che non vendiamo tolti prima dei sinonimi ("paddle tennis" non è padel né
# tennis); entrambi gli sport o una frase di indifferenza valgono `any`.
_NOT_OUR_SPORTS = re.compile(r"\b(?:beach|paddle)[\s-]?tennis\b")
_SPORT_WORDS = {
    "padel": re.compile(r"(?<![\w])(?:padel|pádel|paddle|weebora)\b"),
    "tennis": re.compile(r"\b(?:tennis|terra\s?rossa|clay)\b"),
}
_ANY_SPORT = re.compile(r"\b(?:indifferente|tutti e due|entramb[ie]|non importa|"
                        r"either (?:is|one|sport|will do|way)|both sports|any sport|"
                        r"doesn't matter|does not matter)\b")


def parse_sport(text: str) -> Optional[str]:
    low = _NOT_OUR_SPORTS.sub(" ", text.lower())
    found = [sport for sport, pattern in _SPORT_WORDS.items() if pattern.search(low)]
    if len(found) == 2 or _ANY_SPORT.search(low):
        return "any"
    return found[0] if found else None


_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_ANY_MONTH_RE = "|".join(sorted(ALL_MONTHS, key=len, reverse=True))
_SEASON_RE = "|".join(sorted(SEASONS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"
_TO = r"\s*(?:-|–|al|to|till|until)\s*"
_PEOPLE_AFTER = (r"(?!\s*(?:persone|adulti|giocatori|amici|people|persons|adults|players|"
                 r"friends|pax|of us))")
_WEEKEND_RE = re.compile(r"\bweek-?end\b|\bfine settimana\b")
_THIS_WEEKEND = re.compile(r"\b(?:questo|prossimo|this|next|coming)\s+(?:\w+\s+)?"
                           r"(?:week-?end|fine settimana)\b")
_A_WEEKEND = re.compile(r"\b(?:un|a|an)\s+(?:\w+\s+)?(?:week-?end|fine settimana)\b")
_RANGE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})%s(\d{4})-(\d{2})-(\d{2})\b" % _TO)
_RANGE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})%s(\d{1,2})/(\d{1,2})\b" % _TO)
_RANGE_DAY_FIRST = re.compile(
    r"\b(?:dal\s+|from\s+(?:the\s+)?)?(\d{1,2})%s(?:\s+(?:of\s+)?(%s))?%s(?:the\s+)?(\d{1,2})%s"
    r"\s+(?:of\s+)?(%s)\b" % (_ORD, _ANY_MONTH_RE, _TO, _ORD, _ANY_MONTH_RE))
_RANGE_BETWEEN = re.compile(
    r"\b(?:tra|fra|between)\s+(?:il\s+|l'|the\s+)?(\d{1,2})%s(?:\s+(?:of\s+)?(%s))?\s+(?:e|and)\s+"
    r"(?:il\s+|l'|the\s+)?(\d{1,2})%s\s+(?:of\s+)?(%s)\b"
    % (_ORD, _ANY_MONTH_RE, _ORD, _ANY_MONTH_RE))
_RANGE_MONTH_FIRST = re.compile(
    r"\b(%s)\s+(\d{1,2})%s%s(?:(%s)\s+)?(\d{1,2})%s\b"
    % (_ANY_MONTH_RE, _ORD, _TO, _ANY_MONTH_RE, _ORD))
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})%s\s+(?:of\s+)?(%s)\b" % (_ORD, _ANY_MONTH_RE))
_MONTH_DAY = re.compile(r"\b(%s)\s+(\d{1,2})%s\b%s" % (_ANY_MONTH_RE, _ORD, _PEOPLE_AFTER))
_MONTH_PART = re.compile(r"\b(inizio|fine|metà|meta|early|mid|late)[\s-]+(?:di\s+|of\s+)?(%s)\b"
                         % _MONTH_RE)
_NEXT_MONTH = re.compile(r"\b(?:il\s+)?(?:mese prossimo|prossimo mese|next month)\b")
_MONTH = re.compile(r"\b(%s)\b" % _MONTH_RE)
_SEASON = re.compile(r"\b(%s)\b" % _SEASON_RE)


def _month_period(month: int, today: date, label: str) -> Period:
    year = today.year if month >= today.month else today.year + 1
    return Period(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), label)


def _span(d1: int, m1: int, y1: Optional[int], d2: int, m2: int, y2: Optional[int], today: date,
          label: str) -> Optional[Period]:
    """Intervallo da giorno/mese/anno; senza anno l'inizio passato va all'anno prossimo e una fine
    prima dell'inizio va all'anno successivo. Una data impossibile dà None."""
    try:
        start = date(y1 or today.year, m1, d1)
        if y1 is None and start < today:
            start = date(today.year + 1, m1, d1)
        end = date(y2 or start.year, m2, d2)
        if y2 is None and end < start:
            end = date(start.year + 1, m2, d2)
    except ValueError:
        return None
    return Period(start, end, label) if start <= end else None


def _range_iso(low, today):
    m = _RANGE_ISO.search(low)
    if m:
        g = [int(x) for x in m.groups()]
        return _span(g[2], g[1], g[0], g[5], g[4], g[3], today, m.group(0))


def _range_slash(low, today):
    m = _RANGE_SLASH.search(low)
    if m:
        d1, m1, d2, m2 = (int(x) for x in m.groups())
        return _span(d1, m1, None, d2, m2, None, today, m.group(0))


def _range_day_first(low, today):
    for pattern in (_RANGE_DAY_FIRST, _RANGE_BETWEEN):
        m = pattern.search(low)
        if m:
            d1, first, d2, second = m.groups()
            month2 = ALL_MONTHS[second]
            month1 = ALL_MONTHS[first] if first else month2
            return _span(int(d1), month1, None, int(d2), month2, None, today, m.group(0).strip())


def _range_month_first(low, today):
    m = _RANGE_MONTH_FIRST.search(low)
    if m:
        first, d1, second, d2 = m.groups()
        month1 = ALL_MONTHS[first]
        month2 = ALL_MONTHS[second] if second else month1
        return _span(int(d1), month1, None, int(d2), month2, None, today, m.group(0))


def _single_iso(low, today):
    m = _ISO_DATE.search(low)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return _span(d, mo, y, d, mo, y, today, m.group(0))


def _single_slash(low, today):
    m = _SLASH_DATE.search(low)
    if m:
        year = int(m.group(3)) if m.group(3) else None
        d, mo = int(m.group(1)), int(m.group(2))
        return _span(d, mo, year, d, mo, year, today, m.group(0))


def _single_day_month(low, today):
    m = _DAY_MONTH.search(low)
    if m:
        d, mo = int(m.group(1)), ALL_MONTHS[m.group(2)]
        return _span(d, mo, None, d, mo, None, today, m.group(0))


def _single_month_day(low, today):
    m = _MONTH_DAY.search(low)
    if m:
        mo, d = ALL_MONTHS[m.group(1)], int(m.group(2))
        return _span(d, mo, None, d, mo, None, today, m.group(0))


def _month_part(low, today):
    m = _MONTH_PART.search(low)
    if m:
        whole = _month_period(MONTHS[m.group(2)], today, m.group(0))
        first, last = MONTH_PARTS[m.group(1)]
        end = whole.end if last is None else whole.start.replace(day=last)
        return Period(whole.start.replace(day=first), end, m.group(0))


def _next_month(low, today):
    m = _NEXT_MONTH.search(low)
    if m:
        return _month_period(today.month % 12 + 1, today, m.group(0).strip())


def _whole_month(low, today):
    m = _MONTH.search(low)
    if m:
        return _month_period(MONTHS[m.group(1)], today, m.group(1))


def _season(low, today):
    m = _SEASON.search(low)
    if m:
        first, last = SEASONS[m.group(1)]
        if first == 12:   # inverno: dicembre → febbraio
            year = today.year if today.month >= 3 else today.year - 1
            return Period(date(year, 12, 1), date(year + 1, 3, 1) - timedelta(days=1), m.group(1))
        year = today.year if last >= today.month else today.year + 1
        return Period(date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1]),
                      m.group(1))


def _weekend(low, today):
    """"Questo/prossimo weekend" e "weekend" da solo sono un periodo; "un weekend" è solo una
    durata (decisione "Un weekend", M21)."""
    m = _WEEKEND_RE.search(low)
    if m and (_THIS_WEEKEND.search(low) or not _A_WEEKEND.search(low)):
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        return Period(start, start + timedelta(days=1), m.group(0))


# dal più specifico al più generico: vince il primo che produce un periodo valido
_PERIOD_FINDERS = (_range_iso, _range_slash, _range_day_first, _range_month_first, _single_iso,
                   _single_slash, _single_day_month, _single_month_day, _month_part, _next_month,
                   _whole_month, _season, _weekend)


def parse_period(text: str, today: date) -> Optional[Period]:
    low = text.lower()
    for finder in _PERIOD_FINDERS:
        period = finder(low, today)
        if period is not None:
            return period
    return None


def _to_int(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def parse_pax(text: str) -> Optional[int]:
    low = text.lower()
    for pattern, factor in _PAX_PATTERNS:
        for m in pattern.finditer(low):
            value = _to_int(m.group(1))
            if value is not None and 1 <= value * factor <= MAX_PAX:
                return value * factor
    for pattern, value in _PAX_PHRASES:
        if pattern.search(low):
            return value
    return None


_NUM = r"(\d+|%s)" % "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
# camere (M21-D, RF-65): "tre camere", "in 2 camere", "two double rooms", "a room"
_ROOM_NUM = r"(\d+|%s|a|an)" % "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_ROOMS_COUNT = re.compile(r"\b%s\s+(?:\w+\s+)?%s\b" % (_ROOM_NUM, _ROOM_WORDS))
# tipi di camera sommati: "una matrimoniale e una doppia" = 2, "camera doppia" = 1, "due doppie" = 2
_ROOM_TYPES = re.compile(r"\b(?:%s\s+)?(?:camer[ae]\s+)?(?:matrimonial[ei]|doppi[ae]|singol[ae]|"
                         r"tripl[ae]|quadrupl[ae]|(?:double|twin|single|triple)\s+rooms?)\b" % _ROOM_NUM)
_ROOMS_COUPLES = re.compile(r"\b%s\s+(?:coppie|couples)\b" % _ROOM_NUM)
_NIGHTS = r"(?:notti|notte|nights?)\b"
_DURATION_RANGE = re.compile(r"\b(?:da\s+)?%s\s*(?:-|–|o|a|or|to)\s*%s\s+%s" % (_NUM, _NUM, _NIGHTS))
_DURATION_AT_LEAST = re.compile(r"\b(?:almeno|at least)\s+%s\s+%s" % (_NUM, _NIGHTS))
_DURATION_NIGHTS = re.compile(r"\b%s\s+%s" % (_NUM, _NIGHTS))
_DURATION_DAYS = re.compile(r"\b%s\s+(?:giorni|giorno|days?)\b" % _NUM)
# tabella di UC-A: (pattern, (min, max)), dal più specifico al più generico
_DURATION_WORDS = [
    (re.compile(r"\b(?:due|2|two)\s+(?:settimane|weeks)\b"), (13, 15)),
    (re.compile(r"\b(?:una|1)\s+settimana\b|\b(?:a|one|1)\s+week\b"), (6, 8)),
    (re.compile(r"\bponte\b|\blungo\s+(?:week-?end|fine settimana)\b|\bweek-?end\s+lungo\b|"
                r"\blong\s+week-?end\b"), (2, 4)),
    (_WEEKEND_RE, (1, 3)),
]


def _nights_ok(*values) -> bool:
    return all(v is None or 1 <= v <= MAX_NIGHTS for v in values)


def _room_number(token: Optional[str]) -> int:
    """"a", "an" e nessun numero valgono 1."""
    return 1 if token in (None, "a", "an") else (_to_int(token) or 0)


def parse_rooms(text: str) -> Optional[int]:
    """RF-65: numero di camere dal testo. Il conteggio esplicito ("tre camere") e la somma dei
    tipi ("una matrimoniale e una doppia") si combinano col massimo, così "3 camere, una doppia"
    resta 3; senza nessuno dei due, "due coppie" sono 2 camere. Fuori da 1..MAX_PAX non è un
    numero di camere."""
    low = text.lower()
    count = max((_room_number(m.group(1)) for m in _ROOMS_COUNT.finditer(low)), default=0)
    types = sum(_room_number(m.group(1)) for m in _ROOM_TYPES.finditer(low))
    rooms = max(count, types)
    if rooms == 0:
        m = _ROOMS_COUPLES.search(low)
        rooms = _room_number(m.group(1)) if m else 0
    return rooms if 1 <= rooms <= MAX_PAX else None


def parse_duration(text: str) -> Optional[Tuple[int, Optional[int]]]:
    """RF-58: (min, max) notti dal testo, `max` None per "almeno N notti". Le notti di N giorni
    sono N − 1; fuori da 1..30 non è una durata."""
    low = text.lower()
    m = _DURATION_RANGE.search(low)
    if m:
        low_n, high_n = _to_int(m.group(1)), _to_int(m.group(2))
        if _nights_ok(low_n, high_n) and low_n <= high_n:
            return low_n, high_n
    m = _DURATION_AT_LEAST.search(low)
    if m and _nights_ok(_to_int(m.group(1))):
        return _to_int(m.group(1)), None
    m = _DURATION_NIGHTS.search(low)
    if m and _nights_ok(_to_int(m.group(1))):
        return _to_int(m.group(1)), _to_int(m.group(1))
    m = _DURATION_DAYS.search(low)
    if m and _nights_ok(_to_int(m.group(1)) - 1):
        return _to_int(m.group(1)) - 1, _to_int(m.group(1)) - 1
    for pattern, nights in _DURATION_WORDS:
        if pattern.search(low):
            return nights
    return None


def _to_money(token: str) -> Optional[Decimal]:
    token = re.sub(r"[.,](?=\d{3}\b)", "", token)   # separatori delle migliaia
    token = token.replace(",", ".").rstrip(".")
    try:
        return Decimal(token)
    except ArithmeticError:
        return None


def _expand_thousands(low: str) -> str:
    """'2k' → '2000', '1,5k' → '1500'."""
    return _THOUSANDS_K.sub(
        lambda m: format((Decimal(m.group(1).replace(",", ".")) * 1000).quantize(Decimal(1)), "f"),
        low)


def parse_budget(text: str) -> Optional[Decimal]:
    low = _expand_thousands(text.lower())
    for pattern in _BUDGET_PATTERNS:
        for m in pattern.finditer(low):
            value = _to_money(m.group(1))
            if value is None or value <= 0:
                continue
            if pattern is _BUDGET_PATTERNS[-1] and value <= MAX_PAX:
                continue
            return value
    return None


def is_per_person(text: str) -> bool:
    return _PER_PERSON.search(text.lower()) is not None


def _about_people(low: str, start: int) -> bool:
    m = _PEOPLE_BEFORE.search(low[:start])
    if m is None:
        return False
    value = _to_int(m.group(1))
    return value is not None and value <= MAX_PAX


def parse_budget_scope(text: str) -> Optional[str]:
    """RF-69, regole 2-3: "a testa", "each"… → `per_person`; "in tutto", "in total"… → `total`
    (non dopo un numero di persone); nessuna parola → None."""
    low = text.lower()
    if _PER_PERSON.search(low):
        return "per_person"
    if any(not _about_people(low, m.start()) for m in _TOTAL.finditer(low)):
        return "total"
    return None


CheapestTotal = Callable[[Criteria], Optional[Decimal]]


def scope_of_figure(figure: Decimal, pax: int, cheapest: Optional[Decimal]) -> str:
    """RF-69, regola 4: a persona se la cifra, letta come totale, non copre il totale del
    prodotto compatibile più economico e letta a persona sì; altrimenti totale."""
    if cheapest is not None and figure < cheapest <= figure * pax:
        return "per_person"
    return "total"


def read_budget(criteria: Criteria, cheapest_total: Optional[CheapestTotal] = None) -> Criteria:
    """RF-69: in ingresso `budget` è la cifra detta e `budget_scope` la lettura detta (campo o
    parole) o None; in uscita `budget` è il tetto sul totale usato dal chooser e `budget_scope`
    la lettura. Senza lettura detta: regola 4 con più persone e `cheapest_total`, che legge il
    catalogo solo qui; altrimenti `total` (regola 5)."""
    if criteria.budget is None:
        return replace(criteria, budget_scope=None)
    scope = criteria.budget_scope
    if scope is None and criteria.pax and criteria.pax > 1 and cheapest_total is not None:
        scope = scope_of_figure(criteria.budget, criteria.pax, cheapest_total(criteria))
    scope = scope or "total"
    budget = criteria.budget * criteria.pax if scope == "per_person" and criteria.pax else criteria.budget
    return replace(criteria, budget=budget, budget_scope=scope)


def _valid_period(start_raw, end_raw, today: date, label: str) -> Optional[Period]:
    try:
        start, end = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
    except (TypeError, ValueError):
        return None
    return Period(start, end, label) if start <= end and end >= today else None


def _valid_budget(raw) -> Optional[Decimal]:
    if not isinstance(raw, (int, float, str, Decimal)) or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw))
    except ArithmeticError:
        return None
    return value.quantize(Decimal("0.01")) if value.is_finite() and value > 0 else None


def validate_fields(raw: dict, today: date, label: str = FIELD_PERIOD_LABEL) -> Tuple[dict, tuple]:
    """RF-53: criteri validi tra quelli dati (campi dell'agente o output del fallback) e coppie
    (campo, valore) di quelli scartati. Un campo assente o nullo non è né valido né scartato."""
    valid, discarded = {}, []
    sport = raw.get("sport")
    if sport is not None:
        if isinstance(sport, str) and sport.strip().lower() in SPORTS:
            valid["sport"] = sport.strip().lower()
        else:
            discarded.append(("sport", sport))
    area = raw.get("area")
    if area is not None:
        found = geo.find_area(area) if isinstance(area, str) else None
        if found is not None:
            valid["area"] = found
        else:
            discarded.append(("area", area))
    start, end = raw.get("period_start"), raw.get("period_end")
    if start is not None or end is not None:
        period = _valid_period(start, end, today, label)
        if period is not None:
            valid["period"] = period
        else:
            discarded.append(("period", (start, end)))
    pax = raw.get("pax")
    if pax is not None:
        if isinstance(pax, int) and not isinstance(pax, bool) and 1 <= pax <= MAX_PAX:
            valid["pax"] = pax
        else:
            discarded.append(("pax", pax))
    budget = raw.get("budget")
    if budget is not None:
        value = _valid_budget(budget)
        if value is not None:
            valid["budget"] = value
        else:
            discarded.append(("budget", budget))
    low_n, high_n = raw.get("duration_min_nights"), raw.get("duration_max_nights")
    if low_n is not None or high_n is not None:
        ints = all(v is None or (isinstance(v, int) and not isinstance(v, bool))
                   for v in (low_n, high_n))
        if ints and _nights_ok(low_n, high_n) and (low_n is None or high_n is None
                                                   or low_n <= high_n):
            # uno solo dei due sostituisce tutta la durata letta nel testo
            valid["duration_min_nights"], valid["duration_max_nights"] = low_n, high_n
        else:
            discarded.append(("duration", (low_n, high_n)))
    scope = raw.get("budget_scope")
    if scope is not None:
        if isinstance(scope, str) and scope.strip().lower() in BUDGET_SCOPES:
            valid["budget_scope"] = scope.strip().lower()
        else:
            discarded.append(("budget_scope", scope))
    rooms = raw.get("rooms")
    if rooms is not None:   # il tetto `pax` si conosce solo dopo la precedenza: `resolve_rooms`
        if isinstance(rooms, int) and not isinstance(rooms, bool) and rooms >= 1:
            valid["rooms"] = rooms
        else:
            discarded.append(("rooms", rooms))
    return valid, tuple(discarded)


def resolve_rooms(criteria: Criteria, given: dict, parsed_rooms: Optional[int],
                  discarded: tuple) -> Tuple[Criteria, dict, tuple]:
    """RF-53, RF-65: le camere valgono 1..pax. Un campo oltre le persone è scartato e detto, e
    al suo posto valgono le camere del testo se stanno nel tetto; un testo oltre le persone è
    ignorato. Senza camere, con 1 o 2 persone la camera è una; con più persone resta None (la
    domanda). `given` è restituito senza il campo scartato, così non conta come conflitto."""
    pax, rooms = criteria.pax, criteria.rooms
    if rooms is not None and pax is not None and rooms > pax:
        if "rooms" in given:
            given = dict(given)
            discarded += (("rooms", given.pop("rooms")),)
            rooms = parsed_rooms if parsed_rooms is not None and parsed_rooms <= pax else None
        else:
            rooms = None
    if rooms is None and pax is not None and pax <= ROOMS_DEFAULT_MAX_PAX:
        rooms = 1
    return replace(criteria, rooms=rooms), given, discarded


def _plain(value):
    """Valore leggibile nei log dei conflitti."""
    if isinstance(value, Period):
        return "%s..%s" % (value.start.isoformat(), value.end.isoformat())
    if hasattr(value, "name") and hasattr(value, "country_code"):
        return value.name
    return value


def _same(a, b) -> bool:
    if isinstance(a, Period) and isinstance(b, Period):
        return (a.start, a.end) == (b.start, b.end)
    return a == b


def conflicts_between(read: dict, given: dict) -> tuple:
    """(campo, valore letto nel testo, valore del campo) dove un campo valido contraddice il testo."""
    return tuple((name, _plain(read[name]), _plain(value)) for name, value in given.items()
                 if read.get(name) is not None and not _same(read[name], value))


def _with_fallback(criteria: Criteria, text: str, today: date,
                   extractor: IntentExtractor) -> Criteria:
    """RF-03, RF-53: il fallback riempie solo i criteri che campi e parser hanno lasciato vuoti."""
    try:
        raw = extractor.extract(text, today)
    except Exception as exc:   # il fallback non deve mai rompere create_intent
        log.warning("fallback LLM fallito: %s", type(exc).__name__)
        return criteria
    if not isinstance(raw, dict):
        return criteria
    valid, _ = validate_fields(raw, today, LLM_PERIOD_LABEL)
    return replace(criteria, **{k: v for k, v in valid.items() if getattr(criteria, k) is None})


def parse_intent(text: str, profile: Optional[TravelerProfile] = None,
                 today: Optional[date] = None,
                 extractor: Optional[IntentExtractor] = None,
                 fields: Optional[StructuredFields] = None,
                 cheapest_total: Optional[CheapestTotal] = None) -> ParseResult:
    """`cheapest_total`: la regola 4 di RF-69, chiamata solo se serve e senza domande aperte."""
    today = today or date.today()
    profile = profile or TravelerProfile()
    given, discarded = validate_fields(fields.as_dict(), today) if fields else ({}, ())
    nights = parse_duration(text) or (None, None)
    # budget e lettura come detti: il tetto sul totale lo calcola `read_budget` (RF-69)
    parsed = Criteria(
        sport=parse_sport(text),
        area=geo.find_area(text),
        period=parse_period(text, today),
        pax=parse_pax(text),
        budget=parse_budget(text),
        language=detect_language(text),
        duration_min_nights=nights[0],
        duration_max_nights=nights[1],
        budget_scope=parse_budget_scope(text),
        rooms=parse_rooms(text),
    )
    criteria = replace(parsed, **given)
    if criteria.sport is None and extractor is not None:
        criteria = _with_fallback(criteria, text, today, extractor)
    if criteria.pax is None and profile.pax:
        criteria = replace(criteria, pax=profile.pax)
    criteria, given, discarded = resolve_rooms(criteria, given, parsed.rooms, discarded)
    ask_sport, ask_pax, ask_rooms = _QUESTIONS.get(criteria.language, _QUESTIONS["it"])
    question = None
    if criteria.sport is None:
        question = ask_sport
    elif criteria.pax is None:
        question = ask_pax
    elif criteria.rooms is None:
        question = ask_rooms
    criteria = read_budget(criteria, cheapest_total if question is None else None)
    return ParseResult(criteria, question, discarded,
                       conflicts_between(vars(parsed), given))
