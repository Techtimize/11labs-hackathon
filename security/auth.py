"""The two credentials. They are never interchangeable.

AGENT_TOOL_TOKEN reaches /tools/*. REVIEWER_TOKEN reaches /review/* and /audit/*, either
as a bearer token or as the session cookie a reviewer gets after signing in once.
An unset token rejects everything rather than accepting everything.
"""
from __future__ import annotations

import hmac

from fastapi import Cookie, Depends, Header, HTTPException

from core.config import settings
from errors import error_codes as codes

from .session import COOKIE, reviewer_of


def holds_token(expected: str, authorization: str) -> bool:
    """Compare as bytes: compare_digest rejects str with non-ASCII characters."""
    got = authorization.encode("utf-8", "surrogatepass")
    return bool(expected) and hmac.compare_digest(got, f"Bearer {expected}".encode())


def _bearer(expected: str):
    def dep(authorization: str = Header(default="")):
        if not holds_token(expected, authorization):
            raise HTTPException(401, codes.UNAUTHORISED)
    return dep


def _reviewer(authorization: str = Header(default=""),
              authrelay_reviewer: str = Cookie(default="", alias=COOKIE)):
    if holds_token(settings.reviewer_token, authorization):
        return "reviewer"
    signed_in = reviewer_of(authrelay_reviewer)
    if signed_in is None:
        raise HTTPException(401, codes.UNAUTHORISED)
    return signed_in


agent_auth = Depends(_bearer(settings.agent_tool_token))
reviewer_auth = Depends(_reviewer)
ReviewerName = Depends(_reviewer)
