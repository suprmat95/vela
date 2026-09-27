"""Sonda di /accommodations per M22-a: 12 chiamate HofJ in circa 2,5 minuti, nessun pagamento.

A (1 camera): itinerario su un prodotto con `hotelSelection`, lettura, lista `recommended`, PATCH
su un altro hotel, rilettura del totale. B: lista su un prodotto con l'hotel fisso. C (2 camere):
itinerario, lista `distance`, PATCH, rilettura. Nessun `POST /v1/bookings`, nessuno Stripe; gli
itinerari restano orfani. Una chiamata ogni `GAP` secondi (la chiave è condivisa con Render); si
ferma al primo errore inatteso o 429.

Chiave da HOFJ_API_KEY, base da HOFJ_BASE_URL (default staging). Non stampa la chiave. Le
risposte grezze vanno in `--out` (default `probe-accommodations/`), una per chiamata.
"""
import argparse
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="probe-accommodations")
ap.add_argument("--brand", default="staging.weebora.com")
ap.add_argument("--locale", default="en")                 # locale della fixture di staging
ap.add_argument("--selectable", default="124")            # Magnificent Padel in Lanzarote
ap.add_argument("--selectable-date", default="2026-10-08")
ap.add_argument("--fixed", default="28")                  # Nueva Alcantara, hotelSelection=false
ap.add_argument("--fixed-date", default="2026-10-15")
ap.add_argument("--gap", type=float, default=12.0)
args = ap.parse_args()
base = os.environ.get("HOFJ_BASE_URL", "https://staging.api.hofj.com").rstrip("/")
key = os.environ["HOFJ_API_KEY"]
os.makedirs(args.out, exist_ok=True)
calls, last = [], [0.0]


def call(tag, method, path, body=None, cart=True, query=None):
    wait = last[0] + args.gap - time.time()
    if wait > 0:
        time.sleep(wait)
    q = dict(query or {})
    if cart:
        q.update(brand=args.brand, locale=args.locale)
    url = base + path + ("?" + urllib.parse.urlencode(q) if q else "")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + key, "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    ms = round((time.time() - t0) * 1000)
    last[0] = time.time()
    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        payload = raw.decode(errors="replace")
    calls.append({"n": len(calls) + 1, "tag": tag, "method": method, "path": path, "query": q,
                  "body": body, "status": status, "ms": ms})
    with open(os.path.join(args.out, "%02d-%s.json" % (len(calls), tag)), "w") as f:
        json.dump({"call": calls[-1], "response": payload}, f, indent=2, ensure_ascii=False)
    print("%2d %-10s %-5s %-55s %s %6d ms" % (len(calls), tag, method, path, status, ms), flush=True)
    if status in (401, 403, 429) or (status >= 500 and status != 502):
        raise SystemExit("fermo: %s" % status)
    return status, payload


def data(p):
    return p.get("data") if isinstance(p, dict) else None


def hotel(itin):
    a = (itin or {}).get("accommodation") or {}
    return {"id": a.get("id"), "title": a.get("title"), "rating": a.get("rating"),
            "rooms": a.get("rooms"), "totalPrice": a.get("totalPrice"),
            "checkout": (itin or {}).get("checkout"),
            "hotelSelection": (itin or {}).get("hotelSelection"),
            "allowAccommodationList": (itin or {}).get("allowAccommodationList")}


def pick(elements, current_id):
    """Primo hotel diverso dall'attuale, e la sua configurazione attiva (o la prima)."""
    for acc in elements or []:
        if str(acc.get("id")) == str(current_id):
            continue
        confs = acc.get("roomsConfiguration") or []
        if not confs:
            continue
        conf = next((c for c in confs if c.get("isActive")), confs[0])
        return acc, [r["id"] for r in conf.get("rooms", [])]
    return None, []


