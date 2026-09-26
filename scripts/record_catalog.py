#!/usr/bin/env python3
"""Registra fixtures/catalog.json dalla House of Journeys API (locale `it` di default).

Uso:
  record_catalog.py --raw-dir DIR --dry-run     # stampa le chiamate previste, nessuna rete
  record_catalog.py --raw-dir DIR               # registra in DIR (nuova o vuota), scrive la fixture
  record_catalog.py --raw-dir DIR --build-only  # ricostruisce la fixture da DIR senza chiamate

`--trap-from ID` aggiunge il prodotto trappola del criterio 4 (M7), vedi add_trap.
`--locale en` registra (o ricostruisce) un altro locale: su staging i prodotti funzionano solo
in `en` (M7). L'host è `HOFJ_BASE_URL` e finisce nel `base_url` della fixture.

La chiave viene letta SOLO dalle variabili d'ambiente HOFJ_API_KEY (o API_BEAR_KEY) e non
viene mai stampata né salvata. DIR sta FUORI dal repository: contiene le risposte grezze
salvate da api_explore.Client, così la fixture si può ricostruire senza consumare quota.

Solo stdlib, compatibile con Python 3.7.
"""
import argparse
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_explore  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from vela.domain.catalog import project_detail, strip_media  # noqa: E402,F401

LOCALE = "it"
PAGE_LIMIT = api_explore.PAGE_LIMIT
KEY_ENVS = ("HOFJ_API_KEY", "API_BEAR_KEY")
BRAND_ENV = "HOFJ_BRAND"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures",
                           "catalog.json")
EXPECTED_TOTAL = 123   # docs/api/counts.md (locale en): stima usata dal dry-run
EXPECTED_ACTIVE = 92
class BuildError(RuntimeError):
    """La cartella grezza non basta a costruire una fixture completa."""


def detail_id(record):
    """Id del prodotto se il record è un dettaglio esteso riuscito, altrimenti None."""
    match = re.match(r"^/v1/products/([^/]+)$", record["path"])
    if match and record["params"].get("extended") == "true" and record["status"] == 200:
        return match.group(1)
    return None


def build_catalog(raw_dir, locale=LOCALE, brand=None):
    """Assembla la fixture dai record salvati da api_explore.Client in `raw_dir`.

    Lista: tutti gli item (anche archiviati), l'ultimo record vince a parità di id.
    Dettagli: solo i prodotti non archiviati; se ne manca uno solleva BuildError.
    Il `brand` della fixture è quello letto da `params["brand"]` delle pagine di
    lista registrate (path /v1/products, status 200, locale corrispondente), non
    l'argomento `brand`: se le pagine registrano brand diversi tra loro solleva
    BuildError. L'argomento `brand`, se non None, è solo un controllo incrociato:
    se differisce da quello registrato solleva BuildError.
    """
    if not os.path.isdir(raw_dir):
        raise BuildError("cartella grezza inesistente: %s" % raw_dir)
    products, details, stamps, brands = {}, {}, [], set()
    for record in api_explore.load_records(raw_dir):
        body = record["body"] if isinstance(record["body"], dict) else {}
        if record["params"].get("locale") != locale:
            continue
        if record["path"] == "/v1/products" and record["status"] == 200:
            for product in body.get("data") or []:
                products[str(product["id"])] = product
            stamps.append(record["requestedAt"])
            brands.add(record["params"].get("brand"))
        pid = detail_id(record)
        if pid and isinstance(body.get("data"), dict):
            details[pid] = body["data"]
            stamps.append(record["requestedAt"])
    if len(brands) > 1:
        raise BuildError("brand incoerente tra le pagine registrate: %s"
                         % ", ".join(repr(b) for b in sorted(brands, key=lambda b: b or "")))
    if not products:
        raise BuildError("nessuna pagina di /v1/products (locale %s) in %s" % (locale, raw_dir))
    active = [pid for pid, product in products.items() if not product.get("archived")]
    missing = [pid for pid in active if pid not in details]
    if missing:
        raise BuildError("dettaglio mancante per %d prodotti non archiviati: %s"
                         % (len(missing), ", ".join(missing)))
    recorded_brand = next(iter(brands)) if brands else None
    if brand is not None and brand != recorded_brand:
        raise BuildError("brand %r diverso da quello registrato %r" % (brand, recorded_brand))
    return {
        "recorded_at": max(stamps),
        "locale": locale,
        "brand": recorded_brand,
        "base_url": api_explore.BASE_URL,
        "products": list(products.values()),
        "details": {pid: {"catalog": project_detail(details[pid]),
                          "raw": strip_media(details[pid])} for pid in active},
    }


