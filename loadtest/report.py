"""Report di un giro del load test (M13a): registro del finto HofJ + eventi dei viaggiatori +
statistiche di Locust → Markdown e JSON.

Le misure sulla quota vengono dal registro del finto, non dai log di Vela (seconda lettura §3.5).
Tempi dei viaggiatori in secondi dall'inizio dello scenario; il registro del finto è in secondi
epoch e si allinea con `epoch_start` della riga `run` degli eventi.

  python loadtest/report.py --calls loadtest/out/calls.jsonl \
      --events loadtest/out/run/travelers.jsonl --stats loadtest/out/run/locust_stats.csv \
      --label "50k puliti" --out loadtest/out/run/report
"""
import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from typing import Dict, Iterable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from loadtest.fake_hofj.log import max_in_window  # noqa: E402

USE_CASES = ("create_intent", "get_proposal", "reject_proposal", "accept_proposal",
             "get_order_status")
QUOTA_LINE = 108          # limite effettivo di Vela: 120 × 0,9
ITINERARY_CREATE = "POST /v1/itineraries"
BOOKING = "POST /v1/bookings"
PURCHASE_ENDPOINTS = (ITINERARY_CREATE, "GET /v1/itineraries/{id}")                 # M19: il link
BOOKING_ENDPOINTS = ("PUT /v1/itineraries/{id}/customer", "PUT /v1/itineraries/{id}/pax",
                     "GET /v1/itineraries/{id}/pax", BOOKING)                         # M19: dopo il pagamento
FAILED = {"failed", "booking_failed", "cancelled", "expired", "replaced"}


# --- lettura ------------------------------------------------------------------------------------

