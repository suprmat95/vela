"""Sonda di M19 (domanda 10, seconda metà): HofJ accetta cliente e passeggeri dopo il pagamento?

6 chiamate HofJ staging e 1 Stripe in modalità test, nell'ordine del flusso di M19:

1 `POST /v1/itineraries` (124, 08/10, 2 adulti, 1 camera)
2 `GET /v1/itineraries/{id}`                       `openAmount` da pagare
3 Stripe `POST /v1/payment_intents` confermato con `pm_card_visa`: importo `openAmount`,
  `metadata.checkoutRefId` = itinerario, come il PaymentIntent del link di Vela
4 `PUT .../customer`   dopo il pagamento
5 `PUT .../pax`        dopo il pagamento (`pax-1`, `pax-2`: differenza #36)
6 `GET /v1/itineraries/{id}`                       totale e stato dopo pagamento e `PUT`
7 `POST /v1/bookings` con `paymentIntentId` e `paymentStatus`

Vela paga con una Checkout Session, che non si completa via API: il PaymentIntent diretto con
gli stessi metadata è l'approssimazione dichiarata.

Rifiuta di partire senza una chiave Stripe `sk_test_`/`rk_test_` o con un host HofJ che non è
staging. Si ferma a ogni 401/403/429/5xx; se il pagamento non è `succeeded` si ferma prima dei
`PUT`; se un `PUT` è rifiutato (è l'esito cercato) si ferma prima del booking. `--dry-run` stampa
il piano senza rete. Chiavi da HOFJ_API_KEY e STRIPE_SECRET_KEY, mai stampate. Risposte grezze
in `--out` (default `probe-m19-paid/`), più `findings.json`.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from m19_probe import AMOUNTS, CUSTOMER, PAX, Stop, _context, amounts

STRIPE = "https://api.stripe.com"
PLAN = ["HofJ   POST /v1/itineraries", "HofJ   GET  /v1/itineraries/{id}",
        "Stripe POST /v1/payment_intents (test, pm_card_visa, confirm)",
        "HofJ   PUT  /v1/itineraries/{id}/customer", "HofJ   PUT  /v1/itineraries/{id}/pax",
        "HofJ   GET  /v1/itineraries/{id}", "HofJ   POST /v1/bookings"]


class Rejected(Exception):
    def __init__(self, step, status):
        super().__init__("%s rifiutato dopo il pagamento: %s" % (step, status))
        self.step, self.status = step, status


def main(argv=None, env=None, opener=None, sleep=time.sleep, stdout=sys.stdout):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="probe-m19-paid")
    ap.add_argument("--brand", default="staging.weebora.com")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--product", default="124")
    ap.add_argument("--date", default="2026-10-08")
    ap.add_argument("--gap", type=float, default=12.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    env = os.environ if env is None else env

    def say(*parts):
        print(*parts, file=stdout, flush=True)

    if args.dry_run:
        say("piano: %d chiamate (6 HofJ, 1 Stripe test) su prodotto %s, %s" % (len(PLAN), args.product, args.date))
        for n, line in enumerate(PLAN, 1):
            say("%2d %s" % (n, line))
        return 0

    base = env.get("HOFJ_BASE_URL", "https://staging.api.hofj.com").rstrip("/")
    stripe_key = env.get("STRIPE_SECRET_KEY", "")
    if urllib.parse.urlsplit(base).netloc != "staging.api.hofj.com":
        say("rifiuto: host HofJ diverso da staging")
        return 2
    if not stripe_key.startswith(("sk_test_", "rk_test_")):
        say("rifiuto: la chiave Stripe non è una chiave segreta di test")
        return 2
    hofj_key = env["HOFJ_API_KEY"]
    opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout, context=_context()))
    os.makedirs(args.out, exist_ok=True)
    calls, last = [], [None]

    def send(tag, req, record):
        if len(calls) >= len(PLAN):
            raise Stop("oltre le %d chiamate dichiarate" % len(PLAN))
        if last[0] is not None:
            wait = last[0] + args.gap - time.time()
            if wait > 0:
                sleep(wait)
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
        calls.append({"n": len(calls) + 1, "tag": tag, **record, "status": status, "ms": ms})
        with open(os.path.join(args.out, "%02d-%s.json" % (len(calls), tag)), "w") as f:
            json.dump({"call": calls[-1], "response": payload}, f, indent=2, ensure_ascii=False)
        say("%2d %-9s %-5s %-42s %s %6d ms" % (len(calls), tag, record["method"], record["path"], status, ms))
        if status in (401, 403, 429) or status >= 500:
            raise Stop("fermo: %s" % status)
        return status, payload

    def hofj(tag, method, path, body=None):
        url = base + path + "?" + urllib.parse.urlencode({"brand": args.brand, "locale": args.locale})
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + hofj_key, "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {})})
        return send(tag, req, {"service": "hofj", "method": method, "path": path, "body": body})

    def payment_intent(iid, amount):
        form = {"amount": str(int(Decimal(amount) * 100)), "currency": "eur", "confirm": "true",
                "payment_method": "pm_card_visa", "payment_method_types[]": "card",
                "metadata[checkoutRefId]": iid, "metadata[itinerary_id]": iid,
                "metadata[source]": "vela-m19-probe"}
        req = urllib.request.Request(STRIPE + "/v1/payment_intents", method="POST",
                                     data=urllib.parse.urlencode(form).encode(), headers={
            "Authorization": "Bearer " + stripe_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Idempotency-Key": "vela-m19-paid-probe-" + iid})
        return send("intent", req, {"service": "stripe", "method": "POST",
                                    "path": "/v1/payment_intents", "body": form})

    findings = {"product": args.product, "date": args.date, "brand": args.brand}
    code = 0
    say("host:", base.split("//")[-1], "brand:", args.brand, "stripe: test")
    try:
        pid = int(args.product) if args.product.isdigit() else args.product
        status, p = hofj("create", "POST", "/v1/itineraries", {
            "productId": pid, "startDate": args.date, "adults": 2, "rooms": 1, "currency": "EUR"})
        if status != 200:
            raise Stop("creazione fallita: %s" % status)
        iid = p["data"]["itineraryId"]
        findings["itineraryId"] = iid
        _, p = hofj("before", "GET", "/v1/itineraries/%s" % iid)
        findings["before"] = amounts(p)
        status, intent = payment_intent(iid, findings["before"]["openAmount"])
        intent = intent if isinstance(intent, dict) else {}
        findings["payment"] = {k: intent.get(k) for k in ("id", "status", "amount", "currency", "livemode")}
        if status != 200 or intent.get("status") != "succeeded" or intent.get("livemode"):
            raise Stop("pagamento non riuscito: %s %s" % (status, intent.get("status")))
        for step, path, body in (("customer", "/customer", CUSTOMER), ("pax", "/pax", PAX)):
            status, _ = hofj(step, "PUT", "/v1/itineraries/%s%s" % (iid, path), body)
            if status != 200:
                raise Rejected(step, status)
        _, p = hofj("after", "GET", "/v1/itineraries/%s" % iid)
        findings["after"] = amounts(p)
        findings["changed"] = [k for k in AMOUNTS + ("currency", "status")
                               if findings["before"].get(k) != findings["after"].get(k)]
        status, p = hofj("booking", "POST", "/v1/bookings", {
            "itineraryId": iid, "paymentType": "full",
            "paymentIntentId": intent["id"], "paymentStatus": "succeeded"})
        findings["booking"] = p.get("data") if isinstance(p, dict) else None
        findings["booking_status"] = status
        if status != 200:
            code = 1
    except Rejected as exc:
        findings["rejected"] = {"step": exc.step, "status": exc.status}
        say(str(exc))
        code = 1
    except Stop as exc:
        findings["stopped"] = str(exc)
        say(str(exc))
        code = 1
    findings["calls"] = calls
    with open(os.path.join(args.out, "findings.json"), "w") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    say("chiamate: %d, esiti in %s/findings.json" % (len(calls), args.out))
    if "changed" in findings:
        say("PUT dopo il pagamento accettati; cambiati:", ", ".join(findings["changed"]) or "nessuno",
            "| booking:", findings.get("booking_status"), findings.get("booking"))
    return code


if __name__ == "__main__":
    sys.exit(main())
