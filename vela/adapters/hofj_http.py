"""Adapter HTTP verso House of Journeys (RF-14, RF-23, RF-36, RNF-04).

httpx sincrono, timeout di 15 s, `?brand=&locale=` su ogni chiamata del carrello, `Bearer` in
intestazione. Implementa anche `CatalogSource` per il sync (M10, RF-29): lista paginata e
dettaglio esteso con il brand passato alla chiamata, non quello del client. Risposte `{data, meta}` con `meta` facoltativo; errori RFC 7807 letti senza
guardare il content-type (HofJ usa `application/json` anche per i problemi). Forme verificate su
staging nel Task 1 di M5 (`docs/api/internal-checkout.md`).

Mappatura degli errori (decisione M5):
- timeout, connessione, JSON illeggibile, 5xx → `UpstreamError` (si ripete);
- 429 → `QuotaError` con `retry_after` se HofJ lo dichiara;
- 401/403 → `ConfigError`;
- solo su `POST /v1/itineraries`: 400/404, oppure 502 il cui `detail` riporta un errore
  upstream 4xx o 500 che non sia un timeout → `ProductError` (un id sbagliato e un periodo non
  prenotabile arrivano come 502);
- altri 4xx (per esempio sul booking) → `ProductError`: non si ripetono.
I messaggi degli errori non contengono mai la chiave né il corpo delle richieste.
"""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional, Tuple

import httpx

from vela.domain.models import Product
from vela.ports.hofj import (ConfigError, Customer, HofJError, Itinerary, Pax, PaymentProof,
                             ProductError, QuotaError, QuotaSnapshot, UpstreamError)

TIMEOUT_SECONDS = 15.0
PAGE_LIMIT = 100   # RF-29
_PRODUCT_502 = re.compile(r"(returned|failed:)\s*(4\d\d|500)\b", re.IGNORECASE)


class HofJHttp:
    def __init__(self, base_url: str, api_key: str, brand: str, locale: str = "it",
                 transport: Optional[httpx.BaseTransport] = None, timeout: float = TIMEOUT_SECONDS):
        self.brand, self.locale = brand, locale
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
                                   headers={"Authorization": "Bearer " + api_key,
                                            "Accept": "application/json"})

    # --- carrello (RF-14) ----------------------------------------------------------------

    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> str:
        product_id: Any = int(product.id) if product.id.isdigit() else product.id
        data = self._call("POST", "/v1/itineraries", itinerary=True, json={
            "productId": product_id, "startDate": start_date.isoformat(), "adults": adults,
            "rooms": rooms, "currency": currency})
        return data["itineraryId"]

    def set_customer(self, itinerary_id: str, customer: Customer) -> None:
        self._call("PUT", "/v1/itineraries/%s/customer" % itinerary_id, json={
            "firstName": customer.first_name, "lastName": customer.last_name,
            "email": customer.email, "phone": customer.phone,
            "address": {"street1": customer.street1, "postalCode": customer.postal_code,
                        "city": customer.city, "region": customer.region,
                        "countryCode": customer.country_code}})

    def get_pax(self, itinerary_id: str) -> List[Pax]:
        data = self._call("GET", "/v1/itineraries/%s/pax" % itinerary_id)
        return [Pax(p["refId"], p.get("firstName") or None, p.get("lastName") or None) for p in data]

    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None:
        self._call("PUT", "/v1/itineraries/%s/pax" % itinerary_id, json=[
            {"refId": p.ref_id, "firstName": p.first_name, "lastName": p.last_name} for p in pax])

    def get_itinerary(self, itinerary_id: str) -> Itinerary:
        """L'importo da pagare è `checkout.openAmount` (verifiche di §8)."""
        data = self._call("GET", "/v1/itineraries/%s" % itinerary_id)
        amount = data["checkout"]["openAmount"]
        return Itinerary(itinerary_id, Decimal(str(amount["amount"])), amount["currency"])

    # --- prenotazione (RF-23) ---------------------------------------------------------------

    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str:
        body = {"itineraryId": itinerary_id, "paymentType": proof.payment_type}
        if proof.payment_intent_id:
            body.update(paymentIntentId=proof.payment_intent_id, paymentStatus=proof.payment_status)
        return str(self._call("POST", "/v1/bookings", json=body))

    # --- quota (RF-36) ------------------------------------------------------------------------

    def get_quota(self) -> QuotaSnapshot:
        data = self._call("GET", "/v1/quota", params=False)
        return QuotaSnapshot(int(data["limitPerMinute"]), int(data["usedInWindow"]),
                             _instant(data["windowStartedAt"]), _instant(data["windowEndsAt"]))

    # --- catalogo (RF-29, M10) -------------------------------------------------------------------

    def list_page(self, brand: str, cursor: Optional[str]) -> Tuple[List[dict], Optional[str]]:
        query = {"limit": PAGE_LIMIT}
        if cursor:
            query["cursor"] = cursor
        body = self._request("GET", "/v1/products", brand=brand, extra=query)
        return body["data"], (body.get("meta") or {}).get("nextCursor") or None

    def detail(self, brand: str, product_id: str) -> dict:
        return self._request("GET", "/v1/products/%s" % product_id, brand=brand,
                             extra={"extended": "true"})["data"]

    # --- trasporto ------------------------------------------------------------------------------

    def _call(self, method: str, path: str, json=None, itinerary: bool = False, params: bool = True):
        return self._request(method, path, json=json, itinerary=itinerary, params=params)["data"]

    def _request(self, method: str, path: str, json=None, itinerary: bool = False,
                 params: bool = True, brand: Optional[str] = None, extra: Optional[dict] = None) -> dict:
        """Il corpo `{data, meta}` della risposta; errori mappati come da docstring del modulo."""
        query = {"brand": brand or self.brand, "locale": self.locale, **(extra or {})} if params else None
        try:
            response = self.client.request(method, path, params=query, json=json)
        except httpx.TimeoutException as exc:
            raise UpstreamError("HofJ %s %s: timeout (%s)" % (method, path, type(exc).__name__)) from None
        except httpx.HTTPError as exc:
            raise UpstreamError("HofJ %s %s: rete (%s)" % (method, path, type(exc).__name__)) from None
        try:
            body = response.json()
        except ValueError:
            raise UpstreamError("HofJ %s %s: risposta %d non JSON" % (method, path, response.status_code)) from None
        if response.status_code >= 400:
            raise _error(method, path, response, body, itinerary)
        if not isinstance(body, dict) or "data" not in body:
            raise UpstreamError("HofJ %s %s: risposta senza data" % (method, path))
        return body


def _error(method: str, path: str, response: httpx.Response, body, itinerary: bool) -> HofJError:
    status = response.status_code
    detail = str(body.get("detail", "")) if isinstance(body, dict) else ""
    where = "HofJ %s %s: %d %s" % (method, path, status, detail[:300])
    if status == 429:
        return QuotaError(where, retry_after=_retry_after(response, body))
    if status in (401, 403):
        return ConfigError(where)
    if itinerary and status in (400, 404):
        return ProductError(where)
    if itinerary and status == 502 and _PRODUCT_502.search(detail) and "timeout" not in detail.lower():
        return ProductError(where)
    if 400 <= status < 500:
        return ProductError(where)
    return UpstreamError(where)


def _retry_after(response: httpx.Response, body) -> Optional[float]:
    value = body.get("retryAfterSeconds") if isinstance(body, dict) else None
    value = value if value is not None else response.headers.get("retry-after")
    try:
        return None if value is None else float(value)
    except ValueError:
        return None


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
