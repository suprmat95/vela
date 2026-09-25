"""Porta del fallback LLM per l'estrazione dei criteri di un intento (RF-03)."""
from datetime import date
from typing import Optional, Protocol


class IntentExtractor(Protocol):
    def extract(self, text: str, today: date) -> Optional[dict]:
        """Campi grezzi `sport`, `area`, `period_start`, `period_end` (ISO), `pax`, `budget`,
        ognuno `None` se il testo non lo dice; `None` se il servizio non è disponibile.
        Il dominio valida ogni campo prima di usarlo."""
        ...
