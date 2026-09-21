"""The public call page, and the gated endpoint it uses to open a voice session."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from errors import error_codes as codes
from security.page_token import mint_page_token, require_page_token

from ..dependencies import SessionsDep, session_limit
from ..templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def call_page(request: Request):
    return templates.TemplateResponse(request, "call.html", {"page_token": mint_page_token()})


@router.get("/session/signed-url", dependencies=[session_limit, Depends(require_page_token)])
async def signed_url(sessions: SessionsDep):
    url = await sessions.signed_url()
    if url is None:
        raise HTTPException(502, codes.SIGNED_URL_UNAVAILABLE)
    return {"signed_url": url}
