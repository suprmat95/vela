"""App FastAPI di Vela: un solo processo per REST, MCP e webhook (RNF-02).

``create_app`` è la factory usata dai test; ``app`` è l'istanza per ``uvicorn vela.app:app``.
In replay il dominio è costruito su Postgres con gli adapter finti; il lifespan carica il
catalogo dalla fixture se la tabella è vuota e riprende le prenotazioni pendenti (RF-27).
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
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import Product
from vela.domain.usecases import Vela
from vela.surfaces.health import router as health_router
from vela.surfaces.replay import router as replay_router

REPLAY = "replay"
CatalogLoader = Callable[[], List[Product]]


def build_vela(settings: Settings, engine: Engine) -> Tuple[Vela, BookingRunner, CatalogLoader]:
    if settings.vela_upstream_mode != REPLAY:
        raise RuntimeError("VELA_UPSTREAM_MODE=%s non disponibile prima di M5: usare replay"
                           % settings.vela_upstream_mode)
    hofj = ReplayHofJ()
    vela = Vela(PostgresRepositories(engine), hofj, FakePayments(settings.vela_public_url),
                DEFAULT_TRAVELER)
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
    app.include_router(health_router)
    if settings.vela_upstream_mode == REPLAY:
        app.include_router(replay_router)
    return app


app = create_app()
