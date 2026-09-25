"""Configurazione di Vela, letta solo da variabili d'ambiente (spec §6).

Nessun file viene aperto: i segreti arrivano dall'ambiente del processo.
"""
import os
from dataclasses import dataclass
from typing import Mapping, Optional

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
