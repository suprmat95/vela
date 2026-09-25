"""Frasi italiane pronte da leggere (RF-42): nessun markdown, nessun URL."""
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.models import Criteria, OrderStatus, Period, ProductSummary, Proposal

MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]


def fmt_date(d: date) -> str:
    return "%d %s %d" % (d.day, MONTHS_IT[d.month - 1], d.year)


def on_date(d: date) -> str:
    """Data con l'articolo: "il 1 ottobre 2026", "l'8 ottobre 2026", "l'11 ottobre 2026"."""
    return ("l'%s" if d.day in (8, 11) else "il %s") % fmt_date(d)


def fmt_money(value: Decimal) -> str:
    q = value.quantize(Decimal("0.01"))
    if q == q.to_integral_value():
        return "%d euro" % int(q)
    return format(q, "f").replace(".", ",") + " euro"


def _people(n: Optional[int]) -> str:
    if n is None:
        return ""
    return "1 persona" if n == 1 else "%d persone" % n


def _join(parts: list) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " e " + parts[-1]


def _when(period: Period) -> str:
    if period.start == period.end:
        return on_date(period.start)
    return "tra %s e %s" % (on_date(period.start), on_date(period.end))


def say_intent_created(c: Criteria) -> str:
    parts = ["un viaggio di %s" % c.sport if c.sport else "un viaggio"]
    if c.area:
        parts.append(geo.where(c.area))
    if c.period:
        parts.append(_when(c.period))
    if c.pax:
        parts.append("per %s" % _people(c.pax))
    if c.budget is not None:
        parts.append("con un budget massimo di %s" % fmt_money(c.budget))
    return "Ho capito: %s. Cerco la proposta giusta." % " ".join(parts)


def say_proposal(product: ProductSummary, p: Proposal) -> str:
    where = " a %s" % product.destination if product.destination else ""
    hotel = ", hotel %s" % product.hotel if product.hotel else ""
    if p.start_date == p.end_date:
        when = on_date(p.start_date)
    else:
        when = "dal %s al %s" % (fmt_date(p.start_date), fmt_date(p.end_date))
    return ("Ti propongo %s%s%s, %s per %s, a partire da %s a persona. %s Ti va?"
            % (product.title, where, hotel, when, _people(p.pax), fmt_money(p.price_from), p.reason))


_NO_MATCH = {
    "archived": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
    "bookable": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
    "trip": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
    "rejected": "Hai già scartato tutte le proposte compatibili con la tua richiesta: prova a riformularla.",
    "sport": "Non trovo nessun viaggio per lo sport che hai chiesto: prova con l'altro sport o riformula la richiesta.",
    "dates": "Non trovo partenze nel periodo che hai chiesto: prova con un altro periodo.",
    "pax": "Non trovo viaggi per il numero di persone indicato: prova a cambiare il numero di persone.",
}


def say_no_match(criterion: str, criteria: Optional[Criteria] = None) -> str:
    """Frase di RF-09: dice quale criterio non si riesce a soddisfare e, se noto, con che valore."""
    c = criteria or Criteria()
    if criterion == "sport" and c.sport:
        return ("Non trovo nessun viaggio di %s: prova con l'altro sport o riformula la richiesta."
                % c.sport)
    if criterion == "dates" and c.period:
        return "Non trovo partenze %s: prova con un altro periodo." % _when(c.period)
    if criterion == "pax" and c.pax:
        return ("Non trovo viaggi per %s: prova a cambiare il numero di persone."
                % _people(c.pax))
    return _NO_MATCH.get(criterion, "Non trovo nessun viaggio compatibile: prova a riformulare la richiesta.")


_ORDINALS = ["secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo"]
_FIELD_LABELS = {"first_name": "il nome", "last_name": "il cognome", "email": "l'email", "phone": "il telefono"}


def _label(field: str) -> str:
    if field.startswith("participants["):
        index = int(field[len("participants["):field.index("]")])
        leaf = field.split(".")[-1]
        ordinal = _ORDINALS[index] if index < len(_ORDINALS) else "numero %d" % (index + 2)
        return "%s del %s partecipante" % (_FIELD_LABELS[leaf], ordinal)
    return _FIELD_LABELS.get(field, field)


def say_missing(missing: list) -> str:
    return "Per prenotare mi servono ancora: %s." % _join([_label(f) for f in missing])


def say_accept(total, price_from_total, total_differs: bool) -> str:
    head = ""
    if total_differs:
        head = "Il totale reale è %s, non i %s stimati. " % (fmt_money(total), fmt_money(price_from_total))
    return (head + "Il totale è %s. Ti mando il link di pagamento per testo: appena il pagamento "
            "arriva, prenoto e ti do il codice." % fmt_money(total))


def say_status(status: OrderStatus, booking_code: Optional[str], failure_reason: Optional[str]) -> str:
    if status == OrderStatus.CONFIRMED:
        return "La tua prenotazione è confermata, codice %s." % booking_code
    if status == OrderStatus.AWAITING_PAYMENT:
        return "L'ordine è in attesa del pagamento: usa il link che ti ho mandato."
    if status == OrderStatus.PAID_PENDING_BOOKING:
        return "Pagamento ricevuto, sto completando la prenotazione: richiedi lo stato tra qualche secondo."
    if status == OrderStatus.BOOKING_FAILED:
        return ("Il pagamento è arrivato ma la prenotazione non è riuscita: riprovo io, "
                "e se non ci riesco ti avviso.")
    return "Il link di pagamento è scaduto: dimmi se vuoi che prepari una nuova proposta."


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
