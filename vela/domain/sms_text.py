"""Testi degli SMS al viaggiatore (decisione 2026-09-26): link di pagamento e conferma.

A differenza di `say` questi testi contengono un URL e non si leggono ad alta voce. Solo
caratteri GSM-7: un solo carattere fuori dall'alfabeto passa l'SMS a UCS-2 e dimezza i caratteri
per segmento, quindi tutto il testo (titolo del prodotto compreso) passa da `gsm7`.
L'importo è sempre in euro (RF-22).
"""
import unicodedata
from datetime import date
from decimal import Decimal

GSM7 = frozenset("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
                 "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
                 "^{}\\[~]|€")
_REPLACE = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", " ": " "}


def gsm7(text: str) -> str:
    """Traslittera in GSM-7: segni tipografici sostituiti, accenti non GSM tolti, il resto scartato."""
    out = []
    for ch in text:
        if ch in GSM7:
            out.append(ch)
        elif ch in _REPLACE:
            out.append(_REPLACE[ch])
        else:
            base = unicodedata.normalize("NFKD", ch)[0]
            out.append(base if base in GSM7 else "")
    return "".join(out)


def _day(d: date) -> str:
    return "%02d/%02d" % (d.day, d.month)


def _recap(title: str, start: date, end: date, pax: int, lang: str) -> list:
    if lang == "en":
        people = "1 person" if pax == 1 else "%d people" % pax
        return [title, "from %s to %s, %s" % (_day(start), _day(end), people)]
    people = "1 persona" if pax == 1 else "%d persone" % pax
    return [title, "dal %s al %s, %s" % (_day(start), _day(end), people)]


def _total(amount: Decimal, lang: str) -> str:
    number = format(amount.quantize(Decimal("0.01")), "f")
    return "EUR %s" % number if lang == "en" else "%s €" % number.replace(".", ",")


def payment_link(title: str, start: date, end: date, pax: int, total: Decimal, url: str,
                 lang: str = "it") -> str:
    if lang == "en":
        lines = (["Vela: your trip is ready to pay."] + _recap(title, start, end, pax, lang)
                 + ["Total: " + _total(total, lang), "Pay within 24 hours: " + url])
    else:
        lines = (["Vela: il tuo viaggio è pronto da pagare."] + _recap(title, start, end, pax, lang)
                 + ["Totale: " + _total(total, lang), "Paga entro 24 ore: " + url])
    return gsm7("\n".join(lines))


def confirmed(title: str, start: date, end: date, pax: int, booking_code: str,
              lang: str = "it") -> str:
    if lang == "en":
        lines = (["Vela: booking confirmed!"] + _recap(title, start, end, pax, lang)
                 + ["Booking code: " + booking_code])
    else:
        lines = (["Vela: prenotazione confermata!"] + _recap(title, start, end, pax, lang)
                 + ["Codice prenotazione: " + booking_code])
    return gsm7("\n".join(lines))
