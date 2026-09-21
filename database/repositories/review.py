"""review_item: the human gate. At most one undecided item per request."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid

from ..connection import Database


class SqliteReviewRepository:
    def __init__(self, database: Database):
        self._db = database

    def open_review_for(self, request_ref: str) -> sqlite3.Row | None:
        """The undecided review item for this request, if one is already open."""
        with self._db.lock:
            return self._db.connection.execute(
                "SELECT * FROM review_item WHERE request_ref=? AND decision IS NULL",
                (request_ref,)).fetchone()

    def create_review(self, request_ref, conversation_id, tier, summary, report) -> str:
        ref = "RV-" + uuid.uuid4().hex[:8].upper()
        with self._db.lock:
            self._db.connection.execute(
                "INSERT INTO review_item (review_ref, request_ref, conversation_id, tier, summary,"
                " report_json, created_at) VALUES (?,?,?,?,?,?,?)",
                (ref, request_ref, conversation_id, tier, summary, json.dumps(report), time.time()))
            self._db.connection.commit()
        return ref

    def review_packages_excluding(self, request_ref: str) -> list[sqlite3.Row]:
        """Every other request's review items, newest first, for similar-case matching."""
        with self._db.lock:
            return self._db.connection.execute(
                "SELECT review_ref, request_ref, report_json FROM review_item "
                "WHERE request_ref != ? ORDER BY created_at DESC", (request_ref,)).fetchall()

    def raise_review_tier(self, review_ref: str, tier: str) -> None:
        """Set the tier on an open item. The caller has already taken the higher of the two."""
        with self._db.lock:
            self._db.connection.execute(
                "UPDATE review_item SET tier=? WHERE review_ref=? AND decision IS NULL", (tier, review_ref))
            self._db.connection.commit()

    def review(self, review_ref: str) -> sqlite3.Row | None:
        with self._db.lock:
            return self._db.connection.execute("SELECT * FROM review_item WHERE review_ref=?",
                                               (review_ref,)).fetchone()

    def queue(self) -> list[sqlite3.Row]:
        with self._db.lock:
            return self._db.connection.execute(
                "SELECT * FROM review_item WHERE decision IS NULL "
                "ORDER BY CASE tier WHEN 'tier_2_mandatory_human' THEN 0 "
                "WHEN 'tier_1_priority_review' THEN 1 ELSE 2 END, created_at").fetchall()

    def decide(self, review_ref: str, decision: str, reviewer: str) -> bool:
        """Claim an undecided item. False means someone else decided it first."""
        with self._db.lock:
            cur = self._db.connection.execute(
                "UPDATE review_item SET decision=?, decided_by=?, decided_at=? "
                "WHERE review_ref=? AND decision IS NULL",
                (decision, reviewer, time.time(), review_ref))
            self._db.connection.commit()
            return cur.rowcount == 1
