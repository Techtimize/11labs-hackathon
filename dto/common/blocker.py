"""What the rules engine returns about a request. Conversion to a response dict lives in
mapper/blocker.py, so these stay plain data with no knowledge of any transport."""
from __future__ import annotations

from dataclasses import dataclass, field

from .tier import Tier


@dataclass(frozen=True)
class Blocker:
    code: str  # MISSING_DOC | CODE_MISMATCH | ELIGIBILITY | POLICY_AMBIGUITY | CLINICAL
    detail: str
    rule_id: str
    policy_version: str
    resolvable_on_call: bool
    confidence: str = "high"
    source: str = "rules_engine"


@dataclass
class BlockerReport:
    request_ref: str
    policy_version: str
    blockers: list[Blocker] = field(default_factory=list)
    review_ready: bool = False
    suggested_tier: Tier = Tier.T0
    say: str = ""  # one safe sentence the agent may speak
