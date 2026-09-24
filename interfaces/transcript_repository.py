from __future__ import annotations

from typing import Protocol

from .record import Record


class TranscriptRepository(Protocol):
    """Post-call transcripts. Saving the same conversation twice is a no-op."""

    def save_transcript(self, conversation_id: str, body: dict) -> bool: ...
    def transcript(self, conversation_id: str | None) -> Record | None: ...
    def has_transcript(self, conversation_id: str | None) -> bool: ...
