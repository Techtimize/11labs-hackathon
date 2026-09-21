"""HMAC verification for the ElevenLabs post-call webhook.

ElevenLabs-Signature: t=<unix timestamp>,v0=<hex hmac-sha256>. The signed payload is
the timestamp, a full stop, then the raw request body. The platform's own tolerance is
30 minutes, and the Python SDK does not expose a verifier, so this is implemented here.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from errors.exceptions import BadSignature

TOLERANCE_SECONDS = 1800  # 30 minutes, matching the platform


def _parse(header: str) -> tuple[int, str]:
    fields = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        return int(fields["t"]), fields["v0"]
    except (KeyError, ValueError):
        raise BadSignature("malformed") from None


def verify(header: str, body: bytes, secret: str) -> None:
    """Raise BadSignature unless the header matches this exact body and is recent."""
    if not secret:
        raise BadSignature("unconfigured")
    timestamp, provided = _parse(header)
    if abs(time.time() - timestamp) > TOLERANCE_SECONDS:
        raise BadSignature("stale")
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), provided.encode("utf-8", "surrogatepass")):
        raise BadSignature("mismatch")
