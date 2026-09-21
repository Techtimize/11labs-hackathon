from __future__ import annotations

from typing import Protocol


class TranscriptRepository(Protocol):
    """Post-call transcripts. Saving the same conversation twice is a no-op."""

    def save_transcript(self, conversation_id: str, body: dict) -> bool: ...
    def has_transcript(self, conversation_id: str | None) -> bool: ...
