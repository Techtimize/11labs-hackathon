"""Service error codes to HTTP responses."""
from __future__ import annotations

from fastapi import HTTPException

from . import error_codes as codes

DECISION_STATUS = {codes.NOT_FOUND: 404, codes.TRANSCRIPT_PENDING: 409, codes.ALREADY_DECIDED: 409}


def decision_error(error: str) -> HTTPException:
    """A refused reviewer decision. Anything not listed is a 422."""
    return HTTPException(DECISION_STATUS.get(error, 422), error)
