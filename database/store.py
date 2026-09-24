"""The concrete PreauthStore: one Database, five repositories, and the catalogue.

Services and tests call store.session(...), store.audit(...) and so on. This class keeps
those names and hands each call to the repository that owns the table, so the split
into repositories changed no call site. The catalogue is passed in rather than loaded
here, which keeps this package from importing the fixtures integration.

Swap SQLite for Postgres by replacing Database and the repositories; nothing above this
package changes.
"""
from __future__ import annotations

import sqlite3
from typing import Self

from dto.common.catalogue import Catalogue

from .connection import Database
from .repositories.audit import SqliteAuditRepository
from .repositories.case import SqliteCaseRepository
from .repositories.review import SqliteReviewRepository
from .repositories.session import SqliteSessionRepository
from .repositories.transcript import SqliteTranscriptRepository


class Store:
    def __init__(self, path: str = ":memory:", *, catalogue: Catalogue):
        self._database = Database(path)
        self.providers: dict = catalogue.providers
        self.cases: dict = catalogue.cases
        self.policies: list = catalogue.policies

        self.sessions = SqliteSessionRepository(self._database)
        self.documents = SqliteCaseRepository(self._database, self.cases)
        self.reviews = SqliteReviewRepository(self._database)
        self.transcripts = SqliteTranscriptRepository(self._database)
        self.audit_log = SqliteAuditRepository(self._database)

    @property
    def db(self) -> sqlite3.Connection:
        """The raw connection. For tests and diagnostics; application code uses the methods."""
        return self._database.connection

    def close(self) -> None:
        self._database.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # cases ---------------------------------------------------------------
    def case_with_documents(self, request_ref: str) -> dict | None:
        return self.documents.case_with_documents(request_ref)

    def add_document(self, request_ref: str, doc_type: str, doc_ref: str) -> None:
        self.documents.add_document(request_ref, doc_type, doc_ref)

    # sessions ------------------------------------------------------------
    def session(self, conversation_id: str) -> sqlite3.Row | None:
        return self.sessions.session(conversation_id)

    def ensure_session(self, conversation_id: str) -> sqlite3.Row:
        return self.sessions.ensure_session(conversation_id)

    def record_attempt(self, conversation_id: str) -> int:
        return self.sessions.record_attempt(conversation_id)

    def bind_session(self, conversation_id: str, request_ref: str, provider_id: str) -> None:
        self.sessions.bind_session(conversation_id, request_ref, provider_id)

    def set_callback_consent(self, conversation_id: str) -> None:
        self.sessions.set_callback_consent(conversation_id)

    def callback_consent(self, conversation_id: str) -> bool:
        return self.sessions.callback_consent(conversation_id)

    # review --------------------------------------------------------------
    def open_review_for(self, request_ref: str) -> sqlite3.Row | None:
        return self.reviews.open_review_for(request_ref)

    def create_review(self, request_ref, conversation_id, tier, summary, report) -> str:
        return self.reviews.create_review(request_ref, conversation_id, tier, summary, report)

    def review_packages_excluding(self, request_ref: str) -> list[sqlite3.Row]:
        return self.reviews.review_packages_excluding(request_ref)

    def raise_review_tier(self, review_ref: str, tier: str) -> None:
        self.reviews.raise_review_tier(review_ref, tier)

    def review(self, review_ref: str) -> sqlite3.Row | None:
        return self.reviews.review(review_ref)

    def queue(self) -> list[sqlite3.Row]:
        return self.reviews.queue()

    def decided(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.reviews.decided(limit)


    def decide(self, review_ref: str, decision: str, reviewer: str) -> bool:
        return self.reviews.decide(review_ref, decision, reviewer)

    # transcripts ---------------------------------------------------------
    def save_transcript(self, conversation_id: str, body: dict) -> bool:
        return self.transcripts.save_transcript(conversation_id, body)

    def transcript(self, conversation_id: str | None) -> sqlite3.Row | None:
        return self.transcripts.transcript(conversation_id)

    def has_transcript(self, conversation_id: str | None) -> bool:
        return self.transcripts.has_transcript(conversation_id)

    # audit ---------------------------------------------------------------
    def audit(self, actor, action, result, conversation_id=None, request_ref=None, detail=None) -> None:
        self.audit_log.audit(actor, action, result, conversation_id, request_ref, detail)

    def audit_for(self, request_ref: str) -> list[sqlite3.Row]:
        return self.audit_log.audit_for(request_ref)

