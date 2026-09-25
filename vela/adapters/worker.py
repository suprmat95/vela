"""Worker del processo (RF-50, RNF-02): N thread che chiamano `JobProcessor.run_once`.

Ogni istanza ha il suo worker; il coordinamento tra istanze è tutto in Postgres (prelievo
`SKIP LOCKED`, quota condivisa). Un giro senza lavoro attende `idle_sleep` secondi; un'eccezione
inattesa viene registrata e il ciclo continua (il job resta `running` e torna prelevabile alla
scadenza del lease). `drain` esegue i giri nel thread chiamante finché non resta lavoro: è il
modo in cui i test fanno avanzare la coda senza thread.
"""
import logging
import threading
from typing import List

log = logging.getLogger("vela.worker")


class Worker:
    def __init__(self, processor, concurrency: int = 4, idle_sleep: float = 1.0):
        self.processor = processor
        self.concurrency = concurrency
        self.idle_sleep = idle_sleep
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []

    def start(self) -> None:
        self._stop.clear()
        for n in range(self.concurrency):
            t = threading.Thread(target=self._loop, name="vela-worker-%d" % (n + 1), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, wait: bool = True, timeout: float = 20.0) -> None:
        self._stop.set()
        if wait:
            for t in self._threads:
                t.join(timeout)
        self._threads = []

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.processor.run_once()
            except Exception:   # noqa: BLE001 - un job guasto non deve fermare il worker
                log.exception("giro del worker non riuscito")
                worked = False
            if not worked:
                self._stop.wait(self.idle_sleep)

    def drain(self, max_iterations: int = 1000) -> int:
        done = 0
        while done < max_iterations and self.processor.run_once():
            done += 1
        return done
