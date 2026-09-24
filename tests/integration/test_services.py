"""Service-layer tests: each use case run against a real in-memory SQLite store.

Integration rather than unit because every case goes through the store; the pure
policy, signature and normalisation tests live in tests/unit/."""
import json
import sqlite3
import time
import unittest
from datetime import date

from database.store import Store
from integrations.fixtures.catalogue import load_catalogue
from policies import preauthorisation as rules
from services import preauthorisation as svc
from services import review as review_svc


class ServiceTest(unittest.TestCase):
    """Every test gets a fresh in-memory store, closed when the test ends."""

    def store(self) -> Store:
        s = Store(catalogue=load_catalogue())
        self.addCleanup(s.close)
        return s


def verified(store, conv, provider, ref):
    r = svc.verify_session(store, conv, provider, ref)
    assert r["ok"], r
    return r


class UC1MissingDocument(ServiceTest):
    def test_resolved_on_call_goes_tier0(self):
        s = self.store()
        c = "conv-uc1"
        verified(s, c, "DHA-F-0001", "PA-2026-0001")
        r = svc.get_case_blockers(s, c, "PA-2026-0001")
        self.assertFalse(r["review_ready"])
        self.assertEqual([b["rule_id"] for b in r["blockers"]], ["MRI-LS-02"])
        self.assertEqual(r["suggested_tier"], "tier_0_standard_review")
        self.assertTrue(svc.record_evidence_reference(
            s, c, "PA-2026-0001", "prior_conservative_treatment", "PCT-1001")["ok"])
        r2 = svc.recheck_case(s, c, "PA-2026-0001")
        self.assertTrue(r2["review_ready"])
        out = svc.send_to_review(s, c, "PA-2026-0001", "tier_0_standard_review",
                                 "Prior treatment evidence supplied on call.")
        self.assertEqual(out["tier"], "tier_0_standard_review")

    def test_rejects_document_type_not_in_policy(self):
        s = self.store()
        c = "conv-uc1b"
        verified(s, c, "DHA-F-0001", "PA-2026-0001")
        r = svc.record_evidence_reference(s, c, "PA-2026-0001", "invoice", "X")
        self.assertEqual(r["error"], "doc_type_not_required")


class UC2CodeMismatch(ServiceTest):
    def test_flagged_not_corrected_tier1(self):
        s = self.store()
        c = "conv-uc2"
        verified(s, c, "DHA-F-0001", "PA-2026-0002")
        r = svc.get_case_blockers(s, c, "PA-2026-0002")
        self.assertEqual([b["code"] for b in r["blockers"]], ["CODE_MISMATCH"])
        self.assertEqual(r["suggested_tier"], "tier_1_priority_review")

    def test_agent_cannot_lower_tier(self):
        s = self.store()
        c = "conv-uc2b"
        verified(s, c, "DHA-F-0001", "PA-2026-0002")
        out = svc.send_to_review(s, c, "PA-2026-0002", "tier_0_standard_review", "x")
        self.assertEqual(out["tier"], "tier_1_priority_review")


class UC3Eligibility(ServiceTest):
    def test_inactive_member_tier1(self):
        s = self.store()
        c = "conv-uc3"
        verified(s, c, "DHA-F-0002", "PA-2026-0003")
        r = svc.get_case_blockers(s, c, "PA-2026-0003")
        self.assertIn("ELIGIBILITY", [b["code"] for b in r["blockers"]])
        self.assertEqual(r["suggested_tier"], "tier_1_priority_review")


class UC4PolicyAmbiguity(ServiceTest):
    def test_unscheduled_procedure_tier2(self):
        s = self.store()
        c = "conv-uc4"
        verified(s, c, "DHA-F-0002", "PA-2026-0004")
        r = svc.get_case_blockers(s, c, "PA-2026-0004")
        self.assertEqual(r["suggested_tier"], "tier_2_mandatory_human")


class UC5Clinical(ServiceTest):
    def test_clinical_flag_tier2(self):
        s = self.store()
        c = "conv-uc5"
        verified(s, c, "DHA-F-0001", "PA-2026-0005")
        r = svc.get_case_blockers(s, c, "PA-2026-0005")
        self.assertEqual(r["suggested_tier"], "tier_2_mandatory_human")


