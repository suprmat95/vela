"""Adapter HTTP verso HofJ (RF-14, RF-23, RF-36, RNF-04) con `httpx.MockTransport`: mai la rete.

I corpi di risposta sono quelli osservati su staging nel Task 1 di M5
(`docs/api/internal-checkout.md`, "Verifica su staging").
"""
import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

from support import make_product
from vela.adapters.hofj_http import HofJHttp
from vela.ports.hofj import (ConfigError, Customer, Itinerary, Pax, PaymentProof, ProductError,
                             QuotaError, QuotaSnapshot, UpstreamError)

KEY = "sk-segreta-di-prova"
CUSTOMER = Customer("Mario", "Rossi", "test@example.com", "+390200000000", "Via Roma 1", "20121",
                    "Milano", "MI", "IT")
WRONG_ID_DETAIL = ('Brand "staging.weebora.com" POST /itinerary returned 404: {"error":{"name":"Error",'
                   '"message":"The requested resource was not found.","code":"NOT_FOUND_ERROR",'
                   '"statusCode":404,"metadata":{"queryProps":{"productId":118,"locale":"it"}}}}')
PERIOD_DETAIL = ('Brand "staging.weebora.com" POST /itinerary returned 400: {"error":{"code":'
                 '"RESERVATION_PERIOD_ERROR","message":"Periodo di prenotazione non valido"}}')
ITINERARY = {"data": {"productId": 118, "checkout": {
    "openAmount": {"amount": "337", "currency": "EUR"}, "total": {"amount": "368", "currency": "EUR"},
    "originalTotal": {"amount": "337", "currency": "EUR"}, "status": "BookingInitiated",
    "refId": "dlp5lyj338uf"}, "totalPrice": {"amount": "368.00", "currency": "EUR"}},
    "meta": {"now": 1790354420000}}


def problem(status, detail, slug="upstream-error"):
    return {"type": "https://api.hofj.com/problems/" + slug, "title": "Upstream Error",
            "status": status, "detail": detail, "instance": "328d75f1-fcab-4a16-93d3-8c2d045ef55d"}


