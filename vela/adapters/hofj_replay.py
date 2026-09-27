"""Adapter replay di House of Journeys (RNF-08): nessuna chiamata esterna.

Catalogo da tutte le fixture di produzione (`fixtures/catalog*.json` registrate su
`api.hofj.com`, una per brand, M10) o dalle fixture passate; itinerario sintetico con importo = prezzo × adulti;
customer e pax tenuti in memoria del processo; prenotazione con codice `R-<6 cifre>`.
`create_booking` accetta qualunque id di itinerario replay, anche dopo un riavvio, così la
ripresa di RF-27 funziona in replay.

Simulazione (M5, per M13): `latency=(min, max)` secondi per chiamata e `limit` chiamate per
finestra fissa di 60 s ancorata alla prima chiamata, come HofJ; oltre il limite `QuotaError`.
Default: nessuna latenza, quota illimitata.
"""
import os
import random
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from vela.domain.catalog import load_fixture, select_fixtures
from vela.domain.models import Product
from vela.ports.hofj import (Customer, Itinerary, Pax, PaymentProof, QuotaError, QuotaSnapshot,
                             UpstreamError)
from vela.ports.quota import DEFAULT_LIMIT_PER_MINUTE

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fixtures", "catalog.json")
FIXTURES_DIR = os.path.dirname(FIXTURE_PATH)
PRODUCTION_URL = "https://api.hofj.com"   # host del catalogo replay di default
ITINERARY_PREFIX = "it-replay-"


WINDOW = timedelta(seconds=60)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReplayHofJ:
    def __init__(self, catalog_path: Union[str, Sequence[str], None] = None,
                 rng: Optional[random.Random] = None,
                 latency: Tuple[float, float] = (0.0, 0.0), limit: Optional[int] = None,
                 now: Callable[[], datetime] = _utcnow, sleep: Callable[[float], None] = time.sleep):
        if catalog_path is None:
            catalog_path = select_fixtures(FIXTURES_DIR, PRODUCTION_URL)
        self.catalog_paths = [catalog_path] if isinstance(catalog_path, str) else list(catalog_path)
        self.rng = rng or random.Random()
        self.latency, self.limit, self.now, self.sleep = latency, limit, now, sleep
        self._itineraries: Dict[str, dict] = {}
        self._codes: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._window_start: Optional[datetime] = None
        self._used = 0

    def load_catalog(self) -> List[Product]:
        return [p for path in self.catalog_paths for p in load_fixture(path)]

    def _call(self) -> None:
        """Una chiamata HofJ simulata: conta nella finestra, poi attende la latenza."""
        with self._lock:
            now = self.now()
            if self._window_start is None or now >= self._window_start + WINDOW:
                self._window_start, self._used = now, 0
            if self.limit is not None and self._used >= self.limit:
                raise QuotaError("quota simulata esaurita (%d/min)" % self.limit,
                                 retry_after=(self._window_start + WINDOW - now).total_seconds())
            self._used += 1
        low, high = self.latency
        if high > 0:
            self.sleep(self.rng.uniform(low, high))

    def get_quota(self) -> QuotaSnapshot:
        self._call()
        with self._lock:
            return QuotaSnapshot(self.limit or DEFAULT_LIMIT_PER_MINUTE, self._used,
                                 self._window_start, self._window_start + WINDOW)

    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> str:
        self._call()
        iid = ITINERARY_PREFIX + uuid.uuid4().hex
        self._itineraries[iid] = {
            "product_id": product.id, "start_date": start_date, "adults": adults, "rooms": rooms,
            "customer": None, "pax": [Pax("pax-%d" % (i + 1)) for i in range(adults)],
            "total": product.price * adults, "currency": currency,
        }
        return iid

    def get_itinerary(self, itinerary_id: str) -> Itinerary:
        self._call()
        it = self._get(itinerary_id)
        return Itinerary(itinerary_id, it["total"], it["currency"])

    def _get(self, itinerary_id: str) -> dict:
        try:
            return self._itineraries[itinerary_id]
        except KeyError:
            raise UpstreamError("itinerario sconosciuto: %s" % itinerary_id)

    def _adopt(self, itinerary_id: str) -> dict:
        """M19: cliente e pax arrivano dopo il pagamento, anche dopo un riavvio che ha svuotato i
        carrelli in memoria. Come `create_booking`, un id del replay si accetta anche se non è di
        questo processo; gli altri restano un errore."""
        if itinerary_id not in self._itineraries and itinerary_id.startswith(ITINERARY_PREFIX):
            self._itineraries[itinerary_id] = {"customer": None, "pax": []}
        return self._get(itinerary_id)

    def set_customer(self, itinerary_id: str, customer: Customer) -> None:
        self._call()
        self._adopt(itinerary_id)["customer"] = customer

    def get_pax(self, itinerary_id: str) -> List[Pax]:
        self._call()
        return list(self._get(itinerary_id)["pax"])

    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None:
        self._call()
        self._adopt(itinerary_id)["pax"] = list(pax)

    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str:
        self._call()
        if not itinerary_id.startswith(ITINERARY_PREFIX):
            raise UpstreamError("itinerario non replay: %s" % itinerary_id)
        if itinerary_id not in self._codes:
            self._codes[itinerary_id] = "R-%06d" % self.rng.randrange(1_000_000)
        return self._codes[itinerary_id]
