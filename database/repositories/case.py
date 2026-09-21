"""document: evidence references captured on a call, merged over the submitted case."""
from __future__ import annotations

import time

from ..connection import Database


class SqliteCaseRepository:
    """`cases` is the catalogue's dict itself, not a copy, so a case added or removed
    there is seen here too."""

    def __init__(self, database: Database, cases: dict):
        self._db = database
        self._cases = cases

    def case_with_documents(self, request_ref: str) -> dict | None:
        base = self._cases.get(request_ref)
        if base is None:
            return None
        with self._db.lock:
            extra = self._db.connection.execute(
                "SELECT doc_type, doc_ref, source FROM document WHERE request_ref=? ORDER BY received_at",
                (request_ref,)).fetchall()
        merged = {d["doc_type"]: d for d in base.get("documents", [])}
        merged.update({r["doc_type"]: dict(r) for r in extra})
        return {**base, "documents": list(merged.values())}

    def add_document(self, request_ref: str, doc_type: str, doc_ref: str) -> None:
        with self._db.lock:
            self._db.connection.execute("INSERT INTO document VALUES (?,?,?,?,?)",
                                        (request_ref, doc_type, doc_ref, "on_call", time.time()))
            self._db.connection.commit()
