"""`python -m loadtest.fake_hofj`: avvia il finto HofJ (M13a) con uvicorn, un processo.

Esempio: `python -m loadtest.fake_hofj --port 8001 --background-rpm 12 --log loadtest/out/calls.jsonl`
Guasti: `--fault "POST /v1/bookings=hang_then_execute:0.05"` (ripetibile).
Ogni opzione ha un default da variabile d'ambiente `FAKE_HOFJ_*` (per il compose); i guasti in
`FAKE_HOFJ_FAULTS`, separati da `;`.
"""
import argparse
import os
from typing import List, Optional

import uvicorn

from loadtest.fake_hofj.app import DEFAULT_KEY, FakeConfig, create_app
from loadtest.fake_hofj.faults import LATENCY, parse_fault


def parse_args(argv: Optional[List[str]] = None, env=None) -> argparse.Namespace:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Finto HofJ con le regole di HofJ (M13a)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--api-key", default=env.get("FAKE_HOFJ_KEY", DEFAULT_KEY),
                    help="chiave accettata (finta, non un segreto)")
    ap.add_argument("--window", choices=("anchored", "rolling"),
                    default=env.get("FAKE_HOFJ_WINDOW") or "anchored")
    ap.add_argument("--limit", type=int, default=120, help="chiamate per finestra per chiave")
    ap.add_argument("--background-rpm", type=float,
                    default=float(env.get("FAKE_HOFJ_BACKGROUND_RPM") or 0),
                    help="altri usi della stessa chiave, chiamate al minuto")
    ap.add_argument("--latency", choices=sorted(LATENCY),
                    default=env.get("FAKE_HOFJ_LATENCY") or "standard")
    ap.add_argument("--fault", action="append", type=parse_fault,
                    default=[parse_fault(f) for f in (env.get("FAKE_HOFJ_FAULTS") or "").split(";")
                             if f.strip()])
    ap.add_argument("--hang-seconds", type=float, default=20.0)
    ap.add_argument("--seed", type=int, default=int(env.get("FAKE_HOFJ_SEED") or 13))
    ap.add_argument("--log", default=env.get("FAKE_HOFJ_LOG"), help="registro JSONL delle chiamate")
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
