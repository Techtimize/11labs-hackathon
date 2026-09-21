"""An audit_event row to the shape /audit/{request_ref} returns. Pure."""
from __future__ import annotations

from interfaces.record import Record


def audit_event(row: Record) -> dict:
    return dict(row)
