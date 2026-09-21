"""audit_event: append-only. The table's triggers reject UPDATE and DELETE."""
from __future__ import annotations

import json
import sqlite3
import time

from ..connection import Database


class SqliteAuditRepository:
    def __init__(self, database: Database):
        self._db = database

    def audit(self, actor, action, result, conversation_id=None, request_ref=None, detail=None) -> None:
        with self._db.lock:
            self._db.connection.execute(
                "INSERT INTO audit_event (at, actor, action, conversation_id, request_ref, result, detail)"
                " VALUES (?,?,?,?,?,?,?)",
                (time.time(), actor, action, conversation_id, request_ref, result,
                 json.dumps(detail) if detail is not None else None))
            self._db.connection.commit()

    def audit_for(self, request_ref: str) -> list[sqlite3.Row]:
        with self._db.lock:
            return self._db.connection.execute(
                "SELECT * FROM audit_event WHERE request_ref=? ORDER BY id", (request_ref,)).fetchall()
