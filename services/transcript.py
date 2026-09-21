"""Storing a post-call transcript. Signature checking happens before this is reached."""
from __future__ import annotations

from interfaces.store import PreauthStore


def record_post_call(store: PreauthStore, conversation_id: str, body: dict) -> bool:
    """Store the transcript and audit the delivery. False means a redelivery, ignored."""
    new = store.save_transcript(conversation_id, body)
    store.audit("system", "post_call_webhook", "stored" if new else "duplicate", conversation_id)
    return new
