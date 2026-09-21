from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from .record import Record


class AuditRepository(Protocol):
    """Append-only. Implementations must refuse to change or remove a written row."""

    def audit(self, actor: str, action: str, result: str, conversation_id: str | None = None,
              request_ref: str | None = None, detail: Any = None) -> None: ...
    def audit_for(self, request_ref: str) -> Sequence[Record]: ...
