"""Parser deterministico minimo degli intenti, italiano e inglese (RF-02, RF-04; completo in M9).

Estrae sport, area (dizionario `geo`), periodo, numero di persone, budget e lingua. Se manca
sia lo sport che il periodo, oppure il numero di persone (e il profilo non lo dà), produce una
sola domanda per l'agente. `today` è iniettato per rendere i periodi deterministici.
"""
import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.models import Criteria, Period, TravelerProfile

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
NUMBER_WORDS = {
    "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
    "otto": 8, "nove": 9, "dieci": 10, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
MAX_PAX = 20

IT_MARKERS = {"un", "una", "di", "del", "della", "per", "siamo", "con", "massimo", "vorrei",
              "voglio", "noi", "persone", "giorni", "il", "la", "viaggio", "vacanza", "due",
              "tre", "quattro", "fine", "settimana", "euro", "e"}
EN_MARKERS = {"the", "of", "for", "we", "are", "with", "max", "want", "would", "like", "people",
              "under", "and", "two", "three", "four", "our", "my", "trip", "holiday", "us",
              "euros", "next", "camp"}

_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_SEASON_RE = "|".join(sorted(SEASONS, key=len, reverse=True))
_WEEKEND_RE = re.compile(r"\bweek-?end\b|\bfine settimana\b")
_PAX_PATTERNS = [
    re.compile(r"\bsiamo in (\w+)"),
    re.compile(r"\bwe are (\w+)"),
    re.compile(r"\bwe're (\w+)"),
    re.compile(r"\b(\w+)\s+(?:persone|adulti|giocatori|amici|people|adults|players|friends|pax)\b"),
    re.compile(r"\b(\w+)\s+of us\b"),
    re.compile(r"\b(?:per|for)\s+(\w+)\b"),
    re.compile(r"\bx\s?(\d+)\b"),
    re.compile(r"\bin\s+(\d+)\b"),
]
_BUDGET_PATTERNS = [
    re.compile(r"(?:al massimo|massimo|max|budget|under|up to|fino a|entro|non più di|"
               r"no more than|not more than|less than|meno di)\s*(?:di\s+)?(?:€|eur|euro|euros)?"
               r"\s*(\d[\d.,]*)"),
    re.compile(r"(\d[\d.,]*)\s*(?:€|euros?\b|eur\b)"),
    re.compile(r"€\s*(\d[\d.,]*)"),
]


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


def _month_period(month: int, today: date, label: str) -> Period:
    year = today.year if month >= today.month else today.year + 1
    return Period(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), label)


def _day_period(day: int, month: int, year: Optional[int], today: date, label: str) -> Optional[Period]:
    try:
        d = date(year or today.year, month, day)
    except ValueError:
        return None
    if year is None and d < today:
        d = date(today.year + 1, month, day)
    return Period(d, d, label)


def parse_period(text: str, today: date) -> Optional[Period]:
    low = text.lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if m:
        return _day_period(int(m.group(3)), int(m.group(2)), int(m.group(1)), today, m.group(0))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", low)
    if m:
        year = int(m.group(3)) if m.group(3) else None
        return _day_period(int(m.group(1)), int(m.group(2)), year, today, m.group(0))
    m = re.search(r"\b(\d{1,2})\s+(%s)\b" % _MONTH_RE, low)
    if m:
        return _day_period(int(m.group(1)), MONTHS[m.group(2)], None, today, m.group(0))
    m = re.search(r"\b(%s)\b" % _MONTH_RE, low)
    if m:
        return _month_period(MONTHS[m.group(1)], today, m.group(1))
    m = re.search(r"\b(%s)\b" % _SEASON_RE, low)
    if m:
        first, last = SEASONS[m.group(1)]
        if first == 12:   # inverno: dicembre → febbraio
            year = today.year if today.month >= 3 else today.year - 1
            return Period(date(year, 12, 1), date(year + 1, 3, 1) - timedelta(days=1), m.group(1))
        year = today.year if last >= today.month else today.year + 1
        return Period(date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1]),
                      m.group(1))
    m = _WEEKEND_RE.search(low)
    if m:
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        return Period(start, start + timedelta(days=1), m.group(0))
    return None


def _to_int(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def parse_pax(text: str) -> Optional[int]:
    low = text.lower()
    for pattern in _PAX_PATTERNS:
        for m in pattern.finditer(low):
            value = _to_int(m.group(1))
            if value is not None and 1 <= value <= MAX_PAX:
                return value
    return None


def _to_money(token: str) -> Optional[Decimal]:
    token = re.sub(r"[.,](?=\d{3}\b)", "", token)   # separatori delle migliaia
    token = token.replace(",", ".").rstrip(".")
    try:
        return Decimal(token)
    except ArithmeticError:
        return None


def parse_budget(text: str) -> Optional[Decimal]:
    low = text.lower()
    for pattern in _BUDGET_PATTERNS:
        m = pattern.search(low)
        if m:
            value = _to_money(m.group(1))
            if value is not None and value > 0:
                return value
    return None


def parse_intent(text: str, profile: Optional[TravelerProfile] = None,
                 today: Optional[date] = None) -> ParseResult:
    today = today or date.today()
    profile = profile or TravelerProfile()
    criteria = Criteria(
        sport=parse_sport(text),
        area=geo.find_area(text),
        period=parse_period(text, today),
        pax=parse_pax(text) or profile.pax,
        budget=parse_budget(text),
        language=detect_language(text),
    )
    question = None
    if criteria.sport is None and criteria.period is None:
        question = QUESTION_SPORT_OR_PERIOD
    elif criteria.pax is None:
        question = QUESTION_PAX
    return ParseResult(criteria, question)
