"""What a reviewer can do: see the queue, decide, read the audit trail.

Reachable only with the reviewer token; no agent tool calls anything here. Refusals
carry no 'say' and write no audit row: they are answered to a person at a screen, not
spoken on a call. A recorded decision is audited.
"""
from __future__ import annotations

from errors import error_codes as codes
from interfaces.store import PreauthStore
from mapper.audit import audit_event
from mapper.review import queue_item

DECISIONS = {"approve", "deny", "request_more"}


def pending_queue(store: PreauthStore) -> list[dict]:
    """Undecided items, tier 2 first, each saying whether its transcript has arrived."""
    return [queue_item(r, store.has_transcript(r["conversation_id"])) for r in store.queue()]


def audit_trail(store: PreauthStore, request_ref: str) -> list[dict]:
    return [audit_event(r) for r in store.audit_for(request_ref)]


def decide(store: PreauthStore, review_ref: str, decision: str, reviewer: str) -> dict:
    item = store.review(review_ref)
    if item is None:
        return {"ok": False, "error": codes.NOT_FOUND}
    if item["decision"] is not None:
        return {"ok": False, "error": codes.ALREADY_DECIDED}
    if decision not in DECISIONS:
        return {"ok": False, "error": codes.INVALID_DECISION}
    if not store.has_transcript(item["conversation_id"]):
        return {"ok": False, "error": codes.TRANSCRIPT_PENDING}

    if not store.decide(review_ref, decision, reviewer):
        return {"ok": False, "error": codes.ALREADY_DECIDED}

    store.audit("reviewer", "decision", decision, item["conversation_id"], item["request_ref"],
                {"review_ref": review_ref, "reviewer": reviewer})
    return {"ok": True, "decision": decision}
