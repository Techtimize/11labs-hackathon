"""A stored post-call webhook body to the turns a reviewer reads. Pure.

The platform sends {"data": {"transcript": [{"role", "message", "time_in_call_secs"}]}};
anything that does not match is skipped rather than raising.
"""
from __future__ import annotations


def transcript_turns(body: dict) -> list[dict]:
    data = body.get("data") if isinstance(body, dict) else None
    turns = data.get("transcript") if isinstance(data, dict) else None
    out = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        text = turn.get("message") or turn.get("text")
        if not text:
            continue
        out.append({"speaker": "agent" if turn.get("role") == "agent" else "caller",
                    "text": str(text), "at": turn.get("time_in_call_secs")})
    return out
