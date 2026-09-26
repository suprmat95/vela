# Notifiche SMS (Twilio): piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vela manda al viaggiatore principale un SMS con link di pagamento e riepilogo quando
l'ordine diventa `awaiting_payment`, e un SMS con il codice quando diventa `confirmed`.

**Architecture:** Due tipi di job nuovi (`sms_link`, `sms_confirmed`) nella coda esistente,
accodati dove l'ordine cambia stato (job d'acquisto e job di prenotazione) ed eseguiti da
`SmsJob` tramite la porta `Notifier`. Adapter Twilio con `httpx` in produzione, adapter finto in
test e replay. Le frasi dell'agente e le istruzioni MCP annunciano gli SMS.

**Tech Stack:** Python 3.12 (`uv run`), FastAPI, SQLAlchemy Core, `httpx`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-26-sms-notifiche-design.md`

## Global Constraints

- Test: `uv run python -m unittest discover -s tests` (il `python3` di sistema è 3.7 e non ha le dipendenze).
- Nessuna dipendenza nuova: Twilio si chiama con `httpx`. Nessun cambio di schema né migrazione.
- Nessuna chiamata a Twilio, Stripe o HofJ nei test automatici.
- Numeri: E.164, `+39` di default; `+…` invariato; `00…` → `+…`; valido solo `+` e 8-15 cifre.
- Il numero compare nei log e in `last_error` solo mascherato (`+39******4567`); il testo dell'SMS mai.
- `TWILIO_AUTH_TOKEN` e le altre chiavi non si leggono, stampano o loggano mai; `.env` non si apre.
- Testi SMS solo in caratteri GSM-7.
- Tentativi SMS: 4 in tutto, attese 30 s, 120 s, 600 s, poi `dead`; 4xx di Twilio (salvo 429) → `dead` subito.
- Priorità di prelievo: `booking` 0, `payment_check` 1, `sms_link`/`sms_confirmed` 2, `purchase` 3.
- Un SMS non cambia mai lo stato dell'ordine.
- Commit piccoli, messaggio in inglese all'imperativo come nel resto del repo, chiusi da
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `agent-log/` si aggiorna da solo al commit.

## Review Focus

1. Numero già scritto con `+39`, `0039`, spazi o trattini: non deve diventare `+39+39…` né perdere cifre (Task 1).
2. Titolo del prodotto con apostrofi tipografici, trattini lunghi o lettere accentate non GSM: il testo resta GSM-7 (Task 2).
3. Ordine già pagato, annullato o scaduto quando parte `sms_link`: nessun SMS con un link morto (Task 4).
4. Errore di Twilio il cui corpo ripete il numero: il numero non finisce né in `last_error` né nei log (Task 4, Task 6).
5. Il viaggiatore chiede lo stato più volte e i job si ripetono: arrivano esattamente 2 SMS (Task 5).

---

### Task 1: Normalizzazione del numero

**Files:**
- Create: `vela/domain/phone.py`
- Test: `tests/test_phone.py`

**Interfaces:**
- Produces: `normalize_it(raw: Optional[str]) -> Optional[str]`, `tail(raw: Optional[str]) -> Optional[str]`
  (ultime 4 cifre del numero normalizzato, `None` se non valido), `mask(e164: str) -> str`.

- [ ] **Step 1: Scrivere i test**

```python
"""Numeri per gli SMS (decisione 2026-09-26): E.164 con +39 di default."""
import unittest

from vela.domain.phone import mask, normalize_it, tail


class NormalizeTest(unittest.TestCase):
    def test_italian_mobile_gets_plus39(self):
        self.assertEqual(normalize_it("333 123 4567"), "+393331234567")

    def test_separators_are_removed(self):
        self.assertEqual(normalize_it("(333) 123-45.67"), "+393331234567")
        self.assertEqual(normalize_it("333/1234567"), "+393331234567")

    def test_plus39_is_not_doubled(self):
        self.assertEqual(normalize_it("+39 333 1234567"), "+393331234567")

    def test_0039_becomes_plus39(self):
        self.assertEqual(normalize_it("0039 333 1234567"), "+393331234567")

    def test_foreign_number_is_kept(self):
        self.assertEqual(normalize_it("+44 20 7946 0958"), "+442079460958")

    def test_landline_keeps_leading_zero(self):
        self.assertEqual(normalize_it("02 1234 5678"), "+390212345678")

    def test_invalid_numbers_give_none(self):
        for raw in (None, "", "   ", "abc", "+39 333", "12", "+39 3331234567890123", "333 abc 4567"):
            self.assertIsNone(normalize_it(raw), raw)


class TailAndMaskTest(unittest.TestCase):
    def test_tail_is_last_four_digits_of_normalized_number(self):
        self.assertEqual(tail("333 123 4567"), "4567")
        self.assertIsNone(tail("abc"))
        self.assertIsNone(tail(None))

    def test_mask_keeps_prefix_and_last_four(self):
        self.assertEqual(mask("+393331234567"), "+39******4567")
        self.assertNotIn("3331234", mask("+393331234567"))
```

- [ ] **Step 2: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_phone -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'vela.domain.phone'`

- [ ] **Step 3: Implementare**

```python
"""Numeri di telefono per gli SMS (decisione 2026-09-26): E.164 con `+39` di default.

Test in Italia: un numero senza prefisso internazionale è italiano; `+…` e `00…` restano del
paese scritto, così un `+39` già presente non si raddoppia. Il numero in chiaro non va mai nei
log: si usa `mask`.
"""
import re
from typing import Optional

DEFAULT_PREFIX = "+39"
_SEPARATORS = re.compile(r"[\s\-.()/]")
_E164 = re.compile(r"^\+\d{8,15}$")


def normalize_it(raw: Optional[str]) -> Optional[str]:
    """Numero in E.164, o `None` se dopo la pulizia non è `+` seguito da 8-15 cifre."""
    if not raw:
        return None
    number = _SEPARATORS.sub("", raw)
    if number.startswith("00"):
        number = "+" + number[2:]
    elif not number.startswith("+"):
        number = DEFAULT_PREFIX + number
    return number if _E164.match(number) else None


def tail(raw: Optional[str]) -> Optional[str]:
    """Ultime 4 cifre del numero normalizzato, da dire al viaggiatore; `None` se non valido."""
    number = normalize_it(raw)
    return number[-4:] if number else None


def mask(e164: str) -> str:
    """`+393331234567` → `+39******4567`: l'unica forma del numero ammessa nei log."""
    return e164[:3] + "*" * max(len(e164) - 7, 0) + e164[-4:]
```

- [ ] **Step 4: Verificare che passino**

Run: `uv run python -m unittest tests.test_phone -v`
Expected: OK (9 test)

- [ ] **Step 5: Commit**

```bash
git add vela/domain/phone.py tests/test_phone.py
git commit -m "$(cat <<'EOF'
Normalize traveler phone numbers to E.164 with +39 by default

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Testi degli SMS

**Files:**
- Create: `vela/domain/sms_text.py`
- Test: `tests/test_sms_text.py`

**Interfaces:**
- Produces:
  - `payment_link(title: str, start: date, end: date, pax: int, total: Decimal, url: str, lang: str = "it") -> str`
  - `confirmed(title: str, start: date, end: date, pax: int, booking_code: str, lang: str = "it") -> str`
  - `gsm7(text: str) -> str`, `GSM7: frozenset`

- [ ] **Step 1: Scrivere i test**

```python
"""Testi degli SMS (decisione 2026-09-26): riepilogo, link o codice, solo GSM-7."""
import unittest
from datetime import date
from decimal import Decimal

from vela.domain import sms_text
from vela.domain.sms_text import GSM7, gsm7

START, END = date(2026, 10, 10), date(2026, 10, 12)
URL = "https://checkout.stripe.com/c/pay/cs_test_abc"


class PaymentLinkTest(unittest.TestCase):
    def test_italian_text(self):
        text = sms_text.payment_link("Padel a Valencia", START, END, 2, Decimal("640"), URL)
        self.assertEqual(text, "Vela: il tuo viaggio è pronto da pagare.\n"
                               "Padel a Valencia\n"
                               "dal 10/10 al 12/10, 2 persone\n"
                               "Totale: 640,00 €\n"
                               "Paga entro 24 ore: " + URL)

    def test_english_text(self):
        text = sms_text.payment_link("Padel a Valencia", START, END, 1, Decimal("320.5"), URL, "en")
        self.assertEqual(text, "Vela: your trip is ready to pay.\n"
                               "Padel a Valencia\n"
                               "from 10/10 to 12/10, 1 person\n"
                               "Total: EUR 320.50\n"
                               "Pay within 24 hours: " + URL)


