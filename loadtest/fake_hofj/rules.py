"""Regole di quota del finto HofJ (M13a), pure e con l'orologio passato dal chiamante.

Le regole sono quelle di HofJ, non quelle di Vela: se il finto usasse la finestra di Vela il test
passerebbe per costruzione (seconda lettura del twist, §3.5).

- `AnchoredWindow` (default): finestra fissa di 60 s che parte alla prima chiamata dopo la
  scadenza della precedente, come misurato dalla sonda (`docs/api/quota-health.md`).
- `RollingWindow`: registro scorrevole degli ultimi 60 s, come dicono brief e OAS.

In entrambe la chiamata respinta conta nella finestra (decisione M13a: ipotesi pessimista).
Gli istanti sono secondi epoch (`time.time()`); la quota è per chiave API.
"""
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

WINDOW = 60.0
DEFAULT_LIMIT = 120


@dataclass(frozen=True)
class Admission:
    ok: bool
    used: int
    limit: int
    window_start: float
    window_end: float
    retry_after: float   # 0 se ammessa


class AnchoredWindow:
    def __init__(self, limit: int = DEFAULT_LIMIT):
        self.limit = limit
        self._state: Dict[str, Tuple[float, int]] = {}

    def _current(self, key: str, now: float) -> Tuple[float, int]:
        start, used = self._state.get(key, (None, 0))
        if start is None or now >= start + WINDOW:
            return now, 0
        return start, used

    def admit(self, key: str, now: float) -> Admission:
        start, used = self._current(key, now)
        used += 1
        self._state[key] = (start, used)
        return self._admission(start, used, now)

    def peek(self, key: str, now: float) -> Admission:
        start, used = self._current(key, now)
        return self._admission(start, used, now)

    def _admission(self, start: float, used: int, now: float) -> Admission:
        ok = used <= self.limit
        return Admission(ok, used, self.limit, start, start + WINDOW,
                         0.0 if ok else start + WINDOW - now)


class RollingWindow:
    def __init__(self, limit: int = DEFAULT_LIMIT):
        self.limit = limit
        self._calls: Dict[str, Deque[float]] = {}

    def _purge(self, key: str, now: float) -> Deque[float]:
        calls = self._calls.setdefault(key, deque())
        while calls and calls[0] <= now - WINDOW:
            calls.popleft()
        return calls

    def admit(self, key: str, now: float) -> Admission:
        calls = self._purge(key, now)
        calls.append(now)
        return self._admission(calls, now)

    def peek(self, key: str, now: float) -> Admission:
        return self._admission(self._purge(key, now), now)

    def _admission(self, calls: Deque[float], now: float) -> Admission:
        used = len(calls)
        start = calls[0] if calls else now
        ok = used <= self.limit
        return Admission(ok, used, self.limit, start, start + WINDOW,
                         0.0 if ok else start + WINDOW - now)


def make_window(kind: str, limit: int = DEFAULT_LIMIT):
    if kind == "anchored":
        return AnchoredWindow(limit)
    if kind == "rolling":
        return RollingWindow(limit)
    raise ValueError("finestra %r sconosciuta: anchored o rolling" % kind)


class Background:
    """Gli altri usi della chiave: `rpm` chiamate al minuto a intervalli uguali da `start`.
    `due(now)` dice quante chiamate sono maturate dall'ultima domanda."""

    def __init__(self, rpm: float, start: float):
        self.interval: Optional[float] = 60.0 / rpm if rpm > 0 else None
        self.start = start
        self._done = 0

    def due(self, now: float) -> int:
        if self.interval is None or now < self.start:
            return 0
        total = int((now - self.start) // self.interval) + 1
        fresh, self._done = total - self._done, total
        return fresh
