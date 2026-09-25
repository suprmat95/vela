"""App FastAPI di Vela: un solo processo per REST, MCP e webhook (RNF-02).

``create_app`` è la factory usata dai test; ``app`` è l'istanza per ``uvicorn vela.app:app``.
"""
from typing import Optional

from fastapi import FastAPI

from vela.adapters.db import make_engine
from vela.config import Settings
from vela.surfaces.health import router as health_router


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Vela", version="0.1.0")
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url) if settings.database_url else None
    app.include_router(health_router)
    return app


app = create_app()