class ConfirmedTest(unittest.TestCase):
    def test_italian_text(self):
        text = sms_text.confirmed("Padel a Valencia", date(2026, 10, 1), date(2026, 10, 4), 1, "R-123456")
        self.assertEqual(text, "Vela: prenotazione confermata!\n"
                               "Padel a Valencia\n"
                               "dal 01/10 al 04/10, 1 persona\n"
                               "Codice prenotazione: R-123456")

    def test_english_text(self):
        text = sms_text.confirmed("Padel a Valencia", START, END, 3, "R-1", "en")
        self.assertEqual(text, "Vela: booking confirmed!\n"
                               "Padel a Valencia\n"
                               "from 10/10 to 12/10, 3 people\n"
                               "Booking code: R-1")


class Gsm7Test(unittest.TestCase):
    TITLE = "Padel & Relax – Hotel ’Sol’ Ñandú “Vip”… È"

    def test_typographic_title_is_transliterated(self):
        self.assertEqual(gsm7(self.TITLE), "Padel & Relax - Hotel 'Sol' Ñandu \"Vip\"... E")

    def test_every_text_is_gsm7(self):
        for lang in ("it", "en"):
            for text in (sms_text.payment_link(self.TITLE, START, END, 2, Decimal("640"), URL, lang),
                         sms_text.confirmed(self.TITLE, START, END, 2, "R-1", lang)):
                self.assertEqual([c for c in text if c not in GSM7], [], text)

    def test_unknown_symbols_are_dropped(self):
        self.assertEqual(gsm7("Padel 🎾 Sole"), "Padel  Sole")
```

- [ ] **Step 2: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_sms_text -v`
Expected: ERROR, `ImportError: cannot import name 'sms_text'`

- [ ] **Step 3: Implementare**

```python
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
```

- [ ] **Step 4: Verificare che passino**

Run: `uv run python -m unittest tests.test_sms_text -v`
Expected: OK (7 test)

- [ ] **Step 5: Commit**

```bash
git add vela/domain/sms_text.py tests/test_sms_text.py
git commit -m "$(cat <<'EOF'
Add GSM-7 texts for the payment link and confirmation SMS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Tipi di job SMS e priorità di prelievo

**Files:**
- Modify: `vela/domain/models.py` (`class JobKind`, ~riga 253)
- Modify: `vela/adapters/repo_memory.py` (`CLAIM_PRIORITY`, ~riga 141)
- Modify: `vela/adapters/repo_postgres.py` (`CLAIM_PRIORITY`, ~riga 287)
- Test: `tests/repo_contract.py` (vale per memoria e Postgres)

**Interfaces:**
- Produces: `JobKind.SMS_LINK = "sms_link"`, `JobKind.SMS_CONFIRMED = "sms_confirmed"`.

- [ ] **Step 1: Scrivere il test** in `tests/repo_contract.py`, subito dopo
  `test_claim_prefers_booking_then_payment_check_then_purchase`:

```python
    def test_claim_puts_sms_after_payment_check_and_before_purchase(self):
        self.seed_orders(4)
        self.repos.jobs.enqueue(job("j-p", "o1", enqueued_at=NOW - timedelta(minutes=9)))
        self.repos.jobs.enqueue(job("j-s", "o2", JobKind.SMS_LINK, enqueued_at=NOW - timedelta(minutes=1)))
        self.repos.jobs.enqueue(job("j-c", "o3", JobKind.PAYMENT_CHECK))
        self.repos.jobs.enqueue(job("j-k", "o4", JobKind.SMS_CONFIRMED))
        self.assertEqual([self.repos.jobs.claim(NOW, LEASE).id for _ in range(4)],
                         ["j-c", "j-s", "j-k", "j-p"])
```

- [ ] **Step 2: Verificare che fallisca**

Run: `uv run python -m unittest tests.test_repo_memory -v`
Expected: ERROR, `AttributeError: SMS_LINK`

- [ ] **Step 3: Implementare**

`vela/domain/models.py`:

```python
class JobKind(str, Enum):
    PURCHASE = "purchase"              # RF-46
    BOOKING = "booking"                # RF-23, RF-51
    PAYMENT_CHECK = "payment_check"    # RF-20
    SMS_LINK = "sms_link"              # RF-19: SMS con link e riepilogo (decisione 2026-09-26)
    SMS_CONFIRMED = "sms_confirmed"    # RF-57: SMS con il codice di prenotazione
```

`vela/adapters/repo_memory.py`:

```python
CLAIM_PRIORITY = {JobKind.BOOKING: 0, JobKind.PAYMENT_CHECK: 1, JobKind.SMS_LINK: 2,
                  JobKind.SMS_CONFIRMED: 2, JobKind.PURCHASE: 3}
```

`vela/adapters/repo_postgres.py`:

```python
CLAIM_PRIORITY = case({JobKind.BOOKING.value: 0, JobKind.PAYMENT_CHECK.value: 1,
                       JobKind.SMS_LINK.value: 2, JobKind.SMS_CONFIRMED.value: 2},
                      value=jobs_t.c.kind, else_=3)
```

- [ ] **Step 4: Verificare che passi**

Run: `uv run python -m unittest tests.test_repo_memory tests.test_repo_postgres -v`
Expected: OK (i test Postgres sono saltati senza `DATABASE_URL`; con un Postgres usa e getta
impostato in `DATABASE_URL` devono passare anche loro)

- [ ] **Step 5: Commit**

```bash
git add vela/domain/models.py vela/adapters/repo_memory.py vela/adapters/repo_postgres.py tests/repo_contract.py
git commit -m "$(cat <<'EOF'
Add the SMS job kinds and claim them before purchases

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Porta `Notifier`, SMS finti e `SmsJob`

**Files:**
- Create: `vela/ports/notifier.py`
- Create: `vela/adapters/sms_fake.py`
- Create: `vela/domain/notify.py`
- Create: `vela/domain/sms.py`
- Test: `tests/test_sms_job.py`

**Interfaces:**
- Consumes: `phone.normalize_it`, `phone.mask` (Task 1); `sms_text.payment_link`, `sms_text.confirmed` (Task 2);
  `JobKind.SMS_LINK`, `JobKind.SMS_CONFIRMED` (Task 3); `JobResult` da `vela.domain.purchase`.
- Produces:
  - `vela.ports.notifier`: `NotifierError(Exception)`, `NotifierRejected(NotifierError)`, `Notifier` (Protocol, `send_sms(to: str, body: str) -> str`).
  - `vela.adapters.sms_fake.FakeSms(fail_with: Sequence[Exception] = ())`, attributo `sent: List[Tuple[str, str]]`.
  - `vela.domain.notify.enqueue_sms(repos, kind: JobKind, order_id: str, now: datetime, new_id: Callable[[], str]) -> bool`.
  - `vela.domain.sms.SmsJob(repos, notifier, now, backoff=(30, 120, 600))`, `run(job, next_window) -> JobResult`.

- [ ] **Step 1: Scrivere i test**

