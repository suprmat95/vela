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
    if c.period:
        parts.append(_when(c.period, lang))
    if c.pax:
        parts.append(("for %s" if en else "per %s") % _people(c.pax, lang))
    if c.budget is not None:
        parts.append(("with a maximum budget of %s" if en else "con un budget massimo di %s")
                     % fmt_money(c.budget, lang))
    return " ".join(parts)


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
           "direction": "Non so spostare la ricerca verso %s."},
    "en": {"sport": "I don't handle %s: only padel or tennis.",
           "area": "I don't know the place %s.",
           "period": "I couldn't use the dates %s.",
           "pax": "I couldn't use %s as the number of people.",
           "budget": "I couldn't use %s as the budget.",
           "direction": "I can't move the search %s."},
}
_DIRECTION_WORDS = {"it": {"north": "nord", "south": "sud"}, "en": {"north": "north", "south": "south"}}


def _discarded_value(field: str, value, lang: str) -> str:
    if field == "period":
        start, end = value
        return "%s - %s" % (start or "?", end or "?")
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


def say_proposal(product: ProductSummary, p: Proposal, lang: str = "it") -> str:
    hotel = ", hotel %s" % product.hotel if product.hotel else ""
    if lang == "en":
        where = " in %s" % product.destination if product.destination else ""
        if p.start_date == p.end_date:
            when = on_date(p.start_date, lang)
        else:
            when = "from %s to %s" % (fmt_date(p.start_date, lang), fmt_date(p.end_date, lang))
        return ("I suggest %s%s%s, %s for %s, starting at %s per person. %s Shall I go ahead?"
                % (product.title, where, hotel, when, _people(p.pax, lang),
                   fmt_money(p.price_from, lang), p.reason))
    where = " a %s" % product.destination if product.destination else ""
    if p.start_date == p.end_date:
        when = on_date(p.start_date)
    else:
        when = "dal %s al %s" % (fmt_date(p.start_date), fmt_date(p.end_date))
    return ("Ti propongo %s%s%s, %s per %s, a partire da %s a persona. %s Ti va?"
            % (product.title, where, hotel, when, _people(p.pax), fmt_money(p.price_from), p.reason))


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
        None: "Non trovo nessun viaggio compatibile: dimmi cosa vuoi cambiare.",
        "sport_value": "Non trovo nessun viaggio di %s: prova con l'altro sport o dimmi cosa vuoi cambiare.",
        "dates_value": "Non trovo partenze %s: prova con un altro periodo.",
        "pax_value": "Non trovo viaggi per %s: prova a cambiare il numero di persone.",
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
        None: "I can't find any matching trip: tell me what you want to change.",
        "sport_value": "I can't find any %s trip: try the other sport or tell me what you want to change.",
        "dates_value": "I can't find departures %s: try another period.",
        "pax_value": "I can't find trips for %s: try changing the number of people.",
    },
}


def say_no_match(criterion: str, criteria: Optional[Criteria] = None) -> str:
    """Frase di RF-09: dice quale criterio non si riesce a soddisfare e, se noto, con che valore,
    nella lingua dei criteri."""
    c = criteria or Criteria()
    texts = _NO_MATCH.get(c.language, _NO_MATCH["it"])
    if criterion == "sport" and c.sport:
        return texts["sport_value"] % c.sport
    if criterion == "dates" and c.period:
        return texts["dates_value"] % _when(c.period, c.language)
    if criterion == "pax" and c.pax:
        return texts["pax_value"] % _people(c.pax, c.language)
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
               price_from_total: Optional[Decimal] = None, phone_tail: Optional[str] = None) -> str:
    if status == OrderStatus.QUEUED and minutes is not None:
        return say_queued(minutes, lang, phone_tail)
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


def say_replaced(product: ProductSummary, p: Proposal, lang: str = "it") -> str:
    """RF-17: la proposta sostitutiva, senza nominare l'errore del fornitore."""
    return _REPLACED_INTRO.get(lang, _REPLACED_INTRO["it"]) + say_proposal(product, p, lang)


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
