"""Deterministic pre-authorisation checks. Standard library only, no I/O.

Same inputs always give the same BlockerReport, so every tier is reproducible
from the audit log.

The safe sentence in `_say` is kept here rather than in a mapper: which words the
agent may speak about a blocker is a governance decision, and policies may not
depend on mappers.
"""
from __future__ import annotations

from datetime import date

from dto.common.blocker import Blocker, BlockerReport
from dto.common.tier import TIER_ORDER, Tier
from errors.exceptions import NoPolicyForDate

__all__ = [
    "TIER_ORDER",
    "Blocker",
    "BlockerReport",
    "NoPolicyForDate",
    "Tier",
    "find_blockers",
    "required_doc_types",
    "rules_in_force",
    "select_policy",
]


def select_policy(policies: list[dict], service_date: date) -> dict:
    """Latest policy whose effective_from is on or before the service date."""
    valid = [p for p in policies if date.fromisoformat(p["effective_from"]) <= service_date]
    if not valid:
        raise NoPolicyForDate(service_date.isoformat())
    return max(valid, key=lambda p: p["effective_from"])


def _tier_for(blockers: list[Blocker], clinical_flag: bool) -> Tier:
    if clinical_flag or any(b.code in ("POLICY_AMBIGUITY", "CLINICAL") for b in blockers):
        return Tier.T2
    if any(not b.resolvable_on_call for b in blockers):
        return Tier.T1
    return Tier.T0


def _say(report: BlockerReport) -> str:
    if report.review_ready:
        return "The request is complete and can go to a qualified reviewer."
    parts = [f"{b.detail} (rule {b.rule_id}, policy {b.policy_version})" for b in report.blockers]
    return "The request is waiting on: " + "; ".join(parts) + "."


def find_blockers(case: dict, policies: list[dict]) -> BlockerReport:
    service_date = date.fromisoformat(case["service_date"])
    policy = select_policy(policies, service_date)
    version = policy["version"]
    blockers: list[Blocker] = []

    req = policy["procedures"].get(case["procedure_code"])
    if req is None:
        blockers.append(Blocker("POLICY_AMBIGUITY", "Procedure is not in the schedule of benefits",
                                "GEN-00", version, False))
    else:
        received = {d["doc_type"] for d in case.get("documents", [])}
        for doc in req["required_documents"]:
            if doc["type"] not in received:
                blockers.append(Blocker("MISSING_DOC", doc["label"], doc["rule_id"], version, True))
        if case["diagnosis_code"] not in req["accepted_diagnoses"]:
            blockers.append(Blocker("CODE_MISMATCH",
                                    f"Diagnosis {case['diagnosis_code']} is not accepted for {req['label']}",
                                    req["code_rule_id"], version, False))

    if not case.get("member_active", True):
        blockers.append(Blocker("ELIGIBILITY", "Member is not active on the service date",
                                "ELG-01", version, False))
    if case.get("clinical_flag"):
        blockers.append(Blocker("CLINICAL", "Clinical review is required", "CLN-01", version, False))

    report = BlockerReport(request_ref=case["request_ref"], policy_version=version,
                           blockers=blockers, review_ready=not blockers,
                           suggested_tier=_tier_for(blockers, bool(case.get("clinical_flag"))))
    report.say = _say(report)
    return report


RULE_TEXT = {
    "ELG-01": "The member must be active on the service date.",
    "CLN-01": "A request carrying a clinical flag is decided by a clinical reviewer.",
    "GEN-00": "Only procedures listed in the schedule of benefits can be authorised.",
}


def rules_in_force(case: dict, policies: list[dict]) -> dict:
    """The rules the case was checked against, as a reviewer would read them."""
    policy = select_policy(policies, date.fromisoformat(case["service_date"]))
    procedure = policy["procedures"].get(case["procedure_code"])
    rules = []
    if procedure:
        for doc in procedure["required_documents"]:
            rules.append({"rule_id": doc["rule_id"],
                          "text": f"{procedure['label']} requires {doc['label'][0].lower()}"
                                  f"{doc['label'][1:]}."})
        rules.append({"rule_id": procedure["code_rule_id"],
                      "text": f"{procedure['label']} is accepted for diagnoses "
                              + ", ".join(procedure["accepted_diagnoses"]) + "."})
    else:
        rules.append({"rule_id": "GEN-00", "text": RULE_TEXT["GEN-00"]})
    rules += [{"rule_id": rule_id, "text": RULE_TEXT[rule_id]} for rule_id in ("ELG-01", "CLN-01")]
    return {"policy_version": policy["version"], "effective_from": policy["effective_from"],
            "procedure_code": case["procedure_code"],
            "procedure": procedure["label"] if procedure else None, "rules": rules}


def required_doc_types(case: dict, policies: list[dict]) -> set[str]:
    policy = select_policy(policies, date.fromisoformat(case["service_date"]))
    req = policy["procedures"].get(case["procedure_code"])
    return {d["type"] for d in req["required_documents"]} if req else set()
