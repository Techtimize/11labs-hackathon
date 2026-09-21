"""Composition root: the only module that names concrete persistence and integrations.

Routes ask for a PreauthStore and a ConversationSessions; this module decides that
those are the SQLite store and the ElevenLabs client. Tests override get_store or
get_conversation_sessions to substitute their own.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from core.config import settings
from database.store import Store
from integrations.elevenlabs.client import ElevenLabsClient
from integrations.fixtures.catalogue import load_catalogue
from interfaces.conversation_sessions import ConversationSessions
from interfaces.store import PreauthStore

from .ratelimit import RateLimit


def build_store(path: str) -> Store:
    """The store the app runs on: SQLite at `path`, loaded with the synthetic catalogue."""
    return Store(path, catalogue=load_catalogue())


def get_store(request: Request) -> PreauthStore:
    return request.app.state.store


StoreDep = Annotated[PreauthStore, Depends(get_store)]


def get_conversation_sessions() -> ConversationSessions:
    return ElevenLabsClient(api_key=settings.elevenlabs_api_key, agent_id=settings.elevenlabs_agent_id)


SessionsDep = Annotated[ConversationSessions, Depends(get_conversation_sessions)]


# Unauthenticated endpoints are the ones worth limiting: minting a session costs
# ElevenLabs credit, and the webhook receiver is open to the internet by design.
tool_limiter = RateLimit(limit=240, window=60)
session_limiter = RateLimit(limit=10, window=60)
webhook_limiter = RateLimit(limit=120, window=60)
LIMITERS = (tool_limiter, session_limiter, webhook_limiter)

tool_limit = Depends(tool_limiter)
session_limit = Depends(session_limiter)
webhook_limit = Depends(webhook_limiter)
