"""Frasi italiane pronte da leggere (RF-42): nessun markdown, nessun URL."""
from datetime import date
from decimal import Decimal

MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]


def fmt_date(d: date) -> str:
    return "%d %s %d" % (d.day, MONTHS_IT[d.month - 1], d.year)


def fmt_money(value: Decimal) -> str:
    q = value.quantize(Decimal("0.01"))
    if q == q.to_integral_value():
        return "%d euro" % int(q)
    return format(q, "f").replace(".", ",") + " euro"
