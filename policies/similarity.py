"""Which earlier review items look like this one. Pure: the rows are fetched by the
review repository and passed in, so this module never touches the database."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

from interfaces.record import Record


def similar_cases(rows: Iterable[Record], cases: Mapping[str, dict], request_ref: str,
                  blockers: list[dict], limit: int = 3) -> list[str]:
    """Earlier review items with the same procedure and the same blocker rules.

    `rows` are review items other than this request's, newest first, each with
    review_ref, request_ref and report_json.
    """
    proc = cases[request_ref]["procedure_code"]
    rules_now = sorted(b["rule_id"] for b in blockers)
    out = []
    for row in rows:
        other = json.loads(row["report_json"])
        # "original_blockers" when present, else "blockers". The fallback is read without
        # indexing, so a package holding neither key is skipped rather than raising.
        other_blockers = other["original_blockers"] if "original_blockers" in other \
            else other.get("blockers", [])
        if cases.get(row["request_ref"], {}).get("procedure_code") == proc and \
                sorted(b["rule_id"] for b in other_blockers) == rules_now:
            out.append(row["review_ref"])
            if len(out) >= limit:
                break
    return out
