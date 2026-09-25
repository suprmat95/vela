"""Configurazione di Vela, letta solo da variabili d'ambiente (spec §6).

Nessun file viene aperto: i segreti arrivano dall'ambiente del processo.
"""
import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

DEFAULT_UPSTREAM_MODE = "replay"


def normalize_database_url(url: Optional[str]) -> Optional[str]:
    """Riscrive lo schema Postgres nella forma che SQLAlchemy 2 + psycopg 3 richiedono.

    Render fornisce ``postgres://``; ``postgresql://`` senza driver userebbe psycopg2.
    Tutto il resto (``sqlite://``, driver già esplicito) resta invariato.
    """
    if url is None:
        return None
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: Optional[str] = None
    hofj_api_key: Optional[str] = None
    hofj_base_url: Optional[str] = None
    hofj_brand: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    vela_api_token: Optional[str] = None
    vela_upstream_mode: str = DEFAULT_UPSTREAM_MODE
    anthropic_api_key: Optional[str] = None
    vela_public_url: Optional[str] = None
    # Parametri di M5: configurabili da codice, mai da env (l'elenco di §6 resta chiuso).
    worker_concurrency: int = 4                        # RF-50, thread per istanza
    quota_margin: float = 0.10                         # limite effettivo = limitPerMinute × 0,9
    booking_reserve: float = 0.20                      # RF-47, quota della finestra per i booking
    purchase_max_attempts: int = 3                     # RF-46
    booking_max_attempts: int = 5                      # RF-24
    booking_backoff: Tuple[int, ...] = (5, 10, 20, 40)  # secondi tra i tentativi di booking
    job_lease_seconds: int = 120                       # un job running più vecchio torna prelevabile
    payment_poll_seconds: int = 60                     # RF-20, verifica della Checkout Session
    replay_latency: Tuple[float, float] = (0.0, 0.0)   # replay: latenza simulata min/max (M13)
    replay_limit: Optional[int] = None                 # replay: quota simulata, None = illimitata

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        return cls(
            database_url=normalize_database_url(env.get("DATABASE_URL")),
            hofj_api_key=env.get("HOFJ_API_KEY"),
            hofj_base_url=env.get("HOFJ_BASE_URL"),
            hofj_brand=env.get("HOFJ_BRAND"),
            stripe_secret_key=env.get("STRIPE_SECRET_KEY"),
            stripe_webhook_secret=env.get("STRIPE_WEBHOOK_SECRET"),
            vela_api_token=env.get("VELA_API_TOKEN"),
            vela_upstream_mode=env.get("VELA_UPSTREAM_MODE") or DEFAULT_UPSTREAM_MODE,
            anthropic_api_key=env.get("ANTHROPIC_API_KEY"),
            vela_public_url=env.get("VELA_PUBLIC_URL"),
        )


from vela.domain.models import TravelerDefaults  # noqa: E402

# RF-13: default dichiarati nella configurazione, non chiesti al viaggiatore.
DEFAULT_TRAVELER = TravelerDefaults()
