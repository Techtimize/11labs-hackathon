"""Review tiers: a shared value object used by policy, services, mappers and storage."""
from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    T0 = "tier_0_standard_review"
    T1 = "tier_1_priority_review"
    T2 = "tier_2_mandatory_human"


TIER_ORDER = {Tier.T0: 0, Tier.T1: 1, Tier.T2: 2}
