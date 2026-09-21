"""Stable error codes.

These strings appear in tool responses, audit rows and HTTP detail bodies, and the
tests assert on them, so the values are part of the contract. Add codes here rather
than inlining new literals.
"""
from __future__ import annotations

# session and scope
SESSION_NOT_VERIFIED = "session_not_verified"
CASE_SCOPE_VIOLATION = "case_scope_violation"
ALREADY_VERIFIED = "already_verified"
VERIFICATION_LOCKED = "verification_locked"
VERIFICATION_FAILED = "verification_failed"

# case and policy
CASE_NOT_FOUND = "case_not_found"
NO_POLICY_FOR_DATE = "no_policy_for_date"
DOC_TYPE_NOT_REQUIRED = "doc_type_not_required"
INVALID_TIER = "invalid_tier"

# hand-off
CALLBACK_WITHOUT_CONSENT = "callback_without_consent"
CONSENT_NOT_RECORDED = "consent_not_recorded"

# reviewer decision
NOT_FOUND = "not_found"
ALREADY_DECIDED = "already_decided"
INVALID_DECISION = "invalid_decision"
TRANSCRIPT_PENDING = "transcript_pending"

# transport
UNAUTHORISED = "unauthorised"
RATE_LIMITED = "rate_limited"
PAGE_TOKEN_MISSING = "page_token_missing"
PAGE_TOKEN_EXPIRED = "page_token_expired"
PAGE_TOKEN_INVALID = "page_token_invalid"
SIGNED_URL_UNAVAILABLE = "signed_url_unavailable"
INVALID_JSON = "invalid_json"
NO_CONVERSATION_ID = "no_conversation_id"
