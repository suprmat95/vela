"""Router del carrello per brand (M10, RF-56).

`BrandRouter`: un client per brand, stessa chiave e stesso host; il brand viene dal prodotto e,
per le righe pre-M10 senza brand, dallo sport tramite `HOFJ_BRANDS`. `SingleClientRouter`: un
solo client per tutti i brand (replay, test).
"""
from typing import Dict, Optional

from vela.domain.models import Product
from vela.ports.hofj import ConfigError, HofJPort, QuotaSnapshot


class BrandRouter:
    def __init__(self, clients: Dict[str, HofJPort], sport_brands: Dict[str, str]):
        if not clients:
            raise ValueError("serve almeno un client HofJ")
        self.clients, self.sport_brands = dict(clients), dict(sport_brands)

    def client(self, brand: str) -> HofJPort:
        try:
            return self.clients[brand]
        except KeyError:
            raise ConfigError("brand HofJ %s non configurato in HOFJ_BRANDS" % brand) from None

    def client_for(self, product: Optional[Product]) -> HofJPort:
        if product is None:
            raise ConfigError("prodotto dell'ordine assente: brand HofJ sconosciuto")
        brand = product.brand or self.sport_brands.get(product.sport)
        if brand is None:
            raise ConfigError("nessun brand HofJ per il prodotto %s (%s)" % (product.id, product.sport))
        return self.client(brand)

    def get_quota(self) -> QuotaSnapshot:
        return next(iter(self.clients.values())).get_quota()


class SingleClientRouter:
    def __init__(self, client: HofJPort):
        self._client = client

    def client(self, brand: str) -> HofJPort:
        return self._client

    def client_for(self, product: Optional[Product]) -> HofJPort:
        return self._client

    def get_quota(self) -> QuotaSnapshot:
        return self._client.get_quota()
