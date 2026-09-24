"""transcript: post-call webhook bodies. A reviewer cannot decide until one is stored."""
from __future__ import annotations

import json
import sqlite3
import time

from ..connection import Database


class SqliteTranscriptRepository:
    def __init__(self, database: Database):
        self._db = database

    def save_transcript(self, conversation_id: str, body: dict) -> bool:
        with self._db.lock:
            cur = self._db.connection.execute("INSERT OR IGNORE INTO transcript VALUES (?,?,?)",
                                              (conversation_id, json.dumps(body), time.time()))
            self._db.connection.commit()
            return cur.rowcount == 1  # False = duplicate delivery

    def transcript(self, conversation_id: str | None) -> sqlite3.Row | None:
        if not conversation_id:
            return None
        with self._db.lock:
            return self._db.connection.execute(
                "SELECT conversation_id, body_json, received_at FROM transcript WHERE conversation_id=?",
                (conversation_id,)).fetchone()

    def has_transcript(self, conversation_id: str | None) -> bool:
        if not conversation_id:
            return False
        with self._db.lock:
            return self._db.connection.execute("SELECT 1 FROM transcript WHERE conversation_id=?",
                                               (conversation_id,)).fetchone() is not None
