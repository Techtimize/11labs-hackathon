"""Synthetic stand-in for eClaimLink request data and the payer's policy service.

Reads data/cases.json and data/policies.json. Each call returns fresh objects, so one
store's changes to its cases never leak into another's.
"""
from __future__ import annotations

import json
from pathlib import Path

from dto.common.catalogue import Catalogue

DATA = Path(__file__).resolve().parents[2] / "data"


def load_catalogue(data_dir: Path = DATA) -> Catalogue:
    seed = json.loads((data_dir / "cases.json").read_text(encoding="utf-8"))
    policies = json.loads((data_dir / "policies.json").read_text(encoding="utf-8"))["policies"]
    return Catalogue(providers=seed["providers"],
                     cases={c["request_ref"]: c for c in seed["cases"]},
                     policies=policies)
