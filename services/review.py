"""What a reviewer can do: see the queue, decide, read the audit trail.

Reachable only with the reviewer token; no agent tool calls anything here. Refusals
carry no 'say' and write no audit row: they are answered to a person at a screen, not
spoken on a call. A recorded decision is audited.
"""
from __future__ import annotations

import json

from errors import error_codes as codes
from interfaces.store import PreauthStore
from mapper.audit import audit_event
from mapper.review import queue_item
from mapper.transcript import transcript_turns
from policies import preauthorisation as rules

DECISIONS = {"approve", "deny", "request_more"}


def _provider_of(store: PreauthStore, request_ref: str) -> tuple[str | None, str | None]:
    """The facility a request belongs to, so the queue can be searched by name."""
    provider_id = (store.cases.get(request_ref) or {}).get("provider_id")
    name = (store.providers.get(provider_id) or {}).get("name") if provider_id else None
    return provider_id, name


def _listed(store: PreauthStore, row) -> dict:
    return queue_item(row, store.has_transcript(row["conversation_id"]),
                      *_provider_of(store, row["request_ref"]))


def pending_queue(store: PreauthStore) -> list[dict]:
    """Undecided items, tier 2 first, each saying whether its transcript has arrived."""
    return [_listed(store, r) for r in store.queue()]


def decided_history(store: PreauthStore, limit: int = 50) -> list[dict]:
    """What has already been settled, most recent first, with who decided it."""
    return [_listed(store, r) for r in store.decided(limit)]


def audit_trail(store: PreauthStore, request_ref: str) -> list[dict]:
    return [audit_event(r) for r in store.audit_for(request_ref)]


def rules_for(store: PreauthStore, review_ref: str) -> dict | None:
    """The policy text behind a review item, marking the rules this case actually broke."""
    item = store.review(review_ref)
    if item is None:
        return None
    case = store.cases.get(item["request_ref"])
    if case is None:
        return {"policy_version": None, "rules": []}
    cited = {b["rule_id"] for b in json.loads(item["report_json"]).get("blockers", [])}
    in_force = rules.rules_in_force(case, store.policies)
    in_force["rules"] = [{**rule, "cited": rule["rule_id"] in cited} for rule in in_force["rules"]]
    return in_force


def transcript_for(store: PreauthStore, review_ref: str) -> dict | None:
    """The call behind a review item. None means no such item; an item whose transcript
    has not arrived yet returns stored=False, which is also why it cannot be decided."""
    item = store.review(review_ref)
    if item is None:
        return None
    row = store.transcript(item["conversation_id"])
    if row is None:
        return {"review_ref": review_ref, "stored": False, "turns": []}
    return {"review_ref": review_ref, "stored": True, "received_at": row["received_at"],
            "turns": transcript_turns(json.loads(row["body_json"]))}


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
