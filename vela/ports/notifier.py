"""Porta verso il fornitore di SMS (decisione 2026-09-26). Implementazioni: Twilio, finta.

`to` è sempre in E.164 (`vela.domain.phone`). I messaggi delle eccezioni non contengono il
numero in chiaro, il testo dell'SMS né le credenziali: finiscono in `last_error` e nei log.
"""
from typing import Protocol


class NotifierError(Exception):
    """Errore temporaneo (rete, timeout, 5xx, 429): il job riprova."""


class NotifierRejected(NotifierError):
    """Errore definitivo (4xx, es. numero non valido): il job non riprova."""


class Notifier(Protocol):
    def send_sms(self, to: str, body: str) -> str: ...   # id del messaggio presso il fornitore