```python
"""Job SMS (decisione 2026-09-26): stato atteso, numero, tentativi, niente dati in chiaro nei log."""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.sms_fake import FakeSms
from vela.domain import sms_text
from vela.domain.models import (Area, Criteria, Intent, Job, JobKind, JobStatus, Order, OrderStatus,
                                Period, Proposal, TravelerProfile)
from vela.domain.notify import enqueue_sms
from vela.domain.sms import SmsJob
from vela.ports.notifier import NotifierError, NotifierRejected

NEXT_WINDOW = NOW + timedelta(seconds=45)
CRITERIA = Criteria("padel", Area("country", "Spagna", "ES"),
                    Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
PHONE = "333 123 4567"
URL = "https://pay.test/o1"


class Setup:
    def __init__(self, status=OrderStatus.AWAITING_PAYMENT, phone=PHONE, language="it", sms=None,
                 kind=JobKind.SMS_LINK):
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many([make_product(1, destination="Valencia")])
        profile = TravelerProfile("Anna", "Rossi", "a@x.it", phone, 2)
        self.repos.intents.add(Intent("i1", "padel", replace(CRITERIA, language=language), profile, NOW))
        self.repos.proposals.add(Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2,
                                          Decimal("350"), "EUR", "Motivo.", NOW))
        self.repos.orders.add(Order("o1", "p1", "i1", "1", status, 2, Decimal("350"), Decimal("700"),
                                    "EUR", profile, NOW, NOW, itinerary_id="it-1", payment_url=URL,
                                    payment_ref="cs_1", booking_code="R-123456"))
        self.sms = sms or FakeSms()
        self.job = SmsJob(self.repos, self.sms, now=lambda: NOW)
        self.repos.jobs.enqueue(Job("s1", kind, "o1", JobStatus.PENDING, NOW, NOW))
        self.title = self.repos.products.get("1").title

    def run(self, attempts=0):
        j = replace(self.repos.jobs.get("s1"), status=JobStatus.RUNNING, locked_at=NOW, attempts=attempts)
        self.repos.jobs.save(j)
        return self.job.run(j, NEXT_WINDOW)


class SendTest(unittest.TestCase):
    def test_link_sms_has_recap_and_link(self):
        s = Setup()
        result = s.run()
        expected = sms_text.payment_link(s.title, date(2026, 10, 1), date(2026, 10, 4), 2,
                                         Decimal("700"), URL, "it")
        self.assertEqual(s.sms.sent, [("+393331234567", expected)])
        self.assertEqual(result.job.status, JobStatus.DONE)
        self.assertEqual(s.repos.jobs.get("s1"), result.job)

    def test_confirmation_sms_has_booking_code(self):
        s = Setup(status=OrderStatus.CONFIRMED, kind=JobKind.SMS_CONFIRMED)
        s.run()
        expected = sms_text.confirmed(s.title, date(2026, 10, 1), date(2026, 10, 4), 2, "R-123456", "it")
        self.assertEqual(s.sms.sent, [("+393331234567", expected)])

    def test_language_of_the_intent(self):
        s = Setup(language="en")
        s.run()
        self.assertTrue(s.sms.sent[0][1].startswith("Vela: your trip is ready to pay."))

    def test_order_is_never_changed(self):
        s = Setup()
        before = s.repos.orders.get("o1")
        s.run()
        self.assertEqual(s.repos.orders.get("o1"), before)


class SkipTest(unittest.TestCase):
    def test_order_no_longer_awaiting_payment_sends_nothing(self):
        for status in (OrderStatus.PAID_PENDING_BOOKING, OrderStatus.CANCELLED, OrderStatus.EXPIRED,
                       OrderStatus.CONFIRMED):
            s = Setup(status=status)
            result = s.run()
            self.assertEqual((s.sms.sent, result.job.status), ([], JobStatus.DONE), status)

    def test_confirmation_for_unconfirmed_order_sends_nothing(self):
        s = Setup(status=OrderStatus.BOOKING_FAILED, kind=JobKind.SMS_CONFIRMED)
        self.assertEqual(s.run().job.status, JobStatus.DONE)
        self.assertEqual(s.sms.sent, [])

    def test_invalid_phone_is_skipped_and_logged(self):
        s = Setup(phone="abc")
        with self.assertLogs("vela.domain.sms", "WARNING") as logs:
            result = s.run()
        self.assertEqual((s.sms.sent, result.job.status), ([], JobStatus.DONE))
        self.assertIn("numero non valido", logs.output[0])
        self.assertIn("o1", logs.output[0])


class RetryTest(unittest.TestCase):
    def test_temporary_error_retries_after_30s_2min_10min_then_dead(self):
        s = Setup(sms=FakeSms(fail_with=[NotifierError("Twilio: HTTP 503")] * 4))
        waits = []
        for attempt in range(3):
            result = s.run(attempts=attempt)
            self.assertEqual((result.job.status, result.job.attempts), (JobStatus.PENDING, attempt + 1))
            waits.append((result.job.run_after - NOW).total_seconds())
        self.assertEqual(waits, [30, 120, 600])
        result = s.run(attempts=3)
        self.assertEqual((result.job.status, result.job.attempts), (JobStatus.DEAD, 4))
        self.assertIn("503", result.job.last_error)
        self.assertEqual(s.sms.sent, [])

    def test_retry_after_temporary_error_sends_once(self):
        s = Setup(sms=FakeSms(fail_with=[NotifierError("Twilio: timeout")]))
        s.run()
        result = s.run(attempts=1)
        self.assertEqual((result.job.status, len(s.sms.sent)), (JobStatus.DONE, 1))

    def test_rejected_is_dead_at_once(self):
        s = Setup(sms=FakeSms(fail_with=[NotifierRejected("Twilio: HTTP 400, codice 21211")]))
        result = s.run()
        self.assertEqual((result.job.status, result.job.attempts), (JobStatus.DEAD, 1))
        self.assertIn("21211", result.job.last_error)


class PrivacyTest(unittest.TestCase):
    def test_success_log_masks_number_and_hides_text(self):
        s = Setup()
        with self.assertLogs("vela.domain.sms", "INFO") as logs:
            s.run()
        output = "\n".join(logs.output)
        self.assertIn("+39******4567", output)
        self.assertNotIn("3331234567", output)
        self.assertNotIn(URL, output)

    def test_errors_mask_the_number(self):
        s = Setup(sms=FakeSms(fail_with=[NotifierRejected("Twilio: HTTP 400, codice 21211")]))
        with self.assertLogs("vela.domain.sms", "WARNING") as logs:
            result = s.run()
        self.assertNotIn("3331234567", "\n".join(logs.output) + result.job.last_error)


class EnqueueTest(unittest.TestCase):
    def test_one_active_job_per_order_and_kind(self):
        s = Setup()
        ids = iter(["n1", "n2", "n3"])
        self.assertFalse(enqueue_sms(s.repos, JobKind.SMS_LINK, "o1", NOW, lambda: next(ids)))
        self.assertTrue(enqueue_sms(s.repos, JobKind.SMS_CONFIRMED, "o1", NOW, lambda: next(ids)))
        self.assertFalse(enqueue_sms(s.repos, JobKind.SMS_CONFIRMED, "o1", NOW, lambda: next(ids)))
        kinds = sorted(j.kind.value for j in s.repos.jobs._jobs.values())
        self.assertEqual(kinds, ["sms_confirmed", "sms_link"])
```

- [ ] **Step 2: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_sms_job -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'vela.adapters.sms_fake'`

- [ ] **Step 3: Implementare la porta** `vela/ports/notifier.py`:

```python
"""Porta verso il fornitore di SMS (decisione 2026-09-26). Implementazioni: Twilio, finta.

`to` è sempre in E.164 (`vela.domain.phone`). I messaggi delle eccezioni non contengono il
numero in chiaro, il testo dell'SMS né le credenziali: finiscono in `last_error` e nei log.
"""
from typing import Protocol


class NotifierError(Exception):
    """Errore temporaneo (rete, timeout, 5xx, 429): il job riprova."""


class NotifierRejected(NotifierError):
    """Errore definitivo (4xx, es. numero non valido): il job non riprova."""


class Notifier(Protocol):
    def send_sms(self, to: str, body: str) -> str: ...   # id del messaggio presso il fornitore
```

- [ ] **Step 4: Implementare l'adapter finto** `vela/adapters/sms_fake.py`:

```python
"""SMS finti per replay e test: gli invii restano in `sent`, nessuna chiamata di rete.

`fail_with` programma le eccezioni da sollevare, una per invio, prima di riuscire.
"""
import threading
from typing import List, Sequence, Tuple


class FakeSms:
    def __init__(self, fail_with: Sequence[Exception] = ()):
        self._lock = threading.Lock()
        self._failures = list(fail_with)
        self.sent: List[Tuple[str, str]] = []

    def send_sms(self, to: str, body: str) -> str:
        with self._lock:
            if self._failures:
                raise self._failures.pop(0)
            self.sent.append((to, body))
            return "SMfake%d" % len(self.sent)
```

- [ ] **Step 5: Implementare l'accodamento** `vela/domain/notify.py`:

```python
"""Accodamento degli SMS (decisione 2026-09-26): un solo job attivo per ordine e tipo.

Separato da `vela.domain.sms` perché lo usano il job d'acquisto e quello di prenotazione, e
`sms` importa `JobResult` da `purchase`.
"""
from datetime import datetime
from typing import Callable

from vela.domain.models import Job, JobKind, JobStatus
from vela.ports.repositories import Repositories


def enqueue_sms(repos: Repositories, kind: JobKind, order_id: str, now: datetime,
                new_id: Callable[[], str]) -> bool:
    """Accoda `kind` per l'ordine, se non ce n'è già uno attivo. False se c'era già."""
    if repos.jobs.active_for_order(order_id, kind) is not None:
        return False
    repos.jobs.enqueue(Job(new_id(), kind, order_id, JobStatus.PENDING, now, now))
    return True
```

- [ ] **Step 6: Implementare il job** `vela/domain/sms.py`:

```python
"""Job degli SMS al viaggiatore (decisione 2026-09-26, RF-19, RF-57): link e conferma.

Il job d'acquisto accoda `sms_link` quando l'ordine diventa `awaiting_payment`; il job di
prenotazione accoda `sms_confirmed` alla conferma. Nessuna chiamata a HofJ, nessuna quota.
Un ordine che non è più nello stato atteso (pagato, annullato, scaduto) chiude il job senza
invio, e così un numero che non si normalizza. Errore temporaneo: nuovo tentativo dopo 30 s,
2 min, 10 min, poi `dead`; errore definitivo: `dead` subito. L'ordine non cambia mai per colpa
di un SMS. Nei log il numero è mascherato e il testo (che contiene il link) non compare.
"""
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, Sequence

