from __future__ import annotations

from typing import Protocol


class CaseRepository(Protocol):
    """Submitted requests merged with evidence captured on calls."""

    def case_with_documents(self, request_ref: str) -> dict | None: ...
    def add_document(self, request_ref: str, doc_type: str, doc_ref: str) -> None: ...
