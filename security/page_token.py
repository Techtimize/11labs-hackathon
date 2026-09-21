"""Short-lived tokens that let the public call page, and only it, mint a session.

The page is handed a token when it is served; /session/signed-url requires it. It costs
an attacker a page load per session instead of a bare GET, and the rate limit caps the
rest. The secret is per process, so tokens die with a restart.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import Header, HTTPException

from errors import error_codes as codes

_PAGE_SECRET = secrets.token_bytes(32)
PAGE_TOKEN_TTL_SECONDS = 600


def mint_page_token() -> str:
    issued = int(time.time())
    mac = hmac.new(_PAGE_SECRET, str(issued).encode(), hashlib.sha256).hexdigest()
    return f"{issued}.{mac}"


def require_page_token(x_page_token: str = Header(default="")) -> None:
    issued_raw, _, provided = x_page_token.partition(".")
    try:
        issued = int(issued_raw)
    except ValueError:
        raise HTTPException(401, codes.PAGE_TOKEN_MISSING) from None
    if time.time() - issued > PAGE_TOKEN_TTL_SECONDS:
        raise HTTPException(401, codes.PAGE_TOKEN_EXPIRED)
    expected = hmac.new(_PAGE_SECRET, str(issued).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(401, codes.PAGE_TOKEN_INVALID)