class UC6Status(ServiceTest):
    def test_missing_plan_reported_with_rule(self):
        s = self.store()
        c = "conv-uc6"
        verified(s, c, "DHA-F-0001", "PA-2026-0006")
        r = svc.get_case_blockers(s, c, "PA-2026-0006")
        self.assertIn("PT-02", r["say"])


class PolicyVersionByServiceDate(ServiceTest):
    def test_older_policy_applies_before_july(self):
        s = self.store()
        c = "conv-ver"
        verified(s, c, "DHA-F-0002", "PA-2026-0007")
        r = svc.get_case_blockers(s, c, "PA-2026-0007")
        self.assertEqual(r["policy_version"], "2026-01-01")
        self.assertTrue(r["review_ready"])

    def test_no_policy_before_first_version(self):
        with self.assertRaises(rules.NoPolicyForDate):
            rules.select_policy(self.store().policies, date(2025, 12, 31))


class UC7NoDecisionPath(ServiceTest):
    def test_service_exposes_no_agent_decision_function(self):
        agent_tools = {"verify_session", "get_case_blockers", "record_evidence_reference",
                       "recheck_case", "send_to_review", "transfer_to_human"}
        for name in agent_tools:
            self.assertNotIn("decide", name)

        # decision requires a stored transcript even for a reviewer
        s = self.store()
        c = "conv-uc7"
        verified(s, c, "DHA-F-0001", "PA-2026-0001")
        ref = svc.send_to_review(s, c, "PA-2026-0001", "tier_0_standard_review", "x")["review_ref"]
        self.assertEqual(review_svc.decide(s, ref, "approve", "rev1")["error"], "transcript_pending")
        s.save_transcript(c, {"transcript": []})
        self.assertTrue(review_svc.decide(s, ref, "approve", "rev1")["ok"])
        self.assertEqual(review_svc.decide(s, ref, "deny", "rev1")["error"], "already_decided")


class UC8Scope(ServiceTest):
    def test_other_case_refused_and_audited(self):
        s = self.store()
        c = "conv-uc8"
        verified(s, c, "DHA-F-0001", "PA-2026-0001")
        r = svc.get_case_blockers(s, c, "PA-2026-0002")
        self.assertEqual(r["error"], "case_scope_violation")
        rows = s.audit_for("PA-2026-0002")
        self.assertEqual(rows[-1]["result"], "refused")

    def test_unverified_refused(self):
        s = self.store()
        self.assertEqual(svc.get_case_blockers(s, "conv-x", "PA-2026-0001")["error"],
                         "session_not_verified")

    def test_wrong_provider_then_lock(self):
        s = self.store()
        c = "conv-lock"
        self.assertEqual(svc.verify_session(s, c, "DHA-F-0002", "PA-2026-0001")["error"],
                         "verification_failed")
        self.assertEqual(svc.verify_session(s, c, "DHA-F-0002", "PA-2026-0001")["error"],
                         "verification_failed")
        self.assertEqual(svc.verify_session(s, c, "DHA-F-0001", "PA-2026-0001")["error"],
                         "verification_locked")

    def test_suspended_provider_is_refused_on_its_own_case(self):
        """PA-2026-0008 belongs to DHA-F-0099, so only the active flag can refuse this."""
        s = self.store()
        self.assertEqual(s.providers["DHA-F-0099"]["active"], False)
        self.assertEqual(s.cases["PA-2026-0008"]["provider_id"], "DHA-F-0099")
        r = svc.verify_session(s, "c-susp", "DHA-F-0099", "PA-2026-0008")
        self.assertEqual(r["error"], "verification_failed")

    def test_active_provider_on_the_same_shape_of_case_succeeds(self):
        s = self.store()
        self.assertTrue(svc.verify_session(s, "c-act", "DHA-F-0001", "PA-2026-0001")["ok"])

    def test_vanished_case_is_refused_not_crashed(self):
        s = self.store()
        c = "conv-gone"
        verified(s, c, "DHA-F-0001", "PA-2026-0001")
        del s.cases["PA-2026-0001"]
        self.assertEqual(svc.get_case_blockers(s, c, "PA-2026-0001")["error"], "case_not_found")
        self.assertEqual(svc.send_to_review(s, c, "PA-2026-0001", "tier_0_standard_review", "x")["error"],
                         "case_not_found")

    def test_one_case_per_call(self):
        s = self.store()
        c = "conv-one"
        verified(s, c, "DHA-F-0001", "PA-2026-0001")
        self.assertEqual(svc.verify_session(s, c, "DHA-F-0001", "PA-2026-0002")["error"],
                         "already_verified")