from vela.domain import phone, sms_text
from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus
from vela.domain.purchase import JobResult
from vela.ports.notifier import Notifier, NotifierError, NotifierRejected
from vela.ports.repositories import Repositories

log = logging.getLogger(__name__)

EXPECTED = {JobKind.SMS_LINK: OrderStatus.AWAITING_PAYMENT,
            JobKind.SMS_CONFIRMED: OrderStatus.CONFIRMED}


class SmsJob:
    def __init__(self, repos: Repositories, notifier: Notifier, now: Callable[[], datetime],
                 backoff: Sequence[int] = (30, 120, 600)):
        self.repos, self.notifier, self.now = repos, notifier, now
        self.backoff = tuple(backoff)

    def run(self, job: Job, next_window: datetime) -> JobResult:
        order = self.repos.orders.get(job.order_id)
        if order is None or order.status != EXPECTED[job.kind]:
            return self._close(job, JobStatus.DONE)
        to = phone.normalize_it(order.traveler.phone)
        if to is None:
            log.warning("sms %s saltato: numero non valido (ordine %s)", job.kind.value, order.id)
            return self._close(job, JobStatus.DONE)
        try:
            message_id = self.notifier.send_sms(to, self._body(job.kind, order))
        except NotifierRejected as exc:
            log.warning("sms %s rifiutato per %s (ordine %s): %s", job.kind.value, phone.mask(to),
                        order.id, exc)
            return self._close(replace(job, attempts=job.attempts + 1), JobStatus.DEAD, exc)
        except NotifierError as exc:
            attempts = job.attempts + 1
            if attempts > len(self.backoff):
                log.warning("sms %s non inviato a %s dopo %d tentativi (ordine %s): %s",
                            job.kind.value, phone.mask(to), attempts, order.id, exc)
                return self._close(replace(job, attempts=attempts), JobStatus.DEAD, exc)
            run_after = self.now() + timedelta(seconds=self.backoff[attempts - 1])
            job = replace(job, status=JobStatus.PENDING, run_after=run_after, locked_at=None,
                          attempts=attempts, last_error=_describe(exc))
            self.repos.jobs.save(job)
            return JobResult(job)
        log.info("sms %s inviato a %s (ordine %s, messaggio %s)", job.kind.value, phone.mask(to),
                 order.id, message_id)
        return self._close(job, JobStatus.DONE)

    def _body(self, kind: JobKind, order: Order) -> str:
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        proposal = self.repos.proposals.get(order.proposal_id)
        title = self.repos.products.get(order.product_id).title
        if kind == JobKind.SMS_LINK:
            return sms_text.payment_link(title, proposal.start_date, proposal.end_date, order.pax,
                                         order.total, order.payment_url, lang)
        return sms_text.confirmed(title, proposal.start_date, proposal.end_date, order.pax,
                                  order.booking_code, lang)

    def _close(self, job: Job, status: JobStatus, exc: Exception = None) -> JobResult:
        job = replace(job, status=status, locked_at=None,
                      last_error=_describe(exc) if exc is not None else job.last_error)
        self.repos.jobs.save(job)
        return JobResult(job)


def _describe(exc: Exception) -> str:
    return ("%s: %s" % (type(exc).__name__, exc))[:500]
```

- [ ] **Step 7: Verificare che passino**

Run: `uv run python -m unittest tests.test_sms_job -v`
Expected: OK (14 test)

- [ ] **Step 8: Commit**

```bash
git add vela/ports/notifier.py vela/adapters/sms_fake.py vela/domain/notify.py vela/domain/sms.py tests/test_sms_job.py
git commit -m "$(cat <<'EOF'
Add the Notifier port, fake SMS adapter and SMS job

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Accodare gli SMS e collegarli al worker

**Files:**
- Modify: `vela/domain/purchase.py` (passo `STEP_LINK`, ~righe 108-114)
- Modify: `vela/domain/booking.py` (costruttore e conferma, ~righe 23-48)
- Modify: `vela/app.py` (`build_worker`)
- Test: `tests/test_purchase_job.py`, `tests/test_booking_job.py`, `tests/test_sms_flow.py` (nuovo)

**Interfaces:**
- Consumes: `enqueue_sms` (Task 4), `SmsJob` (Task 4), `FakeSms` (Task 4).
- Produces: `BookingJob(..., new_id: Callable[[], str] = lambda: str(uuid.uuid4()))`;
  `build_worker(vela, settings, router=None, notifier=None)`: senza `notifier` usa `FakeSms()`
  (il Task 7 lo sostituisce con `build_notifier(settings)`).

- [ ] **Step 1: Test del job d'acquisto** in `tests/test_purchase_job.py`, nuova classe in fondo:

```python
class SmsLinkTest(unittest.TestCase):
    def test_link_step_enqueues_one_sms_link(self):
        s = Setup()
        j = replace(s.repos.jobs.get("j1"), status=JobStatus.RUNNING, locked_at=NOW)
        s.job.run(j, NEXT_WINDOW)
        self.assertEqual(s.repos.orders.get("o1").status, OrderStatus.AWAITING_PAYMENT)
        sms = [j for j in s.repos.jobs._jobs.values() if j.kind == JobKind.SMS_LINK]
        self.assertEqual([(j.order_id, j.status) for j in sms], [("o1", JobStatus.PENDING)])

    def test_failed_purchase_enqueues_no_sms(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_itinerary": [ConfigError("401")]}))
        j = replace(s.repos.jobs.get("j1"), status=JobStatus.RUNNING, locked_at=NOW)
        s.job.run(j, NEXT_WINDOW)
        self.assertFalse(any(j.kind == JobKind.SMS_LINK for j in s.repos.jobs._jobs.values()))
```

- [ ] **Step 2: Test del job di prenotazione** in `tests/test_booking_job.py`, nuova classe in fondo:

```python
class SmsConfirmedTest(unittest.TestCase):
    def sms_jobs(self, s):
        return [j for j in s.repos.jobs._jobs.values() if j.kind == JobKind.SMS_CONFIRMED]

    def test_confirmation_enqueues_one_sms(self):
        s = Setup()
        s.run()
        self.assertEqual([j.order_id for j in self.sms_jobs(s)], ["o1"])

    def test_second_run_on_confirmed_order_adds_nothing(self):
        s = Setup()
        s.run()
        s.run()
        self.assertEqual(len(self.sms_jobs(s)), 1)

    def test_failed_booking_enqueues_no_sms(self):
        s = Setup(hofj=FakeHofJ(fail_at={"create_booking": [ProductError("400")]}))
        s.run()
        self.assertEqual(self.sms_jobs(s), [])
```

- [ ] **Step 3: Test del flusso completo** `tests/test_sms_flow.py`:

```python
"""Flusso completo in replay con gli SMS finti: due messaggi, nell'ordine, mai doppioni."""
import unittest
from datetime import timedelta

from support import NOW
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.sms_fake import FakeSms
from vela.adapters.stripe_fake import FakePayments
from vela.app import build_worker
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import OrderStatus, Participant, TravelerProfile
from vela.domain.usecases import Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
TRAVELER = TravelerProfile("Anna", "Rossi", "anna@x.it", "333 123 4567",
                           participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at


class Flow:
    def __init__(self, traveler=TRAVELER):
        self.clock = Clock()
        self.repos = MemoryRepositories()
        hofj = ReplayHofJ(now=self.clock)
        self.repos.products.upsert_many(hofj.load_catalog())
        self.payments = FakePayments("http://test", now=self.clock)
        self.vela = Vela(self.repos, hofj, self.payments, DEFAULT_TRAVELER, now=self.clock)
        self.sms = FakeSms()
        self.worker = build_worker(self.vela, Settings(worker_concurrency=0), notifier=self.sms)
        self.worker.processor.refresh_quota()
        self.traveler = traveler

    def accept(self):
        iid = self.vela.create_intent(INTENT, self.traveler).intent_id
        return self.vela.accept_proposal(self.vela.get_proposal(iid).proposal.id)

    def run_until(self, order_id, status, max_seconds=900):
        for _ in range(max_seconds):
            self.worker.drain()
            if self.repos.orders.get(order_id).status == status:
                return self.repos.orders.get(order_id)
            self.clock.at += timedelta(seconds=1)
        raise AssertionError("ordine non %s in %d secondi simulati" % (status.value, max_seconds))


class SmsFlowTest(unittest.TestCase):
    def test_link_then_confirmation_exactly_once(self):
        f = Flow()
        order_id = f.accept().order_id
        order = f.run_until(order_id, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(len(f.sms.sent), 1)
        to, body = f.sms.sent[0]
        self.assertEqual(to, "+393331234567")
        self.assertIn(order.payment_url, body)
        for _ in range(3):                                   # il viaggiatore chiede lo stato
            f.vela.get_order_status(order_id)
            f.worker.drain()
        f.payments.pay(order)
        order = f.run_until(order_id, OrderStatus.CONFIRMED)
        f.worker.drain()
        self.assertEqual(len(f.sms.sent), 2)
        self.assertTrue(f.sms.sent[1][1].startswith("Vela: prenotazione confermata!"))
        self.assertIn(order.booking_code, f.sms.sent[1][1])

    def test_invalid_phone_books_without_sms(self):
        f = Flow(TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000",
                                 participants=(Participant("Bo", "Bi"),)))
        order_id = f.accept().order_id
        order = f.run_until(order_id, OrderStatus.AWAITING_PAYMENT)
        f.payments.pay(order)
        f.run_until(order_id, OrderStatus.CONFIRMED)
        self.assertEqual(f.sms.sent, [])
```

