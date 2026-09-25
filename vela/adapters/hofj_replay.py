"""Adapter replay di House of Journeys (RNF-08): nessuna chiamata esterna.

Catalogo da `fixtures/catalog.json`; itinerario sintetico con totale = prezzo × adulti;
customer e pax tenuti in memoria del processo (servono solo dentro `accept_proposal`);
prenotazione con codice `R-<6 cifre>`. `create_booking` accetta qualunque id di itinerario
replay, anche dopo un riavvio, così la ripresa di RF-27 funziona in replay.
"""
import os
import random
import uuid
from datetime import date
from typing import Dict, List, Optional

from vela.domain.catalog import load_fixture
from vela.domain.models import Product
from vela.ports.hofj import Customer, Itinerary, Pax, PaymentProof, UpstreamError

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fixtures", "catalog.json")
ITINERARY_PREFIX = "it-replay-"


class ReplayHofJ:
    def __init__(self, catalog_path: str = FIXTURE_PATH, rng: Optional[random.Random] = None):
        self.catalog_path = catalog_path
        self.rng = rng or random.Random()
        self._itineraries: Dict[str, dict] = {}
        self._codes: Dict[str, str] = {}

    def load_catalog(self) -> List[Product]:
        return load_fixture(self.catalog_path)

    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> Itinerary:
        iid = ITINERARY_PREFIX + uuid.uuid4().hex
        self._itineraries[iid] = {
            "product_id": product.id, "start_date": start_date, "adults": adults, "rooms": rooms,
            "customer": None, "pax": [Pax("pax-%d" % (i + 1)) for i in range(adults)],
        }
        return Itinerary(iid, product.price * adults, currency)

    def _get(self, itinerary_id: str) -> dict:
        try:
            return self._itineraries[itinerary_id]
        except KeyError:
            raise UpstreamError("itinerario sconosciuto: %s" % itinerary_id)

    def set_customer(self, itinerary_id: str, customer: Customer) -> None:
        self._get(itinerary_id)["customer"] = customer

    def get_pax(self, itinerary_id: str) -> List[Pax]:
        return list(self._get(itinerary_id)["pax"])

    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None:
        self._get(itinerary_id)["pax"] = list(pax)

    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str:
        if not itinerary_id.startswith(ITINERARY_PREFIX):
            raise UpstreamError("itinerario non replay: %s" % itinerary_id)
        if itinerary_id not in self._codes:
            self._codes[itinerary_id] = "R-%06d" % self.rng.randrange(1_000_000)
        return self._codes[itinerary_id]