class NoPolicyForServiceDate(ServiceTest):
    """A case older than every policy must refuse on every tool, never raise."""

    def _case_before_any_policy(self):
        s = self.store()
        s.cases["PA-2026-0100"] = {**s.cases["PA-2026-0001"], "request_ref": "PA-2026-0100",
                                   "service_date": "2025-01-01"}
        verified(s, "conv-nop", "DHA-F-0001", "PA-2026-0100")
        return s

    def test_every_tool_refuses_cleanly(self):
        s = self._case_before_any_policy()
        for result in (
            svc.get_case_blockers(s, "conv-nop", "PA-2026-0100"),
            svc.record_evidence_reference(s, "conv-nop", "PA-2026-0100", "referral", "R-1"),
            svc.send_to_review(s, "conv-nop", "PA-2026-0100", "tier_0_standard_review", "x"),
        ):
            self.assertEqual(result["error"], "no_policy_for_date")
            self.assertIn("qualified reviewer", result["say"])


class DecisionIsClaimedOnce(ServiceTest):
    def _ready_item(self, s):
        verified(s, "conv-claim", "DHA-F-0001", "PA-2026-0001")
        ref = svc.send_to_review(s, "conv-claim", "PA-2026-0001", "tier_0_standard_review", "x")["review_ref"]
        s.save_transcript("conv-claim", {"transcript": []})
        return ref

    def test_second_writer_loses_even_if_it_read_an_undecided_item(self):
        s = self.store()
        ref = self._ready_item(s)
        self.assertTrue(s.decide(ref, "approve", "rev1"))
        self.assertFalse(s.decide(ref, "deny", "rev2"))
        self.assertEqual(s.review(ref)["decision"], "approve")
        self.assertEqual(s.review(ref)["decided_by"], "rev1")

    def test_service_reports_already_decided_when_it_loses_the_claim(self):
        s = self.store()
        ref = self._ready_item(s)
        s.decide(ref, "approve", "rev1")
        self.assertEqual(review_svc.decide(s, ref, "deny", "rev2"), {"ok": False, "error": "already_decided"})


class DocumentReferences(ServiceTest):
    def test_re_reading_a_reference_replaces_it_rather_than_duplicating(self):
        s = self.store()
        verified(s, "conv-dup", "DHA-F-0001", "PA-2026-0001")
        for doc_ref in ("PCT-1", "PCT-2"):
            svc.record_evidence_reference(s, "conv-dup", "PA-2026-0001",
                                          "prior_conservative_treatment", doc_ref)
        docs = s.case_with_documents("PA-2026-0001")["documents"]
        by_type = [d["doc_type"] for d in docs]
        self.assertEqual(by_type.count("prior_conservative_treatment"), 1)
        held = next(d for d in docs if d["doc_type"] == "prior_conservative_treatment")
        self.assertEqual(held["doc_ref"], "PCT-2")

    def test_both_references_stay_in_the_audit_log(self):
        s = self.store()
        verified(s, "conv-dup2", "DHA-F-0001", "PA-2026-0001")
        for doc_ref in ("PCT-1", "PCT-2"):
            svc.record_evidence_reference(s, "conv-dup2", "PA-2026-0001",
                                          "prior_conservative_treatment", doc_ref)
        recorded = [r["action"] for r in s.audit_for("PA-2026-0001")]
        self.assertEqual(recorded.count("record_evidence_reference"), 2)


class UC9OptOut(ServiceTest):
    def test_callback_needs_consent(self):
        s = self.store()
        self.assertEqual(svc.transfer_to_human(s, "c9", "caller asked", callback=True)["error"],
                         "callback_without_consent")
        self.assertTrue(svc.transfer_to_human(s, "c9", "caller asked", callback=True, consent=True)["ok"])


class Audit(ServiceTest):
    def test_append_only(self):
        s = self.store()
        s.audit("system", "x", "ok")
        with self.assertRaises(sqlite3.IntegrityError):
            s.db.execute("UPDATE audit_event SET result='changed'")
        with self.assertRaises(sqlite3.IntegrityError):
            s.db.execute("DELETE FROM audit_event")

    def test_duplicate_webhook_idempotent(self):
        s = self.store()
        self.assertTrue(s.save_transcript("conv-d", {"a": 1}))
        self.assertFalse(s.save_transcript("conv-d", {"a": 1}))