- [ ] **Step 4: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_purchase_job tests.test_booking_job tests.test_sms_flow -v`
Expected: FAIL su `SmsLinkTest.test_link_step_enqueues_one_sms_link`, `SmsConfirmedTest.test_confirmation_enqueues_one_sms`;
ERROR su `SmsFlowTest` (`build_worker() got an unexpected keyword argument 'notifier'`)

- [ ] **Step 5: Accodare `sms_link`** in `vela/domain/purchase.py`. Import in cima:

```python
from vela.domain.notify import enqueue_sms
```

e il ramo `STEP_LINK` diventa:

```python
        elif job.step == STEP_LINK:
            link = self.payments.create_payment_link(order, product.title)
            self._save_order(replace(order, status=OrderStatus.AWAITING_PAYMENT,
                                     payment_url=link.url, payment_ref=link.reference))
            now = self.now()   # RF-20: da qui la verifica del pagamento per interrogazione
            self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PAYMENT_CHECK, order.id, JobStatus.PENDING,
                                        now, now + timedelta(seconds=self.poll_seconds)))
            enqueue_sms(self.repos, JobKind.SMS_LINK, order.id, now, self.new_id)   # RF-19
```

Aggiornare il docstring del modulo, riga del passo 4:

```
  4 link di pagamento (porta dei pagamenti), job di verifica e SMS    0
```

- [ ] **Step 6: Accodare `sms_confirmed`** in `vela/domain/booking.py`. Import:

```python
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, Sequence

from vela.domain import say
from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus
from vela.domain.notify import enqueue_sms
```

Costruttore:

```python
    def __init__(self, repos: Repositories, hofj: HofJRouter, now: Callable[[], datetime],
                 max_attempts: int = 5, backoff: Sequence[int] = (5, 10, 20, 40),
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())):
        self.repos, self.hofj, self.now = repos, hofj, now
        self.max_attempts, self.backoff, self.new_id = max_attempts, tuple(backoff), new_id
```

Conferma (sostituisce la riga `self._save(replace(order, status=OrderStatus.CONFIRMED, booking_code=code))`):

```python
        self._save(replace(order, status=OrderStatus.CONFIRMED, booking_code=code))
        enqueue_sms(self.repos, JobKind.SMS_CONFIRMED, order.id, self.now(), self.new_id)   # RF-57
```

- [ ] **Step 7: Collegare il worker** in `vela/app.py`. Import:

```python
from vela.adapters.sms_fake import FakeSms
from vela.domain.sms import SmsJob
from vela.ports.notifier import Notifier
```

`build_worker`:

```python
def build_worker(vela: Vela, settings: Settings, router: Optional[HofJRouter] = None,
                 notifier: Optional[Notifier] = None) -> Worker:
    """Job d'acquisto, prenotazione, verifica del pagamento e SMS sotto un solo processore (RF-50).
    Senza `router` (test con un client finto) tutti i brand usano `vela.hofj`."""
    router = router or SingleClientRouter(vela.hofj)
    notifier = notifier or FakeSms()
    purchase = PurchaseJob(vela.repos, router, vela.payments, vela._propose, vela.defaults,
                           now=vela.now, max_attempts=settings.purchase_max_attempts,
                           new_id=vela.new_id, poll_seconds=settings.payment_poll_seconds)
    booking = BookingJob(vela.repos, router, now=vela.now,
                         max_attempts=settings.booking_max_attempts, backoff=settings.booking_backoff,
                         new_id=vela.new_id)
    check = PaymentCheckJob(vela.repos, vela.payments, vela.orders, now=vela.now,
                            poll_seconds=settings.payment_poll_seconds)
    sms = SmsJob(vela.repos, notifier, now=vela.now)
    processor = JobProcessor(vela.repos, router, {JobKind.PURCHASE: purchase,
                                                     JobKind.BOOKING: booking,
                                                     JobKind.PAYMENT_CHECK: check,
                                                     JobKind.SMS_LINK: sms,
                                                     JobKind.SMS_CONFIRMED: sms},
                             now=vela.now, lease_seconds=settings.job_lease_seconds)
    return Worker(processor, settings.worker_concurrency)
```

Aggiornare il commento di `quota_needs` in `vela/domain/jobs.py`:

```python
    return None, 0      # verifica del pagamento e SMS: nessuna chiamata HofJ
```

- [ ] **Step 8: Verificare che passino, poi tutta la suite**

Run: `uv run python -m unittest tests.test_purchase_job tests.test_booking_job tests.test_sms_flow -v`
Expected: OK

Run: `uv run python -m unittest discover -s tests`
Expected: OK (nessuna regressione; i test Postgres saltati senza `DATABASE_URL`)

- [ ] **Step 9: Commit**

```bash
git add vela/domain/purchase.py vela/domain/booking.py vela/domain/jobs.py vela/app.py tests/test_purchase_job.py tests/test_booking_job.py tests/test_sms_flow.py
git commit -m "$(cat <<'EOF'
Text the payment link and the booking confirmation from the job queue

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Adapter Twilio

**Files:**
- Create: `vela/adapters/sms_twilio.py`
- Test: `tests/test_sms_twilio.py`

**Interfaces:**
- Consumes: `NotifierError`, `NotifierRejected` (Task 4).
- Produces: `TwilioSms(account_sid: str, auth_token: str, from_number: str, transport: Optional[httpx.BaseTransport] = None, timeout: float = 10.0)`, `send_sms(to, body) -> str`.

- [ ] **Step 1: Scrivere i test**

```python
"""Adapter Twilio con `httpx.MockTransport`: mai la rete, mai segreti o numeri negli errori."""
import base64
import unittest
from urllib.parse import parse_qs

import httpx

from vela.adapters.sms_twilio import TwilioSms
from vela.ports.notifier import NotifierError, NotifierRejected

SID, TOKEN, FROM = "AC0123456789", "token-segreto-di-prova", "+15550001111"
TO, BODY = "+393331234567", "Vela: testo con https://checkout.stripe.com/c/pay/cs_test_x"


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, body = r
        return httpx.Response(status, json=body)


def make(*responses):
    rec = Recorder(*responses)
    return TwilioSms(SID, TOKEN, FROM, transport=httpx.MockTransport(rec)), rec


class SendTest(unittest.TestCase):
    def test_posts_the_message_form_with_basic_auth(self):
        sms, rec = make((201, {"sid": "SM123"}))
        self.assertEqual(sms.send_sms(TO, BODY), "SM123")
        req = rec.requests[0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(str(req.url), "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % SID)
        self.assertEqual(parse_qs(req.content.decode()), {"To": [TO], "From": [FROM], "Body": [BODY]})
        expected = "Basic " + base64.b64encode(("%s:%s" % (SID, TOKEN)).encode()).decode()
        self.assertEqual(req.headers["authorization"], expected)


class ErrorTest(unittest.TestCase):
    def errors(self):
        rejected = (400, {"code": 21211, "message": "The 'To' number %s is not valid." % TO})
        cases = [rejected, (401, {"code": 20003}), (429, {"code": 20429}), (500, {}), (503, {}),
                 httpx.ReadTimeout("timeout"), httpx.ConnectError("rete giù")]
        out = []
        for case in cases:
            sms, _ = make(case)
            with self.assertRaises(NotifierError) as ctx:
                sms.send_sms(TO, BODY)
            out.append(ctx.exception)
        return out

    def test_4xx_is_definitive_with_twilio_code(self):
        rejected, unauthorized = self.errors()[:2]
        self.assertIsInstance(rejected, NotifierRejected)
        self.assertIn("21211", str(rejected))
        self.assertIsInstance(unauthorized, NotifierRejected)

    def test_429_5xx_timeout_and_network_are_temporary(self):
        for exc in self.errors()[2:]:
            self.assertNotIsInstance(exc, NotifierRejected, exc)

    def test_errors_never_contain_token_number_or_text(self):
        for exc in self.errors():
            text = str(exc) + repr(exc.__cause__) + repr(exc.__context__)
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("3331234567", text)
            self.assertNotIn("cs_test_x", text)
```

