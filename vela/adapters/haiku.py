"""Fallback Claude Haiku 4.5 per l'estrazione dei criteri (RF-03).

Una sola chiamata con lo strumento `record_criteria` forzato: il suo input è lo schema dei
criteri. Ogni errore dell'API diventa `None` e resta il risultato del parser deterministico.
Il testo dell'intento non viene mai loggato.
"""
import logging
from datetime import date
from typing import Optional

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_SECONDS = 5.0
MAX_RETRIES = 1
MAX_TOKENS = 512
TOOL_NAME = "record_criteria"
TOOL = {
    "name": TOOL_NAME,
    "description": "Registra i criteri del viaggio letti nel testo. null per ogni campo non detto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sport": {"type": ["string", "null"], "enum": ["padel", "tennis", "any", None]},
            "area": {"type": ["string", "null"],
                     "description": "Paese, regione o città come scritto nel testo."},
            "period_start": {"type": ["string", "null"], "description": "Inizio, YYYY-MM-DD."},
            "period_end": {"type": ["string", "null"], "description": "Fine, YYYY-MM-DD."},
            "pax": {"type": ["integer", "null"], "description": "Numero di persone."},
            "budget": {"type": ["number", "null"],
                       "description": "Budget totale massimo in euro per tutto il gruppo."},
        },
        "required": ["sport", "area", "period_start", "period_end", "pax", "budget"],
        "additionalProperties": False,
    },
}
SYSTEM = ("Estrai i criteri di un viaggio di padel o tennis dal testo del viaggiatore, scritto in "
          "italiano o in inglese. Chiama sempre record_criteria. Usa null per ogni campo che il "
          "testo non dice: non inventare. Sport: \"terra rossa\", \"Terrarossa\" e \"clay\" "
          "indicano il tennis, \"paddle\" e \"Weebora\" il padel; usa any se al viaggiatore va "
          "bene l'uno o l'altro (\"indifferente\", \"tutti e due\", padel e tennis insieme); "
          "beach tennis e paddle tennis non sono né padel né tennis, quindi null. Le date sono nel "
          "formato YYYY-MM-DD e non precedono la data di oggi indicata nel messaggio. Il budget è "
          "il totale massimo in euro per tutto il gruppo.")


class HaikuExtractor:
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_api_key(cls, api_key: str) -> "HaikuExtractor":
        return cls(anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS,
                                       max_retries=MAX_RETRIES))

    def extract(self, text: str, today: date) -> Optional[dict]:
        try:
            message = self.client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM, tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user",
                           "content": "Oggi è %s.\n\n%s" % (today.isoformat(), text)}])
        except anthropic.APIError as exc:
            log.warning("fallback Haiku non disponibile: %s %s", type(exc).__name__,
                        getattr(exc, "status_code", ""))
            return None
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
                return dict(block.input) if isinstance(block.input, dict) else None
        log.warning("fallback Haiku senza record_criteria (stop_reason=%s)",
                    getattr(message, "stop_reason", None))
        return None
