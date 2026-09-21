"""The six agent tools, independent of the web framework.

Every function returns a dict the agent can use; refusals carry an 'error' code and a
safe 'say' sentence, and every call writes an audit row under the tool's own name.

Persistence arrives as a PreauthStore (interfaces/store.py), never as a concrete class,
so this module has no knowledge of SQLite.
"""
from __future__ import annotations

import json

from errors import error_codes as codes
from errors.exceptions import ScopeError
from interfaces.store import PreauthStore
from mapper.blocker import report_to_dict
from policies import preauthorisation as rules
from policies.similarity import similar_cases
from utils.normalise import PROVIDER_ID, REQUEST_REF, normalise_ref

MAX_VERIFY_ATTEMPTS = 2
NO_POLICY_SAY = "No policy applies to this service date, so a qualified reviewer must handle it."
CASE_GONE_SAY = "I can't find that request any more. Let me pass you to a colleague."


def _refuse(store: PreauthStore, conv, action, code, say, request_ref=None):
    store.audit("agent", action, "refused", conv, request_ref, {"error": code})
    return {"ok": False, "error": code, "say": say}


def _scoped(store: PreauthStore, conv: str, request_ref: str):
    s = store.session(conv)
    if s is None or not s["verified"]:
        raise ScopeError(codes.SESSION_NOT_VERIFIED, "I need to verify the provider and request first.")
    if s["request_ref"] != request_ref:
        raise ScopeError(codes.CASE_SCOPE_VIOLATION, "I can only discuss the request verified on this call.")
    return s


# UC all: verify ---------------------------------------------------------------
def verify_session(store: PreauthStore, conv: str, provider_id: str, request_ref: str) -> dict:
    s = store.ensure_session(conv)
    if s["verified"]:
        return _refuse(store, conv, "verify_session", codes.ALREADY_VERIFIED,
                       "This call is already verified for one request.", s["request_ref"])
    if s["attempts"] >= MAX_VERIFY_ATTEMPTS:
        return _refuse(store, conv, "verify_session", codes.VERIFICATION_LOCKED,
                       "I can't verify this request on this call. Please contact provider services.")

    pid, ref = normalise_ref(provider_id), normalise_ref(request_ref)
    case = store.cases.get(ref)
    prov = store.providers.get(pid)
    ok = (PROVIDER_ID.match(pid) and REQUEST_REF.match(ref) and case is not None
          and prov is not None and prov["active"] and case["provider_id"] == pid)
    if not ok:
        n = store.record_attempt(conv)
        return _refuse(store, conv, "verify_session", codes.VERIFICATION_FAILED,
                       "Those details don't match a request from your facility." +
                       (" Please check and try once more." if n < MAX_VERIFY_ATTEMPTS else ""))

    store.bind_session(conv, ref, pid)
    store.audit("agent", "verify_session", "ok", conv, ref)
    return {"ok": True, "request_ref": ref, "say": f"Verified request {ref}."}


# UC1-UC6: diagnose ----------------------------------------------------------------
def get_case_blockers(store: PreauthStore, conv: str, request_ref: str,
                      _action: str = "get_case_blockers") -> dict:
    """Blockers for the verified request. `_action` is the tool name to audit under, so
    recheck_case appears in the trail as itself rather than as this function."""
    ref = normalise_ref(request_ref)
    try:
        _scoped(store, conv, ref)
    except ScopeError as e:
        return _refuse(store, conv, _action, e.code, e.say, ref)

    case = store.case_with_documents(ref)
    if case is None:
        return _refuse(store, conv, _action, codes.CASE_NOT_FOUND, CASE_GONE_SAY, ref)
    try:
        report = rules.find_blockers(case, store.policies)
    except rules.NoPolicyForDate:
        return _refuse(store, conv, _action, codes.NO_POLICY_FOR_DATE, NO_POLICY_SAY, ref)

    store.audit("agent", _action, "ok", conv, ref,
                {"tier": report.suggested_tier.value, "blockers": [b.rule_id for b in report.blockers]})
    return {"ok": True, **report_to_dict(report)}


