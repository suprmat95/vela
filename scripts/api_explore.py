#!/usr/bin/env python3
"""Esplora in sola lettura (GET) la House of Journeys API senza mai sforare la quota.

Uso:
  api_explore.py --out DIR fixed [--dry-run]           # chiamate fisse (quota, config, prime pagine, dettagli)
  api_explore.py --out DIR paginate ENTITY... [--max-pages N] [--dry-run]
  api_explore.py --out DIR quota                       # una sola chiamata a /v1/quota

La chiave viene letta SOLO dalla variabile d'ambiente API_BEAR_KEY e non viene mai
stampata né salvata. Ogni risposta viene salvata in DIR come JSON numerato, così ogni
endpoint viene chiamato al più una volta e la documentazione si scrive dai file.

Solo stdlib, compatibile con Python 3.7.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = os.environ.get("HOFJ_BASE_URL", "https://api.hofj.com")
KEY_ENV = "API_BEAR_KEY"
CAP_PER_WINDOW = 90       # richieste massime che ci concediamo per finestra (limite API: 120)
WINDOW_MARGIN_S = 2.0     # secondi di attesa oltre windowEndsAt prima di riprendere
LIST_ENTITIES = ("products", "categories", "destinations", "venues", "pages", "articles")
PAGE_LIMIT = 100          # massimo dichiarato dall'OpenAPI


class QuotaExceededError(RuntimeError):
    """Il server ha risposto 429: non deve mai accadere, ci fermiamo subito."""


class QuotaGuard:
    """Contatore locale che impedisce di superare il budget per finestra.

    Il budget viene sincronizzato con la risposta di GET /v1/quota:
    budget = min(remainingInWindow, CAP - usedInWindow). Quando arriva a zero,
    `wait_seconds()` dice quanto dormire (fino a windowEndsAt + margine) prima di
    risincronizzare con una nuova chiamata a /v1/quota.
    """

    def __init__(self, cap=CAP_PER_WINDOW, margin=WINDOW_MARGIN_S, now=time.time):
        self.cap = cap
        self.margin = margin
        self.now = now
        self.budget = 0
        self.window_ends_at = None
        self.total_requests = 0
        self.synced = False

    def sync(self, quota_data):
        used = int(quota_data.get("usedInWindow", 0))
        remaining = int(quota_data.get("remainingInWindow", 0))
        self.budget = max(0, min(remaining, self.cap - used))
        self.window_ends_at = parse_iso(quota_data.get("windowEndsAt"))
        self.synced = True

    def can_request(self):
        return self.synced and self.budget > 0

    def wait_seconds(self):
        """Secondi da attendere prima che la finestra corrente si chiuda."""
        if self.window_ends_at is None:
            return 60.0 + self.margin
        return max(0.0, self.window_ends_at - self.now() + self.margin)

    def record(self):
        self.budget -= 1
        self.total_requests += 1


def parse_iso(value):
    """Converte un timestamp ISO-8601 (con Z) in epoch. None se assente o malformato."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None


def safe_name(path, params):
    name = re.sub(r"[^A-Za-z0-9]+", "_", path.strip("/"))
    if params:
        name += "__" + re.sub(r"[^A-Za-z0-9=,]+", "_", urllib.parse.urlencode(params))
    return name[:150]


