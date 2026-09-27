"""Un giro del load test (M13a), il comando del servizio compose `locust`.

1. aspetta che Vela risponda con tutto il catalogo (caricato al boot dalle fixture dei brand);
2. lancia Locust headless (`loadtest/locustfile.py`) contro Vela;
3. copia il registro del finto e le sue statistiche nella cartella del giro e scrive il report.

  docker compose run --rm locust --travelers 10000 --label 10k --duration 10

`--duration` (minuti, default 10) è la durata dell'intero giro: 2/3 di arrivi e 1/3 di coda, oppure
la divisione data con `--arrival-minutes`/`--tail-minutes`, che insieme non la superano.

Solo reti del compose (`vela`, `fake-hofj`): nessuna chiamata a HofJ né a Stripe.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, List, Optional, Tuple

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from loadtest import report  # noqa: E402

FIXTURES = os.path.join(ROOT, "fixtures")
DEFAULT_BRANDS = "weebora.com,terrarossa.com"


def expected_products(brands: List[str], fixtures_dir: str = FIXTURES) -> int:
    """Prodotti attivi nelle fixture dei brand: quanti ne carica Vela al boot."""
    total = 0
    for name in sorted(os.listdir(fixtures_dir)):
        if not (name.startswith("catalog") and name.endswith(".json")):
            continue
        with open(os.path.join(fixtures_dir, name), encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("brand") in brands:
            total += sum(1 for p in data.get("products") or [] if not p.get("archived"))
    return total


def wait_for_catalog(get: Callable[[str], dict], expected: int, timeout: float = 900.0,
                     sleep: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.monotonic,
                     say: Callable[[str], None] = print) -> dict:
    """Interroga `/health` finché il catalogo ha `expected` prodotti; errori di rete all'avvio dei
    container si ignorano."""
    start = clock()
    while True:
        try:
            health = get("/health")
            products = (health.get("catalog") or {}).get("products") or 0
        except (httpx.HTTPError, ValueError):
            health, products = {}, 0
        if products >= expected:
            return health
        if clock() - start > timeout:
            raise RuntimeError("catalogo a %d prodotti su %d dopo %g s"
                               % (products, expected, timeout))
        say("attendo il catalogo: %d/%d prodotti" % (products, expected))
        sleep(10)


def durations(duration: float, arrival: Optional[float],
              tail: Optional[float]) -> Tuple[float, float]:
    """(minuti di arrivi, minuti di coda) dentro `duration`. Senza indicazioni 2/3 e 1/3; con una
    sola parte l'altra riempie il giro; con entrambe la somma non supera `duration`."""
    if duration <= 0:
        raise ValueError("--duration deve essere positiva")
    if arrival is None and tail is None:
        arrival, tail = duration * 2 / 3, duration / 3
    elif tail is None:
        tail = duration - arrival
    elif arrival is None:
        arrival = duration - tail
    if arrival <= 0 or tail < 0:
        raise ValueError("arrivi %g e coda %g minuti non validi per un giro di %g"
                         % (arrival, tail, duration))
    if arrival + tail > duration + 1e-9:
        raise ValueError("arrivi %g + coda %g minuti superano --duration %g"
                         % (arrival, tail, duration))
    return arrival, tail


def locust_command(args, run_dir: str) -> List[str]:
    minutes = args.arrival_minutes + args.tail_minutes
    return ["locust", "-f", os.path.join(ROOT, "loadtest", "locustfile.py"), "--headless",
            "-u", "1", "-r", "1", "--host", args.vela, "--only-summary",
            "--run-time", "%ds" % int(minutes * 60 + 60), "--stop-timeout", "30",
            "--csv", os.path.join(run_dir, "locust"),
            "--travelers", str(args.travelers), "--arrival-minutes", str(args.arrival_minutes),
            "--tail-minutes", str(args.tail_minutes), "--scenario-seed", str(args.seed),
            "--pay", str(args.pay),
            "--events-out", os.path.join(run_dir, "travelers.jsonl")]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--travelers", type=int, default=1000)
    ap.add_argument("--label", help="nome del giro e della sua cartella (default: <N>)")
    ap.add_argument("--duration", type=float, default=10.0,
                    help="minuti dell'intero giro, arrivi + coda (default 10)")
    ap.add_argument("--arrival-minutes", type=float, help="default: 2/3 di --duration")
    ap.add_argument("--tail-minutes", type=float, help="default: il resto di --duration")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--pay", type=float, default=0.60,
                    help="quota di chi riceve il link e paga (default 0,60; M19: 0,02)")
    ap.add_argument("--vela", default=os.environ.get("VELA_URL", "http://vela:8000"))
    ap.add_argument("--fake", default=os.environ.get("FAKE_HOFJ_URL", "http://fake-hofj:8001"))
    ap.add_argument("--calls", default=os.path.join(ROOT, "loadtest", "out", "calls.jsonl"),
                    help="registro del finto (volume condiviso)")
    ap.add_argument("--brands", default=DEFAULT_BRANDS)
    ap.add_argument("--out", default=os.path.join(ROOT, "loadtest", "out"))
    args = ap.parse_args(argv)
    try:
        args.arrival_minutes, args.tail_minutes = durations(args.duration, args.arrival_minutes,
                                                            args.tail_minutes)
    except ValueError as exc:
        ap.error(str(exc))
    label = args.label or str(args.travelers)
    run_dir = os.path.join(args.out, label)
    os.makedirs(run_dir, exist_ok=True)

    with httpx.Client(base_url=args.vela, timeout=10) as vela:
        health = wait_for_catalog(lambda path: vela.get(path).json(),
                                  expected_products(args.brands.split(",")))
    print("catalogo pronto: %s prodotti" % health["catalog"]["products"], flush=True)

    code = subprocess.call(locust_command(args, run_dir))
    print("locust terminato con codice %d" % code, flush=True)

    with httpx.Client(base_url=args.fake, timeout=10) as fake:
        with open(os.path.join(run_dir, "fake_stats.json"), "w", encoding="utf-8") as fh:
            json.dump(fake.get("/_fake/stats").json(), fh, indent=2, sort_keys=True)
    shutil.copyfile(args.calls, os.path.join(run_dir, "calls.jsonl"))
    report.main(["--calls", os.path.join(run_dir, "calls.jsonl"),
                 "--events", os.path.join(run_dir, "travelers.jsonl"),
                 "--stats", os.path.join(run_dir, "locust_stats.csv"),
                 "--label", label, "--out", os.path.join(run_dir, "report")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
