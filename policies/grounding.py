"""Post-call groundedness: which rule IDs the agent spoke that no tool gave it."""
from __future__ import annotations

import re

RULE_ID = re.compile(r"\b(?:[A-Z]{2,4}-){1,2}(?:\d{2}|CODE)\b")


def ungrounded_rule_ids(agent_text: str, tool_results: list[dict]) -> set[str]:
    """Rule IDs the agent spoke that no tool returned in this conversation."""
    returned = {b["rule_id"] for r in tool_results for b in r.get("blockers", [])}
    spoken = set(RULE_ID.findall(agent_text))
    return spoken - returned
