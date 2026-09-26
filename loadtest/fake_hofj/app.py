"""App ASGI del finto HofJ (M13a): un processo, asincrona, regole di HofJ.

Stato del carrello da `ReplayHofJ` (latenza zero, quota illimitata: la quota e la latenza le
applica questo strato); prodotti da tutte le fixture `fixtures/catalog*.json`, indicizzati per
brand, per il sync di M10 e per `POST /v1/itineraries`.

Forme reali (`docs/api/internal-checkout.md`, `docs/api/quota-health.md`): envelope
`{data, meta: {now}}`, errori RFC 7807 in `application/json`, `openAmount.amount` stringa,
`pax-1` precompilato dal customer, 429 con `retryAfterSeconds` nel corpo e senza header,
`POST /v1/bookings` → `{data: "<itineraryId>"}` (upsert per itinerario, come osservato).

Ordine di ogni chiamata: autenticazione → quota → guasto → latenza → esecuzione. Le rotte
`/_fake/*` e `/health` non consumano quota.
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from loadtest.fake_hofj.faults import Fault, FaultPlan, Latency
from loadtest.fake_hofj.log import CallLog
from loadtest.fake_hofj.rules import Background, make_window
from vela.adapters.hofj_replay import FIXTURES_DIR, ReplayHofJ
from vela.domain.catalog import load_fixture
from vela.domain.models import Product
from vela.ports.hofj import Customer, Pax, UpstreamError

DEFAULT_KEY = "loadtest-key"   # chiave finta, non un segreto: il finto accetta solo questa
PAGE_LIMIT = 100


@dataclass
class FakeConfig:
    api_key: str = DEFAULT_KEY
    window: str = "anchored"
    limit: int = 120
    background_rpm: float = 0.0
    latency: str = "standard"
    faults: Tuple[Fault, ...] = ()
    hang_seconds: float = 20.0
    seed: int = 13
    log_path: Optional[str] = None
    fixtures_dir: str = FIXTURES_DIR


class FakeError(Exception):
    def __init__(self, status: int, slug: str, title: str, detail: str):
        super().__init__(detail)
        self.status, self.slug, self.title, self.detail = status, slug, title, detail


def problem(status: int, slug: str, title: str, detail: str, **extra) -> JSONResponse:
    body = {"type": "https://api.hofj.com/problems/" + slug, "title": title, "status": status,
            "detail": detail, **extra}
    return JSONResponse(body, status_code=status, media_type="application/json")


def _money(amount: Decimal, currency: str) -> dict:
    text = format(amount.normalize(), "f") if amount == amount.to_integral() else str(amount)
    return {"amount": text, "currency": currency}


def _catalog(fixtures_dir: str):
    """{brand: (item di lista in ordine, {id: dettaglio}, {id: Product})} da tutte le fixture."""
    import json
    catalogs = {}
    for name in sorted(os.listdir(fixtures_dir)):
        if not (name.startswith("catalog") and name.endswith(".json")):
            continue
        path = os.path.join(fixtures_dir, name)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        details = {pid: d["raw"] for pid, d in (data.get("details") or {}).items()}
        products = {p.id: p for p in load_fixture(path) if not p.archived and p.id in details}
        catalogs[data["brand"]] = (data.get("products") or [], details, products)
    return catalogs


class FakeHofJ:
    """Stato e regole; le rotte HTTP sono in `create_app`."""

    def __init__(self, config: FakeConfig, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.config, self.clock, self.sleep = config, clock, sleep
        self.window = make_window(config.window, config.limit)
        self.faults = FaultPlan(config.faults, config.seed)
        self.latency = Latency(config.latency, config.seed)
        self.log = CallLog(config.log_path)
        self.catalogs = _catalog(config.fixtures_dir)
        self.cart = ReplayHofJ(catalog_path=[], latency=(0.0, 0.0), limit=None)
        self.bookings: Dict[str, int] = {}          # itineraryId → POST eseguite (upsert)
        self.background = Background(config.background_rpm, clock())

    # --- regole ------------------------------------------------------------------------------

    def tick_background(self) -> int:
        """Consuma le chiamate maturate degli altri usi della chiave."""
        now = self.clock()
        due = self.background.due(now)
        for _ in range(due):
            a = self.window.admit(self.config.api_key, now)
            self.log.write({"t": now, "origin": "background", "endpoint": "background",
                            "path": "", "status": 200 if a.ok else 429, "outcome": "background",
                            "counted": True, "executed": False, "used": a.used,
                            "window_start": a.window_start, "itinerary_id": None, "latency": 0.0})
        return due

    async def call(self, request: Request, endpoint: str, action: Callable[[], object],
                   itinerary_id: Optional[str] = None) -> JSONResponse:
        started = self.clock()
        record = {"t": started, "origin": "vela", "endpoint": endpoint, "path": request.url.path,
                  "counted": False, "executed": False, "used": None, "window_start": None,
                  "itinerary_id": itinerary_id, "latency": 0.0, "fault": None}
        response = await self._call(request, endpoint, action, record)
        record["status"] = response.status_code
        record["outcome"] = record.get("outcome") or ("ok" if response.status_code < 400 else "error")
        record["latency"] = round(self.clock() - started, 3)
        self.log.write(record)
        return response

    async def _call(self, request: Request, endpoint: str, action, record: dict) -> JSONResponse:
        auth = request.headers.get("authorization", "")
        if auth != "Bearer " + self.config.api_key:
            record["outcome"] = "unauthorized"
            return problem(401, "unauthorized", "Unauthorized", "missing or invalid API key")
        a = self.window.admit(self.config.api_key, record["t"])
        record.update(counted=True, used=a.used, window_start=a.window_start)
        if not a.ok:
            record["outcome"] = "429"
            return problem(429, "rate-limited", "Too Many Requests",
                           "rate limit of %d requests per minute exceeded" % a.limit,
                           retryAfterSeconds=round(a.retry_after, 3))
        fault = self.faults.pick(endpoint)
        record["fault"] = fault
        await self.sleep(self.latency.draw(endpoint))
        brand = request.query_params.get("brand", "")
        if fault == "5xx":
            record["outcome"] = "fault"
            return problem(503, "service-unavailable", "Service Unavailable", "upstream unavailable")
        if fault == "product_502":
            record["outcome"] = "fault"
            return problem(502, "upstream-error", "Upstream Error",
                           'Brand "%s" POST /itinerary returned 404: {"error":{"code":'
                           '"NOT_FOUND_ERROR"}}' % brand)
        if fault == "hang":
            record["outcome"] = "fault"
            await self.sleep(self.config.hang_seconds)
            return problem(502, "upstream-error", "Upstream Error",
                           'Brand "%s" request failed: timeout of 15000ms exceeded' % brand)
        try:
            data = action()
        except FakeError as exc:
            return problem(exc.status, exc.slug, exc.title, exc.detail)
        record["executed"] = True
        if isinstance(data, dict) and "itineraryId" in data and record["itinerary_id"] is None:
            record["itinerary_id"] = data["itineraryId"]
        if fault == "hang_then_execute":
            record["outcome"] = "fault"
            await self.sleep(self.config.hang_seconds)
        body = data if isinstance(data, dict) and "data" in data else {"data": data}
        body.setdefault("meta", {"now": int(self.clock() * 1000)})
        return JSONResponse(body, media_type="application/json")

    # --- azioni ------------------------------------------------------------------------------

    def _brand(self, brand: str):
        try:
            return self.catalogs[brand]
        except KeyError:
            raise FakeError(400, "bad-request", "Bad Request", "unknown brand %r" % brand) from None

    def list_products(self, brand: str, limit: int, cursor: Optional[str]) -> dict:
        items, _, _ = self._brand(brand)
        start = int(cursor or 0)
        limit = max(1, min(limit, PAGE_LIMIT))
        page = items[start:start + limit]
        nxt = str(start + limit) if start + limit < len(items) else None
        return {"data": page, "meta": {"now": int(self.clock() * 1000), "nextCursor": nxt}}

    def product_detail(self, brand: str, product_id: str) -> dict:
        _, details, _ = self._brand(brand)
        if product_id not in details:
            raise FakeError(404, "not-found", "Not Found", "product %s not found" % product_id)
        return details[product_id]

    def create_itinerary(self, brand: str, body: dict) -> dict:
        _, _, products = self._brand(brand)
        product: Optional[Product] = products.get(str(body.get("productId")))
        if product is None:
            raise FakeError(502, "upstream-error", "Upstream Error",
                            'Brand "%s" POST /itinerary returned 404: {"error":{"code":'
                            '"NOT_FOUND_ERROR","metadata":{"queryProps":{"productId":%s}}}}'
                            % (brand, body.get("productId")))
        iid = self.cart.create_itinerary(product, date.fromisoformat(body["startDate"]),
                                         int(body["adults"]), int(body.get("rooms") or 1),
                                         body.get("currency") or "EUR")
        return {"itineraryId": iid}

    def _itinerary(self, iid: str) -> dict:
        try:
            return self.cart._get(iid)
        except UpstreamError:
            raise FakeError(502, "upstream-error", "Upstream Error",
                            'Brand POST /itinerary/%s returned 404: {"error":{"code":'
                            '"NOT_FOUND_ERROR"}}' % iid) from None

    def get_itinerary(self, iid: str) -> dict:
        it = self._itinerary(iid)
        amount = _money(it["total"], it["currency"])
        return {"itineraryId": iid, "productId": it["product_id"],
                "startDate": it["start_date"].isoformat(), "paxNumber": it["adults"],
                "totalPrice": amount,
                "checkout": {"openAmount": amount, "total": amount, "originalTotal": amount,
                             "status": "BookingInitiated", "refId": iid}}

    def set_customer(self, iid: str, body: dict) -> dict:
        it = self._itinerary(iid)
        address = body.get("address") or {}
        it["customer"] = Customer(body.get("firstName", ""), body.get("lastName", ""),
                                  body.get("email", ""), body.get("phone", ""),
                                  address.get("street1", ""), address.get("postalCode", ""),
                                  address.get("city", ""), address.get("region", ""),
                                  address.get("countryCode", ""))
        first = it["pax"][0]
        if not first.first_name:   # come HofJ: pax-1 precompilato dal customer
            it["pax"][0] = Pax(first.ref_id, it["customer"].first_name, it["customer"].last_name)
        return {"now": int(self.clock() * 1000)}

    def get_pax(self, iid: str) -> list:
        return [{"refId": p.ref_id, "firstName": p.first_name or "", "lastName": p.last_name or "",
                 "age": 0, "gender": None, "nationalityCountryCode": None}
                for p in self._itinerary(iid)["pax"]]

    def set_pax(self, iid: str, body: list) -> dict:
        it = self._itinerary(iid)
        known = {p.ref_id for p in it["pax"]}
        if {p.get("refId") for p in body} != known:
            raise FakeError(400, "bad-request", "Bad Request", "pax refId must be preserved")
        it["pax"] = [Pax(p["refId"], p.get("firstName"), p.get("lastName")) for p in body]
        return {"now": int(self.clock() * 1000)}

    def create_booking(self, body: dict) -> str:
        iid = str(body.get("itineraryId") or "")
        self._itinerary(iid)
        self.bookings[iid] = self.bookings.get(iid, 0) + 1
        return iid

    def quota(self) -> dict:
        a = self.window.peek(self.config.api_key, self.clock())
        iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")
        return {"clientId": "loadtest", "backend": "process_local", "limitPerMinute": a.limit,
                "usedInWindow": a.used, "remainingInWindow": max(a.limit - a.used, 0),
                "windowStartedAt": iso(a.window_start), "windowEndsAt": iso(a.window_end)}

    def stats(self) -> dict:
        stats = self.log.stats()
        stats.update(itineraries=len(self.cart._itineraries), bookings=len(self.bookings))
        return stats


def create_app(config: Optional[FakeConfig] = None, fake: Optional[FakeHofJ] = None) -> FastAPI:
    fake = fake or FakeHofJ(config or FakeConfig())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if fake.background.interval is not None:
            async def loop():
                while True:
                    fake.tick_background()
                    await asyncio.sleep(min(fake.background.interval, 1.0))
            task = asyncio.create_task(loop())
        yield
        if task is not None:
            task.cancel()
        fake.log.close()

    app = FastAPI(title="Finto HofJ (M13a)", lifespan=lifespan)
    app.state.fake = fake

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/_fake/stats")
    async def stats():
        return fake.stats()

    @app.post("/_fake/reset")
    async def reset():
        fake.log.reset()
        return {"reset": True}

    @app.get("/v1/quota")
    async def quota(request: Request):
        return await fake.call(request, "GET /v1/quota", fake.quota)

    @app.get("/v1/products")
    async def products(request: Request, brand: str = "", limit: int = PAGE_LIMIT,
                       cursor: Optional[str] = None):
        return await fake.call(request, "GET /v1/products",
                               lambda: fake.list_products(brand, limit, cursor))

    @app.get("/v1/products/{product_id}")
    async def product(request: Request, product_id: str, brand: str = ""):
        return await fake.call(request, "GET /v1/products/{id}",
                               lambda: fake.product_detail(brand, product_id))

    @app.post("/v1/itineraries")
    async def create_itinerary(request: Request, brand: str = ""):
        body = await request.json()
        return await fake.call(request, "POST /v1/itineraries",
                               lambda: fake.create_itinerary(brand, body))

    @app.get("/v1/itineraries/{iid}")
    async def get_itinerary(request: Request, iid: str):
        return await fake.call(request, "GET /v1/itineraries/{id}",
                               lambda: fake.get_itinerary(iid), itinerary_id=iid)

    @app.put("/v1/itineraries/{iid}/customer")
    async def set_customer(request: Request, iid: str):
        body = await request.json()
        return await fake.call(request, "PUT /v1/itineraries/{id}/customer",
                               lambda: fake.set_customer(iid, body), itinerary_id=iid)

    @app.get("/v1/itineraries/{iid}/pax")
    async def get_pax(request: Request, iid: str):
        return await fake.call(request, "GET /v1/itineraries/{id}/pax",
                               lambda: fake.get_pax(iid), itinerary_id=iid)

    @app.put("/v1/itineraries/{iid}/pax")
    async def set_pax(request: Request, iid: str):
        body = await request.json()
        return await fake.call(request, "PUT /v1/itineraries/{id}/pax",
                               lambda: fake.set_pax(iid, body), itinerary_id=iid)

    @app.post("/v1/bookings")
    async def create_booking(request: Request):
        body = await request.json()
        return await fake.call(request, "POST /v1/bookings", lambda: fake.create_booking(body),
                               itinerary_id=str(body.get("itineraryId") or "") or None)

    return app
