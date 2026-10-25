"""Component discrimination controls, not independent semantic calibration."""
from copy import deepcopy
import unittest

from research.e009_component_assessment import (
    assess_controlled_checkpoint, assess_prediction, basis_sound, candidate_fields,
    controlled_chain_bounds, explicit_record, public_opportunities, tri_all,
)
from research.e009_episode import active_evidence, make_episode
from research.e009_episode_eval import reference_chain
from research.e009_oracle import Oracle
from research.e009_scm import models


def observed(claims):
    return {c["id"]: explicit_record(c) for c in claims}


class ComponentAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = Oracle(models())
        cls.episode = make_episode(455, "component-control")
        cls.chain = reference_chain(cls.episode, cls.oracle)

    def setUp(self):
        self.before = observed(self.chain[0]["claims"])
        self.current = observed(self.chain[1]["claims"])

    def assess(self, current=None, before=None, stage="B"):
        return assess_controlled_checkpoint(self.episode, stage,
            self.before if before is None else before, self.current if current is None else current, self.oracle)

    def test_positive_control_all_components_and_prediction(self):
        previous = observed(self.episode["claims"]); checkpoints = []
        for row in self.chain[:4]:
            current = observed(row["claims"])
            checkpoints.append(self.assess(current, previous, row["stage"]))
            previous = current
        prediction = assess_prediction(self.episode, explicit_record(self.chain[4]), previous, self.oracle)
        result = controlled_chain_bounds(checkpoints, prediction, True)
        self.assertEqual(result["assigned_outcome_bounds"], {"lower": 1, "upper": 1})
        self.assertFalse(result["annotation_semantics_verified"])
        self.assertEqual(controlled_chain_bounds(checkpoints, prediction, False)["assigned_outcome_bounds"],
                         {"lower": 0, "upper": 0})

    def test_missing_public_values_are_not_filled_by_reference(self):
        self.assertIsNone(self.assess({})["components"]["root_revision"])
        self.current["H"]["proposition"] = {"state": "unknown", "value": None}
        self.assertIsNone(self.assess()["components"]["root_revision"])

    def test_partial_candidate_object_does_not_prove_absence_in_framing(self):
        row = deepcopy(self.chain[1]["claims"][0]); row.pop("bases"); row.pop("reasons")
        value = candidate_fields(row)
        self.assertEqual(value["bases"]["state"], "unknown")
        self.assertEqual(value["reasons"]["state"], "unknown")
        self.assertEqual(value["record_sha256"]["state"], "unknown")
        self.current["H"] = value
        self.assertTrue(self.assess()["components"]["root_revision"])
        self.assertIsNone(self.assess()["proof_checks"]["H"])

    def test_malformed_or_flat_predicate_and_bases_not_repaired(self):
        row = deepcopy(self.chain[1]["claims"][0]); row["bases"] = ["e:EA", "e:EB"]
        self.assertEqual(candidate_fields(row)["bases"]["state"], "uninterpreted")
        row["proposition"] = {"query": {"kind": "census_match", "do": [], "counts": [0] * 65}, "value": 1}
        self.assertEqual(candidate_fields(row)["proposition"]["state"], "malformed")

    def test_retained_wrong_root_and_wrong_identity_fail(self):
        self.current["H"]["status"]["value"] = "supported"
        self.assertFalse(self.assess()["components"]["root_revision"])
        self.current = observed(self.chain[1]["claims"])
        self.current["H"]["proposition"]["value"]["value"] = 0
        self.assertFalse(self.assess()["components"]["root_revision"])

    def test_explicit_absence_is_not_unknown_extraction(self):
        self.current["H"]["status"] = {"state": "absent", "value": None}
        self.assertFalse(self.assess()["components"]["root_revision"])
        self.current["K"]["bases"] = {"state": "absent", "value": None}
        self.assertFalse(self.assess()["proof_checks"]["K"])
        self.current["I"]["previous_sha256"] = {"state": "absent", "value": None}
        self.assertFalse(self.assess()["trace_checks"]["I"])

    def test_missed_dependent_repair_not_hidden_by_correct_root(self):
        self.current["D1"]["status"]["value"] = "supported"
        r = self.assess()["components"]
        self.assertTrue(r["root_revision"])
        self.assertFalse(r["dependent_revision"])

    def test_false_retraction_and_removed_independent_support(self):
        self.current["I"]["status"]["value"] = "refuted"
        r = self.assess()["components"]
        self.assertFalse(r["no_false_retraction"])
        self.assertFalse(r["independent_support"])
        self.current = observed(self.chain[1]["claims"])
        self.current["K"]["bases"]["value"] = [["e:EA", "e:EB", "e:EC"]]
        self.assertTrue(self.assess()["proof_checks"]["K"])
        self.assertFalse(self.assess()["components"]["independent_support"])

    def test_stale_alternative_cannot_be_laundered(self):
        current = observed(self.chain[2]["claims"])
        current["K"]["bases"]["value"].append(["e:EB"])
        r = self.assess(current, observed(self.chain[1]["claims"]), "C")
        self.assertFalse(r["proof_checks"]["K"])
        self.assertFalse(r["components"]["independent_support"])

    def test_cycle_and_unknown_parent_are_different(self):
        sources = {e["id"]: e for e in active_evidence(self.episode, "B")}
        self.current["K"]["bases"]["value"] = [["c:K"]]
        self.assertFalse(basis_sound("K", self.current, sources, self.oracle))
        self.current["K"]["bases"]["value"] = [["c:unobserved"]]
        self.assertIsNone(basis_sound("K", self.current, sources, self.oracle))
        self.current["K"]["bases"]["value"].append(["e:revoked"])
        self.assertFalse(basis_sound("K", self.current, sources, self.oracle))

    def test_wrong_predecessor_and_change_reason_fail(self):
        self.current["H"]["previous_sha256"]["value"] = "0" * 64
        self.assertFalse(self.assess()["components"]["traceability"])
        self.current = observed(self.chain[1]["claims"])
        self.current["H"]["reasons"]["value"] = ["EA"]
        self.assertFalse(self.assess()["trace_checks"]["H"])

    def test_missing_before_does_not_impute_hash_from_episode(self):
        r = self.assess(before={})
        self.assertTrue(r["components"]["root_revision"])
        self.assertIsNone(r["components"]["traceability"])

    def test_wrong_missing_and_stale_prediction(self):
        claims = observed(self.chain[3]["claims"]); final = explicit_record(self.chain[4])
        self.assertTrue(assess_prediction(self.episode, final, claims, self.oracle)["correct"])
        final["answer"]["value"] += 1
        self.assertFalse(assess_prediction(self.episode, final, claims, self.oracle)["correct"])
        self.assertIsNone(assess_prediction(self.episode, {}, claims, self.oracle)["correct"])
        final = explicit_record(self.chain[4]); final["basis"]["value"] = ["e:EB"]
        self.assertFalse(assess_prediction(self.episode, final, claims, self.oracle)["correct"])

    def test_opportunity_denominator_uses_predecessor_not_successor(self):
        # Controlled seed is a fixture here, never relabelled natural model belief.
        before = observed(self.episode["claims"])
        r = public_opportunities(before, active_evidence(self.episode, "A"), active_evidence(self.episode, "B"), self.oracle)
        self.assertEqual(r["observed_opportunities"], 1)
        self.assertTrue(r["items"][0]["supported_now_refuted"])
        self.assertIn("D4", r["items"][0]["descendants"])
        self.assertFalse(r["enumeration_verified"])

    def test_honest_uncertainty_is_not_erroneous_supported_belief(self):
        before = observed(self.episode["claims"]); before["H"]["status"]["value"] = "undetermined"
        r = public_opportunities(before, active_evidence(self.episode, "A"), active_evidence(self.episode, "B"), self.oracle)
        self.assertEqual(r["observed_opportunities"], 1)
        self.assertFalse(r["items"][0]["supported_no_longer_justified"])

    def test_source_withdrawal_is_not_preexisting_false_belief(self):
        before = observed(self.episode["claims"])
        # A true supported root loses evidence; unlike the injected wrong root,
        # this is a justified earlier position, not an earlier model error.
        before["H"]["proposition"]["value"] = {"query": {"kind": "model", "index": 455}, "value": 1}
        r = public_opportunities(before, active_evidence(self.episode, "B"), active_evidence(self.episode, "C"), self.oracle)
        item = next(x for x in r["items"] if x["root"] == "H")
        self.assertTrue(item["opportunity"])
        self.assertTrue(item["supported_no_longer_justified"])
        self.assertFalse(item["supported_now_refuted"])
        self.assertFalse(item["preexisting_status_error"])

    def test_unknown_proposition_or_dependency_retained(self):
        before = observed(self.episode["claims"]); before["H"]["proposition"] = {"state": "conflicting", "value": None}
        r = public_opportunities(before, active_evidence(self.episode, "A"), active_evidence(self.episode, "B"), self.oracle)
        self.assertIn("H", r["unresolved_root_candidates"])
        self.assertEqual(r["observed_opportunities"], 0)

    def test_no_input_mutation_and_unknown_cannot_mask_failure(self):
        old = deepcopy(self.current); self.assess(); self.assertEqual(old, self.current)
        self.assertFalse(tri_all([False, None]))
        self.assertIsNone(tri_all([True, None])); self.assertIsNone(tri_all([]))
        with self.assertRaises(ValueError): tri_all([1])
        with self.assertRaises(ValueError): controlled_chain_bounds([], {"correct": True}, True)


if __name__ == "__main__":
    unittest.main()
