"""Everything the pre-authorisation services need from persistence, as one dependency.

The services take a single store argument because every use case touches several
tables (a hand-off reads the session, the case and the review queue, and writes the
audit). This protocol is that argument's type; database/store.py is the concrete one.
"""
from __future__ import annotations

from typing import Protocol

from .audit_repository import AuditRepository
from .case_repository import CaseRepository
from .review_repository import ReviewRepository
from .session_repository import SessionRepository
from .transcript_repository import TranscriptRepository


class PreauthStore(SessionRepository, CaseRepository, ReviewRepository, TranscriptRepository,
                   AuditRepository, Protocol):
    providers: dict
    cases: dict
    policies: list
