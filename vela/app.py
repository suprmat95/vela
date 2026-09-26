"""App FastAPI di Vela: un solo processo per REST e MCP (RNF-02).

La superficie MCP (M3) è innestata su ``/mcp`` in ogni modalità; il suo session manager gira nel
lifespan.

``create_app`` è la factory usata dai test; ``app`` è l'istanza per ``uvicorn vela.app:app``.
In replay il dominio è costruito su Postgres con gli adapter finti; il lifespan riallinea il
catalogo alla fixture dell'ambiente (M7), legge la quota HofJ, riaccoda le prenotazioni
pendenti (RF-27) e avvia il worker (RF-50).
La superficie REST (``/v1``) è sempre montata; gli errori sotto ``/v1`` sono RFC 7807.
Nessun webhook Stripe: il pagamento si chiude con ``POST /v1/bookings`` di HofJ e Vela lo scopre
interrogando la Checkout Session (job di M5).
Il pagamento è Stripe se ``STRIPE_SECRET_KEY`` è impostata, altrimenti finto.
"""
import os
from contextlib import asynccontextmanager
from typing import Callable, List, Optional, Tuple

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from vela.adapters.db import make_engine
from vela.adapters.hofj_http import HofJHttp
from vela.adapters.hofj_replay import FIXTURE_PATH, ReplayHofJ
from vela.adapters.repo_postgres import PostgresRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.adapters.stripe_links import StripePayments, build_stripe_client
from vela.adapters.worker import Worker
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.booking import BookingJob
from vela.domain.catalog import fixture_meta, select_fixtures
from vela.domain.jobs import JobProcessor
from vela.domain.models import JobKind, Product
from vela.domain.payment_check import PaymentCheckJob
from vela.domain.purchase import PurchaseJob
from vela.domain.usecases import Vela
from vela.ports.payments import PaymentsPort
from vela.surfaces.checkout_pages import router as checkout_router
from vela.surfaces.health import router as health_router
from vela.surfaces.mcp import build_mcp, mcp_routes
from vela.surfaces.problems import install_problem_handlers
from vela.surfaces.replay import router as replay_router
from vela.surfaces.rest import router as rest_router

REPLAY = "replay"
LIVE = "live"
CatalogLoader = Callable[[], List[Product]]
FIXTURES_DIR = os.path.dirname(FIXTURE_PATH)   # una fixture per ambiente HofJ (decisione M7)


def build_payments(settings: Settings) -> PaymentsPort:
    """Stripe se `STRIPE_SECRET_KEY` è impostata (indipendente dall'upstream HofJ), altrimenti
    il pagamento finto. Senza `VELA_PUBLIC_URL` l'avvio si blocca: servono i ritorni del Checkout."""
    if not settings.stripe_secret_key:
        return FakePayments(settings.vela_public_url)
    if not settings.vela_public_url:
        raise RuntimeError("STRIPE_SECRET_KEY richiede VELA_PUBLIC_URL per le pagine di ritorno "
                           "del Checkout")
    return StripePayments(build_stripe_client(settings.stripe_secret_key), settings.vela_public_url)


def build_hofj(settings: Settings) -> Tuple[object, CatalogLoader]:
    """Replay (RNF-08) oppure HofJ vero con `VELA_UPSTREAM_MODE=live` (M5). In live servono le
    tre variabili HofJ e un pagamento vero: il checkout finto non è montato in live.
    Restituisce l'adapter e il caricatore del catalogo: in live la fixture registrata su
    HOFJ_BASE_URL (decisione M7), il cui locale è anche quello del carrello, finché non c'è il
    sync (M10)."""
    if settings.vela_upstream_mode == REPLAY:
        hofj = ReplayHofJ(latency=settings.replay_latency, limit=settings.replay_limit)
        return hofj, hofj.load_catalog
    if settings.vela_upstream_mode != LIVE:
        raise RuntimeError("VELA_UPSTREAM_MODE=%s sconosciuto: usare replay o live"
                           % settings.vela_upstream_mode)
    missing = [name for name, value in (("HOFJ_API_KEY", settings.hofj_api_key),
                                        ("HOFJ_BASE_URL", settings.hofj_base_url),
                                        ("HOFJ_BRAND", settings.hofj_brand)) if not value]
    if missing:
        raise RuntimeError("VELA_UPSTREAM_MODE=live richiede %s" % ", ".join(missing))
    if not settings.stripe_secret_key:
        raise RuntimeError("VELA_UPSTREAM_MODE=live richiede STRIPE_SECRET_KEY: il pagamento finto "
                           "non esiste contro HofJ vero")
    fixtures = select_fixtures(FIXTURES_DIR, settings.hofj_base_url)
    hofj = HofJHttp(settings.hofj_base_url, settings.hofj_api_key, settings.hofj_brand,
                    locale=fixture_meta(fixtures[0])["locale"])
    return hofj, ReplayHofJ(fixtures).load_catalog


