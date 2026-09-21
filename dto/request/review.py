"""The reviewer's decision body."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The reviewer name is self-declared behind a shared token, so it is bounded and
    # recorded as a claim. Per-reviewer identity is the SSO step on the production path.
    decision: Literal["approve", "deny", "request_more"]
    reviewer: str = Field(min_length=1, max_length=120)
