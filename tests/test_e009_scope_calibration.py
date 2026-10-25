"""Calibration integrity and denominator tests; not model or natural-language validity."""
from copy import deepcopy
import unittest

from research import e009_scope_calibration as scope


def view():
    return {"memory": {"format": "F", "payload": "R7: historical status supported. Кириллица сохранена."},
            "stage": "D", "origin": {"actor": "fixture"}, "sha256": None, "trust": "unverified"}


def answer(case, observation=None, evidence=None):
    return {"schema": scope.SCHEMA, "target_id": case["public"]["target_id"],
            "observation": deepcopy(observation if observation is not None else case["gold"]["expected"]),
            "evidence": evidence if evidence is not None else [{"quote": q} for q in case["gold"]["required_witnesses"]]}


class ScopeCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.source = view()
        self.cases = scope.build_scope_cases("input-1", self.source, "R7")
        self.modes = {c["gold"]["mode"]: c for c in self.cases}

    def test_full_snapshot_retained_and_input_detached(self):
        original = deepcopy(self.source)
        self.assertEqual(len(self.cases), 7)
        self.assertEqual(len({c["id"] for c in self.cases}), 7)
        for case in self.cases:
            self.assertTrue(scope.verify_preserved_snapshot(case, self.source))
            self.assertEqual(set(case["public"]), {"schema", "target_id", "context"})
            self.assertNotIn("expected", case["public"])
        self.cases[0]["gold"]["expected"] = {"state": "known"}
        self.assertEqual(self.source, original)

    def test_deterministic_cases_and_distinct_input_identity(self):
        self.assertEqual(self.cases, scope.build_scope_cases("input-1", self.source, "R7"))
        other = scope.build_scope_cases("input-2", self.source, "R7")
        self.assertFalse(set(c["id"] for c in self.cases) & set(c["id"] for c in other))

    def test_paired_gold_has_opposite_current_status_and_nonadopted_quotes(self):
        for mode, value in [("current_supported", "supported"), ("current_refuted", "refuted"),
                            ("quoted_refuted", "supported"), ("quoted_supported", "refuted")]:
            case = self.modes[mode]
            self.assertEqual(case["gold"]["expected"], {"state": "known", "value": value, "alternatives": []})
            if mode.startswith("quoted"):
                self.assertIn("status supported", case["gold"]["required_witnesses"][0])
                self.assertIn("status refuted", case["gold"]["required_witnesses"][0])
        self.assertEqual(self.modes["unresolved_conflict"]["gold"]["expected"]["state"], "conflicting")
        self.assertEqual(self.modes["withdrawn"]["gold"]["expected"]["state"], "absent")

    def test_constructed_gold_answers_sanity_check_not_scientific_validation(self):
        answers = {c["id"]: answer(c) for c in self.cases if c["gold"]["controlled"]}
        result = scope.evaluate_scope_answers(self.cases, answers)["summary"]
        self.assertEqual(result["controlled_assigned"], 6)
        self.assertEqual(result["controlled_exact"], 6)
        self.assertEqual(result["original_unscored_assigned"], 1)
        self.assertTrue(result["controlled_complete_gate"])
        self.assertFalse(result["natural_validity_established"])
        self.assertFalse(result["public_bri_recomputed"])

    def test_all_abstaining_cannot_pass_or_change_denominator(self):
        unknown = {"state": "unknown", "value": None, "alternatives": []}
        answers = {c["id"]: answer(c, unknown, []) for c in self.cases}
        result = scope.evaluate_scope_answers(self.cases, answers)["summary"]
        self.assertEqual(result["controlled_abstained"], 6)
        self.assertEqual(result["controlled_assigned"], 6)
        self.assertEqual(result["controlled_exact_rate"], 0)
        self.assertFalse(result["controlled_complete_gate"])

    def test_missing_and_invalid_preserved_in_assigned_denominator(self):
        case = self.modes["current_supported"]
        invalid = answer(case);invalid["evidence"] = [{"quote": "fabricated"}]
        result = scope.evaluate_scope_answers(self.cases, {case["id"]: invalid})["summary"]
        self.assertEqual(result["controlled_invalid"], 1)
        self.assertEqual(result["controlled_missing"], 5)
        self.assertEqual(result["controlled_assigned"], 6)
        self.assertEqual(result["controlled_exact"], 0)

    def test_original_never_gets_synthetic_gold_even_for_asserted_answer(self):
        case = self.modes["original"]
        candidate = answer(case, {"state": "known", "value": "supported", "alternatives": []},
                           [{"quote": case["public"]["context"]}])
        result = scope.compare_scope_answer(case, candidate)
        self.assertFalse(result["scored"])
        self.assertIsNone(result["exact"])

    def test_existing_quote_does_not_validate_wrong_status(self):
        case = self.modes["quoted_refuted"]
        candidate = answer(case);candidate["observation"]["value"] = "refuted"
        checked = scope.validate_scope_answer(case["public"], candidate)
        self.assertTrue(checked["structurally_valid"])
        self.assertFalse(checked["semantic_verification"])
        result = scope.compare_scope_answer(case, candidate)
        self.assertTrue(result["witness_covered"])
        self.assertFalse(result["correct"])
        self.assertFalse(result["exact"])

    def test_correct_status_with_irrelevant_existing_quote_fails_witness_check(self):
        case = self.modes["current_supported"]
        span = case["preserved_snapshot"]
        quote = case["public"]["context"][span["start"]:span["end"]]
        result = scope.compare_scope_answer(case, answer(case, evidence=[{"quote": quote}]))
        self.assertTrue(result["correct"])
        self.assertFalse(result["witness_covered"])
        self.assertFalse(result["exact"])

    def test_conflicting_alternative_order_is_not_semantics(self):
        case = self.modes["unresolved_conflict"]
        candidate = answer(case);candidate["observation"]["alternatives"].reverse()
        self.assertTrue(scope.compare_scope_answer(case, candidate)["exact"])
        candidate["observation"] = {"state": "known", "value": "supported", "alternatives": []}
        self.assertFalse(scope.compare_scope_answer(case, candidate)["exact"])

    def test_absence_is_not_unknown_or_known_null(self):
        case = self.modes["withdrawn"]
        candidate = answer(case);candidate["observation"]["state"] = "unknown"
        self.assertFalse(scope.compare_scope_answer(case, candidate)["exact"])
        candidate["observation"]["state"] = "known"
        with self.assertRaises(ValueError):
            scope.validate_scope_answer(case["public"], candidate)

    def test_fabricated_ambiguous_empty_and_extra_evidence_rejected(self):
        case = self.modes["current_supported"]
        for evidence in [[{"quote": "missing text"}], [{"quote": ""}], [], [{"quote": case["public"]["context"], "private": 1}]]:
            with self.assertRaises(ValueError):
                scope.validate_scope_answer(case["public"], answer(case, evidence=evidence))
        request = deepcopy(case["public"])
        request["context"] += "\n" + case["gold"]["required_witnesses"][0]
        with self.assertRaises(ValueError):
            scope.validate_scope_answer(request, answer(case))

    def test_private_fields_wrong_identity_and_duplicate_assignments_rejected(self):
        case = self.modes["current_supported"]
        request = deepcopy(case["public"]);request["private_truth"] = True
        with self.assertRaises(ValueError):
            scope.validate_scope_answer(request, answer(case))
        candidate = answer(case);candidate["target_id"] = "R8"
        with self.assertRaises(ValueError):
            scope.validate_scope_answer(case["public"], candidate)
        with self.assertRaises(ValueError):
            scope.evaluate_scope_answers([case, case], {})
        with self.assertRaises(ValueError):
            scope.evaluate_scope_answers(self.cases, {"not-assigned": candidate})

    def test_invalid_target_and_private_source_rejected(self):
        for target in [None, "", 'R7" or R8']:
            with self.assertRaises(ValueError):
                scope.build_scope_cases("input", self.source, target)
        self.source["private_sidecar"] = {"truth": 1}
        with self.assertRaises(ValueError):
            scope.build_scope_cases("input", self.source, "R7")

    def test_source_and_request_tampering_detected(self):
        case = self.modes["current_supported"]
        different = deepcopy(self.source);different["memory"]["payload"] += " altered"
        self.assertFalse(scope.verify_preserved_snapshot(case, different))
        case["public"]["context"] += " altered"
        self.assertFalse(scope.verify_preserved_snapshot(case, self.source))


if __name__ == "__main__":
    unittest.main()
