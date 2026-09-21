"""The SQLite connection and the lock that serialises it."""
from __future__ import annotations

import sqlite3
import threading
from typing import Self

from .models.schema import SCHEMA


class Database:
    """One SQLite connection, serialised by a lock.

    FastAPI runs synchronous endpoints in a thread pool, and sqlite3 opens an implicit
    transaction before each write. Without the lock, one thread's commit can commit
    another thread's half-finished write, so every repository statement holds it.
    """

    def __init__(self, path: str = ":memory:"):
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        if path != ":memory:":
            # WAL lets readers run while one writer commits; busy_timeout makes a
            # contended write wait rather than fail instantly.
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
