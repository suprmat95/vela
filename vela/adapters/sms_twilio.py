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
