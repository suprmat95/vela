"""Superficie REST (RF-40, RF-43): i cinque casi d'uso di RF-39 sotto ``/v1``.

Bearer statico ``VELA_API_TOKEN``; senza token configurato ogni endpoint risponde 503. Ogni
risposta di successo è ``{"outcome": ..., **to_dict()}``: gli esiti previsti (domanda, niente di
compatibile, dati mancanti) sono 200, non errori. Gli errori sono RFC 7807
(``vela/surfaces/problems.py``). Ordine dei controlli: token, validazione, dominio.
"""
import hmac
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, StringConstraints

from vela.domain.models import (AcceptResponse, IntentCreated, IntentQuestion,
                                MissingTravelerData, NoMatch, OrderStatusResponse, ProposalMade,
                                TravelerProfile, profile_from_dict)
from vela.domain.usecases import Vela
from vela.surfaces.problems import domain_unavailable, rest_not_configured, unauthorized

bearer = HTTPBearer(auto_error=False)

OUTCOMES = {IntentCreated: "intent_created", IntentQuestion: "question",
            ProposalMade: "proposal", NoMatch: "no_match", AcceptResponse: "order",
            MissingTravelerData: "missing_traveler_data", OrderStatusResponse: "order_status"}
CREATED = (IntentCreated, AcceptResponse)


def require_token(request: Request,
                  creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> None:
    expected = request.app.state.settings.vela_api_token
    if not expected:
        raise rest_not_configured()
    if creds is None or not hmac.compare_digest(creds.credentials.encode(), expected.encode()):
        raise unauthorized()


def get_vela(request: Request) -> Vela:
    vela = request.app.state.vela
    if vela is None:
        raise domain_unavailable()
    return vela


def reply(result) -> JSONResponse:
    status = 201 if isinstance(result, CREATED) else 200
    return JSONResponse({"outcome": OUTCOMES[type(result)], **result.to_dict()}, status_code=status)


class ParticipantIn(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ProfileIn(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pax: Optional[int] = Field(default=None, ge=1)
    participants: List[ParticipantIn] = []


def to_profile(p: Optional[ProfileIn]) -> Optional[TravelerProfile]:
    return None if p is None else profile_from_dict(p.model_dump())


class IntentIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    profile: Optional[ProfileIn] = None


class RejectIn(BaseModel):
    reason: Optional[str] = None


class AcceptIn(BaseModel):
    traveler: Optional[ProfileIn] = None


router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(require_token)])


@router.post("/intents")
def create_intent(body: IntentIn, vela: Vela = Depends(get_vela)) -> JSONResponse:
    return reply(vela.create_intent(body.text, to_profile(body.profile)))


@router.get("/intents/{intent_id}/proposal")
def get_proposal(intent_id: str, vela: Vela = Depends(get_vela)) -> JSONResponse:
    return reply(vela.get_proposal(intent_id))


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, body: Optional[RejectIn] = None,
                    vela: Vela = Depends(get_vela)) -> JSONResponse:
    reason = body.reason if body is not None else None
    return reply(vela.reject_proposal(proposal_id, reason or ""))


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str, body: Optional[AcceptIn] = None,
                    vela: Vela = Depends(get_vela)) -> JSONResponse:
    traveler = to_profile(body.traveler) if body is not None else None
    return reply(vela.accept_proposal(proposal_id, traveler))


@router.get("/orders/{order_id}")
def get_order_status(order_id: str, vela: Vela = Depends(get_vela)) -> JSONResponse:
    return reply(vela.get_order_status(order_id))
