"""Sonda della finestra di quota HofJ: 6 chiamate a GET /v1/quota, circa 2 minuti.

Distingue finestra scorrevole, fissa ancorata alla prima richiesta e fissa a griglia.
Chiave da HOFJ_API_KEY, base da HOFJ_BASE_URL (default staging). Non stampa la chiave.
"""
import json, os, ssl, time, urllib.request
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()
from datetime import datetime, timezone
base = os.environ.get("HOFJ_BASE_URL", "https://staging.api.hofj.com").rstrip("/")
key = os.environ["HOFJ_API_KEY"]
def iso(s): return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
def q(tag):
    t = time.time()
    req = urllib.request.Request(base + "/v1/quota", headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as r:
            d = json.load(r)["data"]; hdr = {k:v for k,v in r.headers.items() if "rate" in k.lower() or "retry" in k.lower()}
    except urllib.error.HTTPError as e:
        print(tag, "HTTP", e.code); return None
    print("%-8s local=%.1f used=%s start=%s end=%s hdr=%s" % (tag, t % 1000, d["usedInWindow"], d["windowStartedAt"][11:23], d["windowEndsAt"][11:23], hdr), flush=True)
    return d
print("host:", base.split("//")[-1], flush=True)
d = q("step0")
time.sleep(max(0, iso(d["windowEndsAt"]) - time.time()) + 3)
a = q("A_fresh"); S = iso(a["windowStartedAt"])
time.sleep(max(0, S + 50 - time.time()))
for i in range(3): q("B_%d@50" % i)
time.sleep(max(0, S + 63 - time.time()))
q("Z@63")
