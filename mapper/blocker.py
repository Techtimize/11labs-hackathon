"""BlockerReport to the dict shape the agent tools return. Pure: no I/O, no decisions."""
from __future__ import annotations

from dataclasses import asdict

from dto.common.blocker import BlockerReport


def report_to_dict(report: BlockerReport) -> dict:
    d = asdict(report)
    d["suggested_tier"] = report.suggested_tier.value
    return d
