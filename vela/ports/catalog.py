"""Porta di lettura del catalogo HofJ per il sync (M10, RF-29).

Separata da `HofJPort` (carrello e prenotazione, invariata): il brand è un argomento di ogni
chiamata, perché un sync legge tutti i brand della mappa con la stessa chiave.
"""
from typing import List, Optional, Protocol, Tuple


class CatalogSource(Protocol):
    def list_page(self, brand: str, cursor: Optional[str]) -> Tuple[List[dict], Optional[str]]:
        """Una pagina di `/v1/products` (item di lista, archiviati compresi) e il cursore della
        successiva, None all'ultima."""
        ...

    def detail(self, brand: str, product_id: str) -> dict:
        """Il dettaglio esteso di un prodotto."""
        ...
