"""Parser deterministico degli intenti, italiano e inglese (RF-02, RF-04), con fallback LLM
opzionale (RF-03).

Estrae sport, area (dizionario `geo`), periodo, numero di persone, budget e lingua. Se manca
sia lo sport che il periodo, oppure il numero di persone (e il profilo non lo dà), produce una
sola domanda per l'agente. `today` è iniettato per rendere i periodi deterministici.
"""
import calendar
import logging
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.models import Criteria, Period, TravelerProfile
from vela.ports.llm import IntentExtractor

log = logging.getLogger(__name__)

QUESTION_SPORT_OR_PERIOD = "Che sport ti interessa, padel o tennis, e in che periodo vuoi partire?"
QUESTION_PAX = "In quante persone siete?"

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
LLM_PERIOD_LABEL = "llm"

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

# (pattern, moltiplicatore): il numero catturato × moltiplicatore; i numeri espliciti vincono
_PAX_PATTERNS = [
    (re.compile(r"\b(\w+)\s+(?:coppie|couples)\b"), 2),
    (re.compile(r"\bsiamo in (\w+)"), 1),
    (re.compile(r"\bwe are (\w+)"), 1),
    (re.compile(r"\bwe're (\w+)"), 1),
    (re.compile(r"\b(\w+)\s+(?:persone|adulti|giocatori|amici|people|adults|players|friends|pax)\b"), 1),
    (re.compile(r"\b(\w+)\s+of us\b"), 1),
    (re.compile(r"\b(?:famiglia|gruppo|family|group)\s+(?:di|of)\s+(\w+)"), 1),
    (re.compile(r"\b(?:per|for)\s+(\w+)\b"), 1),
    (re.compile(r"\bx\s?(\d+)\b"), 1),
    (re.compile(r"\bin\s+(\d+)\b"), 1),
]
_PAX_PHRASES = [
    (re.compile(r"\b(?:in coppia|una coppia|as a couple|a couple\b(?! of)|"
                r"io e (?:mia|mio|il mio|la mia|un|una)\b|me and my\b|"
                r"my (?:wife|husband|partner|girlfriend|boyfriend|friend) and i\b)"), 2),
    (re.compile(r"\b(?:da sol[oa]|solo io|io solo|just me|only me|on my own|by myself|alone)\b"), 1),
]
_NOT_MONEY_AFTER = (r"(?!\s*(?:persone|persona|adulti|giocatori|amici|people|persons|adults|"
                    r"players|friends|pax|notti|nights|giorni|days|stelle|stars))")
_BUDGET_PATTERNS = [
    re.compile(r"(?:al massimo|massimo|max|budget|under|up to|fino a|entro|non più di|non oltre|"
               r"no more than|not more than|less than|meno di|sotto(?: i| ai| a)?|below|at most|"
               r"tetto(?: di)?)\s*(?:di\s+)?(?:€|eur|euro|euros)?\s*(\d[\d.,]*+)" + _NOT_MONEY_AFTER),
    re.compile(r"(\d[\d.,]*+)\s*(?:€|euros?\b|eur\b)"),
    re.compile(r"€\s*(\d[\d.,]*+)"),
]
_THOUSANDS_K = re.compile(r"(\d+(?:[.,]\d+)?)\s*k\b")
_PER_PERSON = re.compile(r"\b(?:a testa|a persona|per persona|each|per person|per head|pp)\b")


@dataclass(frozen=True)
class ParseResult:
    criteria: Criteria
    question: Optional[str] = None


def _words(text: str) -> list:
    return re.findall(r"[a-zà-ÿ']+", text.lower())


def detect_language(text: str) -> str:
    words = _words(text)
    it = sum(w in IT_MARKERS for w in words)
    en = sum(w in EN_MARKERS for w in words)
    return "en" if en > it else "it"


def parse_sport(text: str) -> Optional[str]:
    m = re.search(r"\b(padel|tennis)\b", text.lower())
    return m.group(1) if m else None


_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_ANY_MONTH_RE = "|".join(sorted(ALL_MONTHS, key=len, reverse=True))
_SEASON_RE = "|".join(sorted(SEASONS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"
_TO = r"\s*(?:-|–|al|to|till|until)\s*"
_PEOPLE_AFTER = (r"(?!\s*(?:persone|adulti|giocatori|amici|people|persons|adults|players|"
                 r"friends|pax|of us))")
_WEEKEND_RE = re.compile(r"\bweek-?end\b|\bfine settimana\b")
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
    m = _WEEKEND_RE.search(low)
    if m:
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
        m = pattern.search(low)
        if m:
            value = _to_money(m.group(1))
            if value is not None and value > 0:
                return value
    return None


def is_per_person(text: str) -> bool:
    return _PER_PERSON.search(text.lower()) is not None


def _llm_overrides(raw: dict, today: date) -> dict:
    """Campi validi dell'output del fallback; quelli invalidi o nulli non compaiono."""
    out = {}
    sport = raw.get("sport")
    if isinstance(sport, str) and sport.lower() in ("padel", "tennis"):
        out["sport"] = sport.lower()
    area = raw.get("area")
    if isinstance(area, str):
        found = geo.find_area(area)
        if found is not None:
            out["area"] = found
    try:
        start = date.fromisoformat(raw.get("period_start"))
        end = date.fromisoformat(raw.get("period_end"))
    except (TypeError, ValueError):
        start = end = None
    if start is not None and start <= end and end >= today:
        out["period"] = Period(start, end, LLM_PERIOD_LABEL)
    pax = raw.get("pax")
    if isinstance(pax, int) and not isinstance(pax, bool) and 1 <= pax <= MAX_PAX:
        out["pax"] = pax
    budget = raw.get("budget")
    if isinstance(budget, (int, float, str)) and not isinstance(budget, bool):
        try:
            value = Decimal(str(budget))
        except ArithmeticError:
            value = None
        if value is not None and value.is_finite() and value > 0:
            out["budget"] = value.quantize(Decimal("0.01"))
    return out


def _with_fallback(criteria: Criteria, text: str, today: date,
                   extractor: IntentExtractor) -> Criteria:
    try:
        raw = extractor.extract(text, today)
    except Exception as exc:   # il fallback non deve mai rompere create_intent
        log.warning("fallback LLM fallito: %s", type(exc).__name__)
        return criteria
    if not isinstance(raw, dict):
        return criteria
    return replace(criteria, **_llm_overrides(raw, today))


def parse_intent(text: str, profile: Optional[TravelerProfile] = None,
                 today: Optional[date] = None,
                 extractor: Optional[IntentExtractor] = None) -> ParseResult:
    today = today or date.today()
    profile = profile or TravelerProfile()
    pax = parse_pax(text) or profile.pax
    budget = parse_budget(text)
    if budget is not None and pax and is_per_person(text):
        budget = budget * pax
    criteria = Criteria(
        sport=parse_sport(text),
        area=geo.find_area(text),
        period=parse_period(text, today),
        pax=pax,
        budget=budget,
        language=detect_language(text),
    )
    if criteria.sport is None and criteria.period is None and extractor is not None:
        criteria = _with_fallback(criteria, text, today, extractor)
    question = None
    if criteria.sport is None and criteria.period is None:
        question = QUESTION_SPORT_OR_PERIOD
    elif criteria.pax is None:
        question = QUESTION_PAX
    return ParseResult(criteria, question)
