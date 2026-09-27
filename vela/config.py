"""Configurazione di Vela, letta solo da variabili d'ambiente (spec §6).

Nessun file viene aperto: i segreti arrivano dall'ambiente del processo.
"""
import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from vela.domain.quota import DEFAULT_FLOOR, DEFAULT_PAY_SHARE
from vela.domain.quota import booking_reserve as reserve_for

DEFAULT_UPSTREAM_MODE = "replay"
BRAND_SPORTS = ("padel", "tennis")


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


def parse_brands(raw: str) -> Dict[str, str]:
    """`HOFJ_BRANDS` ("padel=weebora.com,tennis=terrarossa.com") → {sport: brand}.

    Sport in {padel, tennis}, uno per voce, brand distinti, almeno una voce (decisione M10).
    Ogni errore è un `ValueError` con il motivo: l'app non parte.
    """
    brands: Dict[str, str] = {}
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        if "=" not in entry:
            raise ValueError("HOFJ_BRANDS: voce %r non nel formato sport=brand" % entry)
        sport, brand = (side.strip() for side in entry.split("=", 1))
        if sport not in BRAND_SPORTS:
            raise ValueError("HOFJ_BRANDS: sport %r sconosciuto, ammessi %s"
                             % (sport, ", ".join(BRAND_SPORTS)))
        if not brand:
            raise ValueError("HOFJ_BRANDS: brand vuoto per %s" % sport)
        if sport in brands:
            raise ValueError("HOFJ_BRANDS: sport %s ripetuto" % sport)
        if brand in brands.values():
            raise ValueError("HOFJ_BRANDS: brand %s usato per due sport" % brand)
        brands[sport] = brand
    if not brands:
        raise ValueError("HOFJ_BRANDS: serve almeno una voce sport=brand")
    return brands


@dataclass(frozen=True)
class Settings:
    database_url: Optional[str] = None
    hofj_api_key: Optional[str] = None
    hofj_base_url: Optional[str] = None
    hofj_brands: Optional[str] = None                  # M10: "padel=weebora.com,tennis=…"
    hofj_brand: Optional[str] = None                   # pre-M10: letta solo per dire di migrare
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    vela_api_token: Optional[str] = None
    vela_upstream_mode: str = DEFAULT_UPSTREAM_MODE
    anthropic_api_key: Optional[str] = None
    vela_public_url: Optional[str] = None
    twilio_account_sid: Optional[str] = None           # SMS al viaggiatore (decisione 2026-09-26)
    twilio_auth_token: Optional[str] = None
    twilio_from: Optional[str] = None                  # numero Twilio del mittente, E.164
    # Parametri di M5: configurabili da codice, mai da env (l'elenco di §6 resta chiuso).
    # M18: il ritmo lo decide il token bucket, non i thread. Legge di Little: ~1,45 chiamate/s
    # × 2-6 s di latenza ≈ 6-9 chiamate contemporanee.
    worker_concurrency: int = 10                       # RF-50, thread per istanza
    quota_margin: float = 0.10                         # limite effettivo = limitPerMinute × 0,9
    expected_pay_share: float = DEFAULT_PAY_SHARE      # M19: quota attesa di chi paga il link, per RF-48
    quota_burst: int = 8                               # M18: capienza B, con B + 60·r = limite effettivo
    quota_floor: int = DEFAULT_FLOOR                   # M18, M19: gettoni che purchase e sync lasciano ai booking
    purchase_max_attempts: int = 3                     # RF-46
    booking_max_attempts: int = 5                      # RF-24
    booking_backoff: Tuple[int, ...] = (5, 10, 20, 40)  # secondi tra i tentativi di booking
    job_lease_seconds: int = 180                       # M18: 3 chiamate × 20 s di timeout (booking, M19) + margine
    payment_poll_seconds: int = 60                     # RF-20, verifica della Checkout Session
    accept_wait_seconds: int = 100                     # accept aspetta prezzo e link (2026-09-26), < 120 s di ElevenLabs
    accept_poll_seconds: float = 1.0                   # rilettura dell'ordine durante l'attesa
    price_quote_ttl_seconds: int = 900                 # RF-84: vita del prezzo in cache; 0 = cache e fanout spenti
    silent_order_minutes: int = 15                     # M19: ordine in coda senza segni di vita → expired; 0 = mai
    replay_latency: Tuple[float, float] = (0.0, 0.0)   # replay: latenza simulata min/max (M13)
    replay_limit: Optional[int] = None                 # replay: quota simulata, None = illimitata

    @property
    def booking_reserve(self) -> float:
        """RF-48, M19: parte del ritmo delle prenotazioni, derivata da `expected_pay_share`."""
        return reserve_for(self.expected_pay_share)

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        return cls(
            database_url=normalize_database_url(env.get("DATABASE_URL")),
            hofj_api_key=env.get("HOFJ_API_KEY"),
            hofj_base_url=env.get("HOFJ_BASE_URL"),
            hofj_brands=env.get("HOFJ_BRANDS"),
            hofj_brand=env.get("HOFJ_BRAND"),
            stripe_secret_key=env.get("STRIPE_SECRET_KEY"),
            stripe_webhook_secret=env.get("STRIPE_WEBHOOK_SECRET"),
            vela_api_token=env.get("VELA_API_TOKEN"),
            vela_upstream_mode=env.get("VELA_UPSTREAM_MODE") or DEFAULT_UPSTREAM_MODE,
            anthropic_api_key=env.get("ANTHROPIC_API_KEY"),
            vela_public_url=env.get("VELA_PUBLIC_URL"),
            twilio_account_sid=env.get("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=env.get("TWILIO_AUTH_TOKEN"),
            twilio_from=env.get("TWILIO_FROM"),
        )


def live_brands(settings: Settings) -> Dict[str, str]:
    """La mappa sport → brand del live. `HOFJ_BRAND` da sola non basta più (decisione M10):
    l'errore dice come migrare invece di indovinare lo sport."""
    if settings.hofj_brands:
        return parse_brands(settings.hofj_brands)
    if settings.hofj_brand:
        raise ValueError("HOFJ_BRAND non è più letta: sostituiscila con HOFJ_BRANDS=padel=%s "
                         "(e tennis=<brand> se serve)" % settings.hofj_brand)
    raise ValueError("manca HOFJ_BRANDS (es. padel=weebora.com,tennis=terrarossa.com)")


from vela.domain.models import TravelerDefaults  # noqa: E402

# RF-13: default dichiarati nella configurazione, non chiesti al viaggiatore.
DEFAULT_TRAVELER = TravelerDefaults()
