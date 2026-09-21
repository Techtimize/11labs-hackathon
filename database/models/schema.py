"""Stored data: tables, the one-open-review index, and the append-only audit triggers.

Raw DDL applied at startup with CREATE ... IF NOT EXISTS; there is no migration tool.
Table and column names are part of the audit contract and must not change.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS call_session (
    conversation_id TEXT PRIMARY KEY, request_ref TEXT, provider_id TEXT,
    verified INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
    callback_consent INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);

CREATE TABLE IF NOT EXISTS document (
    request_ref TEXT NOT NULL, doc_type TEXT NOT NULL, doc_ref TEXT NOT NULL,
    source TEXT NOT NULL, received_at REAL NOT NULL);

CREATE TABLE IF NOT EXISTS review_item (
    review_ref TEXT PRIMARY KEY, request_ref TEXT NOT NULL, conversation_id TEXT,
    tier TEXT NOT NULL, summary TEXT NOT NULL, report_json TEXT NOT NULL,
    decision TEXT, decided_by TEXT, decided_at REAL, created_at REAL NOT NULL);

-- One undecided review item per request, enforced by the database rather than by
-- a check in the service: a second send_to_review cannot open a rival item that
-- could be decided the other way.
CREATE UNIQUE INDEX IF NOT EXISTS review_item_one_open_per_request
    ON review_item(request_ref) WHERE decision IS NULL;

CREATE TABLE IF NOT EXISTS transcript (
    conversation_id TEXT PRIMARY KEY, body_json TEXT NOT NULL, received_at REAL NOT NULL);

CREATE TABLE IF NOT EXISTS audit_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, conversation_id TEXT, request_ref TEXT, result TEXT NOT NULL, detail TEXT);

CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;

CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""
