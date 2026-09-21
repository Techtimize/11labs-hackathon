"""The reviewer queue, the decision, and the audit trail. Reviewer token only, except
the queue page itself, which asks for the token in the browser."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from dto.request.review import DecisionIn
from errors.handlers import decision_error
from security.auth import reviewer_auth
from services import review as review_svc

from ..dependencies import StoreDep
from ..templating import templates

router = APIRouter()


@router.get("/review/queue", dependencies=[reviewer_auth])
def queue(store: StoreDep):
    return review_svc.pending_queue(store)


@router.post("/review/{review_ref}/decision", dependencies=[reviewer_auth])
def decision(review_ref: str, b: DecisionIn, store: StoreDep):
    out = review_svc.decide(store, review_ref, b.decision, b.reviewer)
    if not out["ok"]:
        raise decision_error(out["error"])
    return out


@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request):
    return templates.TemplateResponse(request, "review.html", {})


@router.get("/audit/{request_ref}", dependencies=[reviewer_auth])
def audit(request_ref: str, store: StoreDep):
    return review_svc.audit_trail(store, request_ref)
