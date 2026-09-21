"""A stored row as the upper layers see it: readable by column name, and convertible
with dict().

sqlite3.Row satisfies this, and so does a plain dict, so services, policies and
mappers never import sqlite3.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class Record(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def keys(self) -> Iterable[str]: ...