class TierMonotonic(ServiceTest):
    def test_adding_nonresolvable_blocker_never_lowers_tier(self):
        s = self.store()
        base = dict(s.cases["PA-2026-0001"])
        t0 = rules.find_blockers(base, s.policies).suggested_tier
        worse = {**base, "member_active": False}
        t1 = rules.find_blockers(worse, s.policies).suggested_tier
        self.assertGreaterEqual(rules.TIER_ORDER[t1], rules.TIER_ORDER[t0])


class V4IdeasCarriedForward(ServiceTest):
    def test_blockers_carry_confidence_and_source(self):
        s = self.store()
        b = rules.find_blockers(s.cases["PA-2026-0001"], s.policies).blockers[0]
        self.assertEqual((b.confidence, b.source), ("high", "rules_engine"))


    def test_similar_case_found_for_same_pattern(self):
        s = self.store()
        svc.verify_session(s, "c-a", "DHA-F-0001", "PA-2026-0001")
        svc.record_evidence_reference(s, "c-a", "PA-2026-0001", "prior_conservative_treatment", "PCT-1")
        first = svc.send_to_review(s, "c-a", "PA-2026-0001", "tier_0_standard_review", "x")
        s.cases["PA-2026-0099"] = {**s.cases["PA-2026-0001"], "request_ref": "PA-2026-0099",
                                   "patient_token": "PT-X"}
        svc.verify_session(s, "c-b", "DHA-F-0001", "PA-2026-0099")
        second = svc.send_to_review(s, "c-b", "PA-2026-0099", "tier_0_standard_review", "y")
        self.assertIn(first["review_ref"], second["similar_cases"])


class OneOpenReviewPerRequest(ServiceTest):
    """A second hand-off must not open a rival item that could be decided the other way."""

    def _verified(self, s):
        verified(s, "conv-open", "DHA-F-0001", "PA-2026-0001")

    def test_second_handoff_returns_the_item_already_waiting(self):
        s = self.store()
        self._verified(s)
        first = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "first")
        second = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "second")
        self.assertEqual(second["review_ref"], first["review_ref"])
        self.assertEqual(len(s.queue()), 1)
        self.assertIn("already with a reviewer", second["say"])

    def test_one_request_cannot_be_approved_and_denied(self):
        s = self.store()
        self._verified(s)
        a = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "first")
        b = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "second")
        s.save_transcript("conv-open", {"transcript": []})
        self.assertTrue(review_svc.decide(s, a["review_ref"], "approve", "rev1")["ok"])
        self.assertEqual(review_svc.decide(s, b["review_ref"], "deny", "rev2")["error"], "already_decided")

    def test_reuse_raises_the_tier_but_never_lowers_it(self):
        s = self.store()
        self._verified(s)
        svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "first")
        raised = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_2_mandatory_human", "clinical")
        self.assertEqual(raised["tier"], "tier_2_mandatory_human")
        lowered = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "again")
        self.assertEqual(lowered["tier"], "tier_2_mandatory_human")

    def test_the_database_refuses_a_second_open_item(self):
        s = self.store()
        self._verified(s)
        svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "first")
        with self.assertRaises(sqlite3.IntegrityError):
            s.create_review("PA-2026-0001", "conv-open", "tier_0_standard_review", "rival", {})

    def test_a_decided_request_can_open_a_new_item(self):
        s = self.store()
        self._verified(s)
        first = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "first")
        s.save_transcript("conv-open", {"transcript": []})
        review_svc.decide(s, first["review_ref"], "request_more", "rev1")
        second = svc.send_to_review(s, "conv-open", "PA-2026-0001", "tier_0_standard_review", "second")
        self.assertNotEqual(second["review_ref"], first["review_ref"])


