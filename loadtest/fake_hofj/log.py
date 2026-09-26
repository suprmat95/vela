"""Registro delle chiamate del finto HofJ (M13a): una riga JSON per chiamata, più i contatori
di `/_fake/stats`. Le verifiche del load test si fanno su questo registro, non sui log di Vela."""
import json
import threading
from collections import Counter, deque
from typing import Deque, Dict, List, Optional

WINDOW = 60.0


class CallLog:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._lock = threading.Lock()
        self._fh = open(path, "a", encoding="utf-8") if path else None
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.records: List[dict] = []
            if self._fh is not None:
                self._fh.truncate(0)
                self._fh.seek(0)

    def write(self, record: dict) -> None:
        with self._lock:
            self.records.append(record)
            if self._fh is not None:
                self._fh.write(json.dumps(record, sort_keys=True) + "\n")
                self._fh.flush()

    def stats(self) -> dict:
        with self._lock:
            records = list(self.records)
        return summarize(records)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()


def max_in_window(times: List[float], width: float = WINDOW) -> int:
    """Il massimo di istanti in un qualsiasi intervallo semiaperto lungo `width`."""
    best, window = 0, deque()   # type: int, Deque[float]
    for t in sorted(times):
        window.append(t)
        while window[0] <= t - width:
            window.popleft()
        best = max(best, len(window))
    return best


def summarize(records: List[dict]) -> dict:
    """Contatori del registro: arrivate al finto (servite o respinte), mai le rotte `/_fake`."""
    counted = [r for r in records if r.get("counted")]
    vela = [r["t"] for r in counted if r["origin"] == "vela"]
    by_endpoint: Dict[str, int] = Counter(r["endpoint"] for r in counted if r["origin"] == "vela")
    bookings = Counter(r["itinerary_id"] for r in records
                       if r["endpoint"] == "POST /v1/bookings" and r.get("executed"))
    return {
        "calls": len(counted),
        "calls_vela": len(vela),
        "status_429": sum(1 for r in counted if r["status"] == 429),
        "max_in_60s": max_in_window([r["t"] for r in counted]),
        "max_in_60s_vela": max_in_window(vela),
        "by_endpoint": dict(sorted(by_endpoint.items())),
        "booking_posts_max_per_itinerary": max(bookings.values(), default=0),
    }
