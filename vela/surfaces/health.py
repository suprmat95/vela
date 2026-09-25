"""``GET /health``: pubblico; stato del DB, età del catalogo e quota nota (RNF-06).

Il codice di stato dipende solo dal DB (è il controllo di salute di Render). ``catalog`` è
``null`` con il DB irraggiungibile, senza dominio o se la lettura fallisce; ``quota`` resta
``null`` finché il guardiano della quota non esiste (M5).
"""
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from vela.adapters.db import check_db

router = APIRouter()


def catalog_info(vela) -> Optional[dict]:
    if vela is None:
        return None
    try:
        count = vela.repos.products.count()
        fetched_at = vela.repos.products.last_fetched_at()
    except SQLAlchemyError:
        return None
    if fetched_at is None:
        return {"products": count, "fetched_at": None, "age_seconds": None}
    age = max(int((vela.now() - fetched_at).total_seconds()), 0)
    return {"products": count, "fetched_at": fetched_at.isoformat(), "age_seconds": age}


@router.get("/health")
def health(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    db_ok = engine is not None and check_db(engine)
    body = {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error",
            "catalog": catalog_info(request.app.state.vela) if db_ok else None,
            "quota": None}
    return JSONResponse(body, status_code=200 if db_ok else 503)
