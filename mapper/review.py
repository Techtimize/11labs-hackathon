"""A review_item row to the shape the reviewer queue returns. Pure."""
from __future__ import annotations

from interfaces.record import Record


def queue_item(row: Record, transcript_ready: bool) -> dict:
    return dict(row) | {"transcript_ready": transcript_ready}