def add_trap(catalog, template_id):
    """Aggiunge a `catalog` il prodotto trappola del criterio 4 di spec §10 (decisione M7).

    Clone del prodotto non archiviato `template_id` (lista e dettaglio) con id
    900000 + id, inesistente su HofJ, prezzo più basso di 1 e `vela_trap: true`: il chooser
    lo propone prima del modello e il carrello fallisce con un vero errore di prodotto.
    Solleva BuildError se il modello manca o è archiviato, o se l'id è già usato.
    """
    template_id = str(template_id)
    listed = [p for p in catalog["products"] if str(p["id"]) == template_id]
    if not listed or template_id not in catalog["details"]:
        raise BuildError("modello della trappola %s assente o archiviato" % template_id)
    trap_id = str(900000 + int(template_id))
    if trap_id in catalog["details"] or any(str(p["id"]) == trap_id for p in catalog["products"]):
        raise BuildError("id della trappola %s già usato" % trap_id)
    item = copy.deepcopy(listed[0])
    detail = copy.deepcopy(catalog["details"][template_id])
    for entry in (item, detail["catalog"], detail["raw"]):
        entry["id"] = trap_id
        entry["price"] = entry["price"] - 1
    item["vela_trap"] = detail["catalog"]["vela_trap"] = True
    catalog["products"].append(item)
    catalog["details"][trap_id] = detail
    return trap_id


