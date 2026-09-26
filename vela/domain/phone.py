"""Numeri di telefono per gli SMS (decisione 2026-09-26): E.164 con `+39` di default.

Test in Italia: un numero senza prefisso internazionale è italiano; `+…` e `00…` restano del
paese scritto, così un `+39` già presente non si raddoppia. Il numero in chiaro non va mai nei
log: si usa `mask`.
"""
import re
from typing import Optional

DEFAULT_PREFIX = "+39"
_SEPARATORS = re.compile(r"[\s\-.()/]")
_E164 = re.compile(r"^\+\d{8,15}$")


def normalize_it(raw: Optional[str]) -> Optional[str]:
    """Numero in E.164, o `None` se dopo la pulizia non è `+` seguito da 8-15 cifre."""
    if not raw:
        return None
    # "+39 (0)333…": lo "(0)" dopo il prefisso non si compone; tolto prima dei separatori
    number = _SEPARATORS.sub("", raw.replace("(0)", ""))
    if number.startswith("00"):
        number = "+" + number[2:]
    elif not number.startswith("+"):
        number = DEFAULT_PREFIX + number
    return number if _E164.match(number) else None


def tail(raw: Optional[str]) -> Optional[str]:
    """Ultime 4 cifre del numero normalizzato, da dire al viaggiatore; `None` se non valido."""
    number = normalize_it(raw)
    return number[-4:] if number else None


def mask(e164: str) -> str:
    """`+393331234567` → `+39******4567`: l'unica forma del numero ammessa nei log."""
    return e164[:3] + "*" * max(len(e164) - 7, 0) + e164[-4:]
