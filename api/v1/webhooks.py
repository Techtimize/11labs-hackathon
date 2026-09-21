"""ElevenLabs post-call webhook: verify the signature, parse, hand to the service."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from errors import error_codes as codes
from errors.exceptions import BadSignature
from security.webhook_signature import verify
from services import transcript as transcript_svc

from ..dependencies import StoreDep, webhook_limit

router = APIRouter()


@router.post("/webhooks/elevenlabs/post-call", dependencies=[webhook_limit])
async def post_call(request: Request, store: StoreDep):
    raw = await request.body()
    try:
        verify(request.headers.get("elevenlabs-signature", ""), raw, settings.elevenlabs_webhook_secret)
    except BadSignature as e:
        raise HTTPException(401, f"signature_{e}") from None

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, codes.INVALID_JSON) from None

    data = body.get("data") if isinstance(body, dict) else None
    conv = data.get("conversation_id") if isinstance(data, dict) else None
    if not conv or not isinstance(conv, str):
        raise HTTPException(422, codes.NO_CONVERSATION_ID)

    transcript_svc.record_post_call(store, conv, body)
    return {"ok": True}
