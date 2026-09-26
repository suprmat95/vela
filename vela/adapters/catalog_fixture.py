"""`CatalogSource` sulle fixture registrate (M10): una pagina per brand, il dettaglio è il
`raw` registrato. Serve ai test del sync e alle prove senza rete."""
import json
from typing import Dict, Iterable, List, Optional, Tuple

from vela.ports.hofj import ProductError


class FixtureCatalogSource:
    def __init__(self, paths: Iterable[str]):
        self._catalogs: Dict[str, dict] = {}
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._catalogs[data.get("brand")] = data

    def list_page(self, brand: str, cursor: Optional[str]) -> Tuple[List[dict], Optional[str]]:
        return list(self._catalog(brand).get("products") or []), None

    def detail(self, brand: str, product_id: str) -> dict:
        detail = (self._catalog(brand).get("details") or {}).get(str(product_id))
        if detail is None:
            raise ProductError("fixture %s: nessun dettaglio per %s" % (brand, product_id))
        return detail["raw"]

    def _catalog(self, brand: str) -> dict:
        if brand not in self._catalogs:
            raise ProductError("nessuna fixture per il brand %s" % brand)
        return self._catalogs[brand]
