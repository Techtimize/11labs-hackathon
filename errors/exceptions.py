"""Application exceptions.

Collected here so every layer raises from one place. Behaviour and messages are
unchanged from when these lived in service.py, rules.py and signature.py.
"""
from __future__ import annotations


class ScopeError(Exception):
    """A tool call that falls outside what this call was verified for."""

    def __init__(self, code: str, say: str):
        super().__init__(code)
        self.code, self.say = code, say


class NoPolicyForDate(LookupError):
    """No policy version is effective on the service date."""


class BadSignature(Exception):
    """The webhook signature header is missing, stale, malformed or wrong."""
