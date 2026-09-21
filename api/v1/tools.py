"""The six agent tools. Agent token only; each call is one service call."""
from __future__ import annotations

from fastapi import APIRouter

from dto.request.tools import EvidenceIn, RefIn, ReviewIn, TransferIn, VerifyIn
from security.auth import agent_auth
from services import preauthorisation as svc

from ..dependencies import StoreDep, tool_limit

router = APIRouter()


@router.post("/tools/verify_session", dependencies=[agent_auth, tool_limit])
def t_verify(b: VerifyIn, store: StoreDep):
    return svc.verify_session(store, b.conversation_id, b.provider_id, b.request_ref)


@router.post("/tools/get_case_blockers", dependencies=[agent_auth, tool_limit])
def t_blockers(b: RefIn, store: StoreDep):
    return svc.get_case_blockers(store, b.conversation_id, b.request_ref)


@router.post("/tools/record_evidence_reference", dependencies=[agent_auth, tool_limit])
def t_evidence(b: EvidenceIn, store: StoreDep):
    return svc.record_evidence_reference(store, b.conversation_id, b.request_ref, b.doc_type, b.doc_ref)


@router.post("/tools/recheck_case", dependencies=[agent_auth, tool_limit])
def t_recheck(b: RefIn, store: StoreDep):
    return svc.recheck_case(store, b.conversation_id, b.request_ref)


@router.post("/tools/send_to_review", dependencies=[agent_auth, tool_limit])
def t_review(b: ReviewIn, store: StoreDep):
    return svc.send_to_review(store, b.conversation_id, b.request_ref, b.tier, b.summary)


@router.post("/tools/transfer_to_human", dependencies=[agent_auth, tool_limit])
def t_transfer(b: TransferIn, store: StoreDep):
    return svc.transfer_to_human(store, b.conversation_id, b.reason, b.callback, b.consent)
