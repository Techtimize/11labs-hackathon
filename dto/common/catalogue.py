"""Reference data the rules run against: providers, submitted requests, policy versions.

Today it comes from synthetic fixtures; in production it would come from eClaimLink
and the payer's policy service. Either way the rest of the code sees this shape.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Catalogue:
    providers: dict
    cases: dict
    policies: list
