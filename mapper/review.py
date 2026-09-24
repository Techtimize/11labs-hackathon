"""A review_item row to the shape the reviewer queue returns. Pure.

The provider is carried alongside so a reviewer can search by the facility that called,
not only by reference.
"""
from __future__ import annotations

from interfaces.record import Record


def queue_item(row: Record, transcript_ready: bool, provider_id: str | None = None,
               provider: str | None = None) -> dict:
    return dict(row) | {"transcript_ready": transcript_ready,
                        "provider_id": provider_id, "provider": provider}