def read_jsonl(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def read_stats(path: str) -> Dict[str, dict]:
    """`<prefisso>_stats.csv` di Locust → {nome: {count, failures, p50, p95, p99}} (ms)."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("Name") in ("Aggregated", None):
                continue
            out[row["Name"]] = {"count": int(row["Request Count"]),
                                "failures": int(row["Failure Count"]),
                                "p50": _num(row.get("50%")), "p95": _num(row.get("95%")),
                                "p99": _num(row.get("99%"))}
    return out


def _num(text: Optional[str]) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


# --- misure pure --------------------------------------------------------------------------------

def percentile(values: Iterable[float], p: float) -> Optional[float]:
    """Percentile con il metodo del rango più vicino; None senza valori."""
    data = sorted(values)
    if not data:
        return None
    rank = max(1, math.ceil(p / 100 * len(data)))
    return data[rank - 1]


def quota_measures(calls: List[dict], start: float, end: float) -> dict:
    """Misure sul registro del finto nell'intervallo epoch [start, end)."""
    counted = [c for c in calls if c.get("counted")]
    before = [c for c in counted if c["t"] < start and c["origin"] == "vela"]
    during = [c for c in counted if start <= c["t"] < end]
    vela = [c for c in during if c["origin"] == "vela"]
    minutes = int(math.ceil((end - start) / 60))
    per_minute = []
    for m in range(minutes):
        lo, hi = start + m * 60, start + (m + 1) * 60
        in_minute = [c for c in during if lo <= c["t"] < hi]
        per_minute.append({
            "minute": m + 1,
            "vela": sum(1 for c in in_minute if c["origin"] == "vela"),
            "background": sum(1 for c in in_minute if c["origin"] == "background"),
            "status_429": sum(1 for c in in_minute if c["status"] == 429 and c["origin"] == "vela"),
            "itineraries": sum(1 for c in in_minute if c["endpoint"] == ITINERARY_CREATE
                               and c["origin"] == "vela"),
        })
    return {
        "calls_before_run": len(before),
        "calls_vela": len(vela),
        "max_in_60s_vela": max_in_window([c["t"] for c in vela]),
        "max_in_60s_total": max_in_window([c["t"] for c in during]),
        "status_429": sum(1 for c in vela if c["status"] == 429),
        "by_endpoint": dict(sorted(Counter(c["endpoint"] for c in vela).items())),
        "per_minute": per_minute,
    }


def booking_measures(calls: List[dict], end: float, grace: float = 60.0) -> dict:
    """Prenotazioni per `itineraryId` e itinerari orfani (creati e mai più toccati). Gli itinerari
    creati nell'ultimo minuto non contano come orfani: il job potrebbe non aver fatto il passo dopo."""
    posts = Counter(c["itinerary_id"] for c in calls
                    if c["endpoint"] == BOOKING and c.get("executed") and c["origin"] == "vela")
    created = {}
    touched = set()
    for c in calls:
        iid = c.get("itinerary_id")
        if not iid or c["origin"] != "vela":
            continue
        if c["endpoint"] == ITINERARY_CREATE and c.get("executed"):
            created[iid] = c["t"]
        else:
            touched.add(iid)
    orphans = [iid for iid, t in created.items() if iid not in touched and t < end - grace]
    return {"itineraries": len(created), "booked_itineraries": len(posts),
            "booking_posts_max_per_itinerary": max(posts.values(), default=0),
            "itineraries_booked_more_than_once": sum(1 for n in posts.values() if n > 1),
            "orphan_itineraries": len(orphans)}


def cost_measures(by_endpoint: Dict[str, int], links: int, booked: int) -> dict:
    """M19: chiamate del carrello per link e di cliente, pax e booking per itinerario prenotato.
    I carrelli in volo alla fine del giro contano senza link: il rapporto è per eccesso."""
    purchase = sum(by_endpoint.get(e, 0) for e in PURCHASE_ENDPOINTS)
    booking = sum(by_endpoint.get(e, 0) for e in BOOKING_ENDPOINTS)
    return {"purchase_calls": purchase, "booking_calls": booking,
            "calls_per_link": round(purchase / links, 2) if links else None,
            "calls_per_paid_order": round(booking / booked, 2) if booked else None}


def traveler_measures(travelers: List[dict], duration: float) -> dict:
    accepted = [t for t in travelers if "t_accept" in t]
    linked = [t for t in accepted if "t_link" in t]
    minutes = int(math.ceil(duration / 60))
    links_per_minute = [sum(1 for t in linked if m * 60 <= t["t_link"] < (m + 1) * 60)
                        for m in range(minutes)]
    gaps = [(t["t_link"] - t["t_accept"]) - t["wait_seconds"] for t in linked
            if t.get("wait_seconds") is not None]
    paid = [t for t in linked if "t_paid" in t]
    confirmed = [t for t in paid if "t_confirmed" in t]
    queue_age = []
    for m in range(1, minutes + 1):
        now = m * 60
        waiting = [now - t["t_accept"] for t in accepted
                   if t["t_accept"] <= now and t.get("t_link", math.inf) > now
                   and not (t.get("final") in FAILED and t.get("t_end", math.inf) <= now)]
        queue_age.append({"minute": m, "waiting": len(waiting),
                          "oldest_seconds": round(max(waiting), 1) if waiting else 0})
    finals = Counter(t.get("final") or "unknown" for t in travelers)
    return {
        "travelers": len(travelers),
        "accepted": len(accepted),
        "links": len(linked),
        "links_per_minute": links_per_minute,
        "paid": len(paid),
        "confirmed": len(confirmed),
        "paid_to_confirmed_p95": percentile((t["t_confirmed"] - t["t_paid"] for t in confirmed), 95),
        "paid_to_confirmed_max": max((t["t_confirmed"] - t["t_paid"] for t in confirmed), default=None),
        "wait_gap_p95": percentile(gaps, 95),
        "wait_gap_abs_p95": percentile((abs(g) for g in gaps), 95),
        "still_queued_at_end": sum(1 for t in accepted if "t_link" not in t
                                   and (t.get("final") or "").startswith("open")),
        "queue_age": queue_age,
        "finals": dict(sorted(finals.items())),
        "marco": _sentinel(travelers, "marco"),
        "anna": _sentinel(travelers, "anna"),
    }


def _sentinel(travelers: List[dict], role: str) -> Optional[dict]:
    t = next((t for t in travelers if t.get("role") == role), None)
    if t is None:
        return None
    keys = ("arrival", "proposal_ms", "t_accept", "position", "wait_seconds", "t_link", "t_paid",
            "t_confirmed", "final")
    out = {k: t.get(k) for k in keys}
    if t.get("t_paid") is not None and t.get("t_confirmed") is not None:
        out["paid_to_confirmed"] = round(t["t_confirmed"] - t["t_paid"], 1)
    out["confirmed_by_minute_7"] = t.get("t_confirmed") is not None and t["t_confirmed"] <= 420
    return out


def build(calls: List[dict], events: List[dict], stats: Dict[str, dict]) -> dict:
    run = next(e for e in events if e.get("type") == "run")
    travelers = [e for e in events if e.get("type") == "traveler"]
    duration = (run["arrival_minutes"] + run["tail_minutes"]) * 60
    start = run["epoch_start"]
    quota = quota_measures(calls, start, start + duration)
    bookings = booking_measures(calls, start + duration)
    people = traveler_measures(travelers, duration)
    return {"run": run, "quota": quota, "bookings": bookings, "travelers": people,
            "cost": cost_measures(quota["by_endpoint"], people["links"], bookings["booked_itineraries"]),
            "use_cases": {name: stats.get(name) for name in USE_CASES + ("replay_checkout",)}}


# --- Markdown -----------------------------------------------------------------------------------

def _fmt(value, digits=1) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return ("%%.%df" % digits) % value
    return str(value)


def markdown(report: dict, label: str) -> str:
    q, b, t, run = report["quota"], report["bookings"], report["travelers"], report["run"]
    lines = ["## %s" % label, "",
             "%d viaggiatori in %g minuti + %g di coda, seme %s." % (
                 run["travelers"], run["arrival_minutes"], run["tail_minutes"], run["seed"]), "",
             "| Misura | Valore |", "|---|---|",
             "| Massimo di chiamate Vela → HofJ in 60 s | %d (limite di Vela %d, di HofJ 120) |"
             % (q["max_in_60s_vela"], QUOTA_LINE),
             "| Massimo in 60 s con gli altri usi della chiave | %d |" % q["max_in_60s_total"],
             "| 429 ricevuti da Vela | %d |" % q["status_429"],
             "| Chiamate Vela nel giro (prima del giro: sync) | %d (%d) |"
             % (q["calls_vela"], q["calls_before_run"]),
             "| Accettazioni / link / pagati / confermati | %d / %d / %d / %d |"
             % (t["accepted"], t["links"], t["paid"], t["confirmed"]),
             "| Ancora in coda alla fine | %d |" % t["still_queued_at_end"],
             "| Pagamento → confermato, p95 / max (s) | %s / %s |"
             % (_fmt(t["paid_to_confirmed_p95"]), _fmt(t["paid_to_confirmed_max"])),
             "| Scarto attesa reale − dichiarata, p95 / p95 assoluto (s) | %s / %s |"
             % (_fmt(t["wait_gap_p95"]), _fmt(t["wait_gap_abs_p95"])),
             "| Itinerari creati / prenotati | %d / %d |" % (b["itineraries"], b["booked_itineraries"]),
             "| POST di booking per itinerario, massimo (itinerari con più di una) | %d (%d) |"
             % (b["booking_posts_max_per_itinerary"], b["itineraries_booked_more_than_once"]),
             "| Itinerari orfani | %d |" % b["orphan_itineraries"],
             "| Chiamate per link (carrello) / per ordine prenotato (cliente, pax, booking) | %s / %s |"
             % (_fmt(report["cost"]["calls_per_link"], 2), _fmt(report["cost"]["calls_per_paid_order"], 2)),
             ""]
    for role, name in (("marco", "Marco (accetta a 60 s)"), ("anna", "Anna (arriva al 60% della finestra)")):
        s = t.get(role)
        if s:
            lines.append("- **%s**: proposta %s ms, posizione %s, attesa dichiarata %s s, link a %s s, "
                         "pagato a %s s, confermato a %s s, esito `%s`; confermato entro il minuto 7: %s."
                         % (name, _fmt(s["proposal_ms"]), _fmt(s["position"]), _fmt(s["wait_seconds"]),
                            _fmt(s["t_link"]), _fmt(s["t_paid"]), _fmt(s["t_confirmed"]), s["final"],
                            "sì" if s["confirmed_by_minute_7"] else "no"))
    lines += ["", "| Caso d'uso | Richieste | Errori | p50 ms | p95 ms | p99 ms |",
              "|---|---|---|---|---|---|"]
    for name, s in report["use_cases"].items():
        if s:
            lines.append("| `%s` | %d | %d | %s | %s | %s |" % (name, s["count"], s["failures"],
                                                           _fmt(s["p50"], 0), _fmt(s["p95"], 0),
                                                           _fmt(s["p99"], 0)))
    lines += ["", "| Minuto | Chiamate Vela | 429 | Altri usi | Itinerari creati | Link | In coda | Più vecchio in coda (s) |",
              "|---|---|---|---|---|---|---|---|"]
    for m, age in zip(q["per_minute"], t["queue_age"]):
        links = t["links_per_minute"][m["minute"] - 1] if m["minute"] <= len(t["links_per_minute"]) else 0
        lines.append("| %d | %d | %d | %d | %d | %d | %d | %s |" % (
            m["minute"], m["vela"], m["status_429"], m["background"], m["itineraries"], links,
            age["waiting"], _fmt(age["oldest_seconds"], 0)))
    lines += ["", "Chiamate per endpoint: " + ", ".join("`%s` %d" % kv for kv in q["by_endpoint"].items()),
              "", "Esiti dei viaggiatori: " + ", ".join("`%s` %d" % kv for kv in t["finals"].items()), ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--calls", required=True, help="registro JSONL del finto HofJ")
    ap.add_argument("--events", required=True, help="eventi JSONL dei viaggiatori")
    ap.add_argument("--stats", required=True, help="<prefisso>_stats.csv di Locust")
    ap.add_argument("--label", default="giro")
    ap.add_argument("--out", help="prefisso dei file .md e .json (default: solo stdout)")
    args = ap.parse_args(argv)
    report = build(read_jsonl(args.calls), read_jsonl(args.events), read_stats(args.stats))
    text = markdown(report, args.label)
    if args.out:
        with open(args.out + ".md", "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(args.out + ".json", "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
