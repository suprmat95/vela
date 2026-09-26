"""SMS finti per replay e test: gli invii restano in `sent`, nessuna chiamata di rete.

`fail_with` programma le eccezioni da sollevare, una per invio, prima di riuscire.
"""
import threading
from typing import List, Sequence, Tuple


class FakeSms:
    def __init__(self, fail_with: Sequence[Exception] = ()):
        self._lock = threading.Lock()
        self._failures = list(fail_with)
        self.sent: List[Tuple[str, str]] = []

    def send_sms(self, to: str, body: str) -> str:
        with self._lock:
            if self._failures:
                raise self._failures.pop(0)
            self.sent.append((to, body))
            return "SMfake%d" % len(self.sent)
