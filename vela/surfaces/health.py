"""``GET /health``: pubblico; stato del DB, età del catalogo, quota e coda (RNF-06).

Il codice di stato dipende solo dal DB (è il controllo di salute di Render). ``catalog`` è
``null`` con il DB irraggiungibile, senza dominio o se la lettura fallisce; ``quota`` è lo stato
del token bucket condiviso (M18) e ``queue`` l'età del più vecchio acquisto in coda e il totale
degli itinerari orfani (M18), con le stesse regole per ``null``.
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


def quota_info(vela) -> Optional[dict]:
    if vela is None:
        return None
    try:
        snap = vela.repos.quota.snapshot(vela.now())
    except SQLAlchemyError:
        return None
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in snap.items()}


def queue_info(vela) -> Optional[dict]:
    if vela is None:
        return None
    try:
        oldest = vela.repos.jobs.oldest_purchase_enqueued_at()
        orphans = vela.repos.orders.orphan_itineraries_total()
    except SQLAlchemyError:
        return None
    age = None if oldest is None else max(int((vela.now() - oldest).total_seconds()), 0)
    return {"oldest_purchase_age_seconds": age, "orphan_itineraries": orphans}


@router.get("/health")
def health(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    db_ok = engine is not None and check_db(engine)
    body = {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error",
            "catalog": catalog_info(request.app.state.vela) if db_ok else None,
            "quota": quota_info(request.app.state.vela) if db_ok else None,
            "queue": queue_info(request.app.state.vela) if db_ok else None}
    return JSONResponse(body, status_code=200 if db_ok else 503)
