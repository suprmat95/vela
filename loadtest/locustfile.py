"""Load test del twist a modello aperto (M13a): N viaggiatori in 10 minuti contro la REST di Vela
in modo `loadtest` (finto HofJ, pagamenti finti). Mai contro HofJ vero né Render.

Un solo utente Locust, `Arrivals`, lancia un greenlet per viaggiatore all'istante previsto dallo
scenario (`loadtest/scenario.py`), indipendentemente da come risponde Vela: è il modello aperto.
Le richieste passano dal client Locust con il nome del caso d'uso, quindi le statistiche
(`--csv`) hanno p50/p95/p99 di `create_intent`, `get_proposal`, `reject_proposal`,
`accept_proposal`, `get_order_status`, più `replay_checkout`. Ogni viaggiatore scrive una riga
JSON in `--events-out`; alla fine chi è ancora in corso viene scritto con lo stato raggiunto.

  locust -f loadtest/locustfile.py --headless -u 1 -r 1 --host http://vela:8000 \
         --travelers 1000 --events-out loadtest/out/run/travelers.jsonl --csv loadtest/out/run/locust
"""
import json
import os
import random
import sys

import gevent
from gevent.pool import Group
from locust import FastHttpUser, events, task

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from loadtest.journey import ScenarioClock, run_journey  # noqa: E402
from loadtest.scenario import travelers  # noqa: E402


@events.init_command_line_parser.add_listener
def _arguments(parser):
    parser.add_argument("--travelers", type=int, default=1000, help="viaggiatori in arrivo")
    parser.add_argument("--arrival-minutes", type=float, default=10.0)
    parser.add_argument("--tail-minutes", type=float, default=5.0,
                        help="minuti dopo l'ultimo arrivo prima di chiudere il giro")
    parser.add_argument("--scenario-seed", type=int, default=13)
    parser.add_argument("--events-out", default="loadtest/out/travelers.jsonl")
    parser.add_argument("--vela-token", default=os.environ.get("VELA_API_TOKEN", "loadtest-token"),
                        help="token REST di Vela (quello finto del compose)")


class Arrivals(FastHttpUser):
    fixed_count = 1
    concurrency = 2048          # connessioni del client condiviso fra i greenlet
    network_timeout = 120.0
    connection_timeout = 30.0

    @task
    def scenario(self):
        opts = self.environment.parsed_options
        auth = {"Authorization": "Bearer " + opts.vela_token}
        plan = travelers(opts.travelers, opts.arrival_minutes, opts.scenario_seed)
        deadline = (opts.arrival_minutes + opts.tail_minutes) * 60
        clock = ScenarioClock()
        os.makedirs(os.path.dirname(os.path.abspath(opts.events_out)), exist_ok=True)
        out = open(opts.events_out, "w", encoding="utf-8")
        out.write(json.dumps({"type": "run", "epoch_start": clock.epoch_start,
                              "travelers": opts.travelers, "arrival_minutes": opts.arrival_minutes,
                              "tail_minutes": opts.tail_minutes, "seed": opts.scenario_seed}) + "\n")
        live = {}

        def call(method, path, name, json_body=None):
            with self.client.request(method, path, name=name, json=json_body, headers=auth,
                                     catch_response=True) as r:
                try:
                    body = r.json() if r.content else {}
                except ValueError:
                    body = {}
                if r.status_code is None or r.status_code == 0 or r.status_code >= 400:
                    r.failure("HTTP %s" % r.status_code)
                else:
                    r.success()
                return r.status_code or 0, body

        def traveler(tr):
            record = {"type": "traveler"}
            live[tr.index] = record
            try:
                run_journey(tr, call, clock, gevent.sleep, deadline, record,
                            rng=random.Random(opts.scenario_seed * 1_000_003 + tr.index))
            except Exception as exc:   # un viaggiatore rotto non ferma il giro: resta nel file
                record["final"] = "error_%s" % type(exc).__name__
            out.write(json.dumps(live.pop(tr.index)) + "\n")

        group = Group()
        try:
            for tr in plan:
                if tr.arrival >= deadline:
                    break
                delay = tr.arrival - clock()
                if delay > 0:
                    gevent.sleep(delay)
                group.spawn(traveler, tr)
            group.join(timeout=max(0.0, deadline - clock()) + 10)
        finally:   # anche se Locust interrompe il task: chi è in corso viene scritto
            group.kill(block=True, timeout=10)
            for record in live.values():
                record["final"] = record.get("final") or "open_%s" % record.get("last_status", "unknown")
                out.write(json.dumps(record) + "\n")
            out.close()
        self.environment.runner.quit()
