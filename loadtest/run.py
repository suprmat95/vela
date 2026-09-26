"""Un giro del load test (M13a), il comando del servizio compose `locust`.

1. aspetta che Vela risponda e che il sync M10 contro il finto abbia scritto tutto il catalogo;
2. lancia Locust headless (`loadtest/locustfile.py`) contro Vela;
3. copia il registro del finto e le sue statistiche nella cartella del giro e scrive il report.

  docker compose run --rm locust --travelers 10000 --label 10k

Solo reti del compose (`vela`, `fake-hofj`): nessuna chiamata a HofJ né a Stripe.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, List, Optional

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from loadtest import report  # noqa: E402

FIXTURES = os.path.join(ROOT, "fixtures")
DEFAULT_BRANDS = "weebora.com,terrarossa.com"


def expected_products(brands: List[str], fixtures_dir: str = FIXTURES) -> int:
    """Prodotti attivi nelle fixture dei brand: quanti ne scrive un sync completo."""
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
    """Interroga `/health` finché il catalogo ha `expected` prodotti. Il sync a 120/min ci mette
    1-2 minuti; errori di rete all'avvio dei container si ignorano."""
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
            raise RuntimeError("catalogo a %d prodotti su %d dopo %g s: il sync non è finito"
                               % (products, expected, timeout))
        say("attendo il sync del catalogo: %d/%d prodotti" % (products, expected))
        sleep(10)


def locust_command(args, run_dir: str) -> List[str]:
    minutes = args.arrival_minutes + args.tail_minutes
    return ["locust", "-f", os.path.join(ROOT, "loadtest", "locustfile.py"), "--headless",
            "-u", "1", "-r", "1", "--host", args.vela, "--only-summary",
            "--run-time", "%ds" % int(minutes * 60 + 120), "--stop-timeout", "30",
            "--csv", os.path.join(run_dir, "locust"),
            "--travelers", str(args.travelers), "--arrival-minutes", str(args.arrival_minutes),
            "--tail-minutes", str(args.tail_minutes), "--scenario-seed", str(args.seed),
            "--events-out", os.path.join(run_dir, "travelers.jsonl")]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--travelers", type=int, default=1000)
    ap.add_argument("--label", help="nome del giro e della sua cartella (default: <N>)")
    ap.add_argument("--arrival-minutes", type=float, default=10.0)
    ap.add_argument("--tail-minutes", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--vela", default=os.environ.get("VELA_URL", "http://vela:8000"))
    ap.add_argument("--fake", default=os.environ.get("FAKE_HOFJ_URL", "http://fake-hofj:8001"))
    ap.add_argument("--calls", default=os.path.join(ROOT, "loadtest", "out", "calls.jsonl"),
                    help="registro del finto (volume condiviso)")
    ap.add_argument("--brands", default=DEFAULT_BRANDS)
    ap.add_argument("--out", default=os.path.join(ROOT, "loadtest", "out"))
    args = ap.parse_args(argv)
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
