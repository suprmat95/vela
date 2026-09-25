"""``GET /health``: pubblico, riporta lo stato del DB (RNF-06, parte M0)."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from vela.adapters.db import check_db

router = APIRouter()


@router.get("/health")
def health(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    db_ok = engine is not None and check_db(engine)
    if db_ok:
        return JSONResponse({"status": "ok", "db": "ok"})
    return JSONResponse({"status": "degraded", "db": "error"}, status_code=503)