# UC1: resolve --------------------------------------------------------------------
def record_evidence_reference(store: PreauthStore, conv: str, request_ref: str, doc_type: str,
                              doc_ref: str) -> dict:
    ref = normalise_ref(request_ref)
    try:
        _scoped(store, conv, ref)
    except ScopeError as e:
        return _refuse(store, conv, "record_evidence_reference", e.code, e.say, ref)

    case = store.cases.get(ref)
    if case is None:
        return _refuse(store, conv, "record_evidence_reference", codes.CASE_NOT_FOUND, CASE_GONE_SAY, ref)
    try:
        allowed = rules.required_doc_types(case, store.policies)
    except rules.NoPolicyForDate:
        return _refuse(store, conv, "record_evidence_reference", codes.NO_POLICY_FOR_DATE, NO_POLICY_SAY, ref)
    if doc_type not in allowed:
        return _refuse(store, conv, "record_evidence_reference", codes.DOC_TYPE_NOT_REQUIRED,
                       "That document type isn't required for this request.", ref)

    store.add_document(ref, doc_type, doc_ref.strip())
    store.audit("agent", "record_evidence_reference", "ok", conv, ref, {"doc_type": doc_type})
    spoken_type = doc_type.replace("_", " ")
    return {"ok": True, "say": f"Recorded {spoken_type} reference {doc_ref.strip()}."}


def recheck_case(store: PreauthStore, conv: str, request_ref: str) -> dict:
    return get_case_blockers(store, conv, request_ref, _action="recheck_case")


# hand-off ----------------------------------------------------------------------------
def send_to_review(store: PreauthStore, conv: str, request_ref: str, tier: str, summary: str) -> dict:
    ref = normalise_ref(request_ref)
    try:
        _scoped(store, conv, ref)
    except ScopeError as e:
        return _refuse(store, conv, "send_to_review", e.code, e.say, ref)

    case = store.case_with_documents(ref)
    if case is None:
        return _refuse(store, conv, "send_to_review", codes.CASE_NOT_FOUND, CASE_GONE_SAY, ref)

    try:
        report = rules.find_blockers(case, store.policies)
        original = report_to_dict(rules.find_blockers(store.cases[ref], store.policies))["blockers"]
    except rules.NoPolicyForDate:
        return _refuse(store, conv, "send_to_review", codes.NO_POLICY_FOR_DATE, NO_POLICY_SAY, ref)

    try:
        requested = rules.Tier(tier)
    except ValueError:
        return _refuse(store, conv, "send_to_review", codes.INVALID_TIER, "I couldn't route that.", ref)

    # the agent may raise a tier, never lower it below what the rules require
    final = max(requested, report.suggested_tier, key=lambda t: rules.TIER_ORDER[t])

    # One open review item per request. A repeated hand-off returns the item already
    # waiting rather than opening a rival one that could be decided the other way.
    open_item = store.open_review_for(ref)
    if open_item is not None:
        final = max(final, rules.Tier(open_item["tier"]), key=lambda t: rules.TIER_ORDER[t])
        review_ref = open_item["review_ref"]
        if final.value != open_item["tier"]:
            store.raise_review_tier(review_ref, final.value)
        store.audit("agent", "send_to_review", "reused", conv, ref,
                    {"review_ref": review_ref, "tier": final.value})
        return {"ok": True, "review_ref": review_ref, "tier": final.value,
                "similar_cases": json.loads(open_item["report_json"]).get("similar_cases", []),
                "say": f"This request is already with a reviewer under reference {review_ref}."}

    package = {**report_to_dict(report), "original_blockers": original}
    package["similar_cases"] = similar_cases(store.review_packages_excluding(ref), store.cases, ref, original)

    review_ref = store.create_review(ref, conv, final.value, summary[:1000], package)
    store.audit("agent", "send_to_review", "ok", conv, ref, {"review_ref": review_ref, "tier": final.value})
    return {"ok": True, "review_ref": review_ref, "tier": final.value,
            "similar_cases": package["similar_cases"],
            "say": f"Your review reference is {review_ref}. A qualified employee will make the decision."}


def transfer_to_human(store: PreauthStore, conv: str, reason: str,
                      callback: bool = False, consent: bool = False) -> dict:
    """`consent` is asserted by the agent from what the caller said; the call recording is
    the evidence for it. What this enforces is that no callback is arranged unless that
    consent has been written to the session row and read back."""
    s = store.ensure_session(conv)
    if callback and not consent:
        return _refuse(store, conv, "transfer_to_human", codes.CALLBACK_WITHOUT_CONSENT,
                       "I can arrange a callback only if you agree to be called back.", s["request_ref"])
    if callback:
        store.set_callback_consent(conv)
        if not store.callback_consent(conv):
            return _refuse(store, conv, "transfer_to_human", codes.CONSENT_NOT_RECORDED,
                           "I couldn't record your consent, so I'll pass you to a colleague instead.",
                           s["request_ref"])

    store.audit("agent", "transfer_to_human", "ok", conv, s["request_ref"],
                {"reason": reason, "callback": callback, "consent_recorded": callback})
    return {"ok": True, "say": "I'm passing you to a member of the team now." if not callback
            else "A member of the team will call you back about this request."}
