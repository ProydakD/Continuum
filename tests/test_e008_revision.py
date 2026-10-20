import copy
import unittest

from research.e008_assessment import assess, hypothesis_index, hypothesis_key, inherited_claims
from research.e008_revision import aggregate_revision, revision_metrics, uncertainty_metrics
from research.e008_scm import VARIABLES


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.question = {"id": "P01", "kind": "probability", "target": "V1", "do": [["V0", 1]]}
        self.h = {"id": "A:H1", "family": "relay", "order": list(VARIABLES), "gate": "and", "flips": [0, 0, 0],
                  "status": "preferred", "confidence": .9, "evidence": ["EA"]}
        self.old_index = hypothesis_index()[hypothesis_key(self.h)]
        self.new_index = hypothesis_index()[hypothesis_key(dict(self.h, family="confounded"))]
        old = {"identified": False, "expected": None, "possibilities": ["1", "1/2"]}
        new = {"identified": True, "expected": "1/2", "possibilities": ["1/2"]}
        self.gold = {"subsets": {"EA": {"candidate_indices": [self.old_index, self.new_index], "questions": {"P01": old}},
                                "EA+EB": {"candidate_indices": [self.new_index], "questions": {"P01": new}},
                                "EA+EB+EC": {"candidate_indices": [self.new_index], "questions": {"P01": new}}},
                     "integrative_question_ids": []}
        self.world = {"id": "world", "truth": {"family": "confounded"}, "panel": [self.question]}
        self.job = {"id": "b", "source": "a", "stage": "B", "condition": "C1", "phase": "test",
                    "role": "investigator", "world": "world"}
        self.chain = [{"job": {"id": "a", "stage": "A"},
                       "result": {"answer": {"answers": [{"id": "P01", "value": "1", "depends_on": ["A:H1"]}],
                                             "hypotheses": [self.h]}}}]
        self.answer = {"answers": [{"id": "P01", "value": "1/2", "confidence": 1, "evidence": ["EA", "EB"],
                                     "depends_on": [], "explanation": "New intervention excludes the old premise.", "witnesses": []}],
                       "hypotheses": [dict(self.h, status="rejected", evidence=["EA", "EB"])],
                       "revisions": [{"claim_id": "A:P01", "previous_value": "1", "new_value": "1/2",
                                      "evidence": ["EA", "EB"], "reason": "Interventional contradiction."}],
                       "save_status": "saved"}

    def score(self):
        return assess(self.answer, [self.question], self.gold, ["EA", "EB"],
                      inherited_answers=inherited_claims(self.chain, self.gold))

    def test_root_and_dependent_correction_require_same_observed_assignment(self):
        score = self.score()
        result = revision_metrics(self.job, score, self.chain, self.world, self.gold)["groups"]["natural"]
        self.assertEqual(result["root_opportunities"], 1)
        self.assertEqual(result["root_rejections"], 1)
        self.assertEqual(result["dependent_opportunities"], 1)
        self.assertEqual(result["dependent_corrections"], 1)
        self.answer["hypotheses"][0]["family"] = "confounded"
        result = revision_metrics(self.job, self.score(), self.chain, self.world, self.gold)["groups"]["natural"]
        self.assertEqual(result["root_rejections"], 0)
        self.assertEqual(result["dependent_corrections"], 0)
        self.assertEqual(result["claim_error_corrections"], 1)

    def test_repeated_revision_cannot_inflate_a_single_opportunity(self):
        self.answer["revisions"] *= 2
        result = revision_metrics(self.job, self.score(), self.chain, self.world, self.gold)["groups"]["natural"]
        self.assertEqual(result["claim_error_opportunities"], 1)
        self.assertEqual(result["claim_error_corrections"], 1)
        self.assertEqual(result["dependent_corrections"], 1)

    def test_old_a_error_is_not_demanded_again_after_b_corrected_it(self):
        self.chain.append({"job": {"id": "b", "stage": "B"}, "result": {"answer": copy.deepcopy(self.answer)}})
        self.job.update(id="c", stage="C", source="b")
        result = revision_metrics(self.job, self.score(), self.chain, self.world, self.gold)["groups"]["natural"]
        self.assertEqual(result["claim_error_opportunities"], 0)
        self.assertEqual(result["root_opportunities"], 0)
        self.assertEqual(result["correct_prior_claims"], 1)

    def test_direct_injection_has_its_own_denominator(self):
        self.job["bulletin"] = {"hypothesis": {k: self.h[k] for k in ("family", "order", "gate", "flips")},
                                "claims": [{"id": "probe:P01", "question_id": "P01", "value": "1",
                                            "depends_on": ["probe:H0"]}]}
        self.chain = [{"job": self.job, "result": {}}]
        self.answer["hypotheses"][0]["id"] = "probe:H0"
        self.answer["revisions"][0]["claim_id"] = "probe:P01"
        result = revision_metrics(self.job, self.score(), self.chain, self.world, self.gold)
        self.assertEqual(result["groups"]["natural"]["root_opportunities"], 0)
        self.assertEqual(result["groups"]["deliberate_injection"]["root_rejections"], 1)
        self.assertEqual(result["groups"]["deliberate_injection"]["dependent_corrections"], 1)

    def test_false_correction_uses_correct_prior_claim_denominator(self):
        self.chain[0]["result"]["answer"]["answers"][0]["value"] = "1/2"
        self.answer["answers"][0]["value"] = "1"
        self.answer["revisions"][0].update(previous_value="1/2", new_value="1")
        result = revision_metrics(self.job, self.score(), self.chain, self.world, self.gold)["groups"]["natural"]
        self.assertEqual(result["correct_prior_claims"], 1)
        self.assertEqual(result["false_corrections"], 1)
        self.assertEqual(result["claim_error_opportunities"], 0)

    def test_unobservable_prior_is_not_guessed_from_raw_memory(self):
        self.chain[0]["result"] = {"status": "injected_crash_after_commit"}
        result = revision_metrics(self.job, None, self.chain, self.world, self.gold)
        self.assertFalse(result["prior_answer_observable"])
        self.assertEqual(result["groups"]["natural"]["claim_error_opportunities"], 0)

    def test_missing_confidence_is_not_zero_brier_success(self):
        result = uncertainty_metrics(None, assigned_questions=16, identified_questions=10)
        self.assertEqual(result["valid_answers"], 0)
        self.assertEqual(result["assigned_questions"], 16)
        self.assertEqual(result["unidentified_questions"], 6)
        self.assertEqual(sum(x["count"] for x in result["confidence_bins"]), 0)

    def test_repeated_contexts_do_not_raise_world_n(self):
        score = self.score()
        row = {"job": self.job, "status": "completed", "audit": {"pass": True},
               "revision": revision_metrics(self.job, score, self.chain, self.world, self.gold),
               "uncertainty": uncertainty_metrics(score, assigned_questions=1, identified_questions=1)}
        report = aggregate_revision([row, row], [self.world], draws=100)["test|C1|main|B"]
        self.assertEqual(report["contexts"], 2)
        self.assertEqual(report["independent_worlds"], 1)
        self.assertEqual(report["origins"]["natural"]["dependent_corrections"]["eligible_worlds"], 1)
        self.assertEqual(report["origins"]["natural"]["dependent_corrections"]["mean"], 1)


if __name__ == "__main__":
    unittest.main()
