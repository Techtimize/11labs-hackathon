"""Fixed-window per-client rate limiting, in process.

Small on purpose: enough that an unauthenticated endpoint cannot be used to mint
ElevenLabs sessions in bulk or to flood the webhook receiver. A multi-instance
deployment moves the counters to a shared store.
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

from errors import error_codes as codes

MAX_TRACKED_CLIENTS = 10_000


class RateLimit:
    """A FastAPI dependency allowing `limit` requests per `window` seconds per client."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._hits.get(client, []) if now - t < self.window]
            if len(recent) >= self.limit:
                self._hits[client] = recent
                raise HTTPException(429, codes.RATE_LIMITED)
            recent.append(now)
            self._hits[client] = recent
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                self._evict(now)

    def _evict(self, now: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]
        for k in stale:
            del self._hits[k]

    def reset(self) -> None:
        """Drop all counters. Counters outlive a request, so tests clear them between cases."""
        with self._lock:
            self._hits.clear()
