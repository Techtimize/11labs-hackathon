"""Single source of truth for which tools exist and which workflow node may use them.

A test fails if this drifts from agent/tools.json, or if any node can reach a
reviewer-only action.
"""

AGENT_TOOLS = {
    "verify_session", "get_case_blockers", "record_evidence_reference",
    "recheck_case", "send_to_review", "transfer_to_human",
}

NODE_TOOLS = {
    "disclosure": set(),
    "verify": {"verify_session", "transfer_to_human"},
    "diagnose": {"get_case_blockers", "transfer_to_human"},
    "resolve": {"record_evidence_reference", "recheck_case", "transfer_to_human"},
    "handoff": {"send_to_review", "transfer_to_human"},
}

REVIEWER_ONLY = {"decide"}
