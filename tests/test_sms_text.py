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
