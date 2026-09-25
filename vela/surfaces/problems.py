"""Errori RFC 7807 della superficie REST (RF-40).

Solo i path sotto ``/v1`` rispondono ``application/problem+json``; ``/health``, ``/replay`` e
le pagine di FastAPI tengono il formato predefinito. ``type`` è uno slug relativo
(``/problems/<slug>``); ``say`` è la frase italiana che un agente può leggere al viaggiatore
(RF-42). Il corpo non contiene mai messaggi di eccezioni interne né il token ricevuto.
"""
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (http_exception_handler,
                                        request_validation_exception_handler)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException

from vela.domain.orders import NotFound

PROBLEM_JSON = "application/problem+json"
REST_PREFIX = "/v1"
KINDS_IT = {"intent": "intento", "proposal": "proposta", "order": "ordine"}
HTTP_PROBLEMS = {404: ("not-found", "Risorsa non trovata"),
                 405: ("method-not-allowed", "Metodo non consentito")}
SAY_NOT_FOUND = "Non trovo più questa richiesta. Ripartiamo dalla tua idea di viaggio?"
SAY_HTTP = "La richiesta non è andata a buon fine. Riproviamo?"
SAY_INVALID = "La richiesta non è completa. Riproviamo descrivendo di nuovo il viaggio."
SAY_RETRY = "Qualcosa è andato storto da parte mia. Riprova tra un minuto."


class Problem(Exception):
    def __init__(self, status: int, slug: str, title: str, detail: str, say: str,
                 headers: Optional[dict] = None, extra: Optional[dict] = None):
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.say = say
        self.headers = headers or {}
        self.extra = extra or {}


def unauthorized() -> Problem:
    return Problem(401, "unauthorized", "Token mancante o non valido",
                   "Serve l'header Authorization: Bearer con il token di Vela.",
                   "Non sono autorizzato a usare il servizio di prenotazione.",
                   headers={"WWW-Authenticate": "Bearer"})


def rest_not_configured() -> Problem:
    return Problem(503, "rest-not-configured", "Superficie REST non configurata",
                   "VELA_API_TOKEN non è impostata: la superficie REST è chiusa.",
                   "Il servizio di prenotazione non è ancora configurato. Riprova più tardi.")


def domain_unavailable() -> Problem:
    return Problem(503, "domain-unavailable", "Dominio non disponibile",
                   "DATABASE_URL non è impostata: i casi d'uso non sono disponibili.",
                   "Il servizio di prenotazione non è disponibile in questo momento. Riprova tra poco.")


def not_found(kind: str, id: str) -> Problem:
    return Problem(404, "not-found", "Risorsa non trovata",
                   "Id sconosciuto (%s): %s" % (KINDS_IT.get(kind, kind), id), SAY_NOT_FOUND)


def is_rest(request: Request) -> bool:
    path = request.url.path
    return path == REST_PREFIX or path.startswith(REST_PREFIX + "/")


def problem_response(request: Request, problem: Problem) -> JSONResponse:
    body = {"type": "/problems/" + problem.slug, "title": problem.title,
            "status": problem.status, "detail": problem.detail,
            "instance": request.url.path, "say": problem.say}
    body.update(problem.extra)
    return JSONResponse(body, status_code=problem.status, headers=problem.headers,
                        media_type=PROBLEM_JSON)


def install_problem_handlers(app: FastAPI) -> None:
    async def on_problem(request: Request, exc: Problem):
        return problem_response(request, exc)

    async def on_not_found(request: Request, exc: NotFound):
        return problem_response(request, not_found(exc.kind, exc.id))

    async def on_http(request: Request, exc: HTTPException):
        if not is_rest(request):
            return await http_exception_handler(request, exc)
        slug, title = HTTP_PROBLEMS.get(exc.status_code, ("http-error", "Errore HTTP"))
        say = SAY_NOT_FOUND if exc.status_code == 404 else SAY_HTTP
        return problem_response(request, Problem(exc.status_code, slug, title, str(exc.detail),
                                                 say, headers=dict(exc.headers or {})))

    async def on_validation(request: Request, exc: RequestValidationError):
        if not is_rest(request):
            return await request_validation_exception_handler(request, exc)
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem_response(request, Problem(
            422, "invalid-request", "Richiesta non valida",
            "Il corpo o i parametri non rispettano il formato atteso.", SAY_INVALID,
            extra={"errors": errors}))

    async def on_error(request: Request, exc: Exception):
        if not is_rest(request):
            return PlainTextResponse("Internal Server Error", status_code=500)
        return problem_response(request, Problem(
            500, "internal-error", "Errore interno",
            "Errore inatteso: il dettaglio è nei log del server.", SAY_RETRY))

    app.add_exception_handler(Problem, on_problem)
    app.add_exception_handler(NotFound, on_not_found)
    app.add_exception_handler(HTTPException, on_http)
    app.add_exception_handler(RequestValidationError, on_validation)
    app.add_exception_handler(Exception, on_error)