class Client:
    """GET-only. Salva ogni risposta in out_dir; non scrive mai la chiave."""

    def __init__(self, out_dir, guard, api_key, base_url=BASE_URL, opener=None,
                 sleep=time.sleep, log=print, dry_run=False):
        self.out_dir = out_dir
        self.guard = guard
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self.log = log
        self.dry_run = dry_run
        self.planned = []
        os.makedirs(out_dir, exist_ok=True)
        self.index = self._next_index()

    def _next_index(self):
        nums = [int(f[:3]) for f in os.listdir(self.out_dir) if re.match(r"^\d{3}-", f)]
        return (max(nums) + 1) if nums else 1

    def get(self, path, params=None, auth=True):
        """Esegue una GET. Le chiamate autenticate consumano quota e passano dalla guardia."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        if self.dry_run:
            self.planned.append((path, params, auth))
            self.log("[dry-run] GET %s %s" % (path, params or ""))
            return None
        if auth:
            self._ensure_budget()
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        if auth:
            req.add_header("Authorization", "Bearer " + self.api_key)
        started = time.time()
        try:
            resp = self.opener(req, timeout=60)
            status, headers, raw = resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            status, headers, raw = e.code, dict(e.headers), e.read()
        if auth:
            self.guard.record()
        body = self._decode(raw)
        record = self._save(path, params, auth, status, headers, body, started)
        self.log("GET %s %s -> %d | budget locale %d | tot %d" % (
            path, params or "", status, self.guard.budget, self.guard.total_requests))
        if status == 429:
            raise QuotaExceededError("429 su %s: %s" % (path, json.dumps(body)[:300]))
        return record

    def _ensure_budget(self):
        if not self.guard.synced:
            self._sync_quota()
        if not self.guard.can_request():
            wait = self.guard.wait_seconds()
            self.log("budget esaurito: attendo %.0fs fino a fine finestra" % wait)
            self.sleep(wait)
            self._sync_quota()
            if not self.guard.can_request():
                raise QuotaExceededError("nessun budget dopo la risincronizzazione")

    def _sync_quota(self):
        """Chiama /v1/quota (consuma 1) e sincronizza la guardia."""
        # bypass della guardia: la chiamata di sync è l'unica ammessa senza budget
        self.guard.synced = True
        self.guard.budget = max(self.guard.budget, 1)
        rec = self.get("/v1/quota")
        if rec["status"] != 200 or not isinstance(rec["body"], dict):
            raise RuntimeError("quota non leggibile: %s" % rec["status"])
        self.guard.sync(rec["body"].get("data", {}))
        self.log("quota: %s" % json.dumps(rec["body"].get("data")))

    @staticmethod
    def _decode(raw):
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {"_raw": raw.decode("utf-8", "replace")[:5000]}

    def _save(self, path, params, auth, status, headers, body, started):
        headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        record = {
            "index": self.index, "method": "GET", "path": path, "params": params,
            "authenticated": auth, "status": status, "headers": headers, "body": body,
            "requestedAt": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "elapsedMs": int((time.time() - started) * 1000),
        }
        fname = "%03d-GET-%s.json" % (self.index, safe_name(path, params))
        with open(os.path.join(self.out_dir, fname), "w") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
        self.index += 1
        return record


# --------------------------------------------------------------------------- fasi

def first_item(record):
    body = record["body"] if record else None
    data = body.get("data") if isinstance(body, dict) else None
    return data[0] if isinstance(data, list) and data else None


def phase_fixed(client):
    """Chiamate fisse: pubbliche, config, prime pagine, dettagli, casi limite."""
    client.get("/health", auth=False)
    client.get("/v1/quota")
    channels = client.get("/v1/distribution-channels")
    client.get("/v1/locales")

    first_pages = {}
    for ent in LIST_ENTITIES:
        first_pages[ent] = client.get("/v1/" + ent, {"limit": PAGE_LIMIT})

    # dettagli: un id per entità, preso dalla prima pagina
    for ent in LIST_ENTITIES:
        item = first_item(first_pages[ent])
        if item and item.get("id") is not None:
            client.get("/v1/%s/%s" % (ent, item["id"]))
    product = first_item(first_pages["products"])
    if product and product.get("id") is not None:
        ext = client.get("/v1/products/%s" % product["id"], {"extended": "true"})
        detail = ext["body"].get("data", {}) if ext and isinstance(ext["body"], dict) else {}
        detail = detail if isinstance(detail, dict) else {}
        if detail.get("tripCode"):
            client.get("/v1/products/tripcode/%s" % detail["tripCode"])
        if detail.get("providerID"):
            client.get("/v1/products/providerid/%s" % detail["providerID"])

    # casi limite: validazione parametri e filtri
    client.get("/v1/products", {"limit": PAGE_LIMIT + 1})
    client.get("/v1/products", {"limit": 1, "brand": "brand-inesistente"})
    client.get("/v1/products", {"limit": 1, "locale": "xx"})
    channel = first_item(channels)
    if channel and channel.get("id") is not None:
        client.get("/v1/products", {"limit": 1, "channelIds": channel["id"]})
        client.get("/v1/categories", {"limit": 1, "channelIds": channel["id"]})
    client.get("/v1/products/id-inesistente")


def phase_paginate(client, entities, max_pages):
    """Segue meta.nextCursor a partire dall'ultima pagina salvata di ogni entità."""
    for ent in entities:
        cursor, pages = last_cursor(client.out_dir, ent)
        if cursor is None:
            client.log("%s: nessun cursore da seguire (%d pagine salvate)" % (ent, pages))
            continue
        while cursor and pages < max_pages:
            rec = client.get("/v1/" + ent, {"limit": PAGE_LIMIT, "cursor": cursor})
            pages += 1
            if rec is None:      # dry-run
                break
            cursor = (rec["body"].get("meta") or {}).get("nextCursor") \
                if isinstance(rec["body"], dict) else None
        client.log("%s: %d pagine, cursore finale %r" % (ent, pages, cursor))


def last_cursor(out_dir, entity):
    """Ultimo nextCursor per le pagine (limit=100, senza filtri) di una entità."""
    cursor, pages = None, 0
    for rec in load_records(out_dir):
        p = rec["params"]
        if rec["path"] == "/v1/" + entity and p.get("limit") == PAGE_LIMIT \
                and set(p) <= {"limit", "cursor"} and rec["status"] == 200:
            pages += 1
            cursor = (rec["body"].get("meta") or {}).get("nextCursor")
    return cursor, pages


def load_records(out_dir):
    for f in sorted(os.listdir(out_dir)):
        if re.match(r"^\d{3}-GET-", f):
            with open(os.path.join(out_dir, f)) as fh:
                yield json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="cartella dove salvare le risposte")
    ap.add_argument("--dry-run", action="store_true", help="stampa le chiamate senza eseguirle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fixed")
    pg = sub.add_parser("paginate")
    pg.add_argument("entities", nargs="+", choices=LIST_ENTITIES)
    pg.add_argument("--max-pages", type=int, default=50)
    sub.add_parser("quota")
    args = ap.parse_args(argv)

    api_key = os.environ.get(KEY_ENV)
    if not api_key and not args.dry_run:
        sys.exit("variabile d'ambiente %s assente" % KEY_ENV)

    client = Client(args.out, QuotaGuard(), api_key or "", dry_run=args.dry_run)
    try:
        if args.cmd == "fixed":
            phase_fixed(client)
        elif args.cmd == "paginate":
            phase_paginate(client, args.entities, args.max_pages)
        elif args.cmd == "quota":
            client.get("/v1/quota")
    except QuotaExceededError as e:
        sys.exit("STOP: %s" % e)
    if args.dry_run:
        auth_calls = sum(1 for _, _, a in client.planned if a)
        print("chiamate pianificate: %d (autenticate: %d, più 1 sync quota se necessario)"
              % (len(client.planned), auth_calls))
    else:
        print("richieste autenticate eseguite: %d" % client.guard.total_requests)


if __name__ == "__main__":
    main()
