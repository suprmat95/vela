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
