"""call_session: which request a conversation is verified for, attempts, consent."""
from __future__ import annotations

import sqlite3
import time

from ..connection import Database


class SqliteSessionRepository:
    def __init__(self, database: Database):
        self._db = database

    def session(self, conversation_id: str) -> sqlite3.Row | None:
        with self._db.lock:
            return self._db.connection.execute("SELECT * FROM call_session WHERE conversation_id=?",
                                               (conversation_id,)).fetchone()

    def ensure_session(self, conversation_id: str) -> sqlite3.Row:
        with self._db.lock:
            self._db.connection.execute(
                "INSERT OR IGNORE INTO call_session (conversation_id, created_at) VALUES (?,?)",
                (conversation_id, time.time()))
            self._db.connection.commit()
            row = self._db.connection.execute("SELECT * FROM call_session WHERE conversation_id=?",
                                              (conversation_id,)).fetchone()
        if row is None:
            raise RuntimeError("call_session row missing after insert")
        return row

    def record_attempt(self, conversation_id: str) -> int:
        with self._db.lock:
            self._db.connection.execute(
                "UPDATE call_session SET attempts=attempts+1 WHERE conversation_id=?", (conversation_id,))
            self._db.connection.commit()
        return self.ensure_session(conversation_id)["attempts"]

    def bind_session(self, conversation_id: str, request_ref: str, provider_id: str) -> None:
        with self._db.lock:
            self._db.connection.execute(
                "UPDATE call_session SET verified=1, request_ref=?, provider_id=? WHERE conversation_id=?",
                (request_ref, provider_id, conversation_id))
            self._db.connection.commit()

    def set_callback_consent(self, conversation_id: str) -> None:
        with self._db.lock:
            self._db.connection.execute(
                "UPDATE call_session SET callback_consent=1 WHERE conversation_id=?", (conversation_id,))
            self._db.connection.commit()

    def callback_consent(self, conversation_id: str) -> bool:
        """Read consent back from the row, so a callback rests on a stored fact."""
        row = self.session(conversation_id)
        return bool(row is not None and row["callback_consent"])