class Recorder:
    """Transport finto: risponde con `responses` in ordine e registra le richieste."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, body = r
        # HofJ usa application/json anche per i problemi RFC 7807 (differences #4)
        return httpx.Response(status, json=body, headers={"content-type": "application/json; charset=utf-8"})

    def body(self, n=0):
        return json.loads(self.requests[n].content)


def adapter(*responses, locale="it"):
    rec = Recorder(*responses)
    return HofJHttp("https://staging.api.hofj.com/", KEY, "staging.weebora.com", locale=locale,
                    transport=httpx.MockTransport(rec)), rec


class RequestShapeTest(unittest.TestCase):
    def test_create_itinerary_request_shape(self):
        hofj, rec = adapter((200, {"data": {"itineraryId": "dlp5lyj338uf"}, "meta": {"now": 1}}))
        iid = hofj.create_itinerary(make_product(118), date(2026, 12, 8), 2, 1, "EUR")
        self.assertEqual(iid, "dlp5lyj338uf")
        req = rec.requests[0]
        self.assertEqual((req.method, req.url.path), ("POST", "/v1/itineraries"))
        self.assertEqual(dict(req.url.params), {"brand": "staging.weebora.com", "locale": "it"})
        self.assertEqual(req.headers["authorization"], "Bearer " + KEY)
        self.assertEqual(rec.body(), {"productId": 118, "startDate": "2026-12-08", "adults": 2,
                                      "rooms": 1, "currency": "EUR"})

    def test_non_numeric_product_id_is_sent_as_string(self):
        hofj, rec = adapter((200, {"data": {"itineraryId": "x"}}))
        hofj.create_itinerary(make_product("t0054825"), date(2026, 12, 8), 2, 1, "EUR")
        self.assertEqual(rec.body()["productId"], "t0054825")

    def test_set_customer_uses_oas_address(self):
        hofj, rec = adapter((200, {"data": {"now": 1}, "meta": {}}))
        hofj.set_customer("it1", CUSTOMER)
        req = rec.requests[0]
        self.assertEqual((req.method, req.url.path), ("PUT", "/v1/itineraries/it1/customer"))
        self.assertEqual(rec.body(), {"firstName": "Mario", "lastName": "Rossi", "email": "test@example.com",
                                      "phone": "+390200000000", "address": {
                                          "street1": "Via Roma 1", "postalCode": "20121", "city": "Milano",
                                          "region": "MI", "countryCode": "IT"}})

    def test_get_pax_reads_ref_ids(self):
        hofj, _ = adapter((200, {"data": [
            {"refId": "pax-1", "firstName": "Mario", "lastName": "Rossi", "age": 0, "gender": None,
             "nationalityCountryCode": "IT"},
            {"refId": "pax-2", "firstName": "", "lastName": "", "age": 0, "gender": None,
             "nationalityCountryCode": ""}]}))
        self.assertEqual(hofj.get_pax("it1"), [Pax("pax-1", "Mario", "Rossi"), Pax("pax-2", None, None)])

    def test_set_pax_preserves_ref_ids(self):
        hofj, rec = adapter((200, {"data": {"now": 1}, "meta": {}}))
        hofj.set_pax("it1", [Pax("pax-1", "Mario", "Rossi"), Pax("pax-2", "Lucia", "Bianchi")])
        self.assertEqual((rec.requests[0].method, rec.requests[0].url.path), ("PUT", "/v1/itineraries/it1/pax"))
        self.assertEqual(rec.body(), [{"refId": "pax-1", "firstName": "Mario", "lastName": "Rossi"},
                                      {"refId": "pax-2", "firstName": "Lucia", "lastName": "Bianchi"}])

    def test_get_itinerary_reads_open_amount(self):
        hofj, rec = adapter((200, ITINERARY))
        self.assertEqual(hofj.get_itinerary("dlp5lyj338uf"),
                         Itinerary("dlp5lyj338uf", Decimal("337"), "EUR"))
        self.assertEqual(rec.requests[0].url.path, "/v1/itineraries/dlp5lyj338uf")

    def test_money_amount_without_decimals(self):
        body = json.loads(json.dumps(ITINERARY))
        body["data"]["checkout"]["openAmount"] = {"amount": "812.5", "currency": "EUR"}
        hofj, _ = adapter((200, body))
        self.assertEqual(hofj.get_itinerary("x").total, Decimal("812.5"))

    def test_create_booking_sends_payment_intent_and_returns_data_as_code(self):
        hofj, rec = adapter((200, {"data": "dlp5lyj338uf", "meta": {"now": 1}}))
        code = hofj.create_booking("dlp5lyj338uf", PaymentProof("pi_123", "succeeded"))
        self.assertEqual(code, "dlp5lyj338uf")
        self.assertEqual((rec.requests[0].method, rec.requests[0].url.path), ("POST", "/v1/bookings"))
        self.assertEqual(rec.body(), {"itineraryId": "dlp5lyj338uf", "paymentType": "full",
                                      "paymentIntentId": "pi_123", "paymentStatus": "succeeded"})

    def test_create_booking_without_payment_intent_omits_it(self):
        hofj, rec = adapter((200, {"data": "R-12345"}))
        self.assertEqual(hofj.create_booking("it1", PaymentProof("", "succeeded")), "R-12345")
        self.assertEqual(rec.body(), {"itineraryId": "it1", "paymentType": "full"})

    def test_get_quota_snapshot(self):
        hofj, rec = adapter((200, {"data": {
            "clientId": "test-dev-2", "limitPerMinute": 120, "usedInWindow": 1, "remainingInWindow": 119,
            "windowStartedAt": "2026-09-25T16:37:55.609Z", "windowEndsAt": "2026-09-25T16:38:55.609Z",
            "backend": "firestore"}}))
        snap = hofj.get_quota()
        self.assertEqual(snap, QuotaSnapshot(
            120, 1, datetime(2026, 9, 25, 16, 37, 55, 609000, tzinfo=timezone.utc),
            datetime(2026, 9, 25, 16, 38, 55, 609000, tzinfo=timezone.utc)))
        self.assertEqual((rec.requests[0].method, rec.requests[0].url.path), ("GET", "/v1/quota"))

    def test_meta_missing_is_tolerated(self):
        hofj, _ = adapter((200, {"data": {"itineraryId": "x"}}))
        self.assertEqual(hofj.create_itinerary(make_product(1), date(2026, 12, 8), 2, 1, "EUR"), "x")

    def test_locale_comes_from_the_constructor(self):
        hofj, rec = adapter((200, {"data": {"itineraryId": "x"}}), locale="en")
        hofj.create_itinerary(make_product(1), date(2026, 12, 8), 2, 1, "EUR")
        self.assertEqual(rec.requests[0].url.params["locale"], "en")

    def test_timeout_is_fifteen_seconds(self):
        hofj, _ = adapter()
        self.assertEqual(hofj.client.timeout.read, 15.0)


class ErrorMappingTest(unittest.TestCase):
    def test_timeout_is_upstream_error(self):
        hofj, _ = adapter(httpx.ReadTimeout("scaduto"))
        with self.assertRaises(UpstreamError):
            hofj.set_customer("it1", CUSTOMER)

    def test_connection_error_is_upstream_error(self):
        hofj, _ = adapter(httpx.ConnectError("rifiutata"))
        with self.assertRaises(UpstreamError):
            hofj.get_quota()

    def test_429_is_quota_error_with_retry_after(self):
        hofj, _ = adapter((429, dict(problem(429, "rate limited", "rate-limited"), retryAfterSeconds=12)))
        with self.assertRaises(QuotaError) as ctx:
            hofj.get_pax("it1")
        self.assertEqual(ctx.exception.retry_after, 12)

    def test_429_without_retry_after(self):
        hofj, _ = adapter((429, problem(429, "rate limited", "rate-limited")))
        with self.assertRaises(QuotaError) as ctx:
            hofj.get_pax("it1")
        self.assertIsNone(ctx.exception.retry_after)

    def test_401_403_are_config_errors(self):
        for status in (401, 403):
            hofj, _ = adapter((status, problem(status, "forbidden", "forbidden")))
            with self.subTest(status), self.assertRaises(ConfigError):
                hofj.create_itinerary(make_product(1), date(2026, 12, 8), 2, 1, "EUR")

    def test_502_wrong_id_is_product_error(self):
        hofj, _ = adapter((502, problem(502, WRONG_ID_DETAIL)))
        with self.assertRaises(ProductError):
            hofj.create_itinerary(make_product(118), date(2026, 12, 8), 2, 1, "EUR")

    def test_502_reservation_period_is_product_error(self):
        hofj, _ = adapter((502, problem(502, PERIOD_DETAIL)))
        with self.assertRaises(ProductError):
            hofj.create_itinerary(make_product(118), date(2026, 12, 14), 2, 1, "EUR")

    def test_502_upstream_500_is_product_error(self):
        hofj, _ = adapter((502, problem(502, "Upstream get failed: 500")))
        with self.assertRaises(ProductError):
            hofj.create_itinerary(make_product(999999), date(2026, 12, 8), 2, 1, "EUR")

    def test_400_and_404_on_itinerary_are_product_errors(self):
        for status in (400, 404):
            hofj, _ = adapter((status, problem(status, "bad request", "bad-request")))
            with self.subTest(status), self.assertRaises(ProductError):
                hofj.create_itinerary(make_product(1), date(2026, 12, 8), 2, 1, "EUR")

    def test_502_upstream_timeout_is_upstream_error(self):
        hofj, _ = adapter((502, problem(502, "upstream timeout")))
        with self.assertRaises(UpstreamError) as ctx:
            hofj.create_itinerary(make_product(1), date(2026, 12, 8), 2, 1, "EUR")
        self.assertNotIsInstance(ctx.exception, ProductError)

    def test_502_on_customer_is_upstream_error(self):
        hofj, _ = adapter((502, problem(502, WRONG_ID_DETAIL)))
        with self.assertRaises(UpstreamError) as ctx:
            hofj.set_customer("it1", CUSTOMER)
        self.assertNotIsInstance(ctx.exception, ProductError)

    def test_4xx_on_booking_is_not_a_network_error(self):
        hofj, _ = adapter((400, problem(400, "itinerario non valido", "bad-request")))
        with self.assertRaises(ProductError):
            hofj.create_booking("it1", PaymentProof("pi", "succeeded"))

    def test_invalid_json_is_upstream_error(self):
        rec_hofj = HofJHttp("https://h", KEY, "b", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html>gateway</html>")))
        with self.assertRaises(UpstreamError):
            rec_hofj.get_quota()

    def test_api_key_never_in_error_messages(self):
        cases = [(429, problem(429, "x")), (403, problem(403, "x")), (502, problem(502, "x")),
                 httpx.ConnectError("Bearer " + KEY)]
        for case in cases:
            hofj, _ = adapter(case)
            with self.subTest(case=str(case)[:20]):
                with self.assertRaises(Exception) as ctx:
                    hofj.get_pax("it1")
                self.assertNotIn(KEY, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
