"""Sonda di M19 (domanda 10): il totale cambia dopo cliente e passeggeri? 5 chiamate HofJ.

1 `POST /v1/itineraries` (124 "Magnificent Padel in Lanzarote", 08/10, 2 adulti, 1 camera)
2 `GET /v1/itineraries/{id}`   totale subito dopo la creazione
3 `PUT /v1/itineraries/{id}/customer`
4 `PUT /v1/itineraries/{id}/pax` (`pax-1`, `pax-2`, i `refId` osservati in M5: niente `GET pax`)
5 `GET /v1/itineraries/{id}`   totale dopo cliente e passeggeri

Nessun `GET /v1/quota`, nessun pagamento, nessun `POST /v1/bookings`: l'itinerario resta orfano.
Una chiamata ogni `--gap` secondi (la chiave è condivisa con Render). Si ferma se la creazione
fallisce e a ogni 401/403/429/5xx; un 4xx su customer o pax non ferma la rilettura, che resta
dentro le 5 chiamate. `--dry-run` stampa il piano senza rete.

Chiave da HOFJ_API_KEY, base da HOFJ_BASE_URL (default staging). Non stampa la chiave. Le
risposte grezze vanno in `--out` (default `probe-m19/`), una per chiamata, più `findings.json`.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AMOUNTS = ("openAmount", "total", "originalTotal", "totalPrice")
CUSTOMER = {"firstName": "Vela", "lastName": "Probe", "email": "probe@example.com",
            "phone": "+390200000000",
            "address": {"street1": "Via del Prototipo 1", "postalCode": "20100", "city": "Milano",
                        "region": "MI", "countryCode": "IT"}}   # TravelerDefaults di Vela
PAX = [{"refId": "pax-1", "firstName": "Vela", "lastName": "Probe"},
       {"refId": "pax-2", "firstName": "Anna", "lastName": "Probe"}]
PLAN = ["POST /v1/itineraries", "GET  /v1/itineraries/{id}", "PUT  /v1/itineraries/{id}/customer",
        "PUT  /v1/itineraries/{id}/pax", "GET  /v1/itineraries/{id}"]


def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class Stop(Exception):
    pass


def amounts(payload):
    """Gli importi dell'itinerario come stringhe, così come arrivano da HofJ."""
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    data = data or {}
    checkout = data.get("checkout") or {}
    found = {name: (checkout.get(name) or {}).get("amount") for name in AMOUNTS[:3]}
    found["totalPrice"] = (data.get("totalPrice") or {}).get("amount")
    found["currency"] = (checkout.get("openAmount") or {}).get("currency")
    found["status"] = checkout.get("status")
    return found


def main(argv=None, env=None, opener=None, sleep=time.sleep, stdout=sys.stdout):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="probe-m19")
    ap.add_argument("--brand", default="staging.weebora.com")
    ap.add_argument("--locale", default="en")               # locale della fixture di staging
    ap.add_argument("--product", default="124")             # allowAccommodationList: false
    ap.add_argument("--date", default="2026-10-08")
    ap.add_argument("--gap", type=float, default=12.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    env = os.environ if env is None else env

    def say(*parts):
        print(*parts, file=stdout, flush=True)

    if args.dry_run:
        say("piano: %d chiamate su prodotto %s, %s, brand %s" % (len(PLAN), args.product, args.date, args.brand))
        for n, line in enumerate(PLAN, 1):
            say("%2d %s" % (n, line))
        return 0

    base = env.get("HOFJ_BASE_URL", "https://staging.api.hofj.com").rstrip("/")
    key = env["HOFJ_API_KEY"]
    opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout, context=_context()))
    os.makedirs(args.out, exist_ok=True)
    calls, last = [], [None]

    def call(tag, method, path, body=None):
        if len(calls) >= len(PLAN):
            raise Stop("oltre le %d chiamate dichiarate" % len(PLAN))
        if last[0] is not None:
            wait = last[0] + args.gap - time.time()
            if wait > 0:
                sleep(wait)
        url = base + path + "?" + urllib.parse.urlencode({"brand": args.brand, "locale": args.locale})
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + key, "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {})})
        t0 = time.time()
        try:
            with opener(req, timeout=30) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        ms = round((time.time() - t0) * 1000)
        last[0] = time.time()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode(errors="replace")
        calls.append({"n": len(calls) + 1, "tag": tag, "method": method, "path": path,
                      "body": body, "status": status, "ms": ms})
        with open(os.path.join(args.out, "%02d-%s.json" % (len(calls), tag)), "w") as f:
            json.dump({"call": calls[-1], "response": payload}, f, indent=2, ensure_ascii=False)
        say("%2d %-9s %-5s %-40s %s %6d ms" % (len(calls), tag, method, path, status, ms))
        if status in (401, 403, 429) or status >= 500:
            raise Stop("fermo: %s" % status)
        return status, payload

    findings = {"product": args.product, "date": args.date, "brand": args.brand}
    code = 0
    say("host:", base.split("//")[-1], "brand:", args.brand)
    try:
        pid = int(args.product) if args.product.isdigit() else args.product
        status, p = call("create", "POST", "/v1/itineraries", {
            "productId": pid, "startDate": args.date, "adults": 2, "rooms": 1, "currency": "EUR"})
        if status != 200:
            raise Stop("creazione fallita: %s" % status)
        iid = p["data"]["itineraryId"]
        findings["itineraryId"] = iid
        _, p = call("before", "GET", "/v1/itineraries/%s" % iid)
        findings["before"] = amounts(p)
        call("customer", "PUT", "/v1/itineraries/%s/customer" % iid, CUSTOMER)
        call("pax", "PUT", "/v1/itineraries/%s/pax" % iid, PAX)
        _, p = call("after", "GET", "/v1/itineraries/%s" % iid)
        findings["after"] = amounts(p)
        findings["changed"] = [k for k in AMOUNTS + ("currency",)
                               if findings["before"].get(k) != findings["after"].get(k)]
    except Stop as exc:
        findings["stopped"] = str(exc)
        say(str(exc))
        code = 1
    findings["calls"] = calls
    with open(os.path.join(args.out, "findings.json"), "w") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    say("chiamate HofJ: %d, esiti in %s/findings.json" % (len(calls), args.out))
    if "changed" in findings:
        say("importi cambiati dopo customer e pax:", ", ".join(findings["changed"]) or "nessuno")
    return code


if __name__ == "__main__":
    sys.exit(main())