def summary(elements):
    return [{"id": a.get("id"), "title": a.get("title"), "rating": a.get("rating"),
             "guestRating": a.get("guestRating"), "reviewsCount": a.get("reviewsCount"),
             "isRecommended": a.get("isRecommended"), "totalPrice": a.get("totalPrice"),
             "confs": [{"price": c.get("price"), "isActive": c.get("isActive"),
                        "rooms": [(r.get("id"), r.get("numPax"), r.get("count"), r.get("numPaxValues"))
                                  for r in c.get("rooms", [])]} for c in a.get("roomsConfiguration") or []]}
            for a in elements or []]


def itinerary(product, start, rooms):
    pid = int(product) if product.isdigit() else product
    return {"productId": pid, "startDate": start, "adults": 2, "rooms": rooms, "currency": "EUR"}


findings = {}
print("host:", base.split("//")[-1], "brand:", args.brand, flush=True)
_, q = call("quota", "GET", "/v1/quota", cart=False)
findings["quota_before"] = data(q)

# A: 2 persone, 1 camera, prodotto con hotelSelection
s, p = call("A-create", "POST", "/v1/itineraries", itinerary(args.selectable, args.selectable_date, 1))
if s != 200:
    raise SystemExit("A: creazione fallita, mi fermo")
a_id = data(p)["itineraryId"]
_, p = call("A-itin", "GET", "/v1/itineraries/%s" % a_id)
findings["A_before"] = hotel(data(p))
_, p = call("A-list", "GET", "/v1/itineraries/%s/accommodations" % a_id,
            query={"startDate": args.selectable_date, "sortByValue": "recommended"})
elements = (data(p) or {}).get("elements")
findings["A_list"] = {"summary": summary(elements), "pagination": (data(p) or {}).get("pagination"),
                      "aggregate": (data(p) or {}).get("aggregate")}
acc, room_ids = pick(elements, findings["A_before"]["id"])
if acc:
    s, p = call("A-patch", "PATCH", "/v1/itineraries/%s/accommodations/%s" % (a_id, acc["id"]),
                {"roomIds": room_ids})
    findings["A_patch"] = {"accommodation": acc.get("id"), "roomIds": room_ids, "status": s, "response": p}
    _, p = call("A-reread", "GET", "/v1/itineraries/%s" % a_id)
    findings["A_after"] = hotel(data(p))

# B: prodotto con hotel fisso
s, p = call("B-create", "POST", "/v1/itineraries", itinerary(args.fixed, args.fixed_date, 1))
if s == 200:
    b_id = data(p)["itineraryId"]
    s, p = call("B-list", "GET", "/v1/itineraries/%s/accommodations" % b_id,
                query={"startDate": args.fixed_date, "sortByValue": "recommended"})
    findings["B_list"] = {"status": s, "summary": summary((data(p) or {}).get("elements")),
                          "response_if_error": p if s != 200 else None}

# C: 2 persone, 2 camere, stesso prodotto di A, lista per distanza
s, p = call("C-create", "POST", "/v1/itineraries", itinerary(args.selectable, args.selectable_date, 2))
if s == 200:
    c_id = data(p)["itineraryId"]
    _, p = call("C-list", "GET", "/v1/itineraries/%s/accommodations" % c_id,
                query={"startDate": args.selectable_date, "sortByValue": "distance"})
    elements = (data(p) or {}).get("elements")
    findings["C_list"] = {"summary": summary(elements)}
    acc, room_ids = pick(elements, findings.get("A_before", {}).get("id"))
    if acc:
        s, p = call("C-patch", "PATCH", "/v1/itineraries/%s/accommodations/%s" % (c_id, acc["id"]),
                    {"roomIds": room_ids})
        findings["C_patch"] = {"accommodation": acc.get("id"), "roomIds": room_ids, "status": s, "response": p}
        _, p = call("C-reread", "GET", "/v1/itineraries/%s" % c_id)
        findings["C_after"] = hotel(data(p))

findings["calls"] = calls
with open(os.path.join(args.out, "findings.json"), "w") as f:
    json.dump(findings, f, indent=2, ensure_ascii=False)
print("chiamate HofJ: %d, esiti in %s/findings.json" % (len(calls), args.out), flush=True)