- [ ] **Step 2: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_sms_twilio -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'vela.adapters.sms_twilio'`

- [ ] **Step 3: Implementare**

```python
"""Adapter Twilio (decisione 2026-09-26): una `POST /Messages.json` con `httpx`, nessun SDK.

Basic auth con SID e token, form `To`, `From`, `Body`, timeout di 10 s. 2xx → sid del
messaggio; 429, 5xx, rete e timeout → `NotifierError` (si riprova); altri 4xx →
`NotifierRejected` con il solo codice Twilio: il `message` di Twilio può ripetere il numero.
Le eccezioni di `httpx` non vengono concatenate (`from None`) per non portare con sé la richiesta.
"""
from typing import Optional

import httpx

from vela.ports.notifier import NotifierError, NotifierRejected

API_BASE = "https://api.twilio.com/2010-04-01"
TIMEOUT_SECONDS = 10.0


class TwilioSms:
    def __init__(self, account_sid: str, auth_token: str, from_number: str,
                 transport: Optional[httpx.BaseTransport] = None, timeout: float = TIMEOUT_SECONDS):
        self.path = "/Accounts/%s/Messages.json" % account_sid
        self.from_number = from_number
        self.client = httpx.Client(base_url=API_BASE, auth=(account_sid, auth_token),
                                   timeout=timeout, transport=transport)

    def send_sms(self, to: str, body: str) -> str:
        try:
            response = self.client.post(self.path, data={"To": to, "From": self.from_number,
                                                         "Body": body})
        except httpx.TimeoutException as exc:
            raise NotifierError("Twilio: timeout (%s)" % type(exc).__name__) from None
        except httpx.HTTPError as exc:
            raise NotifierError("Twilio: rete (%s)" % type(exc).__name__) from None
        status = response.status_code
        if status == 429 or status >= 500:
            raise NotifierError("Twilio: HTTP %d" % status)
        if status >= 400:
            raise NotifierRejected("Twilio: HTTP %d, codice %s" % (status, _code(response)))
        return _json(response).get("sid") or ""


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _code(response: httpx.Response):
    return _json(response).get("code")
```

- [ ] **Step 4: Verificare che passino**

Run: `uv run python -m unittest tests.test_sms_twilio -v`
Expected: OK (4 test)

- [ ] **Step 5: Commit**

```bash
git add vela/adapters/sms_twilio.py tests/test_sms_twilio.py
git commit -m "$(cat <<'EOF'
Add the Twilio SMS adapter over httpx

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Configurazione Twilio

**Files:**
- Modify: `vela/config.py` (`Settings`, `from_env`)
- Modify: `vela/app.py` (`build_notifier`, `build_worker`, docstring del modulo)
- Modify: `render.yaml`, `README.md` (tabella delle variabili)
- Test: `tests/test_config.py`, `tests/test_render_yaml.py`, `tests/test_notifier_config.py` (nuovo)

**Interfaces:**
- Consumes: `TwilioSms` (Task 6), `FakeSms` (Task 4).
- Produces: `Settings.twilio_account_sid`, `Settings.twilio_auth_token`, `Settings.twilio_from`
  (`Optional[str]`); `build_notifier(settings: Settings) -> Notifier`.

- [ ] **Step 1: Test di `from_env`** in `tests/test_config.py`. In `ALL_VARS` aggiungere:

```python
    "TWILIO_ACCOUNT_SID": "AC1",
    "TWILIO_AUTH_TOKEN": "tt",
    "TWILIO_FROM": "+15550001111",
```

in `test_empty_environment_gives_none_and_replay_default` aggiungere:

```python
        self.assertIsNone(s.twilio_account_sid)
        self.assertIsNone(s.twilio_auth_token)
        self.assertIsNone(s.twilio_from)
```

e in `test_all_variables_are_read`:

```python
        self.assertEqual((s.twilio_account_sid, s.twilio_auth_token, s.twilio_from),
                         ("AC1", "tt", "+15550001111"))
```

- [ ] **Step 2: Test di `build_notifier`** `tests/test_notifier_config.py`:

```python
"""SMS veri con le tre variabili Twilio, finti con nessuna, avvio bloccato a metà (decisione 2026-09-26)."""
import unittest

from vela.adapters.sms_fake import FakeSms
from vela.adapters.sms_twilio import TwilioSms
from vela.app import build_notifier
from vela.config import Settings

FULL = dict(twilio_account_sid="AC1", twilio_auth_token="token-segreto", twilio_from="+15550001111")


class BuildNotifierTest(unittest.TestCase):
    def test_no_twilio_variables_gives_fake_sms(self):
        self.assertIsInstance(build_notifier(Settings()), FakeSms)

    def test_all_three_give_twilio(self):
        self.assertIsInstance(build_notifier(Settings(**FULL)), TwilioSms)

    def test_partial_configuration_blocks_startup_naming_the_missing(self):
        with self.assertRaises(RuntimeError) as ctx:
            build_notifier(Settings(twilio_account_sid="AC1", twilio_auth_token="token-segreto"))
        self.assertIn("TWILIO_FROM", str(ctx.exception))
        self.assertNotIn("token-segreto", str(ctx.exception))

    def test_twilio_is_independent_from_upstream_mode(self):
        self.assertIsInstance(build_notifier(Settings(vela_upstream_mode="replay", **FULL)), TwilioSms)
```

- [ ] **Step 3: Test di Blueprint e README** in `tests/test_render_yaml.py`: aggiungere a `ENV_VARS`

```python
ENV_VARS = ["HOFJ_API_KEY", "HOFJ_BASE_URL", "HOFJ_BRANDS", "DATABASE_URL", "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET", "VELA_API_TOKEN", "VELA_UPSTREAM_MODE", "ANTHROPIC_API_KEY",
            "VELA_PUBLIC_URL", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"]
```

- [ ] **Step 4: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_config tests.test_notifier_config tests.test_render_yaml -v`
Expected: FAIL/ERROR (`twilio_account_sid` sconosciuto, `build_notifier` mancante, `key: TWILIO_ACCOUNT_SID` assente)

- [ ] **Step 5: Implementare `config.py`.** In `Settings`, dopo `vela_public_url`:

```python
    twilio_account_sid: Optional[str] = None           # SMS al viaggiatore (decisione 2026-09-26)
    twilio_auth_token: Optional[str] = None
    twilio_from: Optional[str] = None                  # numero Twilio del mittente, E.164
