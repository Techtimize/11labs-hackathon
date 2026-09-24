"""Reviewer sessions: the token is exchanged once for a signed cookie.

The cookie carries only the reviewer's name and when it was issued, signed with a secret
that lives in this process, so a restart ends every session. The reviewer token itself is
never held by the browser.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

_SECRET = secrets.token_bytes(32)
TTL_SECONDS = 8 * 60 * 60
COOKIE = "authrelay_reviewer"


def _sign(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def mint(reviewer: str) -> str:
    payload = f"{int(time.time())}.{base64.urlsafe_b64encode(reviewer.encode()).decode()}"
    return f"{payload}.{_sign(payload)}"


def reviewer_of(cookie: str | None) -> str | None:
    """The name in a valid, unexpired cookie, or None."""
    if not cookie or cookie.count(".") != 2:
        return None
    issued_raw, name_raw, provided = cookie.split(".")
    if not hmac.compare_digest(_sign(f"{issued_raw}.{name_raw}"), provided):
        return None
    try:
        issued = int(issued_raw)
        name = base64.urlsafe_b64decode(name_raw).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return name if time.time() - issued <= TTL_SECONDS else None