class RecheckIsAuditedAsItself(ServiceTest):
    def test_the_trail_shows_the_tool_the_agent_called(self):
        s = self.store()
        verified(s, "conv-re", "DHA-F-0001", "PA-2026-0001")
        svc.get_case_blockers(s, "conv-re", "PA-2026-0001")
        svc.record_evidence_reference(s, "conv-re", "PA-2026-0001",
                                      "prior_conservative_treatment", "PCT-1001")
        svc.recheck_case(s, "conv-re", "PA-2026-0001")
        self.assertEqual([r["action"] for r in s.audit_for("PA-2026-0001")],
                         ["verify_session", "get_case_blockers", "record_evidence_reference",
                          "recheck_case"])

    def test_a_refused_recheck_is_also_named_correctly(self):
        s = self.store()
        self.assertEqual(svc.recheck_case(s, "conv-none", "PA-2026-0001")["error"], "session_not_verified")
        self.assertEqual([r["action"] for r in s.audit_for("PA-2026-0001")], ["recheck_case"])


class CallbackConsentIsRecorded(ServiceTest):
    def test_consent_is_written_to_the_session_and_read_back(self):
        s = self.store()
        self.assertFalse(s.callback_consent("c-consent"))
        self.assertTrue(svc.transfer_to_human(s, "c-consent", "asked", callback=True, consent=True)["ok"])
        self.assertTrue(s.callback_consent("c-consent"))

    def test_a_refused_callback_records_no_consent(self):
        s = self.store()
        svc.transfer_to_human(s, "c-noconsent", "asked", callback=True)
        self.assertFalse(s.callback_consent("c-noconsent"))

    def test_the_audit_row_states_whether_consent_was_recorded(self):
        s = self.store()
        svc.transfer_to_human(s, "c-audit", "asked", callback=True, consent=True)
        detail = json.loads(s.db.execute(
            "SELECT detail FROM audit_event WHERE conversation_id='c-audit'").fetchone()["detail"])
        self.assertTrue(detail["consent_recorded"])


class MissingCaseIsRefusedEverywhere(ServiceTest):
    """A case that leaves the store mid-call refuses on every tool rather than raising."""

    def _verified_then_removed(self, s, conv):
        verified(s, conv, "DHA-F-0001", "PA-2026-0001")
        del s.cases["PA-2026-0001"]

    def test_every_scoped_tool_refuses(self):
        for conv, call in (
            ("c-gone1", lambda s: svc.get_case_blockers(s, "c-gone1", "PA-2026-0001")),
            ("c-gone2", lambda s: svc.record_evidence_reference(
                s, "c-gone2", "PA-2026-0001", "referral", "R-1")),
            ("c-gone3", lambda s: svc.send_to_review(
                s, "c-gone3", "PA-2026-0001", "tier_0_standard_review", "x")),
        ):
            s = self.store()
            self._verified_then_removed(s, conv)
            result = call(s)
            self.assertEqual(result["error"], "case_not_found", conv)
            self.assertIn("colleague", result["say"])


class SimilarCasesToleratesOldPackages(ServiceTest):
    def test_a_package_without_blocker_keys_is_skipped_not_raised(self):
        s = self.store()
        s.db.execute("INSERT INTO review_item (review_ref, request_ref, conversation_id, tier, summary,"
                     " report_json, created_at) VALUES (?,?,?,?,?,?,?)",
                     ("RV-LEGACY", "PA-2026-0005", "conv-legacy", "tier_0_standard_review", "old",
                      json.dumps({"note": "no blockers key"}), time.time()))
        s.db.commit()
        verified(s, "conv-sim", "DHA-F-0001", "PA-2026-0001")
        out = svc.send_to_review(s, "conv-sim", "PA-2026-0001", "tier_0_standard_review", "x")
        self.assertTrue(out["ok"])
        self.assertNotIn("RV-LEGACY", out["similar_cases"])


class QueueCarriesTheProvider(ServiceTest):
    """A reviewer searches by the clinic that called, so the name travels with the item."""

    def test_open_and_decided_items_name_the_facility(self):
        s = self.store()
        verified(s, "conv-prov", "DHA-F-0001", "PA-2026-0001")
        ref = svc.send_to_review(s, "conv-prov", "PA-2026-0001", "tier_0_standard_review", "x")["review_ref"]
        item = review_svc.pending_queue(s)[0]
        self.assertEqual((item["provider_id"], item["provider"]),
                         ("DHA-F-0001", "Jumeirah Family Clinic"))

        s.save_transcript("conv-prov", {"transcript": []})
        review_svc.decide(s, ref, "approve", "rev1")
        self.assertEqual(review_svc.decided_history(s)[0]["provider"], "Jumeirah Family Clinic")


