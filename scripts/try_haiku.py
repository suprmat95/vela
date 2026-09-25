"""Prova manuale del fallback Haiku (RF-03): esegue UNA chiamata reale ad Anthropic.

Non è un test automatico. Serve ANTHROPIC_API_KEY nell'ambiente:
    uv run python scripts/try_haiku.py "un'idea per il ponte dei morti con la racchetta, siamo in 2"
Stampa i criteri risultanti e l'eventuale domanda. Senza chiave non chiama nulla.
"""
import os
import sys
from datetime import date

from vela.adapters.haiku import HaikuExtractor
from vela.domain.intent import parse_intent
from vela.domain.models import criteria_to_dict

DEFAULT_TEXT = "un'idea per il ponte dei morti con la racchetta, siamo in 2"


def main(argv) -> int:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY assente: nessuna chiamata.")
        return 1
    text = argv[1] if len(argv) > 1 else DEFAULT_TEXT
    result = parse_intent(text, today=date.today(), extractor=HaikuExtractor.from_api_key(key))
    print(criteria_to_dict(result.criteria))
    print("domanda:", result.question)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
