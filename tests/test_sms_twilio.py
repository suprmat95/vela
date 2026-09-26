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
