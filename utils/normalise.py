"""Reference normalisation. Callers speak references aloud, so digits may arrive in
Arabic-Indic form and separators in any dash or space variant."""
from __future__ import annotations

import re

REQUEST_REF = re.compile(r"^PA-\d{4}-\d{4}$")
PROVIDER_ID = re.compile(r"^DHA-F-\d{4}$")

_DIGITS = {ord(c): str(i % 10) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹")}
_SEPARATORS = re.compile(r"[\s_\u2010-\u2015\u2212-]+")


def normalise_ref(value: str) -> str:
    """Fold spoken or pasted references to one canonical form: PA-2026-0001, DHA-F-0001."""
    return _SEPARATORS.sub("-", value.translate(_DIGITS).strip().upper()).strip("-")
