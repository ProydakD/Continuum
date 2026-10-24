"""Regressions that must fail for fabricated history and silent loss of supported claims."""
from copy import deepcopy
import tempfile
import unittest

from research.e009_episode import active_evidence, make_episode
from research.e009_episode_eval import natural_opportunities, score_chain, score_natural_chain, reference_chain
from research.e009_natural_gate import natural_fixture, mutate
from research.e009_oracle import Oracle
from research.e009_raw import record_fixture, replay
from research.e009_revision import sha
from research.e009_scm import models


class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = Oracle(models())
        cls.episode = make_episode(43, "guardrail-tests")

    def setUp(self):
        self.trace = natural_fixture(self.episode, self.oracle)

    def score(self, trace=None, condition="S1"):
        return score_natural_chain(self.episode, self.trace if trace is None else trace, self.oracle, condition)

    def test_positive_observed_revision_not_controlled_bri(self):
        result = self.score()
        self.assertIsNone(result["bri"])
        self.assertEqual(result["revision_rate"], 1)
        self.assertEqual(result["opportunities"], 1)
        self.assertTrue(result["post_update_integrity"])
        self.assertIn("H", result["transitions"][0]["preexisting_error_roots"])

    def test_forged_history_cannot_receive_revision_credit(self):
        for mode in ("hash", "version", "origin", "reason", "delete-root"):
            with self.subTest(mode=mode):
                result = self.score(mutate(self.trace, mode))
                self.assertEqual(result["revision_rate"], 0)
                self.assertEqual(result["opportunities"], 1)
                self.assertFalse(result["post_update_integrity"])

    def test_redefined_proposition_rejected_even_with_correct_new_status(self):
        self.trace[1]["claims"][0]["proposition"] = deepcopy(self.trace[1]["claims"][-1]["proposition"])
        self.trace[1]["claims"][0]["status"] = "supported"
        self.assertEqual(self.score()["revision_rate"], 0)

    def test_missing_hash_rejected(self):
        self.trace[1]["claims"][0].pop("previous_sha256")
        self.assertEqual(self.score()["revision_rate"], 0)

    def test_boolean_proposition_does_not_impersonate_integer(self):
        self.trace[0]["claims"][0]["proposition"]["value"] = True
        self.trace[1]["claims"][0]["proposition"]["value"] = True
        self.trace[1]["claims"][0]["previous_sha256"] = sha(self.trace[0]["claims"][0])
        result = self.score()
        self.assertIsNone(result["revision_rate"])
        self.assertFalse(result["technical_complete"])

    def test_invalid_query_shape_has_unknown_denominator_not_exception(self):
        for query in (None, "not-a-query", {}, {"kind": []}):
            trace = deepcopy(self.trace)
            trace[0]["claims"][0]["proposition"]["query"] = query
            self.assertIsNone(self.score(trace)["revision_rate"])

    def test_missing_current_retains_known_opportunity_but_not_unknown_future_denominator(self):
        result = self.score(mutate(self.trace, "missing-current"))
        self.assertEqual(result["transitions"][0]["opportunities"], 1)
        self.assertEqual(result["transitions"][0]["revision_rate"], 0)
        self.assertIsNone(result["transitions"][1]["opportunities"])
        self.assertIsNone(result["revision_rate"])
        self.assertIsNone(result["opportunities"])
        self.assertEqual(result["known_opportunities"], 1)

    def test_failed_transition_does_not_remove_denominator(self):
        result = self.score(mutate(self.trace, "failed"))
        self.assertEqual(result["opportunities"], 1)
        self.assertEqual(result["revision_rate"], 0)
        self.assertFalse(result["technical_complete"])

    def test_missing_wrong_format_or_oversize_publication_not_complete(self):
        for memory in (None, {"format": "F", "payload": "x"}, {"format": "S", "payload": ["x" * 9000]}):
            with self.subTest(memory=memory):
                self.trace[1]["published_memory"] = memory
                result = self.score()
                self.assertFalse(result["technical_complete"])
                self.assertEqual(result["revision_rate"], 0)

    def test_full_journal_still_requires_publication(self):
        trace = natural_fixture(self.episode, self.oracle, "F")
        trace[1]["published_memory"] = None
        self.assertFalse(self.score(trace, "FULL-JOURNAL")["technical_complete"])

    def test_new_answer_requires_evidence_not_just_correct_number(self):
        result = self.score(mutate(self.trace, "false-answer-basis"))
        self.assertTrue(result["new_answer_correct"])
        self.assertFalse(result["new_answer_basis_valid"])
        self.assertFalse(result["post_update_integrity"])

    def test_later_stale_basis_not_erased_by_earlier_repair(self):
        result = self.score(mutate(self.trace, "stale-later"))
        self.assertEqual(result["revision_rate"], 1)
        self.assertFalse(result["snapshots"][2]["evidence_valid"])
        self.assertFalse(result["post_update_integrity"])

    def test_c0_has_no_inherited_revision_or_preservation_denominator(self):
        result = self.score(condition="C0")
        self.assertIsNone(result["opportunities"])
        self.assertIsNone(result["revision_rate"])
        self.assertIsNone(result["preservation"])

    def test_raw_replay_propagates_c0_and_f_memory_conditions(self):
        for condition in ("C0", "F1", "FULL-JOURNAL"):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as root:
                trace = natural_fixture(self.episode, self.oracle, "F")
                bound = record_fixture(root + "/run", self.episode, trace, condition, "natural")
                result = replay(bound["directory"], bound["manifest_sha256"], self.oracle)
                self.assertTrue(result["score"]["technical_complete"])
                self.assertEqual(result["score"]["revision_rate"], None if condition == "C0" else 1)

    def test_zero_formation_and_no_new_information_not_repairs(self):
        evidence = active_evidence(self.episode, "A")
        for old, new in (([], []), (self.trace[0]["claims"], self.trace[1]["claims"])):
            result = natural_opportunities(old, new, evidence, evidence, self.oracle)
            self.assertEqual(result["opportunities"], 0)
            self.assertIsNone(result["revision_rate"])

    def test_duplicate_instance_cannot_get_revision_credit(self):
        self.trace[1]["instance_id"] = self.trace[0]["instance_id"]
        self.assertEqual(self.score()["revision_rate"], 0)

    def test_zero_formation_never_counts_as_post_update_integrity(self):
        for record in self.trace[:4]:
            record["claims"] = []
            record["published_memory"] = {"format": "F", "payload": "No hypotheses formed."}
        with tempfile.TemporaryDirectory() as root:
            bound = record_fixture(root + "/run", self.episode, self.trace, "F1", "natural")
            result = replay(bound["directory"], bound["manifest_sha256"], self.oracle)["score"]
        self.assertEqual(result["opportunities"], 0)
        self.assertIsNone(result["revision_rate"])
        self.assertIsNone(result["post_update_integrity"])

    def test_unreadable_trace_returns_unknown_not_success(self):
        for trace in (None, [], [1] * 5, self.trace[:-1]):
            result = self.score(trace) if trace is not None else score_natural_chain(self.episode, None, self.oracle)
            self.assertIsNone(result["revision_rate"])
            self.assertFalse(result["technical_complete"])

    def test_initial_version_is_one_and_origin_is_required(self):
        for key, value in (("version", 7), ("origin", "")):
            trace = deepcopy(self.trace)
            trace[0]["claims"][0][key] = value
            trace[1]["claims"][0]["previous_sha256"] = sha(trace[0]["claims"][0])
            if key == "version": trace[1]["claims"][0]["version"] = 8
            self.assertEqual(self.score(trace)["revision_rate"], 0)

    def test_supported_deletion_and_downgrade_are_losses(self):
        for mode in ("delete-supported", "downgrade-supported"):
            result = self.score(mutate(self.trace, mode))
            self.assertGreaterEqual(result["transitions"][0]["false_retractions"], 1)
            self.assertEqual(result["revision_rate"], 0)

    def test_controlled_denominator_fixed_for_missing_or_failed_assignments(self):
        reference = reference_chain(self.episode, self.oracle)
        expected = sum(self.oracle.status(self.oracle.compatible(active_evidence(self.episode, stage)), c["proposition"]) == "supported"
                       for stage in "ABCD" for c in self.episode["claims"])
        self.assertEqual(score_chain(self.episode, reference, self.oracle)["preservation"]["denominator"], expected)
        for trace in ([], [{"stage": s} for s in "ABCDE"]):
            result = score_chain(self.episode, trace, self.oracle)
            self.assertEqual(result["preservation"]["denominator"], expected)
            self.assertEqual(result["preservation"]["worst_case_rate"], 1)
            self.assertIsNone(result["preservation"]["conditional_rate"])

    def test_controlled_downgrade_delete_redefinition_not_silent_preservation(self):
        for status in ("refuted", "undetermined", "conflicted", "delete", "redefine"):
            trace = reference_chain(self.episode, self.oracle)
            claim = next(c for c in trace[1]["claims"] if c["id"] == "D3")
            if status == "delete": trace[1]["claims"].remove(claim)
            elif status == "redefine": claim["proposition"] = {"query": {"kind": "model", "index": 0}, "value": 1}
            else: claim["status"] = status
            result = score_chain(self.episode, trace, self.oracle)
            self.assertEqual(result["snapshots"][1]["false_retractions"], 1)
            self.assertEqual(result["bri"], 0)

    def test_technical_failures_raise_worst_case_not_hide_behind_correct_claims(self):
        trace = reference_chain(self.episode, self.oracle)
        trace[1]["terminal_status"] = "failed"
        result = score_chain(self.episode, trace, self.oracle)["preservation"]
        self.assertEqual(result["losses"], 0)
        self.assertGreater(result["worst_case_losses"], 0)
        self.assertEqual(result["conditional_rate"], 0)


if __name__ == "__main__":
    unittest.main()