def write_catalog(catalog, out_path):
    """Scrive la fixture: indent=1 per contenere la dimensione, UTF-8 non escapato."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def record(client, locale=LOCALE, brand=None, expected=(EXPECTED_TOTAL, EXPECTED_ACTIVE)):
    """Scarica la lista paginata e il dettaglio esteso dei prodotti non archiviati.

    In dry-run non conosce i numeri reali: pianifica dalle stime `expected`
    (prodotti totali, non archiviati) e restituisce None. Un dettaglio che fallisce
    non ferma il giro: sarà build_catalog a segnalare gli id mancanti.
    """
    if client.dry_run:
        total, active = expected
        pages = max(1, -(-total // PAGE_LIMIT))
        for n in range(pages):
            client.get("/v1/products", {"limit": PAGE_LIMIT, "locale": locale, "brand": brand,
                                        "cursor": "pagina-%d" % (n + 1) if n else None})
        for _ in range(active):
            client.get("/v1/products/{id}", {"extended": "true", "locale": locale, "brand": brand})
        return None

    cursor, products, seen_cursors = None, [], set()
    while True:
        page = client.get("/v1/products", {"limit": PAGE_LIMIT, "locale": locale,
                                           "brand": brand, "cursor": cursor})
        if page["status"] != 200:
            raise RuntimeError("lista prodotti: HTTP %d %s" % (page["status"],
                                                               json.dumps(page["body"])[:300]))
        products.extend(page["body"].get("data") or [])
        cursor = (page["body"].get("meta") or {}).get("nextCursor")
        if not cursor:
            break
        if cursor in seen_cursors:
            raise RuntimeError("cursore ripetuto: %r" % cursor)
        seen_cursors.add(cursor)
    active = [p for p in products if not p.get("archived")]
    client.log("%d prodotti in lista, %d non archiviati: scarico i dettagli"
               % (len(products), len(active)))
    for product in active:
        client.get("/v1/products/%s" % product["id"],
                   {"extended": "true", "locale": locale, "brand": brand})
    return products


def call_plan(n_calls, cap=api_explore.CAP_PER_WINDOW):
    """(finestre da 60 s, chiamate autenticate totali) per n_calls, contando un sync
    di /v1/quota per finestra: ogni finestra ospita al più cap - 1 chiamate utili."""
    windows = max(1, -(-n_calls // (cap - 1)))
    return windows, n_calls + windows


def expected_counts(out_path):
    """Stime per il dry-run: dalla fixture esistente se c'è, altrimenti da docs/api/counts.md."""
    try:
        with open(out_path, encoding="utf-8") as fh:
            catalog = json.load(fh)
        return len(catalog["products"]), len(catalog["details"])
    except (OSError, ValueError, KeyError, TypeError):
        return EXPECTED_TOTAL, EXPECTED_ACTIVE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw-dir", required=True,
                    help="cartella FUORI dal repo per le risposte grezze (nuova o vuota)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="fixture da scrivere (default fixtures/catalog.json)")
    ap.add_argument("--locale", default=LOCALE,
                    help="locale da registrare e da leggere in --raw-dir (default it)")
    ap.add_argument("--trap-from", metavar="ID",
                    help="aggiunge il prodotto trappola clonato da ID (criterio 4, M7)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="stampa le chiamate previste senza eseguirle")
    mode.add_argument("--build-only", action="store_true",
                      help="ricostruisce la fixture da --raw-dir senza chiamate")
    args = ap.parse_args(argv)
    brand = os.environ.get(BRAND_ENV) or None

    if not args.build_only:
        if not args.dry_run and os.path.isdir(args.raw_dir) and os.listdir(args.raw_dir):
            sys.exit("--raw-dir %s non è vuota: usa una cartella nuova o --build-only"
                     % args.raw_dir)
        api_key = next((os.environ[k] for k in KEY_ENVS if os.environ.get(k)), None)
        if not api_key and not args.dry_run:
            sys.exit("variabile d'ambiente %s assente" % " o ".join(KEY_ENVS))
        client = api_explore.Client(args.raw_dir, api_explore.QuotaGuard(), api_key or "",
                                    dry_run=args.dry_run)
        if args.dry_run:
            total, active = expected_counts(args.out)
            record(client, locale=args.locale, brand=brand, expected=(total, active))
            lists = sum(1 for path, _, _ in client.planned if path == "/v1/products")
            details = len(client.planned) - lists
            windows, calls = call_plan(len(client.planned))
            print("chiamate previste: %d liste + %d dettagli + %d sync quota = %d autenticate, "
                  "in %d finestre da 60 s (stima: %d prodotti, %d non archiviati)"
                  % (lists, details, windows, calls, windows, total, active))
            return
        try:
            record(client, locale=args.locale, brand=brand)
        except (RuntimeError, OSError) as e:   # QuotaExceededError, lista fallita o errore di rete
            sys.exit("STOP: %s (risposte parziali in %s)" % (e, args.raw_dir))
        print("richieste autenticate eseguite: %d" % client.guard.total_requests)

    try:
        catalog = build_catalog(args.raw_dir, locale=args.locale, brand=brand)
        if args.trap_from:
            print("prodotto trappola: %s" % add_trap(catalog, args.trap_from))
    except BuildError as e:
        sys.exit("fixture non scritta: %s" % e)
    write_catalog(catalog, args.out)
    print("scritta %s: %d prodotti, %d dettagli, %d byte"
          % (args.out, len(catalog["products"]), len(catalog["details"]),
             os.path.getsize(args.out)))


if __name__ == "__main__":
    main()
