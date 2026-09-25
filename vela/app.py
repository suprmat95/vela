"""App FastAPI di Vela: un solo processo per REST e MCP (RNF-02).

La superficie MCP (M3) è innestata su ``/mcp`` in ogni modalità; il suo session manager gira nel
lifespan.

``create_app`` è la factory usata dai test; ``app`` è l'istanza per ``uvicorn vela.app:app``.
In replay il dominio è costruito su Postgres con gli adapter finti; il lifespan carica il
catalogo dalla fixture se la tabella è vuota e riprende le prenotazioni pendenti (RF-27).
La superficie REST (``/v1``) è sempre montata; gli errori sotto ``/v1`` sono RFC 7807.
Nessun webhook Stripe: il pagamento si chiude con ``POST /v1/bookings`` di HofJ e Vela lo scopre
interrogando la Checkout Session (job di M5).
Il pagamento è Stripe se ``STRIPE_SECRET_KEY`` è impostata, altrimenti finto.
"""
from contextlib import asynccontextmanager
from typing import Callable, List, Optional, Tuple

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from vela.adapters.background import BookingRunner
from vela.adapters.db import make_engine
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_postgres import PostgresRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.adapters.stripe_links import StripePayments, build_stripe_client
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import Product
from vela.domain.usecases import Vela
from vela.ports.payments import PaymentsPort
from vela.surfaces.checkout_pages import router as checkout_router
from vela.surfaces.health import router as health_router
from vela.surfaces.mcp import build_mcp, mcp_routes
from vela.surfaces.problems import install_problem_handlers
from vela.surfaces.replay import router as replay_router
from vela.surfaces.rest import router as rest_router

REPLAY = "replay"
CatalogLoader = Callable[[], List[Product]]


def build_payments(settings: Settings) -> PaymentsPort:
    """Stripe se `STRIPE_SECRET_KEY` è impostata (indipendente dall'upstream HofJ), altrimenti
    il pagamento finto. Senza `VELA_PUBLIC_URL` l'avvio si blocca: servono i ritorni del Checkout."""
    if not settings.stripe_secret_key:
        return FakePayments(settings.vela_public_url)
    if not settings.vela_public_url:
        raise RuntimeError("STRIPE_SECRET_KEY richiede VELA_PUBLIC_URL per le pagine di ritorno "
                           "del Checkout")
    return StripePayments(build_stripe_client(settings.stripe_secret_key), settings.vela_public_url)


def build_vela(settings: Settings, engine: Engine) -> Tuple[Vela, BookingRunner, CatalogLoader]:
    if settings.vela_upstream_mode != REPLAY:
        raise RuntimeError("VELA_UPSTREAM_MODE=%s non disponibile prima di M5: usare replay"
                           % settings.vela_upstream_mode)
    hofj = ReplayHofJ()
    extractor = None
    if settings.anthropic_api_key:   # RF-03: senza chiave il fallback è spento, senza errori
        from vela.adapters.haiku import HaikuExtractor
        extractor = HaikuExtractor.from_api_key(settings.anthropic_api_key)
    vela = Vela(PostgresRepositories(engine), hofj, build_payments(settings), DEFAULT_TRAVELER,
                extractor=extractor)
    return vela, BookingRunner(vela.orders), hofj.load_catalog


def bootstrap(vela: Vela, runner, catalog_loader: Optional[CatalogLoader]) -> dict:
    loaded = 0
    if catalog_loader is not None and vela.repos.products.count() == 0:
        products = catalog_loader()
        vela.repos.products.upsert_many(products)
        loaded = len(products)
    return {"catalog_loaded": loaded, "resumed": runner.resume()}


def create_app(settings: Optional[Settings] = None, vela: Optional[Vela] = None, runner=None,
               catalog_loader: Optional[CatalogLoader] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url) if settings.database_url else None
    if vela is None and engine is not None:
        vela, runner, catalog_loader = build_vela(settings, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with app.state.mcp.session_manager.run():
            if app.state.vela is not None:
                app.state.bootstrap = bootstrap(app.state.vela, app.state.runner, app.state.catalog_loader)
            yield
            if app.state.runner is not None:
                app.state.runner.shutdown(wait=False)

    app = FastAPI(title="Vela", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.vela = vela
    app.state.runner = runner
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