class DecidedHistory(ServiceTest):
    """A decided case leaves the queue, so the reviewer needs it back somewhere."""

    def test_empty_until_something_is_decided(self):
        s = self.store()
        verified(s, "conv-hist", "DHA-F-0001", "PA-2026-0001")
        svc.send_to_review(s, "conv-hist", "PA-2026-0001", "tier_0_standard_review", "x")
        self.assertEqual(review_svc.decided_history(s), [])
        self.assertEqual(len(review_svc.pending_queue(s)), 1)

    def test_decided_case_moves_from_queue_to_history(self):
        s = self.store()
        verified(s, "conv-hist", "DHA-F-0001", "PA-2026-0001")
        ref = svc.send_to_review(s, "conv-hist", "PA-2026-0001", "tier_0_standard_review", "x")["review_ref"]
        s.save_transcript("conv-hist", {"transcript": []})
        review_svc.decide(s, ref, "approve", "rev1")

        self.assertEqual(review_svc.pending_queue(s), [])
        history = review_svc.decided_history(s)
        self.assertEqual([(h["review_ref"], h["decision"], h["decided_by"]) for h in history],
                         [(ref, "approve", "rev1")])


class RulesBehindAReviewItem(ServiceTest):
    """A reviewer reads the policy the case was judged against, with its failures marked."""

    def test_rules_name_the_policy_in_force_and_mark_what_failed(self):
        s = self.store()
        verified(s, "conv-rules", "DHA-F-0001", "PA-2026-0001")
        ref = svc.send_to_review(s, "conv-rules", "PA-2026-0001", "tier_0_standard_review", "x")["review_ref"]

        out = review_svc.rules_for(s, ref)
        self.assertEqual((out["policy_version"], out["procedure_code"]), ("2026-07-01", "72148"))
        cited = [r["rule_id"] for r in out["rules"] if r["cited"]]
        self.assertEqual(cited, ["MRI-LS-02"])
        self.assertIn("ELG-01", [r["rule_id"] for r in out["rules"]])
        self.assertTrue(all(r["text"] for r in out["rules"]))

    def test_a_procedure_outside_the_schedule_cites_the_general_rule(self):
        s = self.store()
        verified(s, "conv-gen", "DHA-F-0002", "PA-2026-0004")
        ref = svc.send_to_review(s, "conv-gen", "PA-2026-0004", "tier_2_mandatory_human", "x")["review_ref"]
        out = review_svc.rules_for(s, ref)
        self.assertIsNone(out["procedure"])
        self.assertEqual([r["rule_id"] for r in out["rules"] if r["cited"]], ["GEN-00"])

    def test_unknown_review_ref_has_no_rules(self):
        self.assertIsNone(review_svc.rules_for(self.store(), "RV-NOPE"))


class TranscriptBehindAReviewItem(ServiceTest):
    """A reviewer reads the call the decision rests on, and cannot decide before it lands."""

    def _item(self, s):
        verified(s, "conv-tr", "DHA-F-0001", "PA-2026-0001")
        return svc.send_to_review(s, "conv-tr", "PA-2026-0001", "tier_0_standard_review", "x")["review_ref"]

    def test_unknown_review_ref_has_no_transcript(self):
        self.assertIsNone(review_svc.transcript_for(self.store(), "RV-NOPE"))

    def test_waiting_before_the_webhook_arrives(self):
        s = self.store()
        out = review_svc.transcript_for(s, self._item(s))
        self.assertEqual((out["stored"], out["turns"]), (False, []))

    def test_turns_are_returned_once_stored(self):
        s = self.store()
        ref = self._item(s)
        s.save_transcript("conv-tr", {"data": {"transcript": [
            {"role": "agent", "message": "This call is recorded.", "time_in_call_secs": 2},
            {"role": "user", "message": "My request is stuck.", "time_in_call_secs": 9},
            {"role": "agent", "message": None},
            "not a turn",
        ]}})
        out = review_svc.transcript_for(s, ref)
        self.assertTrue(out["stored"])
        self.assertEqual([(t["speaker"], t["text"], t["at"]) for t in out["turns"]],
                         [("agent", "This call is recorded.", 2), ("caller", "My request is stuck.", 9)])


if __name__ == "__main__":
    unittest.main()
