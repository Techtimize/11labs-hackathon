"""The reviewer queue, the decision, and the audit trail. Reviewer token only, except
the queue page itself, which asks for the token in the browser."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from core.config import settings
from dto.request.review import DecisionIn
from errors import error_codes as codes
from errors.handlers import decision_error
from security.auth import reviewer_auth
from security.session import COOKIE, TTL_SECONDS, mint
from services import review as review_svc

from ..dependencies import StoreDep
from ..templating import templates

router = APIRouter()




@router.get("/review/queue", dependencies=[reviewer_auth])
def queue(store: StoreDep):
    return review_svc.pending_queue(store)


@router.get("/review/history", dependencies=[reviewer_auth])
def history(store: StoreDep):
    return review_svc.decided_history(store)


@router.get("/review/{review_ref}/rules", dependencies=[reviewer_auth])
def rules(review_ref: str, store: StoreDep):
    out = review_svc.rules_for(store, review_ref)
    if out is None:
        raise HTTPException(404, codes.NOT_FOUND)
    return out


@router.get("/review/{review_ref}/transcript", dependencies=[reviewer_auth])
def transcript(review_ref: str, store: StoreDep):
    out = review_svc.transcript_for(store, review_ref)
    if out is None:
        raise HTTPException(404, codes.NOT_FOUND)
    return out


@router.post("/review/{review_ref}/decision", dependencies=[reviewer_auth])
def decision(review_ref: str, b: DecisionIn, store: StoreDep):
    out = review_svc.decide(store, review_ref, b.decision, b.reviewer)
    if not out["ok"]:
        raise decision_error(out["error"])
    return out


@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request):
    """Serving the page opens a reviewer session, so the queue is there on arrival.

    Everything behind it still checks that session, and the API keeps the bearer token.
    Put a sign-in in front of this line before the data stops being synthetic.
    """
    page = templates.TemplateResponse(request, "review.html", {})
    page.set_cookie(COOKIE, mint("Reviewer"), max_age=TTL_SECONDS, httponly=True,
                    samesite="strict", secure=settings.app_env != "dev", path="/")
    return page


@router.get("/audit/{request_ref}", dependencies=[reviewer_auth])
def audit(request_ref: str, store: StoreDep):
    return review_svc.audit_trail(store, request_ref)
