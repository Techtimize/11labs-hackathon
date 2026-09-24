"""HTTP-layer tests: token separation, strict bodies, webhook signature, audit trail.

Tokens and the database path are configured before importing main, which reads
settings once at import. Entering TestClient runs the lifespan, so each test gets its
own in-memory store.
"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import unittest

os.environ.setdefault("AGENT_TOOL_TOKEN", "agent-test-token")
os.environ.setdefault("REVIEWER_TOKEN", "reviewer-test-token")
os.environ.setdefault("ELEVENLABS_WEBHOOK_SECRET", "webhook-test-secret")
os.environ.setdefault("DATABASE_PATH", ":memory:")

from fastapi.testclient import TestClient

from api import dependencies as deps
from main import app
from security import page_token
from security.page_token import PAGE_TOKEN_TTL_SECONDS

AGENT = {"Authorization": "Bearer agent-test-token"}
REVIEWER = {"Authorization": "Bearer reviewer-test-token"}
WEBHOOK_SECRET = b"webhook-test-secret"


def signed(body: bytes, offset: int = 0) -> dict:
    ts = int(time.time()) + offset
    sig = hmac.new(WEBHOOK_SECRET, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"elevenlabs-signature": f"t={ts},v0={sig}"}


class ApiTest(unittest.TestCase):
    def setUp(self):
        # Rate-limit counters are process-wide and outlive a request, so clear them
        # between cases or one test's traffic rejects the next one's.
        for limiter in deps.LIMITERS:
            limiter.reset()
        self.client = self.enterContext(TestClient(app))

    @property
    def store(self):
        return app.state.store

    def agent_post(self, path, body):
        return self.client.post(path, headers=AGENT, json=body)


class Lifespan(unittest.TestCase):
    """Not an ApiTest: this owns the client so it can assert on shutdown."""

    def test_store_opens_on_startup_and_closes_on_shutdown(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").json()["status"], "ok")
            store = app.state.store
            self.assertEqual(store.db.execute("SELECT 1").fetchone()[0], 1)

        with self.assertRaises(sqlite3.ProgrammingError):
            store.db.execute("SELECT 1")


class Health(ApiTest):
    def test_health_and_data_mode(self):
        r = self.client.get("/health")
        self.assertEqual(r.json(), {"status": "ok", "data_mode": "synthetic"})
        self.assertEqual(r.headers["X-Data-Mode"], "synthetic")

    def test_six_agent_tools_published(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertEqual(len([p for p in paths if p.startswith("/tools/")]), 6)


class TokensAreNotInterchangeable(ApiTest):
    def test_tools_require_the_agent_token(self):
        self.assertEqual(self.client.post("/tools/get_case_blockers", json={}).status_code, 401)
        r = self.client.post("/tools/get_case_blockers", headers=REVIEWER,
                             json={"conversation_id": "conv-a", "request_ref": "PA-2026-0001"})
        self.assertEqual(r.status_code, 401)

    def test_reviewer_routes_reject_the_agent_token(self):
        self.assertEqual(self.client.get("/review/queue", headers=AGENT).status_code, 401)
        self.assertEqual(self.client.get("/audit/PA-2026-0001", headers=AGENT).status_code, 401)


class StrictBodies(ApiTest):
    def test_unknown_field_is_refused(self):
        r = self.agent_post("/tools/verify_session", {
            "conversation_id": "conv-strict", "provider_id": "DHA-F-0001",
            "request_ref": "PA-2026-0001", "tier": "tier_0_standard_review"})
        self.assertEqual(r.status_code, 422)

    def test_short_conversation_id_is_refused(self):
        r = self.agent_post("/tools/get_case_blockers",
                            {"conversation_id": "ab", "request_ref": "PA-2026-0001"})
        self.assertEqual(r.status_code, 422)


class DecisionNeedsTranscript(ApiTest):
    def test_full_flow_then_decision_gated_on_webhook(self):
        conv = "conv-api-uc1"
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0001"})
        blockers = self.agent_post("/tools/get_case_blockers",
                                   {"conversation_id": conv, "request_ref": "PA-2026-0001"}).json()
        self.assertEqual([b["rule_id"] for b in blockers["blockers"]], ["MRI-LS-02"])

        self.agent_post("/tools/record_evidence_reference", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "doc_type": "prior_conservative_treatment", "doc_ref": "PCT-1001"})
        recheck = self.agent_post("/tools/recheck_case",
                                  {"conversation_id": conv, "request_ref": "PA-2026-0001"}).json()
        self.assertTrue(recheck["review_ready"])

        review_ref = self.agent_post("/tools/send_to_review", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "tier": "tier_0_standard_review", "summary": "Evidence supplied on call."}).json()["review_ref"]

        decide = {"decision": "approve", "reviewer": "rev1"}
        self.assertEqual(self.client.post(f"/review/{review_ref}/decision",
                                          headers=REVIEWER, json=decide).status_code, 409)

        body = json.dumps({"data": {"conversation_id": conv}}).encode()
        self.assertEqual(self.client.post("/webhooks/elevenlabs/post-call",
                                          content=body, headers=signed(body)).json(), {"ok": True})

        self.assertEqual(self.client.post(f"/review/{review_ref}/decision",
                                          headers=REVIEWER, json=decide).json(),
                         {"ok": True, "decision": "approve"})
        self.assertEqual(self.client.post(f"/review/{review_ref}/decision",
                                          headers=REVIEWER, json=decide).status_code, 409)

    def test_unknown_review_ref_is_404(self):
        r = self.client.post("/review/RV-DEADBEEF/decision", headers=REVIEWER,
                             json={"decision": "approve", "reviewer": "rev1"})
        self.assertEqual(r.status_code, 404)


class WebhookSignature(ApiTest):
    def test_bad_signature_rejected(self):
        body = json.dumps({"data": {"conversation_id": "conv-sig"}}).encode()
        r = self.client.post("/webhooks/elevenlabs/post-call", content=body,
                             headers={"elevenlabs-signature": f"t={int(time.time())},v0=deadbeef"})
        self.assertEqual(r.status_code, 401)

    def test_stale_signature_rejected(self):
        body = json.dumps({"data": {"conversation_id": "conv-stale"}}).encode()
        r = self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body, -4000))
        self.assertEqual(r.status_code, 401)

    def test_missing_conversation_id_is_422(self):
        body = json.dumps({"data": {}}).encode()
        r = self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))
        self.assertEqual(r.status_code, 422)

    def test_signed_but_malformed_json_is_400(self):
        body = b"not json at all"
        r = self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))
        self.assertEqual(r.status_code, 400)

    def test_signed_but_non_object_data_is_422(self):
        for payload in ({"data": ["nope"]}, {"data": None}, ["not", "an", "object"]):
            body = json.dumps(payload).encode()
            r = self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))
            self.assertEqual(r.status_code, 422, payload)

    def test_redelivery_is_idempotent(self):
        body = json.dumps({"data": {"conversation_id": "conv-dupe"}}).encode()
        self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))
        self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))
        results = [r["result"] for r in self.store.db.execute(
            "SELECT result FROM audit_event WHERE conversation_id='conv-dupe' ORDER BY id")]
        self.assertEqual(results, ["stored", "duplicate"])


class AuditTrail(ApiTest):
    def test_every_tool_call_is_recorded_in_order(self):
        conv = "conv-api-audit"
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0006"})
        self.agent_post("/tools/get_case_blockers", {"conversation_id": conv, "request_ref": "PA-2026-0006"})
        self.agent_post("/tools/get_case_blockers", {"conversation_id": conv, "request_ref": "PA-2026-0002"})

        rows = self.client.get("/audit/PA-2026-0006", headers=REVIEWER).json()
        self.assertEqual([r["action"] for r in rows], ["verify_session", "get_case_blockers"])
        refused = self.client.get("/audit/PA-2026-0002", headers=REVIEWER).json()
        self.assertEqual(refused[-1]["result"], "refused")


class Pages(ApiTest):
    def test_call_and_review_pages_render(self):
        self.assertIn("Start call", self.client.get("/").text)
        self.assertIn("Reviewer queue", self.client.get("/review").text)


class _FakeSessions:
    URL = "wss://example.invalid/convai/session"

    async def signed_url(self) -> str | None:
        return self.URL


class _RefusingSessions:
    async def signed_url(self) -> str | None:
        return None


class SignedUrlIsGated(ApiTest):
    """Minting a session spends ElevenLabs credit, so it is not a bare public GET."""

    def page_token(self) -> str:
        page = self.client.get("/").text
        token = re.search(r'const PAGE_TOKEN = "([^"]+)"', page)
        self.assertIsNotNone(token, "call page did not embed a page token")
        return token.group(1)

    def test_no_token_is_rejected(self):
        self.assertEqual(self.client.get("/session/signed-url").status_code, 401)

    def test_a_forged_token_is_rejected(self):
        forged = f"{int(time.time())}.{'0' * 64}"
        r = self.client.get("/session/signed-url", headers={"X-Page-Token": forged})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], "page_token_invalid")

    def test_an_expired_token_is_rejected(self):
        stale = int(time.time()) - (PAGE_TOKEN_TTL_SECONDS + 60)
        mac = hmac.new(page_token._PAGE_SECRET, str(stale).encode(), hashlib.sha256).hexdigest()
        r = self.client.get("/session/signed-url", headers={"X-Page-Token": f"{stale}.{mac}"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], "page_token_expired")

    def test_a_page_token_gets_past_the_gate(self):
        # The platform client is replaced, so this never leaves the machine.
        app.dependency_overrides[deps.get_conversation_sessions] = _FakeSessions
        self.addCleanup(app.dependency_overrides.clear)
        r = self.client.get("/session/signed-url", headers={"X-Page-Token": self.page_token()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"signed_url": _FakeSessions.URL})

    def test_a_platform_refusal_is_a_502(self):
        app.dependency_overrides[deps.get_conversation_sessions] = _RefusingSessions
        self.addCleanup(app.dependency_overrides.clear)
        r = self.client.get("/session/signed-url", headers={"X-Page-Token": self.page_token()})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["detail"], "signed_url_unavailable")


class SignedUrlIsRateLimited(unittest.TestCase):


    def test_signed_url_is_limited(self):
        deps.session_limiter.reset()
        self.addCleanup(deps.session_limiter.reset)
        with TestClient(app) as client:
            codes = {client.get("/session/signed-url").status_code for _ in range(12)}
        self.assertIn(429, codes)


class ReviewerFieldsAreBounded(ApiTest):
    def _open_item(self) -> str:
        conv = "conv-bounds"
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0001"})
        ref = self.agent_post("/tools/send_to_review", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "tier": "tier_0_standard_review", "summary": "x"}).json()["review_ref"]
        self.store.save_transcript(conv, {"transcript": []})
        return ref

    def test_an_unbounded_reviewer_name_is_rejected(self):
        r = self.client.post(f"/review/{self._open_item()}/decision", headers=REVIEWER,
                             json={"decision": "approve", "reviewer": "r" * 500})
        self.assertEqual(r.status_code, 422)

    def test_an_empty_reviewer_name_is_rejected(self):
        r = self.client.post(f"/review/{self._open_item()}/decision", headers=REVIEWER,
                             json={"decision": "approve", "reviewer": ""})
        self.assertEqual(r.status_code, 422)

    def test_an_invented_decision_is_rejected_before_the_service(self):
        r = self.client.post(f"/review/{self._open_item()}/decision", headers=REVIEWER,
                             json={"decision": "escalate", "reviewer": "rev1"})
        self.assertEqual(r.status_code, 422)


class HistoryEndpoint(ApiTest):
    def test_agent_token_is_refused(self):
        self.assertEqual(self.client.get("/review/history", headers=AGENT).status_code, 401)

    def test_decided_case_appears_with_its_reviewer(self):
        conv = "conv-api-hist"
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0001"})
        ref = self.agent_post("/tools/send_to_review", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "tier": "tier_0_standard_review", "summary": "x"}).json()["review_ref"]
        self.assertEqual(self.client.get("/review/history", headers=REVIEWER).json(), [])

        body = json.dumps({"data": {"conversation_id": conv}}).encode()
        self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))
        self.client.post(f"/review/{ref}/decision", headers=REVIEWER,
                         json={"decision": "deny", "reviewer": "rev9"})

        history = self.client.get("/review/history", headers=REVIEWER).json()
        self.assertEqual([(h["review_ref"], h["decision"], h["decided_by"]) for h in history],
                         [(ref, "deny", "rev9")])
        self.assertEqual(self.client.get("/review/queue", headers=REVIEWER).json(), [])


class ReviewerSession(ApiTest):
    """Opening the page starts the session, so the queue is there without typing a token."""

    def test_the_queue_is_closed_until_the_page_is_opened(self):
        self.assertEqual(self.client.get("/review/queue").status_code, 401)

        page = self.client.get("/review")
        cookie = page.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie.replace("samesite", "SameSite"))
        self.assertEqual(self.client.get("/review/queue").status_code, 200)

    def test_the_agent_token_is_still_refused(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/review/queue", headers=AGENT).status_code, 401)

    def test_a_forged_cookie_is_refused(self):
        self.client.cookies.clear()
        self.client.cookies.set("authrelay_reviewer", "9999999999.UmV2aWV3ZXI=.deadbeef")
        self.assertEqual(self.client.get("/review/queue").status_code, 401)
        self.client.cookies.clear()


class RulesEndpoint(ApiTest):
    def test_reviewer_only_and_cites_the_failed_rule(self):
        conv = "conv-api-rules"
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0001"})
        ref = self.agent_post("/tools/send_to_review", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "tier": "tier_0_standard_review", "summary": "x"}).json()["review_ref"]

        self.assertEqual(self.client.get(f"/review/{ref}/rules", headers=AGENT).status_code, 401)
        self.assertEqual(self.client.get("/review/RV-DEADBEEF/rules", headers=REVIEWER).status_code, 404)

        out = self.client.get(f"/review/{ref}/rules", headers=REVIEWER).json()
        self.assertEqual(out["policy_version"], "2026-07-01")
        self.assertEqual([r["rule_id"] for r in out["rules"] if r["cited"]], ["MRI-LS-02"])


class TranscriptEndpoint(ApiTest):
    def _item(self, conv="conv-api-tr"):
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0001"})
        return conv, self.agent_post("/tools/send_to_review", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "tier": "tier_0_standard_review", "summary": "x"}).json()["review_ref"]

    def test_agent_token_cannot_read_a_transcript(self):
        _, ref = self._item()
        self.assertEqual(self.client.get(f"/review/{ref}/transcript", headers=AGENT).status_code, 401)

    def test_unknown_review_ref_is_404(self):
        self.assertEqual(self.client.get("/review/RV-DEADBEEF/transcript",
                                         headers=REVIEWER).status_code, 404)

    def test_turns_are_served_after_the_webhook(self):
        conv, ref = self._item()
        waiting = self.client.get(f"/review/{ref}/transcript", headers=REVIEWER).json()
        self.assertEqual((waiting["stored"], waiting["turns"]), (False, []))

        body = json.dumps({"data": {"conversation_id": conv, "transcript": [
            {"role": "agent", "message": "This call is recorded.", "time_in_call_secs": 2}]}}).encode()
        self.client.post("/webhooks/elevenlabs/post-call", content=body, headers=signed(body))

        stored = self.client.get(f"/review/{ref}/transcript", headers=REVIEWER).json()
        self.assertTrue(stored["stored"])
        self.assertEqual(stored["turns"], [{"speaker": "agent", "text": "This call is recorded.", "at": 2}])


class ReviewerPageDoesNotInterpolateHtml(ApiTest):
    def test_the_queue_is_built_with_the_dom(self):
        page = self.client.get("/review").text
        self.assertIn("textContent", page)
        self.assertNotIn("innerHTML", page)
        self.assertNotIn("onclick=", page)

    def test_an_injected_summary_is_returned_as_data_not_markup(self):
        conv = "conv-xss"
        self.agent_post("/tools/verify_session", {"conversation_id": conv, "provider_id": "DHA-F-0001",
                                                  "request_ref": "PA-2026-0001"})
        payload = "<img src=x onerror=alert(1)>"
        self.agent_post("/tools/send_to_review", {
            "conversation_id": conv, "request_ref": "PA-2026-0001",
            "tier": "tier_0_standard_review", "summary": payload})
        item = self.client.get("/review/queue", headers=REVIEWER).json()[0]
        self.assertEqual(item["summary"], payload)  # stored verbatim for the reviewer to read
