"""Registrazione delle fixture del catalogo con il codice del sync (M10, RF-32).

Una fixture per (host, brand): `CatalogSync` gira su repository in memoria (quindi scarica il
dettaglio di ogni prodotto attivo) con la quota allineata prima a `/v1/quota`, così rispetta anche
le chiamate già fatte da altri client con la stessa chiave. Le pagine di lista vengono tenute così
come arrivano, archiviati compresi. Formato in `docs/fixtures.md`.
"""
import copy
import json
import os
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.catalog import project_detail
from vela.domain.models import QuotaClass
from vela.sync import CatalogSync, _utcnow


class RecordError(RuntimeError):
    """Un brand non è stato registrato per intero: nessuna fixture scritta."""


def fixture_name(base_url: str, sport: str) -> str:
    """`catalog[-<ambiente>][-tennis].json`: produzione e padel senza suffisso, come le fixture
    registrate in M1 e M7."""
    host = base_url.rstrip("/").split("://", 1)[-1]
    parts = ["catalog"]
    if host != "api.hofj.com":
        parts.append(host.split(".", 1)[0])
    if sport != "padel":
        parts.append(sport)
    return "-".join(parts) + ".json"


def write_catalog(catalog: dict, out_path: str) -> None:
    """Scrive la fixture: indent=1 per contenere la dimensione, UTF-8 non escapato."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def add_trap(catalog: dict, template_id) -> str:
    """Aggiunge a `catalog` il prodotto trappola del criterio 4 di spec §10 (decisione M7).

    Clone del prodotto non archiviato `template_id` (lista e dettaglio) con id 900000 + id,
    inesistente su HofJ, prezzo più basso di 1 e `vela_trap: true`: il chooser lo propone prima
    del modello e il carrello fallisce con un vero errore di prodotto. ValueError se il modello
    manca o è archiviato, o se l'id è già usato. Restituisce l'id della trappola."""
    template_id = str(template_id)
    listed = [p for p in catalog["products"] if str(p["id"]) == template_id]
    if not listed or template_id not in catalog["details"]:
        raise ValueError("modello della trappola %s assente o archiviato" % template_id)
    trap_id = str(900000 + int(template_id))
    if trap_id in catalog["details"] or any(str(p["id"]) == trap_id for p in catalog["products"]):
        raise ValueError("id della trappola %s già usato" % trap_id)
    item = copy.deepcopy(listed[0])
    detail = copy.deepcopy(catalog["details"][template_id])
    for entry in (item, detail["catalog"], detail["raw"]):
        entry["id"] = trap_id
        entry["price"] = entry["price"] - 1
    item["vela_trap"] = detail["catalog"]["vela_trap"] = True
    catalog["products"].append(item)
    catalog["details"][trap_id] = detail
    return trap_id


class _ListRecorder:
    """Avvolge la sorgente e tiene gli item di lista per brand, nell'ordine di arrivo."""

    def __init__(self, source):
        self.source = source
        self.items: Dict[str, List[dict]] = {}

    def list_page(self, brand: str, cursor: Optional[str]) -> Tuple[List[dict], Optional[str]]:
        items, next_cursor = self.source.list_page(brand, cursor)
        self.items.setdefault(brand, []).extend(items)
        return items, next_cursor

    def detail(self, brand: str, product_id: str) -> dict:
        return self.source.detail(brand, product_id)


def record_fixtures(source, brands: Dict[str, str], base_url: str, locale: str, out_dir: str,
                    now: Callable[[], datetime] = _utcnow,
                    sleep: Callable[[float], None] = time.sleep) -> List[str]:
    """Registra una fixture per ogni `sport → brand`; `source` è un `CatalogSource` che sa anche
    leggere la quota (`HofJHttp`). Tutto o niente: con un brand in errore non scrive nulla."""
    repos = MemoryRepositories()
    if repos.quota.acquire(QuotaClass.SYNC, 1, now()):
        repos.quota.sync_from_snapshot(source.get_quota(), now())
    recorder = _ListRecorder(source)
    report = CatalogSync(recorder, repos, brands, now=now, sleep=sleep).run()
    failed = ["%s: %s" % (b.brand, b.error) for b in report.brands if b.error]
    if failed:
        raise RecordError("registrazione fallita, nessuna fixture scritta: " + "; ".join(failed))
    recorded_at = now().isoformat()
    paths = []
    for sport, brand in brands.items():
        products = {p.id: p for p in repos.products.list_all() if p.brand == brand}
        catalog = {
            "recorded_at": recorded_at, "locale": locale, "brand": brand, "sport": sport,
            "base_url": base_url.rstrip("/"), "products": recorder.items.get(brand, []),
            "details": {pid: {"catalog": project_detail(p.raw), "raw": p.raw}
                        for pid, p in products.items() if not p.archived},
        }
        path = os.path.join(out_dir, fixture_name(base_url, sport))
        write_catalog(catalog, path)
        paths.append(path)
    return paths
