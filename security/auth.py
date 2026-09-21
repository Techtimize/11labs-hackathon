"""The two bearer credentials. They are never interchangeable.

AGENT_TOOL_TOKEN reaches /tools/*. REVIEWER_TOKEN reaches /review/* and /audit/*.
An unset token rejects everything rather than accepting everything.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException

from core.config import settings
from errors import error_codes as codes


def _bearer(expected: str):
    """Compare as bytes: compare_digest rejects str with non-ASCII characters."""
    want = f"Bearer {expected}".encode()

    def dep(authorization: str = Header(default="")):
        got = authorization.encode("utf-8", "surrogatepass")
        if not expected or not hmac.compare_digest(got, want):
            raise HTTPException(401, codes.UNAUTHORISED)
    return dep


agent_auth = Depends(_bearer(settings.agent_tool_token))
reviewer_auth = Depends(_bearer(settings.reviewer_token))
