"""Request bodies for the six agent tools. Unknown fields are rejected."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(min_length=4, max_length=128)


class VerifyIn(Strict):
    provider_id: str
    request_ref: str


class RefIn(Strict):
    request_ref: str


class EvidenceIn(RefIn):
    doc_type: str
    doc_ref: str = Field(max_length=64)


class ReviewIn(RefIn):
    tier: str
    summary: str = Field(max_length=1000)


class TransferIn(Strict):
    reason: str = Field(max_length=200)
    callback: bool = False
    consent: bool = False