```

In `from_env`, dopo `vela_public_url=...`:

```python
            twilio_account_sid=env.get("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=env.get("TWILIO_AUTH_TOKEN"),
            twilio_from=env.get("TWILIO_FROM"),
```

Nel commento `# Parametri di M5: ... (l'elenco di §6 resta chiuso)` nessuna modifica: le tre
variabili entrano nell'elenco di §6 con il Task 9.

- [ ] **Step 6: Implementare `app.py`.** Import:

```python
from vela.adapters.sms_twilio import TwilioSms
```

Dopo `build_payments`:

```python
TWILIO_VARS = (("TWILIO_ACCOUNT_SID", "twilio_account_sid"), ("TWILIO_AUTH_TOKEN", "twilio_auth_token"),
               ("TWILIO_FROM", "twilio_from"))


def build_notifier(settings: Settings) -> Notifier:
    """SMS Twilio con tutte e tre le variabili, finti con nessuna (indipendente dall'upstream).
    Una configurazione a metà blocca l'avvio: meglio che scoprire in produzione SMS mai partiti."""
    missing = [name for name, attr in TWILIO_VARS if not getattr(settings, attr)]
    if len(missing) == len(TWILIO_VARS):
        return FakeSms()
    if missing:
        raise RuntimeError("SMS Twilio: mancano %s" % ", ".join(missing))
    return TwilioSms(settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from)
```

In `build_worker` sostituire `notifier = notifier or FakeSms()` con:

```python
    notifier = notifier or build_notifier(settings)
```

Nel docstring del modulo, dopo "Il pagamento è Stripe se ``STRIPE_SECRET_KEY`` è impostata, altrimenti finto.":

```
Gli SMS al viaggiatore sono Twilio se le tre variabili ``TWILIO_*`` sono impostate, altrimenti finti.
```

- [ ] **Step 7: `render.yaml`**, dopo il blocco di `ANTHROPIC_API_KEY`:

```yaml
      - key: TWILIO_ACCOUNT_SID
        sync: false
      - key: TWILIO_AUTH_TOKEN
        sync: false
      - key: TWILIO_FROM
        sync: false
```

- [ ] **Step 8: `README.md`**, tre righe in fondo alla tabella delle variabili (dopo `ANTHROPIC_API_KEY`):

```markdown
| `TWILIO_ACCOUNT_SID` | per SMS reali | Account Twilio. Con `TWILIO_AUTH_TOKEN` e `TWILIO_FROM` Vela manda al viaggiatore l'SMS con il link di pagamento e quello di conferma; senza nessuna delle tre gli SMS sono finti; con solo alcune l'app non parte. Vedi `docs/sms.md`. |
| `TWILIO_AUTH_TOKEN` | per SMS reali | Token dell'account Twilio. |
| `TWILIO_FROM` | per SMS reali | Numero Twilio del mittente in E.164 (es. `+1555…`). |
```

- [ ] **Step 9: Verificare che passino, poi tutta la suite**

Run: `uv run python -m unittest tests.test_config tests.test_notifier_config tests.test_render_yaml -v`
Expected: OK

Run: `uv run python -m unittest discover -s tests`
Expected: OK

- [ ] **Step 10: Commit**

```bash
git add vela/config.py vela/app.py render.yaml README.md tests/test_config.py tests/test_notifier_config.py tests/test_render_yaml.py
git commit -m "$(cat <<'EOF'
Read the Twilio variables and choose real or fake SMS at startup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Frasi dell'agente e istruzioni MCP

**Files:**
- Modify: `vela/domain/say.py` (`say_queued`, `say_status`, `_AWAITING_AMOUNT`)
- Modify: `vela/domain/usecases.py` (`accept_proposal` ~riga 204, `get_order_status` ~righe 222-241)
- Modify: `vela/surfaces/mcp.py` (`INSTRUCTIONS`, `DESCRIPTIONS["accept_proposal"]`, `DESCRIPTIONS["get_order_status"]`)
- Test: `tests/test_say.py`, `tests/test_sms_flow.py`, `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `phone.tail` (Task 1).
- Produces: `say_queued(minutes: int, lang: str = "it", phone_tail: Optional[str] = None)`,
  `say_status(..., phone_tail: Optional[str] = None)`. Senza `phone_tail` le frasi restano quelle di oggi.

- [ ] **Step 1: Test delle frasi** in `tests/test_say.py`, nuova classe in fondo:

```python
class SmsPhrasesTest(unittest.TestCase):
    def test_queued_announces_both_sms(self):
        self.assertEqual(say.say_queued(1, phone_tail="4567"),
                         "Ti ho messo in coda: tra circa un minuto il link di pagamento sarà pronto e "
                         "te lo mando per SMS al numero che finisce con 4567. Ti scrivo di nuovo "
                         "quando la prenotazione è confermata.")
        self.assertEqual(say.say_queued(12, "en", "4567"),
                         "You're in the queue: the payment link will be ready in about 12 minutes and "
                         "I'll text it to the number ending in 4567. I'll text you again when the "
                         "booking is confirmed.")

    def test_queued_without_valid_phone_is_unchanged(self):
        self.assertIn("Chiedimi a che punto è", say.say_queued(1))

    def test_awaiting_payment_mentions_the_sms(self):
        s = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "it", Decimal("700"),
                           phone_tail="4567")
        self.assertEqual(s, "L'ordine è in attesa del pagamento di 700 euro: usa il link che ti ho "
                            "mandato, anche per SMS al numero che finisce con 4567.")
        en = say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "en", Decimal("700"),
                            phone_tail="4567")
        self.assertEqual(en, "The order is waiting for payment of 700 euros: use the link I sent "
                             "you, also by text to the number ending in 4567.")

    def test_queued_status_passes_the_tail(self):
        s = say.say_status(OrderStatus.QUEUED, None, None, "it", minutes=3, phone_tail="4567")
        self.assertIn("finisce con 4567", s)

    def test_sms_phrases_have_no_url(self):
        for text in (say.say_queued(5, "it", "4567"), say.say_queued(5, "en", "4567"),
                     say.say_status(OrderStatus.AWAITING_PAYMENT, None, None, "it", Decimal("1"),
                                    phone_tail="4567")):
            self.assertNotIn("http", text)
```

(Controllare che `Decimal` sia già importato in `tests/test_say.py`; altrimenti aggiungere
`from decimal import Decimal`.)

- [ ] **Step 2: Test dei casi d'uso** in `tests/test_sms_flow.py`, nuova classe in fondo:

```python
class AgentPhraseTest(unittest.TestCase):
    def test_accept_announces_the_sms_with_the_last_digits(self):
        queued = Flow().accept()
        self.assertIn("SMS al numero che finisce con 4567", queued.say)

    def test_status_while_awaiting_payment_mentions_the_sms(self):
        f = Flow()
        order_id = f.accept().order_id
        f.run_until(order_id, OrderStatus.AWAITING_PAYMENT)
        self.assertIn("anche per SMS", f.vela.get_order_status(order_id).say)

    def test_invalid_phone_keeps_todays_phrase(self):
        f = Flow(TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000",
                                 participants=(Participant("Bo", "Bi"),)))
        self.assertNotIn("SMS", f.accept().say)
```

- [ ] **Step 3: Test delle istruzioni MCP** in `tests/test_mcp_tools.py`, accanto a
  `test_instructions_mention_the_queue`:

```python
    def test_instructions_say_vela_texts_the_link(self):
        self.assertIn("texts the payment link", INSTRUCTIONS)
        self.assertNotIn("comes later from get_order_status", INSTRUCTIONS)
        self.assertIn("only when the user asks", DESCRIPTIONS["get_order_status"])
        self.assertIn("texts", DESCRIPTIONS["accept_proposal"])
```

- [ ] **Step 4: Verificare che falliscano**

Run: `uv run python -m unittest tests.test_say tests.test_sms_flow tests.test_mcp_tools -v`
Expected: ERROR (`say_queued() got an unexpected keyword argument 'phone_tail'`) e FAIL sulle istruzioni

- [ ] **Step 5: Implementare `say.py`.** Sostituire `_AWAITING_AMOUNT` e aggiungere le varianti SMS:

```python
_AWAITING_AMOUNT = {
    "it": "L'ordine è in attesa del pagamento di %s: usa il link che ti ho mandato.",
    "en": "The order is waiting for payment of %s: use the link I sent you.",
}
_AWAITING_AMOUNT_SMS = {
    "it": ("L'ordine è in attesa del pagamento di %s: usa il link che ti ho mandato, anche per SMS "
           "al numero che finisce con %s."),
    "en": "The order is waiting for payment of %s: use the link I sent you, also by text to the number ending in %s.",
}
```

`say_status` (firma e ramo `awaiting_payment`, il resto invariato):

```python
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
```

`say_queued`:

```python
def say_queued(minutes: int, lang: str = "it", phone_tail: Optional[str] = None) -> str:
    """RF-45: l'attesa dichiarata in minuti (già arrotondati per eccesso, almeno 1). Con le
    ultime cifre di un numero valido annuncia i due SMS (RF-19, RF-57) invece di invitare a
    chiedere lo stato."""
    if lang == "en":
        wait = "a minute" if minutes == 1 else "%d minutes" % minutes
        if phone_tail:
            return ("You're in the queue: the payment link will be ready in about %s and I'll text "
                    "it to the number ending in %s. I'll text you again when the booking is "
                    "confirmed." % (wait, phone_tail))
        return ("You're in the queue: the payment link will be ready in about %s. Ask me how it's "
                "going whenever you like." % wait)
    wait = "un minuto" if minutes == 1 else "%d minuti" % minutes
    if phone_tail:
        return ("Ti ho messo in coda: tra circa %s il link di pagamento sarà pronto e te lo mando "
                "per SMS al numero che finisce con %s. Ti scrivo di nuovo quando la prenotazione "
                "è confermata." % (wait, phone_tail))
    return ("Ti ho messo in coda: tra circa %s il link di pagamento sarà pronto. Chiedimi a che "
            "punto è quando vuoi." % wait)
```

- [ ] **Step 6: Implementare `usecases.py`.** Import: `from vela.domain import phone` (accanto
  agli altri import da `vela.domain`). In `accept_proposal`:

```python
        return OrderQueued(order.id, OrderStatus.QUEUED, position, wait,
                           say.say_queued(wait_minutes(wait or 0), lang, phone.tail(order.traveler.phone)))
```

In `get_order_status`, subito dopo `status = order.status`:

```python
        tail = phone.tail(order.traveler.phone)
```

ramo `QUEUED`:

```python
            return OrderStatusResponse(order.id, status, say.say_status(status, None, None, lang,
                                                                        minutes=minutes, phone_tail=tail),
                                       position=position, wait_seconds=wait)
```

e la chiamata finale:

```python
            say.say_status(status, order.booking_code, order.failure_reason, lang, order.total,
                           price_from_total=estimate, phone_tail=tail),
```

- [ ] **Step 7: Implementare `mcp.py`.** Ultima frase di `INSTRUCTIONS`:

```python
    "proposal, never through a new create_intent. Accepting a proposal puts the order in a "
    "queue: Vela texts the payment link and later the booking confirmation to the traveler's "
    "phone, so do not poll get_order_status: call it only when the user asks."
```

Coda di `DESCRIPTIONS["accept_proposal"]` (da "On success the answer is a wait"):

```python
        "calling it again never creates a second order. On success the answer is a wait, not a "
        "link: the order is `queued` with `order_id`, `position` and `wait_seconds`. Vela texts "
        "the payment link to the traveler's phone when it is ready and texts again when the "
        "booking is confirmed; call get_order_status only when the user asks."
        + _VOICE),
```

Inizio di `DESCRIPTIONS["get_order_status"]`:

```python
        "Check an order only when the user asks how it is going or says they paid: Vela already "
        "texts the payment link and the confirmation. Returns `status`: queued (with `position` "
        "and `wait_seconds`), "
```

(il resto della descrizione invariato, da `awaiting_payment (with ...`).

- [ ] **Step 8: Verificare che passino, poi tutta la suite**

Run: `uv run python -m unittest tests.test_say tests.test_sms_flow tests.test_mcp_tools -v`
Expected: OK

Run: `uv run python -m unittest discover -s tests`
Expected: OK. Se un test esistente fissa le vecchie frasi con un numero valido nel profilo,
aggiornarlo alla nuova frase e annotarlo nel Task 9 (`docs/decisions.md`).

- [ ] **Step 9: Commit**

```bash
git add vela/domain/say.py vela/domain/usecases.py vela/surfaces/mcp.py tests/test_say.py tests/test_sms_flow.py tests/test_mcp_tools.py
git commit -m "$(cat <<'EOF'
Tell the traveler the link arrives by SMS and stop the agent from polling

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Documenti

**Files:**
- Create: `docs/sms.md`
- Modify: `docs/spec.md` (RF-19 in §4.4, RF-57 in fondo a §4.5, §6 variabili e chiamate esterne)
- Modify: `docs/decisions.md` (sezione "SMS: esecuzione")
- Test: `tests/test_render_yaml.py` resta verde (README già aggiornato nel Task 7)

- [ ] **Step 1: `docs/sms.md`**

````markdown
# SMS al viaggiatore (Twilio)

Vela manda due SMS al viaggiatore principale, senza che nessuno chieda nulla (decisione del
2026-09-26, design in `docs/superpowers/specs/2026-09-26-sms-notifiche-design.md`):

1. quando l'ordine diventa `awaiting_payment`: riepilogo (titolo, date, persone, totale) e link
   di pagamento Stripe, valido 24 ore;
2. quando l'ordine diventa `confirmed`: riepilogo e codice di prenotazione.

Codice: `vela/domain/sms.py` (job), `vela/domain/sms_text.py` (testi), `vela/domain/phone.py`
(numeri), `vela/adapters/sms_twilio.py`, `vela/adapters/sms_fake.py`.

## Numeri

Il telefono è quello di RF-12. Spazi e separatori vengono tolti; `+…` resta com'è; `00…`
diventa `+…`; altrimenti si aggiunge `+39` (test in Italia). Un numero che non risulta `+` e
8-15 cifre non riceve SMS: il job lo registra nei log e l'ordine va avanti.

## Attivazione

| Variabile | Effetto |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | Tutte e tre: SMS reali con Twilio. Nessuna: SMS finti (replay e test). Solo alcune: l'app non parte. Indipendenti da `VELA_UPSTREAM_MODE` |

`TWILIO_FROM` è il numero Twilio acquistato, in E.164. Mai incollare le chiavi in chat, nei
commit o in `docs/`.

## Tentativi

Job `sms_link` e `sms_confirmed` nella coda del worker, prelevati dopo prenotazioni e verifiche
del pagamento e prima degli acquisti. Errore temporaneo (rete, timeout, 5xx, 429): nuovo
tentativo dopo 30 s, 2 min, 10 min, poi `dead`. Altro 4xx di Twilio: `dead` subito. Un SMS non
cambia mai lo stato dell'ordine. Nei log il numero è mascherato (`+39******4567`) e il testo
non compare.

## Test manuale

Costo: 2 SMS Twilio (circa 3-4 segmenti in tutto), 1 Checkout Session e 1 pagamento di test
Stripe, più quanto indicato in `docs/stripe.md` per HofJ in live.

1. Impostare nell'ambiente le tre variabili Twilio e `STRIPE_SECRET_KEY` con `VELA_PUBLIC_URL`.
2. Eseguire il flusso di `docs/stripe.md` (`scripts/rest_flow.py`) con il proprio numero come
   telefono del viaggiatore.
3. Senza interrogare lo stato: arriva l'SMS con riepilogo e link. Pagare con `4242 4242 4242 4242`.
4. Arriva l'SMS di conferma con lo stesso codice di `GET /v1/orders/<order_id>`.

Registrare l'esito in `docs/acceptance.md` senza numero né chiavi.
````

- [ ] **Step 2: `docs/spec.md`.** Sostituire l'ultima frase di RF-19 ("È compito dell'agente
  consegnare il link nel canale del viaggiatore (messaggio, SMS, lettura ad alta voce
  dell'importo con link inviato via testo).") con:

```markdown
  Vela manda il link con il riepilogo via SMS al telefono del viaggiatore principale appena
  l'ordine è `awaiting_payment` (decisione del 2026-09-26, `docs/sms.md`); l'agente non
  interroga lo stato di sua iniziativa e chiama `get_order_status` solo quando il viaggiatore lo
  chiede.
```

In fondo all'elenco di §4.5, prima di `### 4.6`:

```markdown
- **RF-57** Quando l'ordine è `confirmed`, Vela manda al viaggiatore principale un SMS con
  titolo, date, persone e codice di prenotazione. L'esito dell'invio di un SMS non cambia mai
  lo stato dell'ordine (decisione del 2026-09-26, `docs/sms.md`).
```

In §6, elenco delle variabili: dopo `` `VELA_PUBLIC_URL` `` aggiungere
`` , `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` (opzionali, SMS) ``; nella riga
delle chiamate esterne `(HofJ, Stripe, Anthropic)` → `(HofJ, Stripe, Anthropic, Twilio)`.

- [ ] **Step 3: `docs/decisions.md`**, nuova sezione in fondo:

```markdown
## 2026-09-26 — SMS: esecuzione

| Decisione | Scelta | Motivo |
|---|---|---|
| Moduli dei testi | Testi degli SMS in `vela/domain/sms_text.py`, non in `say.py`; accodamento in `vela/domain/notify.py` | `say.py` promette frasi senza URL; `notify.py` evita l'import circolare tra `sms.py` e `purchase.py` |
| Suite finale | <numero> test, <numero> saltati, verde con `uv run python`. Nessuna chiamata a Twilio | — |
```

Sostituire `<numero>` con i valori reali letti dall'ultima esecuzione della suite (Step 4) e
aggiungere una riga per ogni test esistente modificato nel Task 8, se ce ne sono.

- [ ] **Step 4: Suite completa**

Run: `uv run python -m unittest discover -s tests`
Expected: OK; annotare numero di test e saltati in `docs/decisions.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/sms.md docs/spec.md docs/decisions.md
git commit -m "$(cat <<'EOF'
Document the SMS notifications, RF-19 and RF-57

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Test manuale reale (solo con OK esplicito)

Non è codice: parte solo dopo che l'utente ha impostato nell'ambiente le variabili Twilio e ha
detto di procedere. Chi esegue non legge né stampa le variabili.

- [ ] **Step 1:** Dichiarare all'utente le chiamate: 2 SMS Twilio (circa 3-4 segmenti), 1 Checkout
  Session e 1 pagamento di test Stripe, letture della sessione ogni 60 s, e in live le chiamate
  HofJ di `docs/stripe.md`. Aspettare l'OK.
- [ ] **Step 2:** Eseguire i passi di `docs/sms.md`, "Test manuale", con il numero dato dall'utente.
- [ ] **Step 3:** Registrare l'esito in `docs/acceptance.md` (data, SMS ricevuti sì/no, stato finale
  dell'ordine), senza numero né chiavi; commit `Record the SMS end-to-end test`.
