"""`python -m loadtest.fake_hofj`: avvia il finto HofJ (M13a) con uvicorn, un processo.

Esempio: `python -m loadtest.fake_hofj --port 8001 --background-rpm 12 --log loadtest/out/calls.jsonl`
Guasti: `--fault "POST /v1/bookings=hang_then_execute:0.05"` (ripetibile).
"""
import argparse
import os
from typing import List, Optional

import uvicorn

from loadtest.fake_hofj.app import DEFAULT_KEY, FakeConfig, create_app
from loadtest.fake_hofj.faults import LATENCY, parse_fault


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Finto HofJ con le regole di HofJ (M13a)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--api-key", default=os.environ.get("FAKE_HOFJ_KEY", DEFAULT_KEY),
                    help="chiave accettata (finta, non un segreto)")
    ap.add_argument("--window", choices=("anchored", "rolling"), default="anchored")
    ap.add_argument("--limit", type=int, default=120, help="chiamate per finestra per chiave")
    ap.add_argument("--background-rpm", type=float, default=0.0,
                    help="altri usi della stessa chiave, chiamate al minuto")
    ap.add_argument("--latency", choices=sorted(LATENCY), default="standard")
    ap.add_argument("--fault", action="append", default=[], type=parse_fault)
    ap.add_argument("--hang-seconds", type=float, default=20.0)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--log", default=None, help="registro JSONL delle chiamate")
    return ap.parse_args(argv)


def config_from(args: argparse.Namespace) -> FakeConfig:
    return FakeConfig(api_key=args.api_key, window=args.window, limit=args.limit,
                      background_rpm=args.background_rpm, latency=args.latency,
                      faults=tuple(args.fault), hang_seconds=args.hang_seconds, seed=args.seed,
                      log_path=args.log)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
    uvicorn.run(create_app(config_from(args)), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