def build_vela(settings: Settings, engine: Engine) -> Tuple[Vela, CatalogLoader]:
    hofj, catalog_loader = build_hofj(settings)
    extractor = None
    if settings.anthropic_api_key:   # RF-03: senza chiave il fallback è spento, senza errori
        from vela.adapters.haiku import HaikuExtractor
        extractor = HaikuExtractor.from_api_key(settings.anthropic_api_key)
    repos = PostgresRepositories(engine, quota_margin=settings.quota_margin,
                                 booking_reserve=settings.booking_reserve)
    vela = Vela(repos, hofj, build_payments(settings), DEFAULT_TRAVELER, extractor=extractor)
    return vela, catalog_loader


def build_worker(vela: Vela, settings: Settings) -> Worker:
    """Job d'acquisto, prenotazione e verifica del pagamento sotto un solo processore (RF-50)."""
    purchase = PurchaseJob(vela.repos, vela.hofj, vela.payments, vela._propose, vela.defaults,
                           now=vela.now, max_attempts=settings.purchase_max_attempts,
                           new_id=vela.new_id, poll_seconds=settings.payment_poll_seconds)
    booking = BookingJob(vela.repos, vela.hofj, now=vela.now,
                         max_attempts=settings.booking_max_attempts, backoff=settings.booking_backoff)
    check = PaymentCheckJob(vela.repos, vela.payments, vela.orders, now=vela.now,
                            poll_seconds=settings.payment_poll_seconds)
    processor = JobProcessor(vela.repos, vela.hofj, {JobKind.PURCHASE: purchase,
                                                     JobKind.BOOKING: booking,
                                                     JobKind.PAYMENT_CHECK: check},
                             now=vela.now, lease_seconds=settings.job_lease_seconds)
    return Worker(processor, settings.worker_concurrency)


def realign_catalog(vela: Vela, catalog_loader: CatalogLoader) -> Tuple[int, int]:
    """Decisione M7: se i prodotti attivi del DB non sono quelli della fixture (DB vuoto o cambio
    di ambiente), upsert della fixture e archiviazione degli assenti, mai DELETE. Con lo stesso
    catalogo non tocca nulla: i flag `bookable` di RF-33 sopravvivono ai riavvii.
    Restituisce (caricati, archiviati)."""
    products = catalog_loader()
    wanted = {p.id for p in products if not p.archived}
    stored = {p.id for p in vela.repos.products.list_all() if not p.archived}
    if stored == wanted:
        return 0, 0
    vela.repos.products.upsert_many(products)
    return len(products), vela.repos.products.archive_missing(p.id for p in products)


def bootstrap(vela: Vela, worker: Worker, catalog_loader: Optional[CatalogLoader]) -> dict:
    loaded = archived = 0
    if catalog_loader is not None:
        loaded, archived = realign_catalog(vela, catalog_loader)
    synced = worker.processor.refresh_quota()          # RF-36: al boot
    resumed = vela.orders.resume_bookings()            # RF-27
    worker.start()
    return {"catalog_loaded": loaded, "catalog_archived": archived, "quota_synced": synced,
            "resumed": resumed}


def create_app(settings: Optional[Settings] = None, vela: Optional[Vela] = None,
               worker: Optional[Worker] = None,
               catalog_loader: Optional[CatalogLoader] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url) if settings.database_url else None
    if vela is None and engine is not None:
        vela, catalog_loader = build_vela(settings, engine)
    if vela is not None and worker is None:
        worker = build_worker(vela, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with app.state.mcp.session_manager.run():
            if app.state.vela is not None:
                app.state.bootstrap = bootstrap(app.state.vela, app.state.worker, app.state.catalog_loader)
            yield
            if app.state.worker is not None:
                app.state.worker.stop(wait=False)

    app = FastAPI(title="Vela", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.vela = vela
    app.state.worker = worker
    app.state.catalog_loader = catalog_loader
    app.state.bootstrap = None
    app.state.mcp = build_mcp(lambda: app.state.vela)
    app.include_router(health_router)
    install_problem_handlers(app)
    app.include_router(rest_router)
    app.include_router(checkout_router)
    if settings.vela_upstream_mode == REPLAY:
        app.include_router(replay_router)
    app.router.routes.extend(mcp_routes(app.state.mcp, settings.vela_public_url))
    return app


app = create_app()
