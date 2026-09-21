from __future__ import annotations

from typing import Protocol


class ConversationSessions(Protocol):
    """Mints a browser session with the voice platform. None means the platform refused."""

    async def signed_url(self) -> str | None: ...
