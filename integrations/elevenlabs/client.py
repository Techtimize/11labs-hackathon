"""ElevenLabs Agents Platform: the one call the control plane makes to it.

The signed URL lets the browser open a conversation without ever holding the API key.
A non-200 answer returns None; the route turns that into a 502.
"""
from __future__ import annotations

import httpx

SIGNED_URL_ENDPOINT = "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"


class ElevenLabsClient:
    def __init__(self, api_key: str, agent_id: str, timeout: float = 5):
        self._api_key = api_key
        self._agent_id = agent_id
        self._timeout = timeout

    async def signed_url(self) -> str | None:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.get(SIGNED_URL_ENDPOINT, params={"agent_id": self._agent_id},
                            headers={"xi-api-key": self._api_key})
        if r.status_code != 200:
            return None
        return r.json()["signed_url"]
